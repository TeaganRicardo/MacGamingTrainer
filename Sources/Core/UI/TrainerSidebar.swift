import SwiftUI

struct TrainerSidebarCard<Actions: View>: View {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @EnvironmentObject private var localization: TrainerLocalizationStore
    let descriptor: GameModuleDescriptor
    let presentation: TrainerGamePresentation
    let connected: Bool
    let busy: Bool
    let targetRunning: Bool
    let operationToken: TrainerTextToken
    let statusToken: TrainerTextToken
    let detailToken: TrainerTextToken
    let selected: Bool
    let onSelect: () -> Void
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
        selected: Bool = true,
        onSelect: @escaping () -> Void = {},
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
        self.selected = selected
        self.onSelect = onSelect
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
                ProgressView().controlSize(.mini)
            } else {
                Image(systemName: connected ? "checkmark.circle.fill" : targetRunning ? "minus.circle" : "circle.dashed")
                    .font(.caption2)
                    .foregroundStyle(connected ? theme.success : targetRunning ? theme.warning : theme.inactive)
                    .contentTransition(.opacity)
            }
        }
        .frame(width: 12, height: 12)
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: busy)
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: connected)
        .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: targetRunning)
        .transaction { TrainerMotion.nativeControlTransaction(&$0, reduceMotion: reduceMotion) }
        .help(statusHelp)
        .accessibilityLabel(busy ? localization.string(operationToken) : localization.string(statusToken))
        .accessibilityValue(localization.string(detailToken))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: selected ? 14 : 0) {
            Button(action: onSelect) {
                HStack(spacing: 12) {
                    Image(systemName: presentation.sidebarIconSystemName)
                        .font(.title3.weight(.medium))
                        .foregroundStyle(selected ? theme.accent : .secondary)
                        .frame(width: 24)
                        .accessibilityHidden(true)
                    Text(descriptor.displayName)
                        .font(.headline.weight(selected ? .semibold : .medium))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    statusIndicator
                }
                .frame(minHeight: 30)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(descriptor.displayName)
            .accessibilityValue(localization.string(statusToken))
            .accessibilityIdentifier("host.game.\(descriptor.id)")
            .accessibilityAddTraits(selected ? .isSelected : [])
            VStack(alignment: .leading, spacing: 14) { actions }
                .buttonStyle(.plain)
                .frame(height: selected ? nil : 0, alignment: .top)
                .clipped()
                .opacity(selected ? 1 : 0)
                .allowsHitTesting(selected)
                .disabled(!selected)
                .accessibilityHidden(!selected)
        }
        .padding(14)
        .trainerSurface(selected ? .raised : .panel, cornerRadius: theme.cardCornerRadius)
        .overlay(alignment: .leading) {
            if selected {
                RoundedRectangle(cornerRadius: 1, style: .continuous)
                    .fill(theme.accent)
                    .frame(width: theme.selectionMarkerWidth(for: contrast), height: 20)
                    .padding(.leading, 1)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
        }
        .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)
    }
}

struct TrainerSidebar<Card: View>: View {
    @Environment(\.trainerTheme) private var theme
    let card: Card

    init(@ViewBuilder card: () -> Card) { self.card = card() }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            card
            Spacer()
        }
        .padding(18)
        .frame(width: 260)
        .trainerSurface(.sidebar)
    }
}
