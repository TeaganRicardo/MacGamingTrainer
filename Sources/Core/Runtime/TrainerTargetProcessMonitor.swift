import AppKit
import Combine
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
/// It deliberately uses NSWorkspace launch/activation/termination notifications
/// instead of a repeating process poll, so keeping the trainer open does not add
/// background debugger or process-scan traffic. Activation is a useful second
/// attach opportunity after launch because the target game is already foreground
/// and cannot be paused merely to focus the trainer. The initial snapshot covers
/// the case where the target game was already running before the trainer launched.
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
        let current = currentRunningApplication()
        targetObservation = TrainerTargetObservation(
            isRunning: current != nil,
            launchGeneration: 0,
            processIdentifier: current?.processIdentifier
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
            self.publishPresence(self.currentRunningApplication())
        })
    }

    deinit {
        let center = workspace.notificationCenter
        observers.forEach(center.removeObserver)
    }

    func refresh() {
        publishPresence(currentRunningApplication())
    }

    private func publishPresence(_ application: NSRunningApplication?) {
        let next = TrainerTargetObservation(
            isRunning: application != nil,
            launchGeneration: launchGeneration,
            processIdentifier: application?.processIdentifier
        )
        guard next != targetObservation else { return }
        targetObservation = next
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
                  path.hasSuffix("/" + executablePathSuffix) else { return false }
        }
        if !bundleIdentifier.isEmpty, app.bundleIdentifier == bundleIdentifier {
            return true
        }
        guard !processName.isEmpty else { return false }
        if app.executableURL?.lastPathComponent == processName { return true }
        return app.localizedName == processName
    }
}
