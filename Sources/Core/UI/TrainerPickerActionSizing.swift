import Foundation

/// Allocation policy for the shared trailing picker/action row.
/// `groupWidth` includes the existing picker, all trailing controls, and their
/// internal spacing; subtracting the measured picker width leaves the actual
/// trailing footprint, including localized shortcut and button widths.
enum TrainerPickerActionSizing {
    static func width(
        rowWidth: CGFloat,
        labelWidth: CGFloat,
        groupWidth: CGFloat,
        pickerWidth: CGFloat,
        minimumWidth: CGFloat,
        maximumWidth: CGFloat,
        outerSpacing: CGFloat = 16,
        minimumLabelGap: CGFloat = 8
    ) -> CGFloat {
        let minimum = max(0, minimumWidth)
        guard rowWidth.isFinite, labelWidth.isFinite,
              groupWidth.isFinite, pickerWidth.isFinite,
              rowWidth > 0, groupWidth > 0, pickerWidth > 0,
              maximumWidth.isFinite, maximumWidth >= minimum else {
            return minimum
        }
        let trailingFootprint = max(0, groupWidth - pickerWidth)
        let available = rowWidth - labelWidth - outerSpacing - minimumLabelGap - trailingFootprint
        return max(minimum, min(maximumWidth, available))
    }
}
