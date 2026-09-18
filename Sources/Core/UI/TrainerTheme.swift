import SwiftUI

struct TrainerTheme {
    let background: Color
    let accent: Color
    let panel: Color
    let panelRaised: Color
    let sidebarBackground: Color
    let deferred: Color
    let warning: Color
    let success: Color
    let mutedFill: Color
    let subtleFill: Color
    let separator: Color
    let info: Color
    let inactive: Color
    let panelCornerRadius: CGFloat
    let cardCornerRadius: CGFloat
    let controlCornerRadius: CGFloat
    let compactCornerRadius: CGFloat
    let pageMaxWidth: CGFloat
    let contentMinWidth: CGFloat
    let contentMinHeight: CGFloat
    let pagePadding: CGFloat
    let pageSpacing: CGFloat
    let sectionSpacing: CGFloat
    let panelPadding: CGFloat
    let rowHorizontalPadding: CGFloat
    let rowMinimumHeight: CGFloat
    let sheetPadding: CGFloat
    let sheetSpacing: CGFloat
    let emptyStatePadding: CGFloat

    static let standard = TrainerTheme(
        background: Color(red: 0.065, green: 0.072, blue: 0.102),
        accent: Color(red: 0.64, green: 0.51, blue: 1.0),
        panel: Color(red: 0.105, green: 0.115, blue: 0.155),
        panelRaised: Color(red: 0.125, green: 0.135, blue: 0.18),
        sidebarBackground: Color.white.opacity(0.018),
        deferred: .orange,
        warning: .orange,
        success: .green,
        mutedFill: Color.white.opacity(0.13),
        subtleFill: Color.white.opacity(0.04),
        separator: Color.white.opacity(0.04),
        info: .cyan,
        inactive: .gray,
        panelCornerRadius: 16,
        cardCornerRadius: 14,
        controlCornerRadius: 10,
        compactCornerRadius: 7,
        pageMaxWidth: 1000,
        contentMinWidth: 760,
        contentMinHeight: 740,
        pagePadding: 28,
        pageSpacing: 22,
        sectionSpacing: 12,
        panelPadding: 20,
        rowHorizontalPadding: 22,
        rowMinimumHeight: 64,
        sheetPadding: 28,
        sheetSpacing: 16,
        emptyStatePadding: 24
    )
}

private struct TrainerThemeKey: EnvironmentKey {
    static let defaultValue = TrainerTheme.standard
}

extension EnvironmentValues {
    var trainerTheme: TrainerTheme {
        get { self[TrainerThemeKey.self] }
        set { self[TrainerThemeKey.self] = newValue }
    }
}

extension View {
    func trainerTheme(_ theme: TrainerTheme) -> some View {
        environment(\.trainerTheme, theme)
    }

    func trainerPanel(padding: CGFloat? = nil, cornerRadius: CGFloat? = nil) -> some View {
        modifier(TrainerPanelModifier(padding: padding, cornerRadius: cornerRadius))
    }
}

private struct TrainerPanelModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    let padding: CGFloat?
    let cornerRadius: CGFloat?

    func body(content: Content) -> some View {
        content
            .padding(padding ?? theme.panelPadding)
            .background(theme.panel, in: RoundedRectangle(cornerRadius: cornerRadius ?? theme.panelCornerRadius))
    }
}
