import AppKit
import Combine
import Darwin
import Foundation

/// Atomically published process presence and definitive launch generation.
/// Consumers must never see an intermediate running=true / old-generation
/// snapshot from a single NSWorkspace didLaunch notification.
struct TrainerTargetObservation: Equatable {
    let isRunning: Bool
    let launchGeneration: UInt
    let processIdentifier: pid_t?

    init(isRunning: Bool, launchGeneration: UInt, processIdentifier: pid_t? = nil) {
        self.isRunning = isRunning
        self.launchGeneration = launchGeneration
        self.processIdentifier = processIdentifier
    }
}

/// Event-driven target-app presence monitor shared by all game modules.
///
/// It uses NSWorkspace launch/activation/termination notifications and a narrow
/// kernel-path probe when taking a snapshot. It never polls on a timer, so keeping
/// the trainer open does not add background process-scan traffic. Activation is a
/// useful second attach opportunity after launch because the target game is already
/// foreground and cannot be paused merely to focus the trainer. The initial snapshot
/// covers the case where the target game was already running before the trainer launched.
final class TrainerTargetProcessMonitor: ObservableObject {
    @Published private(set) var targetObservation = TrainerTargetObservation(
        isRunning: false,
        launchGeneration: 0
    )
    @Published private(set) var activationGeneration: UInt = 0

    var isRunning: Bool { targetObservation.isRunning }
    var launchGeneration: UInt { targetObservation.launchGeneration }

    private let processName: String
    private let bundleIdentifier: String
    private let executablePathSuffix: String
    private let workspace: NSWorkspace
    private var observers: [NSObjectProtocol] = []

    init(processName: String, bundleIdentifier: String, executablePathSuffix: String = "", workspace: NSWorkspace = .shared) {
        self.processName = processName
        self.bundleIdentifier = bundleIdentifier
        self.executablePathSuffix = executablePathSuffix
        self.workspace = workspace
        let currentPID = currentTargetProcessIdentifier()
        targetObservation = TrainerTargetObservation(
            isRunning: currentPID != nil,
            launchGeneration: 0,
            processIdentifier: currentPID
        )

        let center = workspace.notificationCenter
        observers.append(center.addObserver(
            forName: NSWorkspace.didLaunchApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self,
                  let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            self.targetObservation = TrainerTargetObservation(
                isRunning: true,
                launchGeneration: self.launchGeneration &+ 1,
                processIdentifier: app.processIdentifier
            )
        })
        observers.append(center.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self,
                  let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            // Activation proves the game is running for Save safety, but it
            // does not grant a launch-time automatic debugger attachment.
            self.publishPresence(app)
            self.activationGeneration &+= 1
        })
        observers.append(center.addObserver(
            forName: NSWorkspace.didTerminateApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self,
                  let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            self.publishCurrentPresence()
        })
    }

    deinit {
        let center = workspace.notificationCenter
        observers.forEach(center.removeObserver)
    }

    func refresh() {
        publishCurrentPresence()
    }

    private func publishPresence(_ application: NSRunningApplication?) {
        publishPresence(processIdentifier: application?.processIdentifier)
    }

    private func publishCurrentPresence() {
        publishPresence(processIdentifier: currentTargetProcessIdentifier())
    }

    private func publishPresence(processIdentifier: pid_t?) {
        let next = TrainerTargetObservation(
            isRunning: processIdentifier != nil,
            launchGeneration: launchGeneration,
            processIdentifier: processIdentifier
        )
        guard next != targetObservation else { return }
        targetObservation = next
    }

    private func currentTargetProcessIdentifier() -> pid_t? {
        if let application = currentRunningApplication() {
            return application.processIdentifier
        }
        return currentMatchingProcessIdentifiers().first
    }

    /// Steam can start Hades I without a LaunchServices application record, and
    /// ps(1)'s comm field can contain only argv[0]. Match candidate PIDs by their
    /// kernel-reported executable path instead of trusting the short process name.
    private func currentMatchingProcessIdentifiers() -> [pid_t] {
        guard !processName.isEmpty,
              !executablePathSuffix.isEmpty,
              URL(fileURLWithPath: executablePathSuffix).lastPathComponent == processName else {
            return []
        }

        let probe = Process()
        probe.executableURL = URL(fileURLWithPath: "/usr/bin/pgrep")
        probe.arguments = ["-x", processName]
        let output = Pipe()
        probe.standardOutput = output
        probe.standardError = FileHandle.nullDevice

        do {
            try probe.run()
        } catch {
            return []
        }

        let data = output.fileHandleForReading.readDataToEndOfFile()
        probe.waitUntilExit()
        guard probe.terminationStatus == 0,
              let text = String(data: data, encoding: .utf8) else {
            return []
        }

        return text.split(whereSeparator: { $0.isNewline }).compactMap { line in
            guard let value = Int32(String(line)) else { return nil }
            let pid = pid_t(value)
            guard let path = processExecutablePath(for: pid),
                  matchesExecutablePath(path) else {
                return nil
            }
            return pid
        }
    }

    private func processExecutablePath(for pid: pid_t) -> String? {
        var buffer = [CChar](repeating: 0, count: 1024)
        let length = proc_pidpath(pid, &buffer, UInt32(buffer.count))
        guard length > 0 else { return nil }
        return String(cString: buffer)
    }

    private func matchesExecutablePath(_ path: String) -> Bool {
        guard !executablePathSuffix.isEmpty else { return false }
        return URL(fileURLWithPath: path).standardizedFileURL.path
            .hasSuffix("/" + executablePathSuffix)
    }

    private func currentRunningApplication() -> NSRunningApplication? {
        if !bundleIdentifier.isEmpty,
           let application = NSRunningApplication
            .runningApplications(withBundleIdentifier: bundleIdentifier)
            .first(where: matches) {
            return application
        }
        return workspace.runningApplications.first(where: matches)
    }

    private func matches(_ app: NSRunningApplication) -> Bool {
        if !executablePathSuffix.isEmpty {
            guard let path = app.executableURL?.standardizedFileURL.path,
                  matchesExecutablePath(path) else { return false }
        }
        if !bundleIdentifier.isEmpty, app.bundleIdentifier == bundleIdentifier {
            return true
        }
        guard !processName.isEmpty else { return false }
        if app.executableURL?.lastPathComponent == processName { return true }
        return app.localizedName == processName
    }
}
