import Foundation

/// A catalog entry determines which explicit options a selection action accepts.
/// Nil means no explicit option is selectable and callers omit that parameter.
package struct TrainerOrderedOptionResolution: Equatable {
    package enum Adjustment: Equatable {
        case none
        case constrainedToSupported
        case externallyControlled
    }

    package let option: String?
    package let adjustment: Adjustment
    package var requiresVisibleConfirmation: Bool { adjustment != .none }
}

package enum TrainerOrderedOptionReconciler {
    /// Reconcile a previously selected option with the active catalog target's
    /// supported choices and preferred ordering.
    package static func resolve(
        previous: String?,
        supported: [String],
        preferredOrder: [String],
        declaredDefault: String? = nil
    ) -> TrainerOrderedOptionResolution {
        var seen = Set<String>()
        let legal = supported.filter { seen.insert($0).inserted }
        guard !legal.isEmpty else {
            return .init(option: nil, adjustment: previous == nil ? .none : .externallyControlled)
        }
        if let previous, legal.contains(previous) {
            return .init(option: previous, adjustment: .none)
        }
        if let declaredDefault, legal.contains(declaredDefault) {
            return .init(option: declaredDefault, adjustment: .constrainedToSupported)
        }
        var order: [String: Int] = [:]
        for (index, item) in preferredOrder.enumerated() where order[item] == nil {
            order[item] = index
        }
        let indexed = legal.compactMap { item -> (String, Int)? in
            guard let position = order[item] else { return nil }
            return (item, position)
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
        return .init(option: selected, adjustment: selected == previous ? .none : .constrainedToSupported)
    }
}
