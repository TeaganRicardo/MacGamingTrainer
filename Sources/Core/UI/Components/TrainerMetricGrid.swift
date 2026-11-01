import SwiftUI

/// The bounded dashboard uses eager, stable children so collapsing additional
/// rows cannot recycle native editors or their view-local drafts.
struct TrainerMetricGrid: Layout {
    private let columns = 4
    private let spacing: CGFloat = 12

    private struct Metrics {
        let width: CGFloat
        let columnWidth: CGFloat
        let rowHeights: [CGFloat]
        let spacing: CGFloat
        var size: CGSize {
            CGSize(width: width, height: rowHeights.reduce(0, +) + CGFloat(max(0, rowHeights.count - 1)) * spacing)
        }
    }

    private func metrics(width proposedWidth: CGFloat?, subviews: Subviews) -> Metrics {
        let constrainedWidth = proposedWidth.flatMap { $0.isFinite ? max(0, $0) : nil }
        let width = constrainedWidth ?? (subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0)
            * CGFloat(columns) + CGFloat(columns - 1) * spacing
        let columnWidth = max(0, (width - CGFloat(columns - 1) * spacing) / CGFloat(columns))
        var rowHeights = Array(repeating: CGFloat.zero, count: (subviews.count + columns - 1) / columns)
        for index in subviews.indices {
            rowHeights[index / columns] = max(rowHeights[index / columns],
                subviews[index].sizeThatFits(ProposedViewSize(width: columnWidth, height: nil)).height)
        }
        return Metrics(width: width, columnWidth: columnWidth, rowHeights: rowHeights, spacing: spacing)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        metrics(width: proposal.width, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let measured = metrics(width: bounds.width, subviews: subviews)
        var y = bounds.minY
        for index in subviews.indices {
            let row = index / columns
            subviews[index].place(at: CGPoint(x: bounds.minX + CGFloat(index % columns) * (measured.columnWidth + spacing), y: y),
                anchor: .topLeading, proposal: ProposedViewSize(width: measured.columnWidth, height: measured.rowHeights[row]))
            if index % columns == columns - 1 { y += measured.rowHeights[row] + spacing }
        }
    }
}
