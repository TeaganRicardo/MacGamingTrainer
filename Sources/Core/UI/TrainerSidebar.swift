import SwiftUI

struct TrainerSidebarCard<Actions: View>: View {
    @Environment(\.trainerTheme) private var theme
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

    private var statusColor: Color {
        if busy { return theme.info }
        if connected { return theme.success }
        if targetRunning { return theme.warning }
        return theme.inactive
    }

    private var statusIndicator: some View {
        Circle()
            .fill(statusColor)
            .frame(width: 8, height: 8)
            .frame(width: 12, height: 12)
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: busy)
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: connected)
            .animation(TrainerMotion.animation(.transientFeedback, reduceMotion: reduceMotion), value: targetRunning)
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
                        .animation(TrainerMotion.animation(.selection, reduceMotion: reduceMotion), value: selected)
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
            .focusEffectDisabled()
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
        // Keep module-selection motion scoped to this small sidebar subtree.
        // Retained game-page trees are deliberately outside this transaction.
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
