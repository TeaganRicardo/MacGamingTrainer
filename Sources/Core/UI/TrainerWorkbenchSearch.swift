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
struct TrainerWorkbenchSearchPresentation<ID: Hashable> {
    var resultsPresented = false
    private(set) var selectedID: ID?

    mutating func queryChanged(_ query: String, pageVisible: Bool, results: [ID]) {
        guard canSearch(query, pageVisible: pageVisible) else { dismiss(); return }
        resultsPresented = true
        resultsChanged(results)
    }

    mutating func resultsChanged(_ results: [ID]) {
        guard resultsPresented else { selectedID = nil; return }
        if let selectedID, results.contains(selectedID) { return }
        selectedID = results.first
    }

    @discardableResult
    mutating func moveSelection(by offset: Int, query: String, pageVisible: Bool, results: [ID]) -> Bool {
        guard canSearch(query, pageVisible: pageVisible) else { dismiss(); return false }
        let wasPresented = resultsPresented
        resultsPresented = true
        resultsChanged(results)
        guard !results.isEmpty else { return false }
        if !wasPresented {
            selectedID = offset < 0 ? results.last : results.first
        } else if let selectedID, let index = results.firstIndex(of: selectedID) {
            self.selectedID = results[min(max(index + offset, 0), results.count - 1)]
        }
        return true
    }

    mutating func pageVisibilityChanged(_ visible: Bool) {
        if !visible { dismiss() }
    }

    mutating func dismiss() {
        resultsPresented = false
        selectedID = nil
    }

    @discardableResult
    mutating func select<Entry>(
        _ id: ID, query: String, pageVisible: Bool, search: (String) -> [Entry],
        identifier: (Entry) -> ID, navigate: (Entry) -> Void
    ) -> Bool {
        // A removed row can still have a queued native action. Resolve its
        // identity against today's query and current page before navigating.
        guard resultsPresented, canSearch(query, pageVisible: pageVisible) else {
            dismiss(); return false
        }
        guard let entry = search(query).first(where: { identifier($0) == id }) else { return false }
        dismiss()
        navigate(entry)
        return true
    }

    @discardableResult
    mutating func submit<Entry>(
        query: String, pageVisible: Bool, search: (String) -> [Entry],
        identifier: (Entry) -> ID, navigate: (Entry) -> Void
    ) -> Bool {
        // Re-read the current input. The clear button submits before SwiftUI
        // recomputes its body, so a captured result array could navigate stale input.
        guard canSearch(query, pageVisible: pageVisible) else { dismiss(); return false }
        let results = search(query)
        let selected = resultsPresented ? selectedID : nil
        let entry = selected.flatMap { id in results.first { identifier($0) == id } } ?? results.first
        dismiss()
        guard let entry else { return false }
        navigate(entry)
        return true
    }

    private func canSearch(_ query: String, pageVisible: Bool) -> Bool {
        pageVisible && !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}
