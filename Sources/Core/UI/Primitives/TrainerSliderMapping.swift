import Foundation

struct TrainerSliderMapping {
    let anchors: [Double]
    let step: Double
    let detents: [Double]
    let magnetDistance: Double
    let settleDistance: Double

    var range: ClosedRange<Double> { anchors[0]...anchors[anchors.count - 1] }
    var marks: [Double] { anchors }

    static func anchoredLogarithmic(
        values: [Double],
        step: Double,
        detents: [Double] = [],
        magnetDistance: Double = 0.10,
        settleDistance: Double = 0.04
    ) -> TrainerSliderMapping {
        precondition(values.count >= 2)
        precondition(values.allSatisfy { $0.isFinite && $0 > 0 })
        precondition(zip(values, values.dropFirst()).allSatisfy(<))
        precondition(step > 0 && magnetDistance >= 0)
        precondition(settleDistance >= 0 && settleDistance <= magnetDistance)
        let range = values[0]...values[values.count - 1]
        return TrainerSliderMapping(
            anchors: values,
            step: step,
            detents: detents.filter(range.contains).sorted(),
            magnetDistance: magnetDistance,
            settleDistance: settleDistance
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

    func magnetizedPosition(_ position: Double) -> Double {
        let position = min(max(position, 0), 1)
        guard magnetDistance > 0, let detent = nearestDetent(to: position) else { return position }
        let delta = position - detent
        let distance = abs(delta)
        guard distance < magnetDistance else { return position }
        let t = distance / magnetDistance
        let release = t * t * (2 - t)
        return detent + delta * release
    }

    func settledPosition(_ position: Double) -> Double {
        let position = min(max(position, 0), 1)
        guard let detent = nearestDetent(to: position) else { return position }
        return abs(position - detent) <= settleDistance ? detent : magnetizedPosition(position)
    }

    func value(at position: Double) -> Double {
        let raw = rawValue(at: min(max(position, 0), 1))
        let quantized = (raw / step).rounded() * step
        return min(max(quantized, range.lowerBound), range.upperBound)
    }

    private func nearestDetent(to position: Double) -> Double? {
        detents.map(position(for:)).min(by: { abs($0 - position) < abs($1 - position) })
    }
}

/// Shared drawing/hit geometry in view-local points. A collapsed track still
/// draws a bounded thumb, but has no usable pointer range.
struct TrainerSliderGeometry {
    let width: Double
    let thumbDiameter: Double

    init(width: Double, thumbDiameter: Double) {
        self.width = max(width, 0)
        self.thumbDiameter = min(max(thumbDiameter, 0), self.width)
    }

    var thumbRadius: Double { thumbDiameter / 2 }
    var trackWidth: Double { width - thumbDiameter }

    func x(at position: Double) -> Double {
        thumbRadius + trackWidth * min(max(position, 0), 1)
    }

    func position(at pointerX: Double, grabOffset: Double = 0) -> Double {
        guard trackWidth > 0 else { return 0.5 }
        return min(max((pointerX - grabOffset - thumbRadius) / trackWidth, 0), 1)
    }
}

/// Own one pointer gesture independently of observations and quantized values.
/// Cancellation stays terminal until that gesture ends or SwiftUI resets it.
struct TrainerSliderDrag {
    private enum Phase {
        case idle
        case tracking(grabOffset: Double)
        case cancelled
    }

    private var phase = Phase.idle

    var isActive: Bool {
        if case .tracking = phase { return true }
        return false
    }

    mutating func update(startX: Double, pointerX: Double, currentPosition: Double,
                         geometry: TrainerSliderGeometry) -> Double? {
        guard geometry.trackWidth > 0 else { cancel(); return nil }
        if case .idle = phase {
            let distance = startX - geometry.x(at: currentPosition)
            let offset = abs(distance) <= geometry.thumbRadius ? distance : 0
            phase = .tracking(grabOffset: offset)
        }
        guard case let .tracking(offset) = phase else { return nil }
        return geometry.position(at: pointerX, grabOffset: offset)
    }

    mutating func finish(pointerX: Double, geometry: TrainerSliderGeometry) -> Double? {
        defer { phase = .idle }
        guard case let .tracking(offset) = phase, geometry.trackWidth > 0 else { return nil }
        return geometry.position(at: pointerX, grabOffset: offset)
    }

    mutating func cancel() {
        if isActive { phase = .cancelled }
    }

    mutating func reset() { phase = .idle }
}
