import SwiftUI

struct TrainerMappedSlider: View {
    @Binding var value: Double
    let mapping: TrainerSliderMapping
    var enabled = true

    @State private var livePosition = 0.0
    @State private var isEditing = false

    private var positionBinding: Binding<Double> {
        Binding(
            get: { isEditing ? livePosition : mapping.position(for: value) },
            set: { newPosition in
                let position = mapping.snappedPosition(newPosition)
                livePosition = position
                value = mapping.value(at: position)
            }
        )
    }

    var body: some View {
        ZStack {
            GeometryReader { proxy in
                ForEach(Array(mapping.marks.enumerated()), id: \.offset) { _, mark in
                    Rectangle()
                        .fill(Color.secondary.opacity(0.35))
                        .frame(width: 1, height: 6)
                        .position(
                            x: proxy.size.width * mapping.position(for: mark),
                            y: proxy.size.height / 2
                        )
                }
            }
            .allowsHitTesting(false)
            .padding(.horizontal, 8)

            Slider(value: positionBinding, in: 0...1, onEditingChanged: { editing in
                if editing { livePosition = mapping.position(for: value) }
                withAnimation(.easeOut(duration: 0.12)) {
                    isEditing = editing
                }
            })
            .controlSize(.regular)
            .disabled(!enabled)
        }
        .accessibilityValue(Text(String(format: "%.1f", value)))
    }
}
