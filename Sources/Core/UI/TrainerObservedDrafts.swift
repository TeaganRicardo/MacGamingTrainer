import SwiftUI

/// Preserves the user's currently focused text draft across background
/// observation refreshes while keeping every unfocused field synchronized.
package struct TrainerObservedDrafts<Field: Hashable>: Equatable {
    package private(set) var values: [Field: String]

    package init(_ values: [Field: String] = [:]) {
        self.values = values
    }

    package subscript(field: Field) -> String {
        get { values[field] ?? "" }
        set { values[field] = newValue }
    }

    package subscript(field: Field, default defaultValue: String) -> String {
        get { values[field] ?? defaultValue }
        set { values[field] = newValue }
    }

    /// Updates unfocused fields from an observation snapshot. Pass `force: true`
    /// only for initial population or an explicit draft-reset barrier.
    package mutating func observe(_ observed: [Field: String], focused: Field?, force: Bool = false) {
        for (field, text) in observed where force || field != focused {
            values[field] = text
        }
    }

    /// Updates a single field from an observation when it is not focused (or forced).
    package mutating func observe(_ field: Field, value: String, focused: Field?, force: Bool = false) {
        guard force || field != focused else { return }
        values[field] = value
    }

    package mutating func reset(to defaults: [Field: String] = [:]) {
        values = defaults
    }
}

extension Binding {
    package func binding<Field: Hashable>(
        _ field: Field,
        default defaultValue: String = ""
    ) -> Binding<String> where Value == TrainerObservedDrafts<Field> {
        Binding<String>(
            get: { wrappedValue[field, default: defaultValue] },
            set: { wrappedValue[field] = $0 }
        )
    }
}

extension View {
    package func trainerObservedDrafts<Field: Hashable>(
        _ drafts: Binding<TrainerObservedDrafts<Field>>,
        observed: [Field: String],
        focused: Field?
    ) -> some View {
        onChange(of: observed, initial: true) { _, next in
            drafts.wrappedValue.observe(next, focused: focused)
        }
    }
}
