import SwiftUI

/// Shared layout for a label, native Picker, and zero or more trailing controls.
/// Each trailing control contributes its own measured width. A nested HStack's
/// aggregate size is not a reliable source for the native popup allocation.
struct TrainerPickerActionLayout: Layout {
    let labelWidth: CGFloat
    let minimumPickerWidth: CGFloat
    let maximumPickerWidth: CGFloat
    let spacing: CGFloat = 16
    let minimumLabelGap: CGFloat = 8

    private func naturalSizes(of subviews: Subviews) -> [CGSize] {
        subviews.map { $0.sizeThatFits(.unspecified) }
    }

    private func trailingIndices(in sizes: [CGSize]) -> [Int] {
        sizes.indices.filter { $0 >= 2 && sizes[$0].width > 0.5 }
    }

    private func allocation(for width: CGFloat, sizes: [CGSize]) -> (picker: CGFloat, occupied: CGFloat) {
        let trailing = trailingIndices(in: sizes)
        let trailingWidths = trailing.map { sizes[$0].width }
        let pickerWidth = TrainerPickerActionSizing.width(
            rowWidth: width, labelWidth: labelWidth,
            trailingWidths: trailingWidths,
            minimumWidth: minimumPickerWidth,
            maximumWidth: maximumPickerWidth,
            spacing: spacing, minimumLabelGap: minimumLabelGap
        )
        let occupied = labelWidth + minimumLabelGap
            + CGFloat(trailing.count + 1) * spacing
            + pickerWidth + trailingWidths.reduce(CGFloat.zero, +)
        return (pickerWidth, occupied)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count >= 2 else { return .zero }
        let sizes = naturalSizes(of: subviews)
        let minimum = allocation(for: 0, sizes: sizes).occupied
        let proposedWidth = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? minimum
        let finalWidth = max(minimum, proposedWidth)
        let pickerWidth = allocation(for: finalWidth, sizes: sizes).picker
        let pickerHeight = subviews[1].sizeThatFits(
            ProposedViewSize(width: pickerWidth, height: nil)
        ).height
        let rowHeight = max(pickerHeight, sizes.map(\.height).max() ?? 0)
        return CGSize(width: finalWidth, height: rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        guard subviews.count >= 2 else { return }
        let sizes = naturalSizes(of: subviews)
        let trailing = trailingIndices(in: sizes)
        let allocated = allocation(for: bounds.width, sizes: sizes)
        let leadingExtra = max(0, bounds.width - allocated.occupied)
        // Always preserve the header column; surplus belongs before Picker.
        subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.midY),
                          anchor: .leading,
                          proposal: ProposedViewSize(width: labelWidth, height: nil))
        var x = bounds.minX + labelWidth + spacing + minimumLabelGap + leadingExtra
        subviews[1].place(at: CGPoint(x: x, y: bounds.midY),
                          anchor: .leading,
                          proposal: ProposedViewSize(width: allocated.picker, height: nil))
        x += allocated.picker
        for index in sizes.indices where index >= 2 {
            // A nil shortcut slot occupies no width or phantom 16pt gap.
            if trailing.contains(index) {
                x += spacing
                subviews[index].place(at: CGPoint(x: x, y: bounds.midY),
                                      anchor: .leading,
                                      proposal: ProposedViewSize(width: sizes[index].width, height: nil))
                x += sizes[index].width
            } else {
                subviews[index].place(at: CGPoint(x: x, y: bounds.midY),
                                      anchor: .leading,
                                      proposal: .zero)
            }
        }
    }
}
