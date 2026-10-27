import Foundation
import Combine

// The wire representation preserves Lua types, physical table occurrences and
// byte strings. Display text is never used as an edit or identity.
indirect enum HadesSaveValue: Codable, Equatable {
    struct Entry: Codable, Equatable { let key: HadesSaveValue; let value: HadesSaveValue }
    case null, boolean(Bool), number(Double), string(String), rawString(String), rawNumber(String)
    case table(arraySize: Int, hashSize: Int, entries: [Entry])

    private enum CodingKeys: String, CodingKey { case luaType, value, encoding, arraySize, hashSize, entries }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        switch try c.decode(String.self, forKey: .luaType) {
        case "nil": self = .null
        case "boolean": self = .boolean(try c.decode(Bool.self, forKey: .value))
        case "number":
            if try c.decodeIfPresent(String.self, forKey: .encoding) == "ieee754" {
                self = .rawNumber(try c.decode(String.self, forKey: .value))
            } else { self = .number(try c.decode(Double.self, forKey: .value)) }
        case "string":
            if try c.decodeIfPresent(String.self, forKey: .encoding) == "base64" {
                self = .rawString(try c.decode(String.self, forKey: .value))
            } else { self = .string(try c.decode(String.self, forKey: .value)) }
        case "table": self = .table(arraySize: try c.decode(Int.self, forKey: .arraySize),
            hashSize: try c.decode(Int.self, forKey: .hashSize), entries: try c.decode([Entry].self, forKey: .entries))
        default: throw DecodingError.dataCorruptedError(forKey: .luaType, in: c, debugDescription: "Unknown Lua value type")
        }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .null: try c.encode("nil", forKey: .luaType)
        case .boolean(let value): try c.encode("boolean", forKey: .luaType); try c.encode(value, forKey: .value)
        case .number(let value): try c.encode("number", forKey: .luaType); try c.encode(value, forKey: .value)
        case .string(let value): try c.encode("string", forKey: .luaType); try c.encode(value, forKey: .value)
        case .rawString(let value):
            try c.encode("string", forKey: .luaType); try c.encode("base64", forKey: .encoding); try c.encode(value, forKey: .value)
        case .rawNumber(let value):
            try c.encode("number", forKey: .luaType); try c.encode("ieee754", forKey: .encoding); try c.encode(value, forKey: .value)
        case .table(let arraySize, let hashSize, let entries):
            try c.encode("table", forKey: .luaType); try c.encode(arraySize, forKey: .arraySize)
            try c.encode(hashSize, forKey: .hashSize); try c.encode(entries, forKey: .entries)
        }
    }
    var object: [String: Any] {
        // Every case encodes to a JSON object by construction.
        try! JSONSerialization.jsonObject(with: JSONEncoder().encode(self)) as! [String: Any]
    }
    var json: String {
        let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return String(data: try! encoder.encode(self), encoding: .utf8)!
    }
    var scalarText: String? {
        switch self {
        case .number(let value): return HadesNumberDraft.format(value)
        case .string(let value): return value
        default: return nil
        }
    }
}

enum HadesSaveEditorDomain: String, CaseIterable, Identifiable, Decodable {
    case resources, progression, equipment, relationships, narrative, statistics, history, advanced
    var id: String { rawValue }
    var titleKey: String { "hades.saveEditor.domain." + rawValue }
}

struct HadesSaveFile: Decodable, Identifiable, Equatable {
    let rootId: String
    let relativePath: String
    let profile: String
    let variant: String
    var id: String { rootId + "/" + relativePath }
    var label: String { profile + " · " + rootId + "/" + relativePath }
    var identity: [String: String] { ["rootId": rootId, "relativePath": relativePath] }
}

struct HadesSaveEditorRow: Decodable, Identifiable, Equatable {
    struct Choice: Decodable, Equatable { let name: String; let value: HadesSaveValue }
    let id: String
    let name: String
    let englishName: String
    let group: String
    let groupId: String
    let owner: String
    let ownerId: String
    let valueType: String
    let displayValue: String
    let typedValue: HadesSaveValue?
    let editable: Bool
    let operations: [String]
    let hasChildren: Bool
    let warning: String?
    let choices: [Choice]?
}

struct HadesSaveEditorReview: Decodable {
    struct Effect: Decodable, Identifiable { let id: String; let name: String; let before: String; let after: String }
    struct Action: Decodable, Identifiable {
        let id: String
        let name: String
        let before: String
        let after: String
        let operation: String
        let valueType: String
        let typedValue: HadesSaveValue?
        let typedKey: HadesSaveValue?
        let effects: [Effect]
    }
    let actions: [Action]
    let count: Int
    let effectCount: Int
    static let empty = Self(actions: [], count: 0, effectCount: 0)
}

