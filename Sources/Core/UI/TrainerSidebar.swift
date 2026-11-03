import SwiftUI

// A measured numeric target lets SwiftUI interpolate the actual accordion
// geometry. Switching Frame(height:) between nil and zero snaps immediately
// even when .animation is present (confirmed in a native AppKit harness).
private struct TrainerSidebarActionHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0

    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

private struct TrainerSidebarDisclosureClip: AnimatableModifier {
    var visibleHeight: CGFloat

    var animatableData: CGFloat {
        get { visibleHeight }
        set { visibleHeight = newValue }
    }

    func body(content: Content) -> some View {
        content
            .frame(height: max(0, visibleHeight), alignment: .top)
            .clipped()
    }
}

struct TrainerSidebarCard<Actions: View>: View {
    @State private var measuredActionHeight: CGFloat = 0
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
        VStack(alignment: .leading, spacing: 0) {
            Button(action: onSelect) {
                HStack(spacing: 12) {
                    Image(systemName: presentation.sidebarIconSystemName)
                        .font(.title3.weight(.medium))
                        .foregroundStyle(selected ? theme.accent : .secondary)
                        .frame(width: 24)
                        .accessibilityHidden(true)
                    Text(descriptor.displayName)
                        .font(.headline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    statusIndicator
                }
                .frame(minHeight: 30)
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .focusable(true, interactions: .activate)
            .focusEffectDisabled()
            .accessibilityLabel(descriptor.displayName)
            .accessibilityValue(localization.string(statusToken))
            .accessibilityIdentifier("host.game.\(descriptor.id)")
            .accessibilityAddTraits(selected ? .isSelected : [])
            // Keep the action tree alive. Measure its intrinsic size outside
            // the clipping modifier so closed cards still know their target
            // height. Only the numeric reveal and opacity animate; the header
            // icon and the workbench retain independent presentation owners.
            VStack(alignment: .leading, spacing: 14) { actions }
                .buttonStyle(.plain)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 14)
                .fixedSize(horizontal: false, vertical: true)
                .background {
                    GeometryReader { geometry in
                        Color.clear.preference(key: TrainerSidebarActionHeightKey.self,
                                               value: geometry.size.height)
                    }
                }
                .modifier(TrainerSidebarDisclosureClip(
                    visibleHeight: selected ? measuredActionHeight : 0
                ))
                .opacity(selected ? 1 : 0)
                .animation(TrainerMotion.animation(.disclosure, reduceMotion: reduceMotion), value: selected)
                .onPreferenceChange(TrainerSidebarActionHeightKey.self) { height in
                    guard height.isFinite, height > 0,
                          abs(height - measuredActionHeight) > 0.5 else { return }
                    // Initial mount and content measurement are data changes,
                    // not a second animation competing with user selection.
                    var transaction = Transaction(animation: nil)
                    transaction.disablesAnimations = true
                    withTransaction(transaction) { measuredActionHeight = height }
                }
                .allowsHitTesting(selected)
                .disabled(!selected)
                .accessibilityHidden(!selected)
        }
        .padding(14)
        .trainerSurface(selected ? .raised : .panel, cornerRadius: theme.cardCornerRadius)
        // A collapsed module has one card-sized mouse target, including its
        // insets. The real header Button retains keyboard/AX activation. Only
        // inactive cards receive this overlay: expanded cards keep their
        // interior action controls independently clickable.
        .overlay {
            if !selected {
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture(perform: onSelect)
                    .accessibilityHidden(true)
            }
        }
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
