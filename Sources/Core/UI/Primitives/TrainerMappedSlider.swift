import SwiftUI

struct TrainerMappedSlider: View {
    @Binding var value: Double
    let mapping: TrainerSliderMapping
    let accessibilityLabel: String
    let accessibilityHint: String
    var enabled = true
    /// Nil ends the preview, including an unchanged edit or cancellation.
    var onPreviewValue: ((Double?) -> Void)? = nil

    @Environment(\.trainerTheme) private var theme
    @Environment(\.isEnabled) private var environmentEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var displayPosition: Double?
    @State private var drag = TrainerSliderDrag()
    @State private var lastPreviewValue: Double?
    @GestureState private var gestureActive = false
    @FocusState private var focused: Bool

    private let thumbDiameter: CGFloat = 20
    private var interactive: Bool { enabled && environmentEnabled }

    var body: some View {
        GeometryReader { proxy in
            let position = displayPosition ?? mapping.position(for: value)
            let geometry = TrainerSliderGeometry(width: Double(proxy.size.width), thumbDiameter: Double(thumbDiameter))
            let trackWidth = CGFloat(geometry.trackWidth)
            let thumbRadius = CGFloat(geometry.thumbRadius)
            let thumbX = CGFloat(geometry.x(at: position))

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.secondary.opacity(0.24))
                    .frame(width: trackWidth, height: 3)
                    .position(x: proxy.size.width / 2, y: proxy.size.height / 2)

                Capsule()
                    .fill(theme.accent)
                    .frame(width: max(thumbX - thumbRadius, 0), height: 3)
                    .position(
                        x: thumbRadius + max(thumbX - thumbRadius, 0) / 2,
                        y: proxy.size.height / 2
                    )

                ForEach(Array(mapping.marks.enumerated()), id: \.offset) { _, mark in
                    Rectangle()
                        .fill(Color.secondary.opacity(0.48))
                        .frame(width: 1, height: 7)
                        .position(
                            x: thumbRadius + trackWidth * CGFloat(mapping.position(for: mark)),
                            y: proxy.size.height / 2
                        )
                }

                Circle()
                    .fill(Color.white)
                    .overlay(Circle().stroke(Color.black.opacity(0.16), lineWidth: 0.5))
                    .shadow(color: Color.black.opacity(0.28), radius: 1.5, x: 0, y: 1)
                    .frame(width: CGFloat(geometry.thumbDiameter), height: CGFloat(geometry.thumbDiameter))
                    .position(x: thumbX, y: proxy.size.height / 2)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .updating($gestureActive) { _, active, transaction in
                        active = true
                        transaction.animation = nil
                        transaction.disablesAnimations = true
                    }
                    .onChanged { gesture in
                        guard interactive, let position = drag.update(
                            startX: Double(gesture.startLocation.x),
                            pointerX: Double(gesture.location.x),
                            currentPosition: displayPosition ?? mapping.position(for: value),
                            geometry: geometry
                        ) else { return }
                        focused = true
                        preview(position)
                    }
                    .onEnded { gesture in
                        guard interactive else { cancelPointer(); return }
                        let position = drag.finish(pointerX: Double(gesture.location.x), geometry: geometry)
                        clearPreview()
                        if let position {
                            commit(mapping.value(at: mapping.settledPosition(position)))
                        } else {
                            show(mapping.position(for: value), animated: false)
                        }
                    }
            )
        }
        .frame(height: 24)
        .opacity(interactive ? 1 : 0.55)
        .focusable(interactive)
        .focused($focused)
        .onMoveCommand { direction in
            switch direction {
            case .left, .down: adjust(by: -mapping.step)
            case .right, .up: adjust(by: mapping.step)
            @unknown default: break
            }
        }
        .onExitCommand { cancelPointer() }
        .onAppear {
            show(mapping.position(for: value), animated: false)
        }
        .onChange(of: value) { _, newValue in
            guard !drag.isActive else { return }
            let position = mapping.position(for: newValue)
            // A commit echo already targets this position; leave its settling
            // transaction intact. Unrelated observations update immediately.
            guard displayPosition.map({ abs($0 - position) >= 0.000001 }) ?? true else { return }
            show(position, animated: false)
        }
        .onChange(of: interactive) { _, interactive in
            if !interactive {
                cancelPointer()
                focused = false
            }
        }
        .onChange(of: focused) { _, focused in
            if !focused { cancelPointer() }
        }
        .onChange(of: gestureActive) { _, active in
            // onEnded only covers a successful gesture. GestureState also
            // resets on system cancellation, so unfinished previews end here.
            if !active { cancelPointer(); drag.reset() }
        }
        .onDisappear { cancelPointer(); drag.reset() }
        .accessibilityRepresentation {
            Slider(
                value: Binding(
                    get: { value },
                    set: { commit($0) }
                ),
                in: mapping.range,
                step: mapping.step
            )
            .disabled(!interactive)
            .accessibilityLabel(Text(accessibilityLabel))
            .accessibilityHint(Text(accessibilityHint))
        }
        .accessibilityLabel(Text(accessibilityLabel))
        .accessibilityHint(Text(accessibilityHint))
        .accessibilityValue(Text(String(format: "%.1f", value)))
    }

    private func preview(_ position: Double) {
        var transaction = Transaction(animation: nil)
        transaction.disablesAnimations = true
        withTransaction(transaction) {
            // Magnetization stabilizes the numeric preview without pulling
            // the visible thumb away from the pointer.
            displayPosition = position
            let previewValue = mapping.value(at: mapping.magnetizedPosition(position))
            if lastPreviewValue.map({ abs($0 - previewValue) >= 0.000001 }) ?? true {
                lastPreviewValue = previewValue
                onPreviewValue?(previewValue)
            }
        }
    }

    private func clearPreview() {
        guard lastPreviewValue != nil else { return }
        lastPreviewValue = nil
        onPreviewValue?(nil)
    }

    private func cancelPointer() {
        guard drag.isActive || lastPreviewValue != nil else { return }
        drag.cancel()
        clearPreview()
        show(mapping.position(for: value), animated: false)
    }

    private func show(_ position: Double, animated: Bool) {
        let animation: Animation? = animated && !reduceMotion
            ? .interactiveSpring(response: 0.18, dampingFraction: 0.82, blendDuration: 0.04) : nil
        var transaction = Transaction(animation: animation)
        transaction.disablesAnimations = animation == nil
        withTransaction(transaction) { displayPosition = position }
    }

    private func adjust(by step: Double) {
        guard interactive else { return }
        cancelPointer()
        let next = min(max(value + step, mapping.range.lowerBound), mapping.range.upperBound)
        commit(next)
    }

    private func commit(_ proposedValue: Double) {
        guard interactive else { return }
        cancelPointer()
        let newValue = mapping.value(at: mapping.position(for: proposedValue))
        show(mapping.position(for: newValue), animated: true)
        guard abs(value - newValue) >= 0.000001 else { return }
        value = newValue
    }
}
