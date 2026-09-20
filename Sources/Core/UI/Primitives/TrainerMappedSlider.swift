import SwiftUI

struct TrainerMappedSlider: View {
    @Binding var value: Double
    let mapping: TrainerSliderMapping
    var enabled = true

    @Environment(\.colorScheme) private var colorScheme
    @State private var displayPosition: Double?
    @State private var dragOffset: CGFloat?
    @State private var isDragging = false
    @State private var lastLocalValue: Double?

    private let thumbDiameter: CGFloat = 20

    var body: some View {
        GeometryReader { proxy in
            let position = displayPosition ?? mapping.position(for: value)
            let trackWidth = max(proxy.size.width - thumbDiameter, 1)
            let thumbRadius = thumbDiameter / 2
            let thumbX = thumbRadius + trackWidth * CGFloat(position)

            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.secondary.opacity(0.24))
                    .frame(width: trackWidth, height: 3)
                    .position(x: proxy.size.width / 2, y: proxy.size.height / 2)

                Capsule()
                    .fill(Color.accentColor)
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
                    .fill(colorScheme == .light ? Color.white : Color(white: 0.8))
                    .overlay(
                        Circle().stroke(
                            Color.black.opacity(colorScheme == .light ? 0.14 : 0.34),
                            lineWidth: 0.5
                        )
                    )
                    .shadow(color: Color.black.opacity(0.28), radius: 1.5, x: 0, y: 1)
                    .frame(width: thumbDiameter, height: thumbDiameter)
                    .position(x: thumbX, y: proxy.size.height / 2)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { gesture in
                        guard enabled else { return }
                        let current = displayPosition ?? mapping.position(for: value)
                        let currentX = thumbRadius + trackWidth * CGFloat(current)
                        if dragOffset == nil {
                            dragOffset = gesture.startLocation.x - currentX
                            isDragging = true
                        }
                        let adjustedX = gesture.location.x - (dragOffset ?? 0)
                        let rawPosition = min(max(Double((adjustedX - thumbRadius) / trackWidth), 0), 1)
                        let visualPosition = mapping.magnetizedPosition(rawPosition)
                        displayPosition = visualPosition
                        commit(mapping.value(at: visualPosition))
                    }
                    .onEnded { gesture in
                        guard enabled else { return }
                        let adjustedX = gesture.location.x - (dragOffset ?? 0)
                        let rawPosition = min(max(Double((adjustedX - thumbRadius) / trackWidth), 0), 1)
                        let settled = mapping.settledPosition(rawPosition)
                        let finalValue = mapping.value(at: settled)
                        let finalPosition = settled == rawPosition ? mapping.position(for: finalValue) : settled
                        commit(finalValue)
                        withAnimation(.interactiveSpring(response: 0.18, dampingFraction: 0.78, blendDuration: 0.04)) {
                            displayPosition = finalPosition
                        }
                        dragOffset = nil
                        isDragging = false
                    }
            )
        }
        .frame(height: 24)
        .opacity(enabled ? 1 : 0.55)
        .onAppear {
            displayPosition = mapping.position(for: value)
        }
        .onChange(of: value) { _, newValue in
            if let local = lastLocalValue, abs(local - newValue) < 0.000001 {
                lastLocalValue = nil
                return
            }
            guard !isDragging else { return }
            withAnimation(.interactiveSpring(response: 0.18, dampingFraction: 0.82, blendDuration: 0.04)) {
                displayPosition = mapping.position(for: newValue)
            }
        }
        .accessibilityRepresentation {
            Slider(
                value: Binding(
                    get: { mapping.position(for: value) },
                    set: { commit(mapping.value(at: $0)) }
                ),
                in: 0...1
            )
        }
        .accessibilityValue(Text(String(format: "%.1f", value)))
    }

    private func commit(_ newValue: Double) {
        guard abs(value - newValue) >= 0.000001 else { return }
        lastLocalValue = newValue
        value = newValue
    }
}
