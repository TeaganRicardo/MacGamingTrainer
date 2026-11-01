import Foundation

/// Matches supplied aliases without reordering the module's destinations.
enum TrainerWorkbenchSearch {
    static func matches<Entry>(
        _ query: String, entries: [Entry], terms: (Entry) -> [String]
    ) -> [Entry] {
        let words = query.split(whereSeparator: \.isWhitespace).map { normalized(String($0)) }
        guard !words.isEmpty else { return [] }
        return entries.filter { entry in
            let searchable = normalized(terms(entry).joined(separator: " "))
            return words.allSatisfy { searchable.contains($0) }
        }
    }

    private static func normalized(_ value: String) -> String {
        value.folding(options: [.caseInsensitive, .diacriticInsensitive],
                      locale: Locale(identifier: "en_US_POSIX"))
    }
}

/// Transient presentation never owns the query or a game action. The module
/// keeps its input when hidden and supplies a navigation-only destination handler.
struct TrainerWorkbenchSearchPresentation {
    var resultsPresented = false

    mutating func queryChanged(_ query: String, pageVisible: Bool) {
        resultsPresented = pageVisible && !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    mutating func pageVisibilityChanged(_ visible: Bool) {
        if !visible { dismiss() }
    }

    mutating func dismiss() {
        resultsPresented = false
    }

    @discardableResult
    mutating func select<Entry>(
        _ entry: Entry?, pageVisible: Bool, navigate: (Entry) -> Void
    ) -> Bool {
        dismiss()
        guard pageVisible, let entry else { return false }
        navigate(entry)
        return true
    }

    @discardableResult
    mutating func submit<Entry>(
        query: String, pageVisible: Bool, search: (String) -> [Entry], navigate: (Entry) -> Void
    ) -> Bool {
        // Re-read the current input. The clear button submits before SwiftUI
        // recomputes its body, so a captured result array could navigate stale input.
        select(search(query).first, pageVisible: pageVisible, navigate: navigate)
    }
}
