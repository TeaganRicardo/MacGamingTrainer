import AppKit
import SwiftUI

/// Product-level presentation states for every workbench popup selector.
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

    private var fill: Color {
        switch effectiveState {
        case .interactive: Color.white.opacity(0.96)
        case .unavailable: Color.white.opacity(0.56)
        }
    }

    private var boundary: Color {
        switch effectiveState {
        case .interactive: Color.black.opacity(0.10)
        case .unavailable: Color.black.opacity(0.08)
        }
    }

    func body(content: Content) -> some View {
        content
            .pickerStyle(.menu)
            .trainerPickerWidth(role)
            .controlSize(.regular)
            .frame(minHeight: 34)
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
                TrainerNativePickerPresentationProbe(state: effectiveState)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
            }
            .clipShape(RoundedRectangle(cornerRadius: theme.compactCornerRadius, style: .continuous))
            .disabled(!state.allowsInteraction)
    }
}

private struct TrainerPickerIndicator: View {
    @Environment(\.trainerTheme) private var theme
    let state: TrainerPickerPresentationState
    let fill: Color

    var body: some View {
        ZStack {
            Rectangle().fill(fill)
            VStack(spacing: -2) {
                Image(systemName: "chevron.up")
                Image(systemName: "chevron.down")
            }
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(state == .interactive ? Color.white : Color.black.opacity(0.30))
            .frame(width: 24, height: 24)
            .background(
                state == .interactive ? theme.accent : Color.clear,
                in: RoundedRectangle(cornerRadius: 5, style: .continuous)
            )
        }
        .frame(width: 32)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// SwiftUI still hosts Picker as NSPopUpButton on macOS. Strip the native
/// bezel/focus drawing so it cannot leak system white/blue variants through
/// retained or reconstructed controls; SwiftUI above owns the two product
/// presentations. The native button continues to own menu semantics and AX.
private struct TrainerNativePickerPresentationProbe: NSViewRepresentable {
    let state: TrainerPickerPresentationState

    final class Probe: NSView {
        var state: TrainerPickerPresentationState = .interactive
        private var scheduled = false

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            scheduleApply()
        }

        override func layout() {
            super.layout()
            scheduleApply()
        }

        func update(state: TrainerPickerPresentationState) {
            self.state = state
            scheduleApply()
        }

        private func scheduleApply() {
            guard !scheduled else { return }
            scheduled = true
            DispatchQueue.main.async { [weak self] in
                guard let self else { return }
                self.scheduled = false
                self.applyPresentation()
            }
        }

        private func applyPresentation() {
            guard let root = window?.contentView,
                  let button = nearestPopUpButton(in: root) else { return }
            button.isBordered = false
            button.focusRingType = .none
            button.bezelColor = nil
            button.contentTintColor = state == .interactive
                ? NSColor(calibratedWhite: 0.10, alpha: 0.92)
                : NSColor(calibratedWhite: 0.30, alpha: 0.72)
        }

        private func nearestPopUpButton(in root: NSView) -> NSPopUpButton? {
            let probeFrame = convert(bounds, to: root)
            var best: (button: NSPopUpButton, overlap: CGFloat, distance: CGFloat)?
            for button in Self.popUpButtons(in: root) {
                let frame = button.convert(button.bounds, to: root)
                let intersection = probeFrame.intersection(frame)
                let overlap = intersection.isNull ? 0 : intersection.width * intersection.height
                let dx = frame.midX - probeFrame.midX
                let dy = frame.midY - probeFrame.midY
                let distance = dx * dx + dy * dy
                if let current = best {
                    if overlap > current.overlap
                        || (overlap == current.overlap && distance < current.distance) {
                        best = (button, overlap, distance)
                    }
                } else {
                    best = (button, overlap, distance)
                }
            }
            guard let best, best.overlap > 0 else { return nil }
            return best.button
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

    func makeNSView(context: Context) -> Probe {
        let view = Probe(frame: .zero)
        view.update(state: state)
        return view
    }

    func updateNSView(_ view: Probe, context: Context) {
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
