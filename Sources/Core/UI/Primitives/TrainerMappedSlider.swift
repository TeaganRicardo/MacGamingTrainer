import SwiftUI

struct TrainerMappedSlider: View {
    @Binding var value: Double
    let mapping: TrainerSliderMapping
    var enabled = true

    private var positionBinding: Binding<Double> {
        Binding(
            get: { mapping.position(for: value) },
            set: { newPosition in value = mapping.value(at: newPosition) }
        )
    }

    var body: some View {
        ZStack {
            GeometryReader { proxy in
                ForEach(Array(mapping.detents.enumerated()), id: \.offset) { _, detent in
                    Rectangle()
                        .fill(detent == mapping.pivot ? Color.primary.opacity(0.55) : Color.secondary.opacity(0.35))
                        .frame(width: 1, height: detent == mapping.pivot ? 8 : 5)
                        .position(
                            x: proxy.size.width * mapping.position(for: detent),
                            y: proxy.size.height / 2
                        )
                }
            }
            .allowsHitTesting(false)
            .padding(.horizontal, 8)

            Slider(value: positionBinding, in: 0...1)
                .disabled(!enabled)
        }
        .frame(minWidth: 180)
        .accessibilityValue(Text(String(format: "%.1f", value)))
    }
}
