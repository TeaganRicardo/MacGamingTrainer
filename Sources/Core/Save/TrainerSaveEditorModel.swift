import Combine
import CoreFoundation
import Foundation
import SwiftUI

package enum TrainerSaveEditorJSONValue: Equatable, Decodable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([TrainerSaveEditorJSONValue])
    case object([String: TrainerSaveEditorJSONValue])

    package init?(any raw: Any?) {
        guard let raw else {
            self = .null
            return
        }
        if raw is NSNull {
            self = .null
            return
        }
        if let text = raw as? String {
            self = .string(text)
            return
        }
        if let number = raw as? NSNumber {
            if CFGetTypeID(number) == CFBooleanGetTypeID() {
                self = .bool(number.boolValue)
                return
            }
            let type = String(cString: number.objCType)
            if type != "f", type != "d", let integer = Int(exactly: number) {
                self = .int(integer)
                return
            }
            let scalar = number.doubleValue
            guard scalar.isFinite else { return nil }
            self = .double(scalar)
            return
        }
        if let items = raw as? [Any] {
            var decoded: [TrainerSaveEditorJSONValue] = []
            decoded.reserveCapacity(items.count)
            for item in items {
                guard let value = TrainerSaveEditorJSONValue(any: item) else { return nil }
                decoded.append(value)
            }
            self = .array(decoded)
            return
        }
        if let fields = raw as? [String: Any] {
            var decoded: [String: TrainerSaveEditorJSONValue] = [:]
            decoded.reserveCapacity(fields.count)
            for (key, item) in fields {
                guard let value = TrainerSaveEditorJSONValue(any: item) else { return nil }
                decoded[key] = value
            }
            self = .object(decoded)
            return
        }
        return nil
    }

    package init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
            return
        }
        if let boolValue = try? container.decode(Bool.self) {
            self = .bool(boolValue)
            return
        }
        if let intValue = try? container.decode(Int.self) {
            self = .int(intValue)
            return
        }
        if let doubleValue = try? container.decode(Double.self) {
            guard doubleValue.isFinite else {
                throw DecodingError.dataCorruptedError(in: container, debugDescription: "Non-finite number")
            }
            self = .double(doubleValue)
            return
        }
        if let stringValue = try? container.decode(String.self) {
            self = .string(stringValue)
            return
        }
        if let arrayValue = try? container.decode([TrainerSaveEditorJSONValue].self) {
            self = .array(arrayValue)
            return
        }
        if let objectValue = try? container.decode([String: TrainerSaveEditorJSONValue].self) {
            self = .object(objectValue)
            return
        }
        throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
    }

    package var anyObject: Any {
        switch self {
        case .null:
            return NSNull()
        case .bool(let value):
            return value
        case .int(let value):
            return value
        case .double(let value):
            return value
        case .string(let value):
            return value
        case .array(let items):
            return items.map(\.anyObject)
        case .object(let fields):
            return fields.mapValues(\.anyObject)
        }
    }

    package var scalarText: String? {
        switch self {
        case .int(let value):
            return String(value)
        case .double(let value):
            return TrainerJSONNumericInput.numberText(value)
        case .string(let value):
            return value
        default:
            return nil
        }
    }

    package var jsonText: String {
        TrainerJSONNumericInput.jsonText(from: anyObject)
    }

    package static func parseJSON(_ text: String) -> TrainerSaveEditorJSONValue? {
        guard TrainerJSONNumericInput.jsonObject(from: text) != nil,
              let raw = try? TrainerJSON.object(with: Data(text.utf8)) else { return nil }
        return TrainerSaveEditorJSONValue(any: raw)
    }
}

package struct TrainerSaveEditorFileIdentity: Decodable, Equatable {
    package let rootId: String
    package let relativePath: String
    package var id: String { rootId + "/" + relativePath }
    package var dictionary: [String: String] { ["rootId": rootId, "relativePath": relativePath] }
}

