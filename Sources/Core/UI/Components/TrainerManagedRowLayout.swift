import SwiftUI

/// Shared row geometry for managed item lists with compact numeric and picker
/// adjustment columns plus a trailing action control.
/// Game modules own item meaning and validation; Core owns row proportions so
/// disconnected and empty states align across modules.
package enum TrainerManagedRowLayout {
    package static let rowSpacing: CGFloat = 12
    package static let trailingActionWidth: CGFloat = 132
    package static let searchWidth: CGFloat = 260

    package static func numericAdjustmentWidth(compactActionWidth: CGFloat) -> CGFloat {
        42 + 58 + compactActionWidth + 2 * 6
    }

    package static func pickerAdjustmentWidth(
        compactActionWidth: CGFloat,
        pickerWidth: CGFloat
    ) -> CGFloat {
        48 + pickerWidth + compactActionWidth + 2 * 6
    }

    package static func trailingControlsWidth(
        compactActionWidth: CGFloat,
        pickerWidth: CGFloat
    ) -> CGFloat {
        numericAdjustmentWidth(compactActionWidth: compactActionWidth)
            + pickerAdjustmentWidth(
                compactActionWidth: compactActionWidth,
                pickerWidth: pickerWidth
            )
            + trailingActionWidth
            + 2 * rowSpacing
    }
}
