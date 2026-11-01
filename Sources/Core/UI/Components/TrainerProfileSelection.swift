import Foundation

struct TrainerProfileEntry: Identifiable, Equatable {
    let name: String
    let updatedAt: String
    var id: String { name }
    var title: String { updatedAt.isEmpty ? name : "\(name) · \(updatedAt)" }
}

/// The draft is independent of the selected stored profile. A save's own
/// acknowledgement and refreshed inventory must agree before selecting its name.
struct TrainerProfileSelection {
    struct SaveRequest: Equatable {
        let id = UUID()
        let name: String
    }

    var draftName = ""
    var selectedName = ""
    private(set) var pendingSave: SaveRequest?
    private(set) var savedNameToSelect: String?

    var trimmedName: String { draftName.trimmingCharacters(in: .whitespacesAndNewlines) }
    var saving: Bool { pendingSave != nil }

    mutating func beginSave() -> SaveRequest? {
        guard !saving, !trimmedName.isEmpty else { return nil }
        let request = SaveRequest(name: trimmedName)
        pendingSave = request
        savedNameToSelect = nil
        return request
    }

    mutating func completeSave(_ request: SaveRequest, succeeded: Bool) {
        guard pendingSave == request else { return }
        pendingSave = nil
        savedNameToSelect = succeeded ? request.name : nil
    }

    mutating func invalidateSave() {
        pendingSave = nil
        savedNameToSelect = nil
    }

    mutating func reconcile(_ names: [String]) {
        if let savedNameToSelect, names.contains(savedNameToSelect) {
            selectedName = savedNameToSelect
            self.savedNameToSelect = nil
        }
        if !names.contains(selectedName) { selectedName = names.first ?? "" }
    }
}
