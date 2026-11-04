import SwiftUI

/// Shared geometry for equivalent current-boon/effect manager controls.
/// Game modules own capability and mutation semantics; Core owns the stable row
/// proportions so disconnected/empty states do not drift between modules.
enum TrainerTraitManagerLayout {
    static let rowSpacing: CGFloat = 12
    static let removeControlWidth: CGFloat = 132
    static let searchWidth: CGFloat = 260

    static func levelControlsWidth(compactActionWidth: CGFloat) -> CGFloat {
        42 + 58 + compactActionWidth + 2 * 6
    }

    static func rarityControlsWidth(
        compactActionWidth: CGFloat,
        pickerWidth: CGFloat
    ) -> CGFloat {
        48 + pickerWidth + compactActionWidth + 2 * 6
    }

    static func commonControlsWidth(
        compactActionWidth: CGFloat,
        pickerWidth: CGFloat
    ) -> CGFloat {
        levelControlsWidth(compactActionWidth: compactActionWidth)
            + rarityControlsWidth(
                compactActionWidth: compactActionWidth,
                pickerWidth: pickerWidth
            )
            + removeControlWidth
            + 2 * rowSpacing
    }
}
