import SwiftUI

/// Hades I meta-currency identities for function discovery. The resource id
/// is the authority; an unknown or future resource uses the generic item.
enum HadesResourceIcon {
    static func systemName(for resourceID: String) -> String {
        switch resourceID {
        case "MetaPoints": "drop.fill"
        case "Gems": "diamond.fill"
        case "LockKeys": "key.fill"
        case "GiftPoints": "waterbottle.fill"
        case "SuperGems": "seal.fill"
        case "SuperGiftPoints": "wineglass.fill"
        case "SuperLockKeys": "drop.circle.fill"
        default: TrainerSemanticIcon.Concept.item
        }
    }
}
