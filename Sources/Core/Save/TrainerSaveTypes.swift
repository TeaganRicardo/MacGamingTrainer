import Foundation

struct TrainerSaveSnapshotPresentation: Equatable {
    let name: String
    let details: [String]

    init?(row: [String: Any]) {
        guard let name = row["name"] as? String, !name.isEmpty else { return nil }
        self.name = name
        self.details = row["details"] as? [String] ?? []
    }
}

struct TrainerSaveSnapshot: Identifiable, Equatable {
    let id: String
    let name: String
    let createdAt: String
    let fileCount: Int
    let nameDetails: [String]
    let automaticName: Bool
    let localizedPresentation: [String: TrainerSaveSnapshotPresentation]
    let hot: Bool
    let path: String
    let valid: Bool
    let error: String

    init?(row: [String: Any]) {
        guard let id = row["id"] as? String,
              let name = row["name"] as? String else { return nil }
        self.id = id
        self.name = name
        self.createdAt = row["createdAt"] as? String ?? ""
        self.fileCount = row["fileCount"] as? Int ?? 0
        self.nameDetails = row["nameDetails"] as? [String] ?? []
        self.automaticName = row["automaticName"] as? Bool ?? false
        let localizedRows = row["localizedPresentation"] as? [String: Any] ?? [:]
        self.localizedPresentation = localizedRows.reduce(into: [:]) { result, entry in
            guard let value = entry.value as? [String: Any],
                  let presentation = TrainerSaveSnapshotPresentation(row: value) else { return }
            result[entry.key] = presentation
        }
        self.hot = row["hot"] as? Bool ?? false
        self.path = row["path"] as? String ?? ""
        self.valid = row["valid"] as? Bool ?? false
        self.error = row["error"] as? String ?? ""
    }

    func displayName(for languageCode: String) -> String {
        guard automaticName,
              let localized = localizedPresentation[languageCode] else {
            return name
        }
        return localized.name
    }

    func displayDetails(for languageCode: String) -> [String] {
        localizedPresentation[languageCode]?.details ?? nameDetails
    }
}

struct TrainerPendingRestore: Equatable {
    let snapshotID: String
    let preserveCurrent: Bool
    let stagedAt: String
    let indeterminate: Bool

    init?(row: [String: Any]) {
        guard let snapshotID = row["snapshotId"] as? String,
              let preserveCurrent = row["preserveCurrent"] as? Bool else { return nil }
        self.snapshotID = snapshotID
        self.preserveCurrent = preserveCurrent
        self.stagedAt = row["stagedAt"] as? String ?? ""
        self.indeterminate = row["indeterminate"] as? Bool ?? false
    }
}
