import SwiftUI

struct TrainerSidebar<Actions: View>: View {
    @Environment(\.trainerTheme) private var theme
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let descriptor: GameModuleDescriptor
    let presentation: TrainerGamePresentation
    let connected: Bool
    let busy: Bool
    let targetRunning: Bool
    let operationToken: TrainerTextToken
    let statusToken: TrainerTextToken
    let detailToken: TrainerTextToken
    let actions: Actions

    init(
        descriptor: GameModuleDescriptor,
        presentation: TrainerGamePresentation,
        connected: Bool,
        busy: Bool,
        targetRunning: Bool,
        operationToken: TrainerTextToken,
        statusToken: TrainerTextToken,
        detailToken: TrainerTextToken,
        @ViewBuilder actions: () -> Actions
    ) {
        self.descriptor = descriptor
        self.presentation = presentation
        self.connected = connected
        self.busy = busy
        self.targetRunning = targetRunning
        self.operationToken = operationToken
        self.statusToken = statusToken
        self.detailToken = detailToken
        self.actions = actions()
    }

    private var statusHelp: String {
        let lines = busy
            ? [localization.string(operationToken), localization.string(statusToken), localization.string(detailToken)]
            : [localization.string(statusToken), localization.string(detailToken)]
        return lines.joined(separator: "\n")
    }

    private var statusIndicator: some View {
        Group {
            if busy {
                ProgressView().controlSize(.mini).frame(width: 8, height: 8)
            } else {
                Circle()
                    .fill(connected ? theme.success : targetRunning ? theme.warning : theme.inactive)
                    .frame(width: 6, height: 6)
            }
        }
        .help(statusHelp)
        .accessibilityLabel(busy ? localization.string(operationToken) : localization.string(statusToken))
        .accessibilityValue(localization.string(detailToken))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 12) {
                    Image(systemName: presentation.sidebarIconSystemName)
                        .font(.title2)
                        .foregroundStyle(theme.accent)
                    Text(descriptor.displayName).font(.headline)
                    Spacer()
                    statusIndicator
                }
                actions.buttonStyle(.plain)
            }
            .padding(14)
            .background(theme.panel, in: RoundedRectangle(cornerRadius: theme.cardCornerRadius))

            Spacer()
        }
        .padding(18)
        .frame(width: 260)
        .background(theme.sidebarBackground)
    }
}
