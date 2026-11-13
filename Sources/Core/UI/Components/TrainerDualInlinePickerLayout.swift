import SwiftUI

/// Measures two inline label/native-Picker pairs independently, then reserves
/// the optional shortcut and trailing action lanes. Used by exact-boon rows.
struct TrainerDualInlinePickerLayout: Layout {
    let minimumPickerWidth: CGFloat
    let maximumPickerWidth: CGFloat
    let minimumShortcutWidth: CGFloat
    let minimumActionWidth: CGFloat
    let spacing: CGFloat = 8

    private func measuredSizes(of subviews: Subviews) -> [CGSize] {
        guard subviews.count >= 6 else { return subviews.map { $0.sizeThatFits(.unspecified) } }
        var sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        sizes[1].width = minimumPickerWidth
        sizes[3].width = minimumPickerWidth
        if sizes[4].width > 0.5 {
            sizes[4].width = max(sizes[4].width, minimumShortcutWidth)
        }
        sizes[5].width = max(sizes[5].width, minimumActionWidth)
        return sizes
    }

    private func trailingIndices(in sizes: [CGSize]) -> [Int] {
        sizes.indices.filter { $0 >= 4 && sizes[$0].width > 0.5 }
    }

    private func allocation(for width: CGFloat, sizes: [CGSize]) -> (picker: CGFloat, occupied: CGFloat) {
        let trailing = trailingIndices(in: sizes)
        let labelsWidth = sizes[0].width + sizes[2].width
        let trailingWidth = trailing.reduce(CGFloat.zero) { $0 + sizes[$1].width }
        let gaps = CGFloat(3 + trailing.count) * spacing
        let available = width - labelsWidth - trailingWidth - gaps
        let pickerWidth = max(minimumPickerWidth, min(maximumPickerWidth, available / 2))
        return (pickerWidth, labelsWidth + trailingWidth + gaps + pickerWidth * 2)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count >= 6 else { return .zero }
        let sizes = measuredSizes(of: subviews)
        let minimumWidth = allocation(for: 0, sizes: sizes).occupied
        let proposedWidth = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? minimumWidth
        let finalWidth = max(minimumWidth, proposedWidth)
        let pickerWidth = allocation(for: finalWidth, sizes: sizes).picker
        let firstHeight = subviews[1].sizeThatFits(ProposedViewSize(width: pickerWidth, height: nil)).height
        let secondHeight = subviews[3].sizeThatFits(ProposedViewSize(width: pickerWidth, height: nil)).height
        return CGSize(width: finalWidth,
                      height: max(max(firstHeight, secondHeight), sizes.map(\.height).max() ?? 0))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        guard subviews.count >= 6 else { return }
        let sizes = measuredSizes(of: subviews)
        let trailing = trailingIndices(in: sizes)
        let allocated = allocation(for: bounds.width, sizes: sizes)
        let trailingExtra = max(0, bounds.width - allocated.occupied)

        var x = bounds.minX
        subviews[0].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: sizes[0].width, height: nil))
        x += sizes[0].width + spacing
        subviews[1].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: allocated.picker, height: nil))
        x += allocated.picker + spacing
        subviews[2].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: sizes[2].width, height: nil))
        x += sizes[2].width + spacing
        subviews[3].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: allocated.picker, height: nil))
        x += allocated.picker + trailingExtra

        for index in sizes.indices where index >= 4 {
            if trailing.contains(index) {
                x += spacing
                subviews[index].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                                      proposal: ProposedViewSize(width: sizes[index].width, height: nil))
                x += sizes[index].width
            } else {
                subviews[index].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                                      proposal: .zero)
            }
        }
    }
}
