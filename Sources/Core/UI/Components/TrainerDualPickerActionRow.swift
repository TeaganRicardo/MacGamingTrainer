import SwiftUI

/// Core-owned geometry for one labeled row with two independently measured
/// native Pickers and optional trailing shortcut/action controls.
struct TrainerDualPickerActionLayout: Layout {
    let labelWidth: CGFloat
    let minimumPickerWidth: CGFloat
    let maximumPickerWidth: CGFloat
    let minimumShortcutWidth: CGFloat
    let minimumActionWidth: CGFloat
    let spacing: CGFloat = 12
    let minimumLabelGap: CGFloat = 8

    private func measuredSizes(of subviews: Subviews) -> [CGSize] {
        guard subviews.count >= 5 else { return subviews.map { $0.sizeThatFits(.unspecified) } }
        var sizes = subviews.map { $0.sizeThatFits(.unspecified) }
        sizes[0].width = labelWidth
        sizes[1].width = minimumPickerWidth
        sizes[2].width = minimumPickerWidth
        if sizes[3].width > 0.5 {
            sizes[3].width = max(sizes[3].width, minimumShortcutWidth)
        }
        if let actionIndex = sizes.indices.last {
            sizes[actionIndex].width = max(sizes[actionIndex].width, minimumActionWidth)
        }
        return sizes
    }

    private func trailingIndices(in sizes: [CGSize]) -> [Int] {
        sizes.indices.filter { $0 >= 3 && sizes[$0].width > 0.5 }
    }

    private func allocation(for width: CGFloat, sizes: [CGSize]) -> (picker: CGFloat, occupied: CGFloat) {
        let trailing = trailingIndices(in: sizes)
        let trailingWidth = trailing.reduce(CGFloat.zero) { $0 + sizes[$1].width }
        let gaps = CGFloat(2 + trailing.count) * spacing
        let available = width - labelWidth - minimumLabelGap - gaps - trailingWidth
        let pickerWidth = max(minimumPickerWidth, min(maximumPickerWidth, available / 2))
        let occupied = labelWidth + minimumLabelGap + gaps + pickerWidth * 2 + trailingWidth
        return (pickerWidth, occupied)
    }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard subviews.count >= 5 else { return .zero }
        let sizes = measuredSizes(of: subviews)
        let minimumWidth = allocation(for: 0, sizes: sizes).occupied
        let proposedWidth = proposal.width.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? minimumWidth
        let finalWidth = max(minimumWidth, proposedWidth)
        let pickerWidth = allocation(for: finalWidth, sizes: sizes).picker
        let firstHeight = subviews[1].sizeThatFits(ProposedViewSize(width: pickerWidth, height: nil)).height
        let secondHeight = subviews[2].sizeThatFits(ProposedViewSize(width: pickerWidth, height: nil)).height
        return CGSize(width: finalWidth,
                      height: max(max(firstHeight, secondHeight), sizes.map(\.height).max() ?? 0))
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize,
                       subviews: Subviews, cache: inout ()) {
        guard subviews.count >= 5 else { return }
        let sizes = measuredSizes(of: subviews)
        let trailing = trailingIndices(in: sizes)
        let allocated = allocation(for: bounds.width, sizes: sizes)
        let trailingExtra = max(0, bounds.width - allocated.occupied)

        subviews[0].place(at: CGPoint(x: bounds.minX, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: labelWidth, height: nil))
        var x = bounds.minX + labelWidth + minimumLabelGap + spacing
        subviews[1].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: allocated.picker, height: nil))
        x += allocated.picker + spacing
        subviews[2].place(at: CGPoint(x: x, y: bounds.midY), anchor: .leading,
                          proposal: ProposedViewSize(width: allocated.picker, height: nil))
        x += allocated.picker + trailingExtra

        for index in sizes.indices where index >= 3 {
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

struct TrainerDualPickerActionRow<FirstPicker: View, SecondPicker: View, Shortcut: View, Action: View>: View {
    @Environment(\.trainerTheme) private var theme
    let title: String
    let icon: String
    let tint: Color
    let emphasized: Bool
    let helpText: String
    let firstPicker: FirstPicker
    let secondPicker: SecondPicker
    let shortcut: Shortcut
    let action: Action

    init(title: String, icon: String, tint: Color, emphasized: Bool,
         helpText: String = "",
         @ViewBuilder firstPicker: () -> FirstPicker,
         @ViewBuilder secondPicker: () -> SecondPicker,
         @ViewBuilder shortcut: () -> Shortcut,
         @ViewBuilder action: () -> Action) {
        self.title = title
        self.icon = icon
        self.tint = tint
        self.emphasized = emphasized
        self.helpText = helpText
        self.firstPicker = firstPicker()
        self.secondPicker = secondPicker()
        self.shortcut = shortcut()
        self.action = action()
    }

    var body: some View {
        TrainerRow {
            TrainerDualPickerActionLayout(
                labelWidth: theme.pickerActionLabelWidth,
                minimumPickerWidth: 144,
                maximumPickerWidth: theme.pickerActionMaxWidth,
                minimumShortcutWidth: theme.shortcutBadgeMinimumWidth,
                minimumActionWidth: theme.compactActionWidth
            ) {
                TrainerIconLabel(title: title, icon: icon, tint: tint, emphasized: emphasized)
                    .frame(width: theme.pickerActionLabelWidth, alignment: .leading)
                    .help(helpText)
                firstPicker
                secondPicker
                shortcut
                action
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}
