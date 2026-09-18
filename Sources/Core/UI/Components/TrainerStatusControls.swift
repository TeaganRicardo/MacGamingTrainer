import SwiftUI

struct TrainerConnectionStatusCard: View {
    @Environment(\.trainerTheme) private var theme
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
                Text(busy ? operationText + "…" : statusText).font(.subheadline.weight(.medium))
                Text(detailText).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            Button(action: onRefresh) { Image(systemName: "arrow.clockwise") }
                .help("按需读取状态，不进行持续调试轮询")
                .disabled(!backendAvailable || !actionsEnabled)
            if backendAvailable {
                Button(connected ? "断开连接" : "连接游戏", action: onPrimary)
                    .buttonStyle(.borderedProminent)
                    .disabled(!actionsEnabled)
            } else {
                Button("重启后端", action: onRestart)
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