package struct TrainerSaveEditorFile: Decodable, Identifiable, Equatable {
    package let rootId: String
    package let relativePath: String
    package let label: String?
    package let profile: String?
    package let variant: String?

    package var id: String { rootId + "/" + relativePath }
    package var identity: [String: String] { ["rootId": rootId, "relativePath": relativePath] }
    package var displayLabel: String {
        if let label, !label.isEmpty { return label }
        if let profile, !profile.isEmpty { return profile + " · " + id }
        return id
    }
}

package struct TrainerSaveEditorSource: Decodable, Equatable {
    package let kind: String
    package let snapshotId: String?
    package let rootId: String
    package let relativePath: String
    package var id: String { rootId + "/" + relativePath }
}

package struct TrainerSaveEditorDomain: Decodable, Identifiable, Equatable, Hashable {
    package let id: String
    package let title: String
    package let icon: String?
}

package struct TrainerSaveEditorChoice: Decodable, Equatable {
    package let value: TrainerSaveEditorJSONValue
    package let name: String
}

package struct TrainerSaveEditorConstraints: Decodable, Equatable {
    package let min: Double?
    package let max: Double?
}

package struct TrainerSaveEditorRow: Decodable, Identifiable, Equatable {
    package let id: String
    package let baselineGeneration: String
    package let domain: String
    package let name: String
    package let englishName: String
    package let group: String
    package let groupId: String
    package let owner: String
    package let ownerId: String
    package let valueType: String
    package let value: TrainerSaveEditorJSONValue?
    package let displayValue: String
    package let editable: Bool
    package let operations: [String]
    package let choices: [TrainerSaveEditorChoice]
    package let constraints: TrainerSaveEditorConstraints?
    package let warning: String?
}

package struct TrainerSaveEditorReview: Decodable, Equatable {
    package struct Effect: Decodable, Identifiable, Equatable {
        package let id: String
        package let name: String
        package let before: String
        package let after: String
    }

    package struct Action: Decodable, Identifiable, Equatable {
        package let id: String
        package let name: String
        package let before: String
        package let after: String
        package let operation: String
        package let valueType: String
        package let value: TrainerSaveEditorJSONValue?
        package let effects: [Effect]
    }

    package let baselineGeneration: String
    package let actions: [Action]
    package let count: Int
    package let effectCount: Int

    package static let empty = Self(baselineGeneration: "", actions: [], count: 0, effectCount: 0)
}

package struct TrainerSaveEditorReceipt: Decodable, Equatable {
    package let baselineGeneration: String
    package let applied: Bool
    package let verified: Bool
    package let installedSHA256: String
    package let hot: Bool?
    package let runtimeReloaded: Bool?
    package let previousSnapshotId: String?
    package let target: TrainerSaveEditorFileIdentity
    package let maintenanceWarning: String?
    package let namingWarning: String?
}

