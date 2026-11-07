import SwiftUI

/// Product-level presentation states for every visual popup selector.
/// Runtime/data reasons may change interaction, but they collapse into exactly
/// these two states. Each state is the native macOS popup presentation for that
/// state (enabled or disabled); Core never repaints the control.
enum TrainerPickerPresentationState: Equatable {
    case interactive
    case unavailable

    fileprivate var allowsInteraction: Bool { self == .interactive }
}

/// Shared owner for geometry, availability and accent of an in-window Picker.
///
/// The native popup owns its bezel, title, indicator, menu, keyboard behavior
/// and accessibility. On macOS 26 and later SwiftUI draws it itself, with no
/// `NSPopUpButton` in the view tree, so it cannot be restyled by repainting
/// around it or by patching AppKit views. The
/// dark appearance is declared once on `NSApp` and the product purple once as
/// the application accent color (see `AppDelegate` and the asset catalog), so
/// every window, sheet, panel, menu and reconstructed popup resolves the same
/// dark chrome and purple indicator without a per-control bridge. The SwiftUI
/// tint below supplies the same purple where the user's explicit system accent
/// choice would otherwise replace the application accent.
private struct TrainerPickerPresentationModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    let role: TrainerPickerWidthRole
    let state: TrainerPickerPresentationState

    func body(content: Content) -> some View {
        content
            .pickerStyle(.menu)
            .trainerPickerWidth(role)
            .tint(theme.accent)
            .disabled(!state.allowsInteraction)
    }
}

extension View {
    /// Shared Picker owner. Width is geometry only; availability selects the
    /// native enabled or disabled popup, never a repainted variant.
    func trainerPicker(
        _ role: TrainerPickerWidthRole = .rowValue,
        state: TrainerPickerPresentationState = .interactive
    ) -> some View {
        modifier(TrainerPickerPresentationModifier(role: role, state: state))
    }
}
