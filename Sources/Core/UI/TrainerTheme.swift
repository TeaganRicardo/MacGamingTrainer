import SwiftUI

struct TrainerTheme {
    let background: Color
    let accent: Color
    let panel: Color
    let panelRaised: Color
    let sidebarBackground: Color
    let selectedFill: Color
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
    let controlPadding: CGFloat
    let compactControlSpacing: CGFloat
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
    let inlineRowVerticalPadding: CGFloat
    let shortcutCaptureWidth: CGFloat
    let connectionActionWidth: CGFloat
    let compactActionWidth: CGFloat
    let pickerCompactWidth: CGFloat
    let pickerStandardWidth: CGFloat
    let pickerWideWidth: CGFloat
    let pickerActionLabelWidth: CGFloat
    let sheetPadding: CGFloat
    let sheetSpacing: CGFloat
    let emptyStatePadding: CGFloat

    static let standard = TrainerTheme(
        // Opaque graphite surfaces keep the accepted dark identity predictable
        // under every window backdrop. Accent is reserved for actions/state.
        background: Color(red: 0.075, green: 0.078, blue: 0.090),
        accent: Color(red: 0.64, green: 0.51, blue: 1.0),
        panel: Color(red: 0.120, green: 0.124, blue: 0.140),
        panelRaised: Color(red: 0.158, green: 0.163, blue: 0.183),
        sidebarBackground: Color(red: 0.092, green: 0.096, blue: 0.110),
        selectedFill: Color(red: 0.190, green: 0.184, blue: 0.238),
        deferred: .orange,
        warning: .orange,
        success: .green,
        mutedFill: Color.white.opacity(0.13),
        subtleFill: Color.white.opacity(0.04),
        separator: Color.white.opacity(0.09),
        info: .cyan,
        inactive: .gray,
        panelCornerRadius: 12,
        cardCornerRadius: 10,
        controlCornerRadius: 8,
        controlPadding: 10,
        compactControlSpacing: 8,
        compactCornerRadius: 6,
        pageMaxWidth: 1000,
        contentMinWidth: 760,
        contentMinHeight: 740,
        pagePadding: 28,
        pageSpacing: 22,
        sectionSpacing: 12,
        panelPadding: 20,
        rowHorizontalPadding: 22,
        rowMinimumHeight: 64,
        inlineRowVerticalPadding: 10,
        shortcutCaptureWidth: 180,
        connectionActionWidth: 160,
        compactActionWidth: 88,
        pickerCompactWidth: 152,
        pickerStandardWidth: 216,
        pickerWideWidth: 288,
        pickerActionLabelWidth: 200,
        sheetPadding: 28,
        sheetSpacing: 16,
        emptyStatePadding: 24
    )

    func boundaryColor(for contrast: ColorSchemeContrast) -> Color {
        contrast == .increased ? Color.primary.opacity(0.42) : separator
    }

    func selectionMarkerWidth(for contrast: ColorSchemeContrast) -> CGFloat {
        contrast == .increased ? 3 : 2
    }
}

enum TrainerPickerWidthRole {
    case compactValue
    case rowValue
    case rowAction
    case form
    case expanding
}

private struct TrainerPickerWidthModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    let role: TrainerPickerWidthRole

    @ViewBuilder
    func body(content: Content) -> some View {
        Group {
            switch role {
            case .compactValue:
                content.frame(width: theme.pickerCompactWidth)
            case .rowValue:
                content.frame(width: theme.pickerStandardWidth)
            case .rowAction, .form:
                content.frame(
                    minWidth: theme.pickerStandardWidth,
                    idealWidth: theme.pickerWideWidth,
                    maxWidth: theme.pickerWideWidth
                )
            case .expanding:
                content.frame(minWidth: theme.pickerStandardWidth, maxWidth: .infinity)
            }
        }
        .transaction { transaction in
            // The selected value is direct input. An ancestor's disclosure or
            // navigation animation must not interpolate the native popup.
            transaction.animation = nil
            transaction.disablesAnimations = true
        }
    }
}

// Inline feature rows share a compact action column. Standalone/sheet
// actions retain their native content width unless the caller specifies one.
private struct TrainerActionWidthKey: EnvironmentKey {
    static let defaultValue: CGFloat? = nil
}

extension EnvironmentValues {
    var trainerActionWidth: CGFloat? {
        get { self[TrainerActionWidthKey.self] }
        set { self[TrainerActionWidthKey.self] = newValue }
    }
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

    func trainerPickerWidth(_ role: TrainerPickerWidthRole = .rowValue) -> some View {
        modifier(TrainerPickerWidthModifier(role: role))
    }

    func trainerPanel(padding: CGFloat? = nil, cornerRadius: CGFloat? = nil) -> some View {
        modifier(TrainerPanelModifier(padding: padding, cornerRadius: cornerRadius))
    }

    func trainerSurface(_ role: TrainerSurfaceRole, cornerRadius: CGFloat? = nil) -> some View {
        modifier(TrainerSurfaceModifier(role: role, cornerRadius: cornerRadius))
    }
}

enum TrainerSurfaceRole {
    case canvas
    case sidebar
    case panel
    case raised
    case subtle
    case selected
    case clear
}

private struct TrainerSurfaceModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.colorSchemeContrast) private var contrast
    let role: TrainerSurfaceRole
    let cornerRadius: CGFloat?

    private var fill: Color {
        switch role {
        case .canvas: return theme.background
        case .sidebar: return theme.sidebarBackground
        case .panel: return theme.panel
        case .raised: return theme.panelRaised
        case .subtle: return theme.subtleFill
        case .selected: return theme.selectedFill
        case .clear: return .clear
        }
    }

    private var boundary: Color {
        switch role {
        case .panel, .raised, .selected:
            return theme.boundaryColor(for: contrast)
        default:
            return .clear
        }
    }

    @ViewBuilder
    func body(content: Content) -> some View {
        if let cornerRadius {
            content
                .background(fill, in: RoundedRectangle(cornerRadius: cornerRadius, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                        .strokeBorder(boundary, lineWidth: 1)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
        } else if case .canvas = role {
            content.background(fill.ignoresSafeArea())
        } else {
            content.background(fill)
        }
    }
}

private struct TrainerPanelModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    let padding: CGFloat?
    let cornerRadius: CGFloat?

    func body(content: Content) -> some View {
        content
            .padding(padding ?? theme.panelPadding)
            .trainerSurface(.panel, cornerRadius: cornerRadius ?? theme.panelCornerRadius)
    }
}
