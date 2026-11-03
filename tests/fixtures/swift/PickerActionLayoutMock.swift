// Minimal SwiftUI Layout surface for exercising production geometry on Linux.
// No Apple framework or native game is required for the allocation contract.
@_exported import Foundation

public enum UnitPoint { case leading }

public struct ProposedViewSize {
    public var width: CGFloat?
    public var height: CGFloat?
    public init(width: CGFloat? = nil, height: CGFloat? = nil) {
        self.width = width
        self.height = height
    }
    public static let unspecified = ProposedViewSize()
    public static let zero = ProposedViewSize(width: 0, height: 0)
}

public final class GeometryRecorder {
    public var point: CGPoint = .zero
    public var proposed: ProposedViewSize = .unspecified
    public init() {}
}

public struct LayoutSubview {
    public let natural: CGSize
    public let recorder: GeometryRecorder
    public init(natural: CGSize, recorder: GeometryRecorder = .init()) {
        self.natural = natural
        self.recorder = recorder
    }
    public func sizeThatFits(_ proposal: ProposedViewSize) -> CGSize {
        CGSize(width: proposal.width ?? natural.width, height: natural.height)
    }
    public func place(at position: CGPoint, anchor: UnitPoint, proposal: ProposedViewSize) {
        recorder.point = position
        recorder.proposed = proposal
    }
}

public struct LayoutSubviews: RandomAccessCollection {
    public typealias Index = Int
    public let elements: [LayoutSubview]
    public init(_ elements: [LayoutSubview]) { self.elements = elements }
    public var startIndex: Int { elements.startIndex }
    public var endIndex: Int { elements.endIndex }
    public subscript(position: Int) -> LayoutSubview { elements[position] }
}

public protocol Layout {
    typealias Subviews = LayoutSubviews
    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize
    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ())
}
