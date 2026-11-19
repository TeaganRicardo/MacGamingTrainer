import SwiftUI

struct TrainerConnectionStatusCard: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let connected: Bool
    let backendAvailable: Bool
    /// Module request gate for connect/disconnect/launch/refresh.
    let actionsEnabled: Bool
    /// Host-owned recovery eligibility used while the backend is unavailable.
    let restartEnabled: Bool
    let onRefresh: () -> Void
    let onPrimary: () -> Void
    let onRestart: () -> Void
    let targetRunning: Bool
    let onLaunch: (() -> Void)?

    init(
        connected: Bool,
        backendAvailable: Bool,
        actionsEnabled: Bool,
        restartEnabled: Bool,
        onRefresh: @escaping () -> Void,
        onPrimary: @escaping () -> Void,
        onRestart: @escaping () -> Void,
        targetRunning: Bool = true,
        onLaunch: (() -> Void)? = nil
    ) {
        self.connected = connected
        self.backendAvailable = backendAvailable
        self.actionsEnabled = actionsEnabled
        self.restartEnabled = restartEnabled
        self.onRefresh = onRefresh
        self.onPrimary = onPrimary
        self.onRestart = onRestart
        self.targetRunning = targetRunning
        self.onLaunch = onLaunch
    }

    var primaryActionTitleKey: String {
        if !backendAvailable { return "host.restartBackend" }
        if connected { return "host.disconnectGame" }
        if !targetRunning && onLaunch != nil { return "host.launchGame" }
        return "host.connectGame"
    }

    var primaryActionEnabled: Bool { backendAvailable ? actionsEnabled : restartEnabled }

    func performPrimaryAction() {
        if !backendAvailable { onRestart() }
        else if !connected && !targetRunning, let onLaunch { onLaunch() }
        else { onPrimary() }
    }

    var body: some View {
        HStack(spacing: 8) {
            TrainerPrimaryActionButton(
                title: localization.localized(primaryActionTitleKey),
                enabled: primaryActionEnabled,
                widthRole: .connection,
                action: performPrimaryAction
            )
            .contentTransition(.opacity)
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: primaryActionTitleKey)
            Button(action: onRefresh) { Image(systemName: TrainerSemanticIcon.Tool.refreshStatus) }
                .help(localization.localized("host.refreshStatusHelp"))
                .accessibilityLabel(localization.localized("host.refreshStatus"))
                .disabled(!backendAvailable || !actionsEnabled)
        }
    }
}

struct TrainerPillBadge: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .foregroundStyle(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.10), in: Capsule())
    }
}

/// Shared small spinner used by host sheets and save-editor toolbars during busy work.
package struct TrainerLoadingIndicator: View {
    @EnvironmentObject private var localization: TrainerLocalizationStore

    package init() {}

    package var body: some View {
        ProgressView()
            .controlSize(.small)
            .frame(width: 16, height: 16)
            .accessibilityLabel(localization.localized("host.operation.inProgress"))
    }
}
