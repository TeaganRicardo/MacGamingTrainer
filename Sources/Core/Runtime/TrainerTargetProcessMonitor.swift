import AppKit
import Combine
import Foundation

/// Atomically published process presence and definitive launch generation.
/// Consumers must never see an intermediate running=true / old-generation
/// snapshot from a single NSWorkspace didLaunch notification.
struct TrainerTargetObservation: Equatable {
    let isRunning: Bool
    let launchGeneration: UInt
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
    @Published private(set) var targetObservation = TrainerTargetObservation(isRunning: false, launchGeneration: 0)
    @Published private(set) var activationGeneration: UInt = 0

    var isRunning: Bool { targetObservation.isRunning }
    var launchGeneration: UInt { targetObservation.launchGeneration }

    private let processName: String
    private let bundleIdentifier: String
    private let workspace: NSWorkspace
    private var observers: [NSObjectProtocol] = []

    init(processName: String, bundleIdentifier: String, workspace: NSWorkspace = .shared) {
        self.processName = processName
        self.bundleIdentifier = bundleIdentifier
        self.workspace = workspace
        targetObservation = TrainerTargetObservation(isRunning: currentRunningState(), launchGeneration: 0)

        let center = workspace.notificationCenter
        observers.append(center.addObserver(
            forName: NSWorkspace.didLaunchApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self, let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            self.targetObservation = TrainerTargetObservation(
                isRunning: true,
                launchGeneration: self.launchGeneration &+ 1
            )
        })
        observers.append(center.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self, let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            // Activation proves the game is running for Save safety, but it
            // does not grant a launch-time automatic debugger attachment.
            self.publishPresence(true)
            self.activationGeneration &+= 1
        })
        observers.append(center.addObserver(
            forName: NSWorkspace.didTerminateApplicationNotification,
            object: workspace,
            queue: .main
        ) { [weak self] note in
            guard let self, let app = note.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication,
                  self.matches(app) else { return }
            self.publishPresence(self.currentRunningState())
        })
    }

    deinit {
        let center = workspace.notificationCenter
        observers.forEach(center.removeObserver)
    }

    func refresh() {
        publishPresence(currentRunningState())
    }

    private func publishPresence(_ running: Bool) {
        guard running != isRunning else { return }
        targetObservation = TrainerTargetObservation(
            isRunning: running,
            launchGeneration: launchGeneration
        )
    }

    private func currentRunningState() -> Bool {
        if !bundleIdentifier.isEmpty,
           !NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier).isEmpty {
            return true
        }
        return workspace.runningApplications.contains(where: matches)
    }

    private func matches(_ app: NSRunningApplication) -> Bool {
        if !bundleIdentifier.isEmpty, app.bundleIdentifier == bundleIdentifier {
            return true
        }
        guard !processName.isEmpty else { return false }
        if app.executableURL?.lastPathComponent == processName { return true }
        return app.localizedName == processName
    }
}
