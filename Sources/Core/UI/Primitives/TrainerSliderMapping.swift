import Foundation

struct TrainerSliderMapping {
    let anchors: [Double]
    let step: Double
    let detents: [Double]
    let snapDistance: Double

    var range: ClosedRange<Double> { anchors[0]...anchors[anchors.count - 1] }
    var marks: [Double] { anchors }

    static func anchoredLogarithmic(
        values: [Double],
        step: Double,
        detents: [Double] = [],
        snapDistance: Double = 0.0125
    ) -> TrainerSliderMapping {
        precondition(values.count >= 2)
        precondition(values.allSatisfy { $0.isFinite && $0 > 0 })
        precondition(zip(values, values.dropFirst()).allSatisfy(<))
        precondition(step > 0 && snapDistance >= 0)
        let range = values[0]...values[values.count - 1]
        return TrainerSliderMapping(
            anchors: values,
            step: step,
            detents: detents.filter(range.contains).sorted(),
            snapDistance: snapDistance
        )
    }

    func position(for value: Double) -> Double {
        let value = min(max(value, range.lowerBound), range.upperBound)
        if value >= range.upperBound { return 1 }
        let segmentCount = anchors.count - 1
        let index = anchors.indices.dropLast().first { value <= anchors[$0 + 1] } ?? segmentCount - 1
        let lower = anchors[index]
        let upper = anchors[index + 1]
        let local = log(value / lower) / log(upper / lower)
        return (Double(index) + local) / Double(segmentCount)
    }

    func rawValue(at position: Double) -> Double {
        let position = min(max(position, 0), 1)
        if position >= 1 { return range.upperBound }
        let segmentCount = anchors.count - 1
        let scaled = position * Double(segmentCount)
        let index = min(Int(scaled), segmentCount - 1)
        let local = scaled - Double(index)
        let lower = anchors[index]
        let upper = anchors[index + 1]
        return lower * pow(upper / lower, local)
    }

    func snappedPosition(_ position: Double) -> Double {
        let position = min(max(position, 0), 1)
        guard let detent = detents.min(by: {
            abs(self.position(for: $0) - position) < abs(self.position(for: $1) - position)
        }) else { return position }
        let detentPosition = self.position(for: detent)
        return abs(detentPosition - position) <= snapDistance ? detentPosition : position
    }

    func value(at position: Double) -> Double {
        let raw = rawValue(at: snappedPosition(position))
        let quantized = (raw / step).rounded() * step
        return min(max(quantized, range.lowerBound), range.upperBound)
    }
}
