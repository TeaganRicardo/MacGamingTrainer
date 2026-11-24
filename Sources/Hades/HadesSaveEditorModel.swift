import Foundation
import CoreFoundation
import Combine
import TrainerCore

// The wire representation preserves Lua types, physical table occurrences and
// byte strings. Display text is never used as an edit or identity.
indirect enum HadesSaveValue: Decodable, Equatable {
    struct Entry: Decodable, Equatable { let key: HadesSaveValue; let value: HadesSaveValue }
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
    var object: [String: Any] {
        switch self {
        case .null: return ["luaType": "nil"]
        case .boolean(let value): return ["luaType": "boolean", "value": value]
        case .number(let value):
            if value == 0 && value.sign == .minus {
                return HadesSaveValue.rawNumber("0000000000000080").object
            }
            return ["luaType": "number", "value": value]
        case .string(let value): return ["luaType": "string", "value": value]
        case .rawString(let value):
            return ["luaType": "string", "encoding": "base64", "value": value]
        case .rawNumber(let value):
            return ["luaType": "number", "encoding": "ieee754", "value": value]
        case .table(let arraySize, let hashSize, let entries):
            return ["luaType": "table", "arraySize": arraySize, "hashSize": hashSize,
                    "entries": entries.map { ["key": $0.key.object, "value": $0.value.object] }]
        }
    }
    var json: String { TrainerJSONNumericInput.jsonText(from: object) }
    static func inputJSON(_ text: String) -> HadesSaveValue? {
        guard let object = TrainerJSONNumericInput.jsonObject(from: text) as? [String: Any] else { return nil }
        func decode(_ object: [String: Any]) -> HadesSaveValue? {
            if let encoding = object["encoding"], !(encoding is NSNull), !(encoding is String) { return nil }
            let encoding = object["encoding"] as? String
            switch object["luaType"] as? String {
            case "nil": return encoding == nil ? .null : nil
            case "boolean":
                guard encoding == nil, let number = object["value"] as? NSNumber,
                      CFGetTypeID(number) == CFBooleanGetTypeID() else { return nil }
                return .boolean(number.boolValue)
            case "number", "string":
                if object["luaType"] as? String == "string" {
                    guard encoding == nil || encoding == "base64", let text = object["value"] as? String else { return nil }
                    return encoding == "base64" ? .rawString(text) : .string(text)
                }
                if encoding == "ieee754" {
                    guard let text = object["value"] as? String else { return nil }
                    return .rawNumber(text)
                }
                guard encoding == nil, let number = object["value"] as? NSNumber,
                      CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
                return .number(number.doubleValue)
            case "table":
                func integer(_ field: String) -> Int? {
                    guard let number = object[field] as? NSNumber,
                          CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
                    return Int(exactly: number.doubleValue)
                }
                guard encoding == nil, let arraySize = integer("arraySize"), let hashSize = integer("hashSize"),
                      let rows = object["entries"] as? [[String: Any]] else { return nil }
                var entries: [Entry] = []
                for row in rows {
                    guard row.count == 2, let keyObject = row["key"] as? [String: Any], let key = decode(keyObject),
                          let valueObject = row["value"] as? [String: Any], let value = decode(valueObject) else { return nil }
                    entries.append(Entry(key: key, value: value))
                }
                return .table(arraySize: arraySize, hashSize: hashSize, entries: entries)
            default: return nil
            }
        }
        return decode(object)
    }
    var scalarText: String? {
        switch self {
        case .number(let value):
            return TrainerJSONNumericInput.numberText(value)
        case .string(let value): return value
        default: return nil
        }
    }
}

enum HadesSaveEditorDomain: String, CaseIterable, Identifiable, Decodable {
    case resources, progression, equipment, relationships, narrative, statistics, history, advanced
    var id: String { rawValue }
    var titleKey: String { "hades.saveEditor.domain." + rawValue }