/// Turnkey Core Save Editor model backed by `CatalogSaveWorkspace` on the Python backend
/// and `TrainerStructuredSaveEditorClient` for workspace, baseline, and recovery safety.
@MainActor
package final class TrainerSaveEditorModel: ObservableObject {
    private struct InventoryPayload: Decodable {
        let sources: [TrainerSaveEditorFile]
        let targets: [TrainerSaveEditorFile]
        let defaultSource: TrainerSaveEditorFileIdentity?
    }

    private struct SummaryPayload: Decodable {
        let workspaceId: String
        let baselineGeneration: String
        let source: TrainerSaveEditorSource
        let sourceSHA256: String
        let target: TrainerSaveEditorFileIdentity?
        let domains: [TrainerSaveEditorDomain]
        let recoveryPath: String?
        let recoveryPaths: [String]?
        let recoveryUnresolved: Bool?
        let review: TrainerSaveEditorReview
    }

    private struct QueryPayload: Decodable {
        let baselineGeneration: String
        let domain: String?
        let domains: [TrainerSaveEditorDomain]?
        let rows: [TrainerSaveEditorRow]
        let total: Int
        let offset: Int
        let limit: Int
        let nextOffset: Int?
    }

    private struct DetailPayload: Decodable {
        let row: TrainerSaveEditorRow
    }

    private struct PageScope: Equatable {
        let domainID: String?
        let language: String
        let search: String
    }

    @Published package private(set) var sources: [TrainerSaveEditorFile] = []
    @Published package private(set) var targets: [TrainerSaveEditorFile] = []
    @Published package var selectedSourceID = ""
    @Published package private(set) var selectedTargetID = ""
    @Published package private(set) var source: TrainerSaveEditorSource?
    @Published package private(set) var sourceSHA256 = ""
    @Published package private(set) var domains: [TrainerSaveEditorDomain] = []
    @Published package private(set) var selectedDomainID: String?
    @Published package var search = ""
    @Published package private(set) var rows: [TrainerSaveEditorRow] = []
    @Published package private(set) var total = 0
    @Published package private(set) var offset = 0
    @Published package private(set) var pageLimit = TrainerSaveEditorModel.pageSize
    @Published package private(set) var nextOffset = 0
    @Published package private(set) var review = TrainerSaveEditorReview.empty
    @Published package private(set) var queryLoading = false
    @Published package private(set) var applying = false
    @Published package private(set) var recoveryUnresolved = false
    @Published private var readyGeneration: String?
    @Published private var activeEdits: Set<String> = []
    @Published private var failedDrafts: Set<String> = []
    @Published package private(set) var failures: [String: TrainerTextToken] = [:]
    @Published package private(set) var receipt: TrainerSaveEditorReceipt?
    @Published package private(set) var editingRow: TrainerSaveEditorRow?
    @Published package private(set) var editRevision = 0

    package let client: TrainerStructuredSaveEditorClient
    package let snapshotID: String?
    package var pageSize: Int = TrainerSaveEditorModel.pageSize
    package static let pageSize = 40

    package var workspaceID: String? { client.workspaceID }
    package var baselineGeneration: String? { client.baselineGeneration }
    package var busy: Bool { client.busy }
    package var recoveryPath: String? { client.recoveryPath }
    package var hasWorkspaceLock: Bool { client.hasWorkspaceLock }

    package var selectedDomain: TrainerSaveEditorDomain? {
        guard let selectedDomainID else { return domains.first }
        return domains.first(where: { $0.id == selectedDomainID }) ?? domains.first
    }

    private var language: TrainerPresentationLanguage = .en
    private var acceptedPageScope: PageScope?
    private var currentPageScope: PageScope {
        PageScope(domainID: selectedDomainID, language: language.rawValue, search: search)
    }
    private var pageHistory: [Int] = []
    private var searchTask: DispatchWorkItem?
    private var started = false
    private var clientObserver: AnyCancellable?

    package init(session: TrainerBackendSession, snapshotID: String? = nil) {
        client = TrainerStructuredSaveEditorClient(session: session)
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

    package static func makeWindow(
        session: TrainerBackendSession,
        snapshotID: String? = nil,
        titleKey: String = "host.saveEditor.title"
    ) -> TrainerToolWindowContent {
        let model = TrainerSaveEditorModel(session: session, snapshotID: snapshotID)
        return TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) {
            TrainerSaveEditorView(model: model, titleKey: titleKey)
        }
    }

    package var canEditRows: Bool {
        client.documentCurrent
            && readyGeneration == baselineGeneration
            && !applying
            && recoveryPath == nil
            && !recoveryUnresolved
    }

    package var canApply: Bool {
        canEditRows
            && !hasWorkspaceLock
            && !busy
            && activeEdits.isEmpty
            && failedDrafts.isEmpty
            && !selectedTargetID.isEmpty
            && review.count > 0
            && review.baselineGeneration == baselineGeneration
    }

    package func canEdit(_ row: TrainerSaveEditorRow) -> Bool {
        row.editable
            && canEditRows
            && row.baselineGeneration == baselineGeneration
            && client.canEditEntry(row.id, baseline: row.baselineGeneration)
    }

    package func hasFailedDraft(_ row: TrainerSaveEditorRow) -> Bool {
        failedDrafts.contains(draftKey(row.id, row.baselineGeneration))
    }

    private func draftKey(_ id: String, _ baseline: String) -> String {
        baseline + ":" + id
    }

    package func editingChanged(_ id: String, baseline: String, active: Bool) {
        let key = draftKey(id, baseline)
        if active {
            guard baseline == baselineGeneration, canEditRows else { return }
            activeEdits.insert(key)
        } else {
            activeEdits.remove(key)
        }
    }

    private func ownsMutation(_ workspace: String?, _ baseline: String?) -> Bool {
        client.owns(workspaceID: workspace, baseline: baseline) && canEditRows
    }

    private func stale(_ scope: String) {
        failures[scope] = TrainerTextToken(key: "host.saveEditor.staleBaseline")
    }

    package func open(language: TrainerPresentationLanguage) {
        self.language = language
        guard !started else { return }
        started = true
        refreshInventory(openDefault: true)
    }

    package func refreshInventory(openDefault: Bool = false) {
        let params: [String: Any] = snapshotID.map { ["snapshotId": $0] } ?? [:]
        perform(
            "inventory",
            params: params,
            scope: "inventory",
            bindsWorkspace: false,
            lane: .inventory
        ) { [weak self] result in
            guard let self,
                  let inventory: InventoryPayload = TrainerStructuredSaveEditorClient.decode(InventoryPayload.self, from: result)
            else {
                self?.failures["inventory"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            self.sources = inventory.sources
            self.targets = inventory.targets
            if openDefault, self.workspaceID == nil,
               let selected = inventory.defaultSource ?? inventory.sources.first.map({
                   TrainerSaveEditorFileIdentity(rootId: $0.rootId, relativePath: $0.relativePath)
               }) {
                self.selectedSourceID = selected.id
                DispatchQueue.main.async { [weak self] in self?.openSelection() }
            }
        }
    }

    package func openSelection() {
        guard !busy, !applying,
              let file = sources.first(where: { $0.id == selectedSourceID }) else { return }
        var params: [String: Any] = [
            "source": file.identity,
            "language": language.rawValue,
        ]
        if let snapshotID { params["snapshotId"] = snapshotID }
        if snapshotID == nil,
           let target = targets.first(where: { $0.id == (selectedTargetID.isEmpty ? file.id : selectedTargetID) }) {
            params["target"] = target.identity
        } else if snapshotID != nil,
                  let target = targets.first(where: { $0.id == selectedTargetID }) {
            params["target"] = target.identity
        }
        let previousWorkspace = client.workspaceID
        let previousGeneration = client.documentBackendGeneration
        searchTask?.cancel()
        queryLoading = false
        perform(
            "open",
            params: params,
            scope: "open",
            bindsWorkspace: false,
            timeout: 35.0,
            isOpenCommand: true
        ) { [weak self] result in
            guard let self else { return }
            guard let summary: SummaryPayload = TrainerStructuredSaveEditorClient.decode(SummaryPayload.self, from: result),
                  summary.review.baselineGeneration == summary.baselineGeneration else {
                if let abandoned = result["workspaceId"] as? String, abandoned != self.workspaceID {
                    self.client.releaseWorkspace(abandoned)
                }
                self.failures["open"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            self.client.bind(workspaceID: summary.workspaceId, baselineGeneration: summary.baselineGeneration)
            self.readyGeneration = nil
            self.source = summary.source
            self.sourceSHA256 = summary.sourceSHA256
            self.selectedSourceID = summary.source.id
            self.selectedTargetID = summary.target?.id ?? ""
            self.domains = summary.domains
            self.selectedDomainID = summary.domains.first?.id
            self.review = summary.review
            self.rows = []
            self.total = 0
            self.offset = 0
            self.nextOffset = 0
            self.pageHistory = []
            self.acceptedPageScope = nil
            self.search = ""
            self.editingRow = nil
            self.recoveryUnresolved = summary.recoveryUnresolved ?? false
            self.client.clearRecoveryPath()
            if let recovered = summary.recoveryPath ?? summary.recoveryPaths?.first {
                self.client.recordRecoveryPath(recovered)
            }
            self.failures = [:]
            self.editRevision += 1
            self.activeEdits = []
            self.failedDrafts = []
            self.receipt = nil
            self.client.releasePreviousWorkspace(previousWorkspace, capturedGeneration: previousGeneration)
            self.query()
        }
    }

    package func selectTarget(_ id: String, baseline: String?) {
        guard !busy, ownsMutation(workspaceID, baseline), let target = targets.first(where: { $0.id == id }) else {
            return
        }
        perform(
            "target",
            params: ["target": target.identity, "language": language.rawValue],
            scope: "target",
            sendBaseline: true,
            explicitBaseline: baseline
        ) { [weak self] result in
            guard let self else { return }
            guard let summary: SummaryPayload = TrainerStructuredSaveEditorClient.decode(SummaryPayload.self, from: result),
                  summary.baselineGeneration == baseline else {
                self.failures["target"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            self.client.bind(workspaceID: summary.workspaceId, baselineGeneration: summary.baselineGeneration)
            self.selectedTargetID = summary.target?.id ?? ""
            self.domains = summary.domains
            self.queryLoading = false
        }
    }

    package func selectDomain(_ domainID: String) {
        guard selectedDomainID != domainID else { return }
        selectedDomainID = domainID
        query()
    }

    package func setLanguage(_ value: TrainerPresentationLanguage) {
        guard language != value else { return }
        language = value
        guard workspaceID != nil else { return }
        query(offset: offset)
        refreshReview()
    }

    package func searchChanged() {
        searchTask?.cancel()
        client.invalidate(.query)
        let task = DispatchWorkItem { [weak self] in self?.query() }
        searchTask = task
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2, execute: task)
    }

    private var canPage: Bool {
        !busy && !applying && !queryLoading
            && workspaceID != nil && baselineGeneration != nil && readyGeneration == baselineGeneration
            && acceptedPageScope == currentPageScope
    }

    package var canPreviousPage: Bool { canPage && offset > 0 }
    package var canNextPage: Bool { canPage && !rows.isEmpty && nextOffset < total }

    package func nextPage() {
        guard canNextPage else { return }
        query(offset: nextOffset, historyOnSuccess: pageHistory + [offset])
    }

    package func previousPage() {
        guard canPreviousPage else { return }
        query(
            offset: pageHistory.last ?? max(0, offset - pageSize),
            historyOnSuccess: Array(pageHistory.dropLast())
        )
    }

    package func query(offset requestedOffset: Int = 0, historyOnSuccess: [Int]? = nil) {
        guard !applying, workspaceID != nil, let baseline = baselineGeneration else { return }
        let scope = currentPageScope
        let sameScope = acceptedPageScope == scope
        let pageOffset = sameScope ? requestedOffset : 0
        let acceptedHistory = sameScope ? (historyOnSuccess ?? (pageOffset == 0 ? [] : pageHistory)) : []
        searchTask?.cancel()
        var params: [String: Any] = [
            "language": language.rawValue,
            "query": search,
            "offset": pageOffset,
            "limit": pageSize,
        ]
        if let domainID = scope.domainID {
            params["domain"] = domainID
        }
        queryLoading = true
        perform(
            "query",
            params: params,
            scope: "query",
            lock: .none,
            lane: .query,
            onFinished: { [weak self] in self?.queryLoading = false }
        ) { [weak self] result in
            guard let self else { return }
            guard let payload: QueryPayload = TrainerStructuredSaveEditorClient.decode(QueryPayload.self, from: result) else {
                self.failures["query"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            guard self.currentPageScope == scope,
                  payload.baselineGeneration == baseline,
                  payload.rows.allSatisfy({ $0.baselineGeneration == baseline }) else {
                self.failures["query"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            if let updatedDomains = payload.domains, !updatedDomains.isEmpty {
                self.domains = updatedDomains
            }
            self.rows = payload.rows
            self.total = payload.total
            self.offset = payload.offset
            self.pageLimit = payload.limit
            self.nextOffset = payload.nextOffset ?? (payload.offset + payload.rows.count)
            self.pageHistory = payload.offset == pageOffset ? acceptedHistory : []
            self.readyGeneration = baseline
            self.acceptedPageScope = self.currentPageScope
        }
    }

    package func detail(_ id: String, baseline: String? = nil) {
        let capturedBaseline = baseline ?? baselineGeneration
        guard canEditRows, capturedBaseline == baselineGeneration, workspaceID != nil else { return }
        perform(
            "detail",
            params: ["entryId": id, "language": language.rawValue],
            scope: "detail",
            lane: .detail
        ) { [weak self] result in
            guard let self,
                  let detail: DetailPayload = TrainerStructuredSaveEditorClient.decode(DetailPayload.self, from: result),
                  detail.row.baselineGeneration == capturedBaseline else {
                self?.failures["detail"] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                return
            }
            self.editingRow = detail.row
        }
    }

    package func dismissDetail() {
        client.invalidate(.detail)
        editingRow = nil
    }

    package func discardDraft(_ row: TrainerSaveEditorRow, workspace captured: String?) {
        if captured == workspaceID, row.baselineGeneration == baselineGeneration {
            failedDrafts.remove(draftKey(row.id, row.baselineGeneration))
            activeEdits.remove(draftKey(row.id, row.baselineGeneration))
            failures.removeValue(forKey: row.id)
            editRevision += 1
        }
        if editingRow?.id == row.id && editingRow?.baselineGeneration == row.baselineGeneration {
            dismissDetail()
        }
    }

    package func commitText(_ row: TrainerSaveEditorRow, text: String, workspace captured: String?) -> String {
        guard ownsMutation(captured, row.baselineGeneration) else {
            stale(row.id)
            return text
        }
        let wireValue: Any
        let canonicalText: String
        switch row.valueType {
        case "integer":
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let integer = Int(trimmed) else {
                invalid(row)
                return text
            }
            if let min = row.constraints?.min, Double(integer) < min {
                invalid(row)
                return text
            }
            if let max = row.constraints?.max, Double(integer) > max {
                invalid(row)
                return text
            }
            wireValue = integer
            canonicalText = String(integer)
        case "number":
            guard let number = TrainerJSONNumericInput.number(text), number.isFinite else {
                invalid(row)
                return text
            }
            if let min = row.constraints?.min, number < min {
                invalid(row)
                return text
            }
            if let max = row.constraints?.max, number > max {
                invalid(row)
                return text
            }
            wireValue = number
            canonicalText = TrainerJSONNumericInput.numberText(number)
        case "string":
            wireValue = text
            canonicalText = text
        default:
            invalid(row)
            return text
        }
        stage(row.id, operation: "set", value: wireValue, workspace: captured, baseline: row.baselineGeneration)
        return canonicalText
    }

    @discardableResult
    package func commitJSON(
        _ row: TrainerSaveEditorRow,
        text: String,
        workspace captured: String?,
        accepted: @escaping (Bool) -> Void = { _ in }
    ) -> Bool {
        guard ownsMutation(captured, row.baselineGeneration) else {
            stale(row.id)
            return false
        }
        guard let parsed = TrainerSaveEditorJSONValue.parseJSON(text) else {
            invalid(row)
            return false
        }
        stage(
            row.id,
            operation: "set",
            value: parsed.anyObject,
            workspace: captured,
            baseline: row.baselineGeneration,
            accepted: accepted
        )
        return true
    }

    package func stage(
        _ id: String,
        operation: String,
        value: Any? = nil,
        workspace captured: String?,
        baseline: String,
        accepted: @escaping (Bool) -> Void = { _ in }
    ) {
        guard ownsMutation(captured, baseline) else {
            stale(id)
            accepted(false)
            return
        }
        var params: [String: Any] = [
            "entryId": id,
            "operation": operation,
            "language": language.rawValue,
        ]
        if let value { params["value"] = value }
        perform(
            "stage",
            params: params,
            scope: id,
            explicitWorkspaceID: captured,
            sendBaseline: true,
            explicitBaseline: baseline,
            lock: .entry(id),
            invalidatesReview: true,
            onFailed: { [weak self] in
                guard let self else { return }
                self.failedDrafts.insert(self.draftKey(id, baseline))
                accepted(false)
            }
        ) { [weak self] result in
            guard let self else { return }
            guard self.applyReview(result, scope: id) else {
                self.failedDrafts.insert(self.draftKey(id, baseline))
                accepted(false)
                return
            }
            self.failedDrafts.remove(self.draftKey(id, baseline))
            self.editRevision += 1
            self.query(offset: self.offset)
            accepted(true)
        }
    }

    package func unstage(
        _ id: String,
        baseline: String,
        accepted: @escaping (Bool) -> Void = { _ in }
    ) {
        guard ownsMutation(workspaceID, baseline) else { return }
        perform(
            "unstage",
            params: ["entryId": id, "language": language.rawValue],
            scope: id,
            sendBaseline: true,
            explicitBaseline: baseline,
            lock: .entry(id),
            invalidatesReview: true,
            onFailed: { accepted(false) }
        ) { [weak self] result in
            guard let self else { return }
            guard self.applyReview(result, scope: id) else {
                accepted(false)
                return
            }
            self.failedDrafts.remove(self.draftKey(id, baseline))
            self.editRevision += 1
            self.query(offset: self.offset)
            accepted(true)
        }
    }

    package func cancel(baseline: String?) {
        guard !busy, ownsMutation(workspaceID, baseline) else { return }
        perform(
            "cancel",
            params: ["language": language.rawValue],
            scope: "cancel",
            sendBaseline: true,
            explicitBaseline: baseline,
            invalidatesReview: true
        ) { [weak self] result in
            guard let self, self.applyReview(result, scope: "cancel") else { return }
            self.failedDrafts = []
            self.editRevision += 1
            self.query(offset: self.offset)
        }
    }

    package func refreshReview() {
        guard !applying, workspaceID != nil, baselineGeneration != nil else { return }
        perform(
            "review",
            params: ["language": language.rawValue],
            scope: "review",
            lock: .none,
            lane: .review
        ) { [weak self] result in
            _ = self?.applyReview(result, scope: "review")
        }
    }

    package func apply(baseline: String?) {
        guard canApply, baseline == baselineGeneration, let workspaceID else { return }
        applying = true
        readyGeneration = nil
        receipt = nil
        searchTask?.cancel()
        client.invalidate(.query)
        client.invalidate(.detail)
        queryLoading = false
        perform(
            "apply",
            scope: "apply",
            sendBaseline: true,
            explicitBaseline: baseline,
            isApplyCommand: true,
            invalidatesReview: true,
            onFailed: { [weak self] in self?.readyGeneration = baseline },
            onFinished: { [weak self] in self?.applying = false }
        ) { [weak self] result in
            guard let self else { return }
            guard let receipt: TrainerSaveEditorReceipt = TrainerStructuredSaveEditorClient.decode(TrainerSaveEditorReceipt.self, from: result),
                  receipt.applied,
                  receipt.verified,
                  receipt.baselineGeneration != baseline else {
                self.applyUnconfirmed()
                return
            }
            self.client.bind(workspaceID: workspaceID, baselineGeneration: receipt.baselineGeneration)
            self.receipt = receipt
            self.applying = false
            self.review = TrainerSaveEditorReview(
                baselineGeneration: receipt.baselineGeneration,
                actions: [],
                count: 0,
                effectCount: 0
            )
            self.editRevision += 1
            self.editingRow = nil
            self.pageHistory = []
            self.query()
        }
    }

    package func close() {
        searchTask?.cancel()
        queryLoading = false
        applying = false
        readyGeneration = nil
        editingRow = nil
        client.retireAndClose()
    }

    private func applyUnconfirmed() {
        client.invalidateDocument()
        readyGeneration = nil
        applying = false
        failures["apply"] = TrainerTextToken(key: "host.save.error.applyUnconfirmed")
    }

    private func invalid(_ row: TrainerSaveEditorRow) {
        failedDrafts.insert(draftKey(row.id, row.baselineGeneration))
        failures[row.id] = TrainerTextToken(key: "host.saveEditor.invalidValue")
    }

    private func applyReview(_ result: [String: Any], scope: String) -> Bool {
        guard let decoded: TrainerSaveEditorReview = TrainerStructuredSaveEditorClient.decode(TrainerSaveEditorReview.self, from: result),
              decoded.baselineGeneration == baselineGeneration else {
            failures[scope] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
            return false
        }
        review = decoded
        return true
    }

    private func perform(
        _ suffix: String,
        params: [String: Any] = [:],
        scope: String,
        bindsWorkspace: Bool = true,
        explicitWorkspaceID: String? = nil,
        sendBaseline: Bool = false,
        explicitBaseline: String? = nil,
        timeout: TimeInterval = 30.0,
        lock: TrainerStructuredSaveEditorClient.LockKind = .workspace,
        lane: TrainerSaveEditorReplyCoordinator.Lane? = nil,
        isOpenCommand: Bool = false,
        isApplyCommand: Bool = false,
        invalidatesReview: Bool = false,
        onFailed: @escaping () -> Void = {},
        onFinished: @escaping () -> Void = {},
        receive: @escaping ([String: Any]) -> Void
    ) {
        failures.removeValue(forKey: scope)
        client.send(
            "save_editor_" + suffix,
            params: params,
            operation: "host.saveEditor.title",
            announceSuccess: false,
            timeout: timeout,
            requiresTrustedTarget: false,
            bindsWorkspace: bindsWorkspace,
            explicitWorkspaceID: explicitWorkspaceID,
            sendBaseline: sendBaseline,
            explicitBaseline: explicitBaseline,
            lock: lock,
            lane: lane,
            isOpenCommand: isOpenCommand,
            isApplyCommand: isApplyCommand,
            invalidatesReview: invalidatesReview,
            onExpired: { [weak self] in
                self?.failures["workspace"] = TrainerTextToken(key: "host.save.error.workspaceExpired")
                onFinished()
            },
            onReply: { [weak self] reply in
                guard let self else { return }
                if reply.success, let result = reply.result {
                    receive(result)
                } else if let failure = reply.failure {
                    if !failure.presentation.isEmpty {
                        self.failures[scope] = TrainerTextToken(
                            key: failure.presentation,
                            arguments: failure.presentationArguments
                        )
                    } else {
                        self.failures[scope] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                    }
                    if failure.code == "rollback_failed" {
                        self.recoveryUnresolved = true
                    }
                    onFailed()
                } else {
                    self.failures[scope] = TrainerTextToken(key: "host.saveEditor.invalidResponse")
                    onFailed()
                }
            },
            onTransportFailure: { [weak self] transport in
                guard let self else { return }
                self.failures[scope] = transport.token
                if isApplyCommand, transport.outcomeUnknown {
                    self.readyGeneration = nil
                    self.applying = false
                } else {
                    onFailed()
                }
            },
            onCompletion: { accepted in
                if accepted {
                    onFinished()
                }
            }
        )
    }
}
