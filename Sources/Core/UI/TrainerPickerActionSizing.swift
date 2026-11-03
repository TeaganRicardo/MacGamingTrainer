import Foundation

/// Computes the picker lane from individually measured trailing controls.
/// A nested HStack's total reported size can omit or compress native controls
/// when a flexible Picker changes size; that total is never used as input.
enum TrainerPickerActionSizing {
    static func width(
        rowWidth: CGFloat,
        labelWidth: CGFloat,
        trailingWidths: [CGFloat],
        minimumWidth: CGFloat,
        maximumWidth: CGFloat,
        spacing: CGFloat = 16,
        minimumLabelGap: CGFloat = 8
    ) -> CGFloat {
        let minimum = max(0, minimumWidth)
        guard rowWidth.isFinite, labelWidth.isFinite,
              spacing.isFinite, minimumLabelGap.isFinite,
              maximumWidth.isFinite, maximumWidth >= minimum,
              rowWidth > 0, labelWidth >= 0,
              spacing >= 0, minimumLabelGap >= 0,
              trailingWidths.allSatisfy({ $0.isFinite && $0 >= 0 }) else {
            return minimum
        }

        let visibleTrailing = trailingWidths.filter { $0 > 0 }
        let totalTrailing = visibleTrailing.reduce(CGFloat.zero, +)
        // Label -> Picker and Picker -> each trailing control each have one
        // inter-control spacing. A zero-width absent shortcut adds no gap.
        let gaps = CGFloat(visibleTrailing.count + 1) * spacing
        let available = rowWidth - labelWidth - minimumLabelGap - totalTrailing - gaps
        return max(minimum, min(maximumWidth, available))
    }
}
