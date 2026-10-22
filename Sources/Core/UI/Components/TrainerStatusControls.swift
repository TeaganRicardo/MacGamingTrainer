import SwiftUI

struct TrainerConnectionStatusCard: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let connected: Bool
    let backendAvailable: Bool
    let actionsEnabled: Bool
    let onRefresh: () -> Void
    let onPrimary: () -> Void
    let onRestart: () -> Void
    let targetRunning: Bool
    let onLaunch: (() -> Void)?

    init(
        connected: Bool,
        backendAvailable: Bool,
        actionsEnabled: Bool,
        onRefresh: @escaping () -> Void,
        onPrimary: @escaping () -> Void,
        onRestart: @escaping () -> Void,
        targetRunning: Bool = true,
        onLaunch: (() -> Void)? = nil
    ) {
        self.connected = connected
        self.backendAvailable = backendAvailable
        self.actionsEnabled = actionsEnabled
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

    func performPrimaryAction() {
        if !backendAvailable { onRestart() }
        else if !connected && !targetRunning, let onLaunch { onLaunch() }
        else { onPrimary() }
    }

    var body: some View {
        HStack(spacing: 8) {
            TrainerPrimaryActionButton(
                title: localization.localized(primaryActionTitleKey),
                enabled: actionsEnabled,
                width: theme.connectionActionWidth,
                action: performPrimaryAction
            )
            Button(action: onRefresh) { Image(systemName: "arrow.clockwise") }
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
