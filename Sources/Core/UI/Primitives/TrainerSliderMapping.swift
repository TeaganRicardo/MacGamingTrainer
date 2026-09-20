import Foundation

struct TrainerSliderMapping {
    let range: ClosedRange<Double>
    let pivot: Double
    let step: Double
    let detents: [Double]
    let snapDistance: Double

    static func centeredLogarithmic(
        range: ClosedRange<Double>,
        pivot: Double,
        step: Double,
        detents: [Double] = [],
        snapDistance: Double = 0.025
    ) -> TrainerSliderMapping {
        precondition(range.lowerBound > 0 && pivot > range.lowerBound && pivot < range.upperBound)
        precondition(step > 0 && snapDistance >= 0)
        return TrainerSliderMapping(
            range: range,
            pivot: pivot,
            step: step,
            detents: detents.filter(range.contains).sorted(),
            snapDistance: snapDistance
        )
    }

    func position(for value: Double) -> Double {
        let value = min(max(value, range.lowerBound), range.upperBound)
        if value <= pivot {
            return 0.5 * log(value / range.lowerBound) / log(pivot / range.lowerBound)
        }
        return 0.5 + 0.5 * log(value / pivot) / log(range.upperBound / pivot)
    }

    func rawValue(at position: Double) -> Double {
        let position = min(max(position, 0), 1)
        if position <= 0.5 {
            return range.lowerBound * pow(pivot / range.lowerBound, position / 0.5)
        }
        return pivot * pow(range.upperBound / pivot, (position - 0.5) / 0.5)
    }

    func value(at position: Double) -> Double {
        let position = min(max(position, 0), 1)
        if let detent = detents.min(by: {
            abs(self.position(for: $0) - position) < abs(self.position(for: $1) - position)
        }), abs(self.position(for: detent) - position) <= snapDistance {
            return detent
        }
        let raw = rawValue(at: position)
        let quantized = (raw / step).rounded() * step
        return min(max(quantized, range.lowerBound), range.upperBound)
    }
}