struct HadesSaveEditorSource: Decodable {
    let kind: String
    let snapshotId: String?
    let rootId: String
    let relativePath: String
    var id: String { rootId + "/" + relativePath }
}

struct HadesSaveEditorReceipt: Decodable {
    let applied: Bool
    let verified: Bool
    let installedSHA256: String
    let hot: Bool?
    let runtimeReloaded: Bool
    let previousSnapshotId: String?
    let target: HadesSaveFileIdentity
}
struct HadesSaveFileIdentity: Decodable {
    let rootId: String
    let relativePath: String
    var id: String { rootId + "/" + relativePath }
}

final class HadesSaveEditorModel: ObservableObject {
    private struct Inventory: Decodable {
        let sources: [HadesSaveFile]; let targets: [HadesSaveFile]; let defaultSource: HadesSaveFileIdentity?
    }
    private struct Summary: Decodable {
        let workspaceId: String; let source: HadesSaveEditorSource; let sourceSHA256: String
        let target: HadesSaveFileIdentity?; let domains: [HadesSaveEditorDomain]; let review: HadesSaveEditorReview
    }
    struct Breadcrumb: Decodable, Identifiable { let id: String; let name: String }
    private struct Query: Decodable {
        let rows: [HadesSaveEditorRow]; let total: Int; let offset: Int; let limit: Int
        let breadcrumbs: [Breadcrumb]; let parentId: String?
    }
    private struct Detail: Decodable { let row: HadesSaveEditorRow }

    @Published private(set) var workspaceID: String?
    @Published private(set) var source: HadesSaveEditorSource?
    @Published private(set) var sourceSHA256 = ""
    @Published private(set) var sources: [HadesSaveFile] = []
    @Published private(set) var targets: [HadesSaveFile] = []
    @Published var selectedSourceID = ""
    @Published private(set) var selectedTargetID = ""
    @Published private(set) var domains = HadesSaveEditorDomain.allCases
    @Published private(set) var domain = HadesSaveEditorDomain.resources
    @Published var search = ""
    @Published private(set) var rows: [HadesSaveEditorRow] = []
    @Published private(set) var breadcrumbs: [Breadcrumb] = []
    @Published private(set) var parentID: String?
    @Published private(set) var total = 0
    @Published private(set) var offset = 0
    @Published private(set) var pageLimit = HadesSaveEditorModel.pageSize
    @Published private(set) var review = HadesSaveEditorReview.empty
    @Published private(set) var busy = false
    @Published private(set) var queryLoading = false
    @Published private(set) var failures: [String: TrainerTextToken] = [:]
    @Published private(set) var recoveryPath: String?
    @Published private(set) var receipt: HadesSaveEditorReceipt?
    @Published private(set) var editingRow: HadesSaveEditorRow?
    @Published private(set) var editingTyped = false
    @Published private(set) var editRevision = 0
    let snapshotID: String?
    static let pageSize = 40
    private let session: TrainerBackendSession
    private var language: TrainerPresentationLanguage = .en
    private var generation = UUID()
    private var queryGeneration = 0
    private var detailGeneration = 0
    private var pageHistory: [Int] = []
    private var typedEntries: Set<String> = []
    private var blockingRequests = 0
    private var searchTask: DispatchWorkItem?
    private var started = false

    init(session: TrainerBackendSession, snapshotID: String? = nil) { self.session = session; self.snapshotID = snapshotID }
    var canApply: Bool { !busy && workspaceID != nil && !selectedTargetID.isEmpty && review.count > 0 && recoveryPath == nil }

