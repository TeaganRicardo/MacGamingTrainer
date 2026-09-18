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
                .background((tint ?? theme.accent).opacity(emphasized ? 0.15 : 0.06), in: RoundedRectangle(cornerRadius: theme.controlCornerRadius))
            Text(title).font(.subheadline.weight(.semibold))
        }
    }
}
