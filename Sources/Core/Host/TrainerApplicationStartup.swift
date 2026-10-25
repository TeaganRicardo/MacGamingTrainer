import AppKit
import Foundation

/// Admit a single Host before constructing the module model/backend session.
/// Keep the lease until process exit, including asynchronous shutdown cleanup.
@MainActor
enum TrainerApplicationStartup {
    static func requireOwnership(targetProcessName: String, targetBundleIdentifier: String, executablePathSuffix: String = "") -> TrainerTargetOwnership {
        let localization = TrainerLocalizationStore()
        do {
            let support = try FileManager.default.url(
                for: .applicationSupportDirectory, in: .userDomainMask,
                appropriateFor: nil, create: true
            )
            let directory = support.appendingPathComponent("MacGamingTrainer/TargetOwners", isDirectory: true)
            switch try TrainerTargetOwnership.acquire(
                directory: directory, processName: targetProcessName,
                bundleIdentifier: targetBundleIdentifier, executablePathSuffix: executablePathSuffix
            ) {
            case .acquired(let lease):
                return lease
            case .occupied(let pid):
                if let pid, let existing = NSRunningApplication(processIdentifier: pid),
                   existing.bundleIdentifier == Bundle.main.bundleIdentifier,
                   existing.activate(options: [.activateAllWindows]) {
                    exit(EXIT_SUCCESS)
                }
                showAlert(localization: localization, title: "host.startup.alreadyRunning",
                          detail: localization.localized("host.startup.useExisting"))
                exit(EXIT_SUCCESS)
            }
        } catch {
            showAlert(localization: localization, title: "host.startup.ownershipUnavailable",
                      detail: localization.localized("host.startup.ownershipRecovery") + "\n\n" + error.localizedDescription)
            exit(EXIT_FAILURE)
        }
    }

    private static func showAlert(localization: TrainerLocalizationStore, title: String, detail: String) {
        let application = NSApplication.shared
        application.setActivationPolicy(.regular)
        application.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.alertStyle = .warning
        alert.messageText = localization.localized(title)
        alert.informativeText = detail
        alert.addButton(withTitle: localization.localized("host.startup.quit"))
        alert.runModal()
    }
}
