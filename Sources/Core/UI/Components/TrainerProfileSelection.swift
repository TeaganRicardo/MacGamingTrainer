import Foundation

struct TrainerProfileEntry: Identifiable, Equatable {
    let name: String
    let updatedAt: String
    var id: String { name }
    var title: String { updatedAt.isEmpty ? name : "\(name) · \(updatedAt)" }
}

/// The draft is independent of the selected stored profile. A save can request
/// a selection, but only a refreshed inventory can make that name selectable.
struct TrainerProfileSelection {
    var draftName = ""
    var selectedName = ""
    private(set) var pendingSavedName: String?

    var trimmedName: String { draftName.trimmingCharacters(in: .whitespacesAndNewlines) }

    mutating func beginSave() -> String? {
        guard !trimmedName.isEmpty else { return nil }
        pendingSavedName = trimmedName
        return trimmedName
    }

    mutating func reconcile(_ names: [String], busy: Bool) {
        if let pendingSavedName, names.contains(pendingSavedName) {
            selectedName = pendingSavedName
            self.pendingSavedName = nil
        }
        if !names.contains(selectedName) { selectedName = names.first ?? "" }
        // An unsuccessful save leaves the stored selection and draft intact.
        // Do not let its old requested name redirect a later unrelated refresh.
        if !busy { pendingSavedName = nil }
    }
}
