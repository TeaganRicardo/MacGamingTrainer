import AppKit
import SwiftUI

/// Product-level presentation states for every visual popup selector.
/// Runtime/data reasons may change interaction, but they collapse into exactly
/// these two visual classes so AppKit does not become a presentation owner.
enum TrainerPickerPresentationState: Equatable {
    case interactive
    case unavailable

    fileprivate var allowsInteraction: Bool { self == .interactive }
}

private struct TrainerPickerPresentationModifier: ViewModifier {
    @Environment(\.trainerTheme) private var theme
    @Environment(\.isEnabled) private var environmentEnabled
    let role: TrainerPickerWidthRole
    let state: TrainerPickerPresentationState

    private var effectiveState: TrainerPickerPresentationState {
        state.allowsInteraction && environmentEnabled ? .interactive : .unavailable
    }

    /// Both classes stay inside the app's dark hierarchy. The interactive
    /// surface tracks the native dark popup family; the unavailable surface is
    /// the same control dimmed, never the light system appearance.
    private var fill: Color {
        switch effectiveState {
        case .interactive: Color(red: 0.208, green: 0.212, blue: 0.231)
        case .unavailable: Color(red: 0.137, green: 0.141, blue: 0.157)
        }
    }

    private var boundary: Color {
        switch effectiveState {
        case .interactive: Color(red: 0.310, green: 0.318, blue: 0.345)
        case .unavailable: Color(red: 0.192, green: 0.196, blue: 0.212)
        }
    }

