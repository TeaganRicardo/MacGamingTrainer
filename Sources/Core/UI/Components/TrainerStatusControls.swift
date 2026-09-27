import SwiftUI

struct TrainerConnectionStatusCard: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let busy: Bool
    let connected: Bool
    let operationText: String
    let statusText: String
    let detailText: String
    let backendAvailable: Bool
    let actionsEnabled: Bool
    let onRefresh: () -> Void
    let onPrimary: () -> Void
    let onRestart: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            if busy {
                ProgressView().controlSize(.small)
            } else {
                Circle().fill(connected ? theme.success : theme.inactive).frame(width: 8, height: 8)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text(busy ? localization.presentation(operationText) + "…" : localization.presentation(statusText))
                    .font(.subheadline.weight(.medium))
                Text(detailText).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button(action: onRefresh) { Image(systemName: "arrow.clockwise") }
                .help(localization.localized("host.refreshStatusHelp"))
                .disabled(!backendAvailable || !actionsEnabled)
            if backendAvailable {
                Button(connected ? localization.localized("host.disconnectGame") : localization.localized("host.connectGame"), action: onPrimary)
                    .buttonStyle(.borderedProminent)
                    .disabled(!actionsEnabled)
            } else {
                Button(localization.localized("host.restartBackend"), action: onRestart)
                    .buttonStyle(.borderedProminent)
                    .disabled(!actionsEnabled)
            }
        }
        .padding(theme.panelPadding)
        .background(theme.panel, in: RoundedRectangle(cornerRadius: theme.cardCornerRadius))
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