    var sectionIcon: String {
        switch self {
        case .resources: return TrainerSemanticIcon.Section.inventory
        case .progression: return "rectangle.stack.fill"
        case .equipment: return "bolt.shield.fill"
        case .relationships: return "person.2.fill"
        case .narrative: return "text.book.closed.fill"
        case .statistics: return "chart.bar.fill"
        case .history: return TrainerSemanticIcon.Tool.saveHistory
        case .advanced: return TrainerSemanticIcon.Tool.profiles
        }
    }
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
    let maintenanceWarning: String?
    let namingWarning: String?
}
struct HadesSaveFileIdentity: Decodable {
    let rootId: String
    let relativePath: String
    var id: String { rootId + "/" + relativePath }
}

@MainActor
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

    @Published private(set) var sources: [HadesSaveFile] = []
    @Published private(set) var targets: [HadesSaveFile] = []
    @Published var selectedSourceID = ""
    @Published private(set) var selectedTargetID = ""
    @Published private(set) var source: HadesSaveEditorSource?
    @Published private(set) var sourceSHA256 = ""
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
    @Published private(set) var applying = false
    @Published private(set) var queryLoading = false
    @Published private var readyGeneration: String?
    @Published private var activeEdits: Set<String> = []
    @Published private var failedDrafts: Set<String> = []
    @Published private(set) var failures: [String: TrainerTextToken] = [:]
    @Published private(set) var receipt: HadesSaveEditorReceipt?
    @Published private(set) var editingRow: HadesSaveEditorRow?
    @Published private(set) var editingTyped = false
    @Published private(set) var editRevision = 0
    let snapshotID: String?
    static let pageSize = 40
    private let client: TrainerStructuredSaveEditorClient
    private var clientObserver: AnyCancellable?
    private var language: TrainerPresentationLanguage = .en
    var workspaceID: String? { client.workspaceID }
    var baselineGeneration: String? { client.baselineGeneration }
    var busy: Bool { client.busy }
    var recoveryPath: String? { client.recoveryPath }
    private struct PageScope: Equatable {
        let domain: String
        let language: String
        let search: String
        let parentID: String?
    }
    private var acceptedPageScope: PageScope?
    private var currentPageScope: PageScope {
        PageScope(domain: domain.rawValue, language: language.rawValue, search: search, parentID: parentID)
    }
    private var pageHistory: [Int] = []
    private var typedEntries: Set<String> = []
    private var searchTask: DispatchWorkItem?
    private var started = false

    init(session: TrainerBackendSession, snapshotID: String? = nil) {
        client = TrainerStructuredSaveEditorClient(
            session: session,
            closeCommand: HadesCommand.saveEditorClose.rawValue,
            closeTimeout: HadesCommand.saveEditorClose.timeout
        )
        self.snapshotID = snapshotID
        clientObserver = client.objectWillChange.sink { [weak self] _ in
            self?.objectWillChange.send()
        }
        client.onLifecycleExpired = { [weak self] in
            guard let self else { return }
            self.searchTask?.cancel()
            self.queryLoading = false
            self.applying = false
            self.readyGeneration = nil
            self.failures["workspace"] = TrainerTextToken(key: "host.save.error.workspaceExpired")
        }
    }
    var canEditRows: Bool {
        client.documentCurrent && readyGeneration == baselineGeneration && !applying && recoveryPath == nil
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
        client.owns(workspaceID: workspace, baseline: baseline) && canEditRows
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
        perform("inventory", params: snapshotID.map { ["snapshotId": $0] } ?? [:], scope: "inventory",
                workspace: nil, lane: .inventory) { [weak self] result in
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
        let oldWorkspace = client.workspaceID
        let oldGeneration = client.documentBackendGeneration
        searchTask?.cancel(); queryLoading = false
        perform("open", params: params, scope: "open", workspace: nil) { [weak self] result in
            guard let self else { return }
            guard let summary: Summary = self.decode(result, scope: "open"),
                  summary.review.baselineGeneration == summary.baselineGeneration else {
                if let abandoned = result["workspaceId"] as? String,
                   abandoned != self.workspaceID { self.client.releaseWorkspace(abandoned) }
                return
            }
            self.client.bind(workspaceID: summary.workspaceId, baselineGeneration: summary.baselineGeneration)
            self.readyGeneration = nil
            self.source = summary.source; self.sourceSHA256 = summary.sourceSHA256
            self.selectedSourceID = summary.source.id; self.selectedTargetID = summary.target?.id ?? ""
            self.domains = summary.domains; self.review = summary.review; self.rows = []; self.breadcrumbs = []; self.parentID = nil
            self.domain = summary.domains.first ?? .resources; self.search = ""; self.editingRow = nil
            self.client.clearRecoveryPath(); self.failures = [:]; self.editRevision += 1; self.typedEntries = []
            self.activeEdits = []; self.failedDrafts = []; self.receipt = nil
            self.client.releasePreviousWorkspace(oldWorkspace, capturedGeneration: oldGeneration)
            self.query()
        }
    }
    func selectTarget(_ id: String, baseline: String?) {
        guard !busy, ownsMutation(workspaceID, baseline), let workspaceID,
              let target = targets.first(where: { $0.id == id }) else { return }
        perform("target", params: ["target": target.identity], scope: "target", workspace: workspaceID, baseline: baseline) { [weak self] result in
            guard let self, let summary: Summary = self.decode(result, scope: "target"), summary.baselineGeneration == baseline else { return }
            self.client.bind(workspaceID: workspaceID, baselineGeneration: summary.baselineGeneration)
            self.selectedTargetID = summary.target?.id ?? ""
            self.queryLoading = false
        }
    }
    func selectDomain(_ selected: HadesSaveEditorDomain) { domain = selected; parentID = nil; breadcrumbs = []; query() }
    func browse(_ id: String?, baseline: String? = nil) {
        guard !applying, baseline == nil || baseline == baselineGeneration else { return }
        parentID = id; query()
    }
    func setLanguage(_ value: TrainerPresentationLanguage) { language = value; query(); refreshReview() }
    func searchChanged() {
        searchTask?.cancel(); client.invalidate(.query)
        let task = DispatchWorkItem { [weak self] in self?.query() }
        searchTask = task; DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: task)
    }
    /// Paging is a document operation: reject while a write or another query owns the view.
    private var canPage: Bool {
        !busy && !applying && !queryLoading
            && workspaceID != nil && baselineGeneration != nil && readyGeneration == baselineGeneration
            && acceptedPageScope == currentPageScope
    }
    var canPreviousPage: Bool { canPage && offset > 0 }
    var canNextPage: Bool { canPage && pageLimit > 0 && offset + pageLimit < total }

    func nextPage() {
        guard canNextPage else { return }
        query(offset: offset + pageLimit, historyOnSuccess: pageHistory + [offset])
    }
    func previousPage() {
        guard canPreviousPage else { return }
        query(offset: pageHistory.last ?? max(0, offset - pageLimit),
              historyOnSuccess: Array(pageHistory.dropLast()))
    }
    func query(offset requestedOffset: Int = 0, historyOnSuccess: [Int]? = nil) {
        guard !applying, let workspaceID, let baseline = baselineGeneration else { return }
        // Only the accepted result's search/domain/path can supply page navigation.
        // A new scope starts at page zero even if a refresh races the search debounce.
        let scope = currentPageScope
        let sameScope = acceptedPageScope == scope
        let pageOffset = sameScope ? requestedOffset : 0
        let acceptedHistory = sameScope
            ? (historyOnSuccess ?? (pageOffset == 0 ? [] : pageHistory)) : []
        // A rejected, cancelled or stale query must not alter Back navigation.
        searchTask?.cancel()
        var params: [String: Any] = ["domain": domain.rawValue, "language": language.rawValue,
            "query": search, "offset": pageOffset, "limit": Self.pageSize]
        if let parentID { params["parentId"] = parentID }
        queryLoading = true
        perform("query", params: params, scope: "query", workspace: workspaceID, blocking: false,
                lane: .query,
                finished: { [weak self] in self?.queryLoading = false }) { [weak self] result in
            guard let self, let query: Query = self.decode(result, scope: "query") else { return }
            guard self.currentPageScope == scope, query.baselineGeneration == baseline,
                  query.rows.allSatisfy({ $0.baselineGeneration == baseline }) else {
                self.failures["query"] = TrainerTextToken(key: "hades.saveEditor.invalidResponse"); return
            }
            self.rows = query.rows; self.total = query.total; self.offset = query.offset; self.pageLimit = query.limit
            // A server-rebased offset invalidates the originally requested Back path.
            self.pageHistory = query.offset == pageOffset && query.parentId == scope.parentID ? acceptedHistory : []
            self.breadcrumbs = query.breadcrumbs; self.parentID = query.parentId; self.readyGeneration = baseline
            self.acceptedPageScope = self.currentPageScope
        }
    }
    func detail(_ id: String, typed: Bool = false, baseline: String? = nil) {
        let capturedBaseline = baseline ?? baselineGeneration
        guard canEditRows, capturedBaseline == baselineGeneration, let workspaceID else { return }
        let forceTyped = typed || typedEntries.contains(id)
        perform("detail", params: ["entryId": id, "language": language.rawValue], scope: "detail", workspace: workspaceID,
                lane: .detail) { [weak self] result in
            guard let self, let detail: Detail = self.decode(result, scope: "detail"), detail.row.baselineGeneration == capturedBaseline else { return }
            self.editingTyped = forceTyped; self.editingRow = detail.row
        }
    }
    func dismissDetail() { client.invalidate(.detail); editingRow = nil; editingTyped = false }
    func discardDraft(_ row: HadesSaveEditorRow, workspace captured: String?) {
        if captured == workspaceID, row.baselineGeneration == baselineGeneration {
            failedDrafts.remove(draftKey(row.id, row.baselineGeneration))
            activeEdits.remove(draftKey(row.id, row.baselineGeneration))
            activeEdits.remove(draftKey(row.id + ":key", row.baselineGeneration))
            failures.removeValue(forKey: row.id)
            editRevision += 1
        }
        if editingRow?.id == row.id && editingRow?.baselineGeneration == row.baselineGeneration {
            dismissDetail()
        }
    }
    func commit(_ row: HadesSaveEditorRow, text: String, workspace captured: String?) -> String {
        guard ownsMutation(captured, row.baselineGeneration) else { stale(row.id); return text }
        let value: HadesSaveValue
        let staged = review.actions.first { $0.id == row.id && $0.operation == "set" }?.typedValue
        switch staged ?? row.typedValue {
        case .some(.number):
            guard let number = TrainerJSONNumericInput.number(text) else { invalid(row); return text }; value = .number(number)
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
        guard let value = HadesSaveValue.inputJSON(text) else { invalid(row); return false }
        var object = value.object
        if let appendKey {
            guard let key = HadesSaveValue.inputJSON(appendKey) else { invalid(row); return false }
            object = ["key": key.object, "value": object]
        }
        stage(row.id, operation: appendKey == nil ? "set" : "append", value: object, workspace: captured,
              baseline: row.baselineGeneration, typed: true, accepted: accepted)
        return true
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
        guard !applying, let workspaceID, baselineGeneration != nil else { return }
        perform("review", params: ["language": language.rawValue], scope: "review", workspace: workspaceID,
                blocking: false, lane: .review) { [weak self] result in
            _ = self?.applyReview(result, scope: "review")
        }
    }
    func apply(baseline: String?) {
        guard canApply, baseline == baselineGeneration, let workspaceID else { return }
        applying = true; readyGeneration = nil; receipt = nil; searchTask?.cancel()
        client.invalidate(.query); client.invalidate(.detail)
        queryLoading = false
        perform("apply", scope: "apply", workspace: workspaceID, baseline: baseline,
                failed: { [weak self] in self?.readyGeneration = baseline },
                finished: { [weak self] in self?.applying = false }) { [weak self] result in
            guard let self else { return }
            guard let receipt: HadesSaveEditorReceipt = self.decode(result, scope: "apply") else {
                self.applyUnconfirmed(); return
            }
            guard receipt.applied, receipt.verified, receipt.baselineGeneration != baseline else {
                self.applyUnconfirmed(); return
            }
            self.client.bind(workspaceID: workspaceID, baselineGeneration: receipt.baselineGeneration)
            self.receipt = receipt; self.applying = false
            self.review = .init(baselineGeneration: receipt.baselineGeneration, actions: [], count: 0, effectCount: 0)
            self.typedEntries = []; self.editRevision += 1; self.editingRow = nil
            self.parentID = nil; self.breadcrumbs = []; self.query()
        }
    }
    private func applyUnconfirmed() {
        client.invalidateDocument(); readyGeneration = nil; applying = false
        failures["apply"] = TrainerTextToken(key: "host.save.error.applyUnconfirmed")
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
        searchTask?.cancel(); started = false; queryLoading = false
        readyGeneration = nil; editingRow = nil
        client.retireAndClose()
    }
    private func decode<T: Decodable>(_ result: [String: Any], scope: String) -> T? {
        guard let decoded = TrainerStructuredSaveEditorClient.decode(T.self, from: result) else {
            failures[scope] = TrainerTextToken(key: "hades.saveEditor.invalidResponse")
            return nil
        }
        return decoded
    }
    private func perform(_ suffix: String, params: [String: Any] = [:], scope: String, workspace: String?, baseline: String? = nil,
                         blocking: Bool = true, lane: TrainerSaveEditorReplyCoordinator.Lane? = nil,
                         failed: @escaping () -> Void = {}, finished: @escaping () -> Void = {},
                         receive: @escaping ([String: Any]) -> Void) {
        failures.removeValue(forKey: scope)
        guard let command = HadesCommand(rawValue: "save_editor_" + suffix) else {
            preconditionFailure("Unknown Hades Save Editor command: \(suffix)")
        }
        client.send(
            command.rawValue,
            params: params,
            operation: "hades.saveEditor.title",
            announceSuccess: false,
            timeout: command.timeout,
            requiresTrustedTarget: command.requiresTrustedTarget(connected: false),
            bindsWorkspace: workspace != nil,
            explicitWorkspaceID: workspace,
            sendBaseline: baseline != nil,
            explicitBaseline: baseline,
            lock: blocking ? .workspace : .none,
            lane: lane,
            isOpenCommand: suffix == "open",
            isApplyCommand: suffix == "apply",
            invalidatesReview: ["stage", "unstage", "cancel", "apply"].contains(suffix),
            onExpired: { [weak self] in
                self?.failures["workspace"] = TrainerTextToken(key: "host.save.error.workspaceExpired")
                finished()
            },
            onReply: { [weak self] reply in
                guard let self else { return }
                if reply.success, let result = reply.result {
                    receive(result)
                } else if let failure = reply.failure {
                    self.failures[scope] = TrainerTextToken(key: failure.presentation, arguments: failure.presentationArguments)
                    failed()
                }
            },
            onTransportFailure: { [weak self] transport in
                guard let self else { return }
                self.failures[scope] = transport.token
                if suffix == "apply", transport.outcomeUnknown {
                    self.readyGeneration = nil
                    self.applying = false
                } else {
                    failed()
                }
            },
            onCompletion: { accepted in
                if accepted { finished() }
            }
        )
    }
}
