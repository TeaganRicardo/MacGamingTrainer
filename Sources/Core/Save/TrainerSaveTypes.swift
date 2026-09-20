import Foundation

struct TrainerSaveSnapshot: Identifiable, Equatable {
    let id: String
    let name: String
    let createdAt: String
    let fileCount: Int
    let nameDetails: [String]
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
        self.hot = row["hot"] as? Bool ?? false
        self.path = row["path"] as? String ?? ""
        self.valid = row["valid"] as? Bool ?? false
        self.error = row["error"] as? String ?? ""
    }
}

struct TrainerPendingRestore: Equatable {
    let snapshotID: String
    let preserveCurrent: Bool
    let stagedAt: String

    init?(row: [String: Any]) {
        guard let snapshotID = row["snapshotId"] as? String,
              let preserveCurrent = row["preserveCurrent"] as? Bool else { return nil }
        self.snapshotID = snapshotID
        self.preserveCurrent = preserveCurrent
        self.stagedAt = row["stagedAt"] as? String ?? ""
    }
}