    func body(content: Content) -> some View {
        content
            .pickerStyle(.menu)
            // A borderless NSPopUpButton drops its title origin from x=12 to
            // x=8 (measured against the regular bordered cell). Restore the
            // native 4 pt inset inside the fixed width so text stays aligned
            // with every other row value; the control height is never forced.
            .padding(.leading, 4)
            .trainerPickerWidth(role)
            .controlSize(.regular)
            .background(fill, in: RoundedRectangle(cornerRadius: theme.compactCornerRadius, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: theme.compactCornerRadius, style: .continuous)
                    .strokeBorder(boundary, lineWidth: 1)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .overlay(alignment: .trailing) {
                TrainerPickerIndicator(state: effectiveState, fill: fill)
            }
            .background {
                TrainerNativePickerPresentationBridge(state: effectiveState)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .clipShape(RoundedRectangle(cornerRadius: theme.compactCornerRadius, style: .continuous))
            .disabled(effectiveState != .interactive)
    }
}

private struct TrainerPickerIndicator: View {
    @Environment(\.trainerTheme) private var theme
    let state: TrainerPickerPresentationState
    let fill: Color

    var body: some View {
        ZStack {
            // Mask the native popup chevron so the product indicator is the
            // only trailing mark; the strip matches the control surface.
            Rectangle().fill(fill)
            VStack(spacing: -2) {
                Image(systemName: "chevron.up")
                Image(systemName: "chevron.down")
            }
            .font(.system(size: 7, weight: .bold))
            .foregroundStyle(
                state == .interactive
                    ? Color(red: 1.0, green: 1.0, blue: 1.0)
                    : Color(red: 0.44, green: 0.45, blue: 0.48)
            )
            .frame(width: 18, height: 18)
            .background(
                state == .interactive
                    ? theme.accent
                    : Color(red: 0.200, green: 0.205, blue: 0.220),
                in: RoundedRectangle(cornerRadius: 4, style: .continuous)
            )
        }
        .frame(width: 24)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// SwiftUI still hosts Picker as NSPopUpButton on macOS. The application owns
/// the dark appearance once (see AppDelegate); this bridge only removes the
/// native bezel/focus chrome that would otherwise resolve the system accent,
/// and keeps the product text tint. The native button continues to own menu
/// semantics, title metrics and AX.
private struct TrainerNativePickerPresentationBridge: NSViewRepresentable {
    let state: TrainerPickerPresentationState

    final class BridgeView: NSView {
        var state: TrainerPickerPresentationState = .interactive
        private weak var cachedButton: NSPopUpButton?
        private var lookupScheduled = false
        private var remainingLookupPasses = 0

        override func viewDidMoveToSuperview() {
            super.viewDidMoveToSuperview()
            cachedButton = nil
            scheduleLookup(passes: 3)
        }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            cachedButton = nil
            scheduleLookup(passes: 3)
        }

        func update(state: TrainerPickerPresentationState) {
            self.state = state
            if let button = cachedButton, button.window != nil {
                applyPresentation(to: button)
            } else {
                cachedButton = nil
                scheduleLookup(passes: 2)
            }
        }

        private func scheduleLookup(passes: Int) {
            remainingLookupPasses = max(remainingLookupPasses, passes)
            guard !lookupScheduled, window != nil else { return }
            lookupScheduled = true
            DispatchQueue.main.async { [weak self] in
                self?.runLookupPass()
            }
        }

        private func runLookupPass() {
            lookupScheduled = false
            guard window != nil else { return }

            if let button = cachedButton, button.window != nil {
                applyPresentation(to: button)
                remainingLookupPasses = 0
                return
            }

            if let button = nearestPopUpButton() {
                cachedButton = button
                applyPresentation(to: button)
                remainingLookupPasses = 0
                return
            }

            remainingLookupPasses -= 1
            if remainingLookupPasses > 0 {
                scheduleLookup(passes: remainingLookupPasses)
            }
        }

        private func applyPresentation(to button: NSPopUpButton) {
            let tint = state == .interactive
                ? NSColor(calibratedWhite: 0.92, alpha: 1.0)
                : NSColor(calibratedWhite: 0.46, alpha: 1.0)

            // Appearance is owned once by NSApp (see AppDelegate). This owner
            // only removes the native bezel/focus chrome that would otherwise
            // resolve the system accent, and keeps the product text tint.
            if button.isBordered { button.isBordered = false }
            if button.focusRingType != .none { button.focusRingType = .none }
            if button.bezelColor != nil { button.bezelColor = nil }
            if button.contentTintColor?.isEqual(tint) != true {
                button.contentTintColor = tint
            }
        }

        /// Locate the popup only when the bridge is mounted, reconstructed or
        /// its semantic state changes. The result is cached so ordinary AppKit
        /// layout never performs a recursive subtree scan.
        private func nearestPopUpButton() -> NSPopUpButton? {
            var scope = superview
            while let currentScope = scope {
                let bridgeFrame = convert(bounds, to: currentScope)
                var best: (button: NSPopUpButton, overlap: CGFloat, distance: CGFloat)?
                for button in Self.popUpButtons(in: currentScope) {
                    let frame = button.convert(button.bounds, to: currentScope)
                    let intersection = bridgeFrame.intersection(frame)
                    let overlap = intersection.isNull ? 0 : intersection.width * intersection.height
                    guard overlap > 0 else { continue }
                    let dx = frame.midX - bridgeFrame.midX
                    let dy = frame.midY - bridgeFrame.midY
                    let distance = dx * dx + dy * dy
                    if let candidate = best {
                        if overlap > candidate.overlap
                            || (overlap == candidate.overlap && distance < candidate.distance) {
                            best = (button, overlap, distance)
                        }
                    } else {
                        best = (button, overlap, distance)
                    }
                }
                if let best { return best.button }
                scope = currentScope.superview
            }
            return nil
        }

        private static func popUpButtons(in view: NSView) -> [NSPopUpButton] {
            var result: [NSPopUpButton] = []
            for subview in view.subviews {
                if let button = subview as? NSPopUpButton { result.append(button) }
                result.append(contentsOf: popUpButtons(in: subview))
            }
            return result
        }
    }

    func makeNSView(context: Context) -> BridgeView {
        let view = BridgeView(frame: .zero)
        view.update(state: state)
        return view
    }

    func updateNSView(_ view: BridgeView, context: Context) {
        view.update(state: state)
    }
}

extension View {
    /// Shared Picker owner. Width is geometry only; presentation is collapsed
    /// to interactive/unavailable and normalized after native reconstruction.
    func trainerPicker(
        _ role: TrainerPickerWidthRole = .rowValue,
        state: TrainerPickerPresentationState = .interactive
    ) -> some View {
        modifier(TrainerPickerPresentationModifier(role: role, state: state))
    }
}