    func open(language: TrainerPresentationLanguage) {
        self.language = language
        guard !started else { return }; started = true
        refreshInventory(openDefault: true)
    }
    func refreshInventory(openDefault: Bool = false) {
        perform("inventory", params: snapshotID.map { ["snapshotId": $0] } ?? [:], scope: "inventory", workspace: nil) { [weak self] result in
            guard let self, let inventory: Inventory = self.decode(result, scope: "inventory") else { return }
            self.sources = inventory.sources; self.targets = inventory.targets
            if openDefault, self.workspaceID == nil, let selected = inventory.defaultSource ?? inventory.sources.first.map({ HadesSaveFileIdentity(rootId: $0.rootId, relativePath: $0.relativePath) }) {
                self.selectedSourceID = selected.id
                DispatchQueue.main.async { [weak self] in self?.openSelection() }
            }
        }
    }
    func openSelection() {
        guard !busy, let file = sources.first(where: { $0.id == selectedSourceID }) else { return }
        var params: [String: Any] = ["source": file.identity]
        if let snapshotID { params["snapshotId"] = snapshotID }
        if let target = targets.first(where: { $0.id == (selectedTargetID.isEmpty ? file.id : selectedTargetID) }) { params["target"] = target.identity }
        load(params)
    }
    private func load(_ params: [String: Any]) {
        let oldWorkspace = workspaceID
        perform("open", params: params, scope: "open", workspace: nil) { [weak self] result in
            guard let self, let summary: Summary = self.decode(result, scope: "open") else { return }
            self.generation = UUID(); self.queryGeneration += 1; self.detailGeneration += 1
            self.workspaceID = summary.workspaceId; self.source = summary.source; self.sourceSHA256 = summary.sourceSHA256
            self.selectedSourceID = summary.source.id; self.selectedTargetID = summary.target?.id ?? ""
            self.domains = summary.domains; self.review = summary.review; self.rows = []; self.breadcrumbs = []; self.parentID = nil
            self.domain = summary.domains.first ?? .resources; self.search = ""; self.editingRow = nil
            self.recoveryPath = nil; self.failures = [:]; self.editRevision += 1; self.typedEntries = []
            self.receipt = nil
            if let oldWorkspace { self.release(oldWorkspace) }
            self.query()
        }
    }
    func selectTarget(_ id: String) {
        guard !busy, let workspaceID, let target = targets.first(where: { $0.id == id }) else { return }
        perform("target", params: ["target": target.identity], scope: "target", workspace: workspaceID) { [weak self] result in
            guard let self, let summary: Summary = self.decode(result, scope: "target") else { return }
            self.selectedTargetID = summary.target?.id ?? ""
        }
    }
    func selectDomain(_ selected: HadesSaveEditorDomain) {
        domain = selected; parentID = nil; breadcrumbs = []; query()
    }
    func browse(_ id: String?) { parentID = id; query() }
    func setLanguage(_ value: TrainerPresentationLanguage) {
        detailGeneration += 1
        language = value; editingRow = nil; query(); refreshReview()
    }
    func searchChanged() {
        searchTask?.cancel(); queryGeneration += 1
        let task = DispatchWorkItem { [weak self] in self?.query() }
        searchTask = task; DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: task)
    }
    func nextPage() { pageHistory.append(offset); query(offset: offset + pageLimit) }
    func previousPage() { query(offset: pageHistory.popLast() ?? 0) }
    func query(offset requestedOffset: Int = 0) {
        guard let workspaceID else { return }
        if requestedOffset == 0 { pageHistory = [] }
        searchTask?.cancel(); queryGeneration += 1; let ticket = queryGeneration
        var params: [String: Any] = ["domain": domain.rawValue, "language": language.rawValue,
            "query": search, "offset": requestedOffset, "limit": Self.pageSize]
        if let parentID { params["parentId"] = parentID }
        queryLoading = true
        perform("query", params: params, scope: "query", workspace: workspaceID, blocking: false,
                accept: { [weak self] in self?.queryGeneration == ticket },
                finished: { [weak self] in if self?.queryGeneration == ticket { self?.queryLoading = false } }) { [weak self] result in
            guard let self, let query: Query = self.decode(result, scope: "query") else { return }
            self.rows = query.rows; self.total = query.total; self.offset = query.offset; self.pageLimit = query.limit
            self.breadcrumbs = query.breadcrumbs; self.parentID = query.parentId
        }
    }
    func detail(_ id: String, typed: Bool = false) {
        guard let workspaceID else { return }; detailGeneration += 1; let ticket = detailGeneration
        let forceTyped = typed || typedEntries.contains(id)
        perform("detail", params: ["entryId": id, "language": language.rawValue], scope: "detail", workspace: workspaceID,
                accept: { [weak self] in self?.detailGeneration == ticket }) { [weak self] result in
            guard let self, let detail: Detail = self.decode(result, scope: "detail") else { return }
            self.editingTyped = forceTyped; self.editingRow = detail.row
        }
    }
    func dismissDetail() { detailGeneration += 1; editingRow = nil; editingTyped = false }
    func commit(_ row: HadesSaveEditorRow, text: String, workspace captured: String?) -> String {
        guard captured == workspaceID else { return text }
        let value: HadesSaveValue
        let staged = review.actions.first { $0.id == row.id && $0.operation == "set" }?.typedValue
        switch staged ?? row.typedValue {
        case .some(.number):
            guard let number = Double(text), number.isFinite else { invalid(row.id); return text }; value = .number(number)
        case .some(.string): value = .string(text)
        default: invalid(row.id); return text
        }
        stage(row.id, operation: "set", value: value.object, workspace: captured)
        return value.scalarText ?? text
    }
    @discardableResult
    func commitJSON(_ row: HadesSaveEditorRow, text: String, appendKey: String? = nil, workspace captured: String?) -> Bool {
        guard captured == workspaceID else { return false }
        do {
            let value = try JSONDecoder().decode(HadesSaveValue.self, from: Data(text.utf8))
            var object = value.object
            if let appendKey {
                let key = try JSONDecoder().decode(HadesSaveValue.self, from: Data(appendKey.utf8))
                object = ["key": key.object, "value": object]
            }
            stage(row.id, operation: appendKey == nil ? "set" : "append", value: object, workspace: captured, typed: true)
            return true
        } catch { invalid(row.id); return false }
    }
    func stage(_ id: String, operation: String, value: [String: Any]? = nil, workspace captured: String?, typed: Bool = false) {
        guard let workspaceID, captured == workspaceID else { return }
        var params: [String: Any] = ["entryId": id, "operation": operation, "language": language.rawValue]
        if let value { params["value"] = value }
        perform("stage", params: params, scope: id, workspace: workspaceID) { [weak self] result in
            guard let self, self.applyReview(result, scope: id) else { return }
            if typed { self.typedEntries.insert(id) } else { self.typedEntries.remove(id) }
            self.editRevision += 1; self.query(offset: self.offset)
        }
    }
    func unstage(_ id: String) {
        guard let workspaceID else { return }
        perform("unstage", params: ["entryId": id, "language": language.rawValue], scope: id, workspace: workspaceID) { [weak self] result in
            guard let self, self.applyReview(result, scope: id) else { return }
            self.typedEntries.remove(id); self.editRevision += 1; self.query(offset: self.offset)
        }
    }
    func cancel() {
        guard !busy, let workspaceID else { return }
        perform("cancel", params: ["language": language.rawValue], scope: "cancel", workspace: workspaceID) { [weak self] result in
            guard let self, self.applyReview(result, scope: "cancel") else { return }; self.typedEntries = []; self.editRevision += 1; self.query(offset: self.offset)
        }
    }
    private func refreshReview() {
        guard let workspaceID else { return }
        perform("review", params: ["language": language.rawValue], scope: "review", workspace: workspaceID, blocking: false) { [weak self] result in
            _ = self?.applyReview(result, scope: "review")
        }
    }
    func apply() {
        guard canApply, let workspaceID else { return }
        perform("apply", scope: "apply", workspace: workspaceID) { [weak self] result in
            guard let self, let receipt: HadesSaveEditorReceipt = self.decode(result, scope: "apply") else { return }
            guard receipt.applied, receipt.verified else {
                self.failures["apply"] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return
            }
            self.receipt = receipt
            self.review = .empty; self.typedEntries = []; self.editRevision += 1; self.query(offset: self.offset)
        }
    }
    private func invalid(_ id: String) { failures[id] = TrainerTextToken(key: "hades.saveEditor.invalidValue") }
    private func applyReview(_ result: [String: Any], scope: String) -> Bool {
        guard let decoded: HadesSaveEditorReview = decode(result["review"] as? [String: Any] ?? result, scope: scope) else { return false }
        review = decoded; return true
    }
    func close() {
        searchTask?.cancel(); generation = UUID(); queryGeneration += 1; detailGeneration += 1
        if let workspaceID { release(workspaceID) }; workspaceID = nil; editingRow = nil
    }
    private func release(_ id: String) {
        session.send("save_editor_close", params: ["workspaceId": id], operation: "host.done", announceSuccess: false)
    }
    private func decode<T: Decodable>(_ result: [String: Any], scope: String) -> T? {
        do { return try JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: result)) }
        catch { failures[scope] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return nil }
    }
    private func perform(_ suffix: String, params: [String: Any] = [:], scope: String, workspace: String?,
                         blocking: Bool = true, accept: @escaping () -> Bool = { true },
                         finished: @escaping () -> Void = {}, receive: @escaping ([String: Any]) -> Void) {
        let capturedGeneration = generation; let lifecycle = session.lifecycleID
        var payload = params
        if let workspace { payload["workspaceId"] = workspace }
        if blocking { blockingRequests += 1; busy = true }
        failures.removeValue(forKey: scope)
        session.send("save_editor_" + suffix, params: payload, operation: "hades.saveEditor.title", announceSuccess: false,
                     timeout: 30, reply: { [weak self] reply in
            guard let self, self.generation == capturedGeneration, self.session.lifecycleID == lifecycle,
                  workspace == nil || self.workspaceID == workspace, accept() else { return }
            if reply.success, let result = reply.result { receive(result) }
            else if let failure = reply.failure {
                self.failures[scope] = TrainerTextToken(key: failure.presentation, arguments: failure.presentationArguments)
                if let path = failure.recoveryPath { self.recoveryPath = path }
            }
        }, completion: { [weak self] _ in
            guard let self else { return }
            if blocking { self.blockingRequests -= 1; self.busy = self.blockingRequests > 0 }
            if self.generation == capturedGeneration { finished() }
        })
    }
}
