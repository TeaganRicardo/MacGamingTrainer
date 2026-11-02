import SwiftUI

/// Shared control-row chrome for every game module. Feature/stat rows provide
/// only their inner controls; horizontal inset, minimum height, panel fill and
/// disabled/pending opacity stay host-wide.
struct TrainerRow<Content: View>: View {
    @Environment(\.trainerTheme) private var theme
    let minimumHeight: CGFloat?
    let opacity: Double
    let content: Content

    init(
        minimumHeight: CGFloat? = nil,
        opacity: Double = 1,
        @ViewBuilder content: () -> Content
    ) {
        self.minimumHeight = minimumHeight
        self.opacity = opacity
        self.content = content()
    }

    var body: some View {
        content
            .environment(\.trainerActionWidth, theme.compactActionWidth)
            .frame(maxWidth: .infinity, minHeight: minimumHeight ?? theme.rowMinimumHeight, alignment: .leading)
            .padding(.horizontal, theme.rowHorizontalPadding)
            .background(theme.panel)
            .opacity(opacity)
    }
}

struct TrainerIconLabel: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let tint: Color?
    let emphasized: Bool

    init(title: String, icon: String, tint: Color? = nil, emphasized: Bool = false) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.emphasized = emphasized
    }

    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(tint ?? theme.accent)
                .frame(width: 40, height: 40)
                .background((tint ?? theme.accent).opacity(emphasized ? 0.12 : 0.045), in: RoundedRectangle(cornerRadius: theme.controlCornerRadius, style: .continuous))
                .accessibilityHidden(true)
            Text(title)
                .font(.subheadline.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

enum TrainerLabeledControlLayout: Equatable {
    case natural
    case pickerAction
}

struct TrainerLabeledControlRow<Controls: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let tint: Color
    let emphasized: Bool
    let opacity: Double
    let helpText: String
    let layout: TrainerLabeledControlLayout
    let controls: Controls

    init(title: String, icon: String, tint: Color, emphasized: Bool,
         opacity: Double = 1, helpText: String = "",
         layout: TrainerLabeledControlLayout = .natural,
         @ViewBuilder controls: () -> Controls) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.emphasized = emphasized
        self.opacity = opacity
        self.helpText = helpText
        self.layout = layout
        self.controls = controls()
    }

    @ViewBuilder
    private var titleLabel: some View {
        if layout == .pickerAction {
            TrainerIconLabel(title: title, icon: icon, tint: tint, emphasized: emphasized)
                .frame(width: theme.pickerActionLabelWidth, alignment: .leading)
                .help(helpText)
        } else {
            // Preserve the original natural row hierarchy exactly. A nil-width
            // frame still changes HStack layout negotiation on macOS.
            TrainerIconLabel(title: title, icon: icon, tint: tint, emphasized: emphasized)
                .help(helpText)
        }
    }

    var body: some View {
        TrainerRow(opacity: opacity) {
            HStack(spacing: 16) {
                titleLabel
                if layout == .natural { Spacer(minLength: 8) }
                controls
                if layout == .pickerAction { Spacer(minLength: 0) }
            }
        }
    }
}
