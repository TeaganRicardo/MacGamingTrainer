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
        case .number(let value):
            let text = String(value)
            return text.hasSuffix(".0") ? String(text.dropLast(2)) : text
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
    struct Content: Decodable, Equatable { let speaker: String; let text: String }
    let baselineGeneration: String
    let content: [Content]?
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
    let baselineGeneration: String
    let actions: [Action]
    let count: Int
    let effectCount: Int
    static let empty = Self(baselineGeneration: "", actions: [], count: 0, effectCount: 0)
}

struct HadesSaveEditorSource: Decodable {
    let kind: String
    let snapshotId: String?
    let rootId: String
    let relativePath: String
    var id: String { rootId + "/" + relativePath }
}

struct HadesSaveEditorReceipt: Decodable {
    let baselineGeneration: String
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
        let workspaceId: String; let baselineGeneration: String
        let source: HadesSaveEditorSource; let sourceSHA256: String
        let target: HadesSaveFileIdentity?; let domains: [HadesSaveEditorDomain]; let review: HadesSaveEditorReview
    }
    struct Breadcrumb: Decodable, Identifiable { let id: String; let name: String }
    private struct Query: Decodable {
        let baselineGeneration: String
        let rows: [HadesSaveEditorRow]; let total: Int; let offset: Int; let limit: Int
        let breadcrumbs: [Breadcrumb]; let parentId: String?
    }
    private struct Detail: Decodable { let row: HadesSaveEditorRow }

    @Published private(set) var workspaceID: String?
    @Published private(set) var baselineGeneration: String?
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
    @Published private(set) var applying = false
    @Published private(set) var queryLoading = false
    @Published private var readyGeneration: String?
    @Published private var activeEdits: Set<String> = []
    @Published private var failedDrafts: Set<String> = []
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
    var canEditRows: Bool {
        baselineGeneration != nil && readyGeneration == baselineGeneration && !applying && recoveryPath == nil
    }
    var canApply: Bool {
        canEditRows && !busy && activeEdits.isEmpty && failedDrafts.isEmpty && !selectedTargetID.isEmpty
            && review.count > 0 && review.baselineGeneration == baselineGeneration
    }
    func canEdit(_ row: HadesSaveEditorRow) -> Bool { canEditRows && row.baselineGeneration == baselineGeneration }
    func hasFailedDraft(_ row: HadesSaveEditorRow) -> Bool { failedDrafts.contains(draftKey(row.id, row.baselineGeneration)) }
    private func draftKey(_ id: String, _ baseline: String) -> String { baseline + ":" + id }
    func editingChanged(_ id: String, baseline: String, active: Bool) {
        let key = draftKey(id, baseline)
        if active {
            guard baseline == baselineGeneration, canEditRows else { return }
            activeEdits.insert(key)
        } else { activeEdits.remove(key) }
    }
    private func ownsMutation(_ workspace: String?, _ baseline: String?) -> Bool {
        workspace != nil && workspace == workspaceID && baseline != nil && baseline == baselineGeneration && canEditRows
    }
    private func stale(_ scope: String) {
        failures[scope] = TrainerTextToken(key: "hades.saveEditor.error", arguments: [
            "This control belongs to an earlier document baseline. Refresh the editor before editing."])
    }
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
        guard !busy, !applying, let file = sources.first(where: { $0.id == selectedSourceID }) else { return }
        var params: [String: Any] = ["source": file.identity]
        if let snapshotID { params["snapshotId"] = snapshotID }
        if let target = targets.first(where: { $0.id == (selectedTargetID.isEmpty ? file.id : selectedTargetID) }) { params["target"] = target.identity }
        let oldWorkspace = workspaceID
        perform("open", params: params, scope: "open", workspace: nil) { [weak self] result in
            guard let self, let summary: Summary = self.decode(result, scope: "open"),
                  summary.review.baselineGeneration == summary.baselineGeneration else { return }
            self.generation = UUID(); self.queryGeneration += 1; self.detailGeneration += 1
            self.workspaceID = summary.workspaceId; self.baselineGeneration = summary.baselineGeneration; self.readyGeneration = nil
            self.source = summary.source; self.sourceSHA256 = summary.sourceSHA256
            self.selectedSourceID = summary.source.id; self.selectedTargetID = summary.target?.id ?? ""
            self.domains = summary.domains; self.review = summary.review; self.rows = []; self.breadcrumbs = []; self.parentID = nil
            self.domain = summary.domains.first ?? .resources; self.search = ""; self.editingRow = nil
            self.recoveryPath = nil; self.failures = [:]; self.editRevision += 1; self.typedEntries = []
            self.activeEdits = []; self.failedDrafts = []; self.receipt = nil
            if let oldWorkspace { self.release(oldWorkspace) }
            self.query()
        }
    }
    func selectTarget(_ id: String, baseline: String?) {
        guard !busy, ownsMutation(workspaceID, baseline), let workspaceID,
              let target = targets.first(where: { $0.id == id }) else { return }
        perform("target", params: ["target": target.identity], scope: "target", workspace: workspaceID, baseline: baseline) { [weak self] result in
            guard let self, let summary: Summary = self.decode(result, scope: "target"), summary.baselineGeneration == baseline else { return }
            self.selectedTargetID = summary.target?.id ?? ""
        }
    }
    func selectDomain(_ selected: HadesSaveEditorDomain) { domain = selected; parentID = nil; breadcrumbs = []; query() }
    func browse(_ id: String?, baseline: String? = nil) {
        guard !applying, baseline == nil || baseline == baselineGeneration else { return }
        parentID = id; query()
    }
    func setLanguage(_ value: TrainerPresentationLanguage) { language = value; query(); refreshReview() }
    func searchChanged() {
        searchTask?.cancel(); queryGeneration += 1
        let task = DispatchWorkItem { [weak self] in self?.query() }
        searchTask = task; DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: task)
    }
    func nextPage() { pageHistory.append(offset); query(offset: offset + pageLimit) }
    func previousPage() { query(offset: pageHistory.popLast() ?? 0) }
    func query(offset requestedOffset: Int = 0) {
        guard !applying, let workspaceID, let baseline = baselineGeneration else { return }
        if requestedOffset == 0 { pageHistory = [] }
        searchTask?.cancel(); queryGeneration += 1; let ticket = queryGeneration
        var params: [String: Any] = ["domain": domain.rawValue, "language": language.rawValue,
            "query": search, "offset": requestedOffset, "limit": Self.pageSize]
        if let parentID { params["parentId"] = parentID }
        queryLoading = true
        perform("query", params: params, scope: "query", workspace: workspaceID, blocking: false,
                accept: { [weak self] in self?.queryGeneration == ticket && self?.baselineGeneration == baseline },
                finished: { [weak self] in if self?.queryGeneration == ticket { self?.queryLoading = false } }) { [weak self] result in
            guard let self, let query: Query = self.decode(result, scope: "query") else { return }
            guard query.baselineGeneration == baseline, query.rows.allSatisfy({ $0.baselineGeneration == baseline }) else {
                self.failures["query"] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return
            }
            self.rows = query.rows; self.total = query.total; self.offset = query.offset; self.pageLimit = query.limit
            self.breadcrumbs = query.breadcrumbs; self.parentID = query.parentId; self.readyGeneration = baseline
        }
    }
    func detail(_ id: String, typed: Bool = false, baseline: String? = nil) {
        let capturedBaseline = baseline ?? baselineGeneration
        guard canEditRows, capturedBaseline == baselineGeneration, let workspaceID else { return }
        detailGeneration += 1; let ticket = detailGeneration
        let forceTyped = typed || typedEntries.contains(id)
        perform("detail", params: ["entryId": id, "language": language.rawValue], scope: "detail", workspace: workspaceID,
                accept: { [weak self] in self?.detailGeneration == ticket && self?.baselineGeneration == capturedBaseline }) { [weak self] result in
            guard let self, let detail: Detail = self.decode(result, scope: "detail"), detail.row.baselineGeneration == capturedBaseline else { return }
            self.editingTyped = forceTyped; self.editingRow = detail.row
        }
    }
    func dismissDetail() { detailGeneration += 1; editingRow = nil; editingTyped = false }
    func discardDraft(_ row: HadesSaveEditorRow, workspace captured: String?) {
        guard ownsMutation(captured, row.baselineGeneration) else { return }
        failedDrafts.remove(draftKey(row.id, row.baselineGeneration))
        activeEdits.remove(draftKey(row.id, row.baselineGeneration))
        activeEdits.remove(draftKey(row.id + ":key", row.baselineGeneration))
        failures.removeValue(forKey: row.id); editRevision += 1
        dismissDetail()
    }
    func commit(_ row: HadesSaveEditorRow, text: String, workspace captured: String?) -> String {
        guard ownsMutation(captured, row.baselineGeneration) else { stale(row.id); return text }
        let value: HadesSaveValue
        let staged = review.actions.first { $0.id == row.id && $0.operation == "set" }?.typedValue
        switch staged ?? row.typedValue {
        case .some(.number):
            guard let number = Double(text), number.isFinite else { invalid(row); return text }; value = .number(number)
        case .some(.string): value = .string(text)
        default: invalid(row); return text
        }
        stage(row.id, operation: "set", value: value.object, workspace: captured, baseline: row.baselineGeneration)
        return value.scalarText ?? text
    }
    @discardableResult
    func commitJSON(_ row: HadesSaveEditorRow, text: String, appendKey: String? = nil, workspace captured: String?,
                    accepted: @escaping (Bool) -> Void = { _ in }) -> Bool {
        guard ownsMutation(captured, row.baselineGeneration) else { stale(row.id); return false }
        do {
            let value = try JSONDecoder().decode(HadesSaveValue.self, from: Data(text.utf8))
            var object = value.object
            if let appendKey {
                let key = try JSONDecoder().decode(HadesSaveValue.self, from: Data(appendKey.utf8))
                object = ["key": key.object, "value": object]
            }
            stage(row.id, operation: appendKey == nil ? "set" : "append", value: object, workspace: captured,
                  baseline: row.baselineGeneration, typed: true, accepted: accepted)
            return true
        } catch { invalid(row); return false }
    }
    func stage(_ id: String, operation: String, value: [String: Any]? = nil, workspace captured: String?, baseline: String,
               typed: Bool = false, accepted: @escaping (Bool) -> Void = { _ in }) {
        guard ownsMutation(captured, baseline), let workspaceID else { stale(id); accepted(false); return }
        var params: [String: Any] = ["entryId": id, "operation": operation, "language": language.rawValue]
        if let value { params["value"] = value }
        perform("stage", params: params, scope: id, workspace: workspaceID, baseline: baseline,
                failed: { [weak self] in
                    guard let self else { return }; self.failedDrafts.insert(self.draftKey(id, baseline)); accepted(false)
                }) { [weak self] result in
            guard let self else { return }
            guard self.applyReview(result, scope: id) else {
                self.failedDrafts.insert(self.draftKey(id, baseline)); accepted(false); return
            }
            self.failedDrafts.remove(self.draftKey(id, baseline))
            if typed { self.typedEntries.insert(id) } else { self.typedEntries.remove(id) }
            self.editRevision += 1; self.query(offset: self.offset); accepted(true)
        }
    }
    func unstage(_ id: String, baseline: String, accepted: @escaping (Bool) -> Void = { _ in }) {
        guard ownsMutation(workspaceID, baseline), let workspaceID else { return }
        perform("unstage", params: ["entryId": id, "language": language.rawValue], scope: id, workspace: workspaceID, baseline: baseline,
                failed: { accepted(false) }) { [weak self] result in
            guard let self else { return }
            guard self.applyReview(result, scope: id) else { accepted(false); return }
            self.failedDrafts.remove(self.draftKey(id, baseline)); self.typedEntries.remove(id)
            self.editRevision += 1; self.query(offset: self.offset); accepted(true)
        }
    }
    func cancel(baseline: String?) {
        guard !busy, ownsMutation(workspaceID, baseline), let workspaceID else { return }
        perform("cancel", params: ["language": language.rawValue], scope: "cancel", workspace: workspaceID, baseline: baseline) { [weak self] result in
            guard let self, self.applyReview(result, scope: "cancel") else { return }
            self.typedEntries = []; self.failedDrafts = []; self.editRevision += 1; self.query(offset: self.offset)
        }
    }
    private func refreshReview() {
        guard !applying, let workspaceID, let baseline = baselineGeneration else { return }
        perform("review", params: ["language": language.rawValue], scope: "review", workspace: workspaceID, blocking: false,
                accept: { [weak self] in self?.baselineGeneration == baseline }) { [weak self] result in
            _ = self?.applyReview(result, scope: "review")
        }
    }
    func apply(baseline: String?) {
        guard canApply, baseline == baselineGeneration, let workspaceID else { return }
        applying = true; readyGeneration = nil; searchTask?.cancel(); queryGeneration += 1; detailGeneration += 1
        queryLoading = false
        perform("apply", scope: "apply", workspace: workspaceID, baseline: baseline,
                failed: { [weak self] in self?.readyGeneration = baseline },
                finished: { [weak self] in self?.applying = false }) { [weak self] result in
            guard let self, let receipt: HadesSaveEditorReceipt = self.decode(result, scope: "apply") else { return }
            guard receipt.applied, receipt.verified, receipt.baselineGeneration != baseline else {
                self.failures["apply"] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return
            }
            self.receipt = receipt; self.baselineGeneration = receipt.baselineGeneration; self.applying = false
            self.review = .init(baselineGeneration: receipt.baselineGeneration, actions: [], count: 0, effectCount: 0)
            self.typedEntries = []; self.editRevision += 1; self.editingRow = nil
            self.parentID = nil; self.breadcrumbs = []; self.query()
        }
    }
    private func invalid(_ row: HadesSaveEditorRow) {
        failedDrafts.insert(draftKey(row.id, row.baselineGeneration))
        failures[row.id] = TrainerTextToken(key: "hades.saveEditor.invalidValue")
    }
    private func applyReview(_ result: [String: Any], scope: String) -> Bool {
        guard let decoded: HadesSaveEditorReview = decode(result, scope: scope) else { return false }
        guard decoded.baselineGeneration == baselineGeneration else {
            failures[scope] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return false
        }
        review = decoded; return true
    }
    func close() {
        searchTask?.cancel(); generation = UUID(); queryGeneration += 1; detailGeneration += 1
        if let workspaceID { release(workspaceID) }; workspaceID = nil; baselineGeneration = nil; readyGeneration = nil; editingRow = nil
    }
    private func release(_ id: String) { session.send("save_editor_close", params: ["workspaceId": id], operation: "host.done", announceSuccess: false) }
    private func decode<T: Decodable>(_ result: [String: Any], scope: String) -> T? {
        do { return try JSONDecoder().decode(T.self, from: JSONSerialization.data(withJSONObject: result)) }
        catch { failures[scope] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return nil }
    }
    private func perform(_ suffix: String, params: [String: Any] = [:], scope: String, workspace: String?, baseline: String? = nil,
                         blocking: Bool = true, accept: @escaping () -> Bool = { true }, failed: @escaping () -> Void = {},
                         finished: @escaping () -> Void = {}, receive: @escaping ([String: Any]) -> Void) {
        let capturedGeneration = generation; let lifecycle = session.lifecycleID
        var payload = params
        if let workspace { payload["workspaceId"] = workspace }
        if let baseline { payload["baselineGeneration"] = baseline }
        if blocking { blockingRequests += 1; busy = true }
        failures.removeValue(forKey: scope)
        session.send("save_editor_" + suffix, params: payload, operation: "hades.saveEditor.title", announceSuccess: false,
                     timeout: 30, reply: { [weak self] reply in
            guard let self, self.generation == capturedGeneration, self.session.lifecycleID == lifecycle,
                  workspace == nil || self.workspaceID == workspace,
                  baseline == nil || self.baselineGeneration == baseline, accept() else { return }
            if reply.success, let result = reply.result { receive(result) }
            else if let failure = reply.failure {
                self.failures[scope] = TrainerTextToken(key: failure.presentation, arguments: failure.presentationArguments)
                if let path = failure.recoveryPath { self.recoveryPath = path }
                failed()
            }
        }, completion: { [weak self] _ in
            guard let self else { return }
            if blocking { self.blockingRequests -= 1; self.busy = self.blockingRequests > 0 }
            if self.generation == capturedGeneration { finished() }
        })
    }
}
