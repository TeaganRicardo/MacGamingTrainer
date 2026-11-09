import Foundation

/// A native catalog determines the options that an exact acquisition accepts.
/// Nil means the game owns rarity and the command must omit that parameter.
struct TrainerAcquisitionRarityResolution: Equatable {
    enum Adjustment: Equatable {
        case none
        case targetRestricted
        case gameControlled
    }
    let rarity: String?
    let adjustment: Adjustment
    var requiresVisibleConfirmation: Bool { adjustment != .none }
}

enum TrainerAcquisitionRarity {
    /// Reconcile the visible setting with the active native acquisition target.
    static func resolve(
        previous: String?,
        supported: [String],
        nativeOrder: [String],
        declaredDefault: String? = nil
    ) -> TrainerAcquisitionRarityResolution {
        var seen = Set<String>()
        let legal = supported.filter { seen.insert($0).inserted }
        guard !legal.isEmpty else {
            return .init(rarity: nil, adjustment: previous == nil ? .none : .gameControlled)
        }
        if let previous, legal.contains(previous) {
            return .init(rarity: previous, adjustment: .none)
        }
        if let declaredDefault, legal.contains(declaredDefault) {
            return .init(rarity: declaredDefault, adjustment: .targetRestricted)
        }
        var order: [String: Int] = [:]
        for (index, rarity) in nativeOrder.enumerated() where order[rarity] == nil {
            order[rarity] = index
        }
        let indexed = legal.compactMap { rarity -> (String, Int)? in
            guard let position = order[rarity] else { return nil }
            return (rarity, position)
        }
        let selected: String
        if let previous, let ceiling = order[previous],
           let atOrBelow = indexed.filter({ $0.1 <= ceiling }).max(by: { $0.1 < $1.1 }) {
            selected = atOrBelow.0
        } else if let lowest = indexed.min(by: { $0.1 < $1.1 }) {
            selected = lowest.0
        } else {
            selected = legal[0]
        }
        return .init(rarity: selected, adjustment: selected == previous ? .none : .targetRestricted)
    }
}
