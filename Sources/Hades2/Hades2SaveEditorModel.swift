import Foundation
import CoreFoundation
import Combine

enum Hades2SaveEditorDomain: String, CaseIterable, Identifiable {
    case entities
    case overview
    case discover
    case resources
    case playerStats
    case progression
    case quests
    case arcana
    case investigate
    case dialogue
    case flags
    case relationships
    case weapons
    case advanced

    var id: String { rawValue }
}

enum Hades2SaveEditorPathComponent: Hashable {
    case string(String)
    case integer(Int)
    case number(Double)
    case boolean(Bool)
    case typed(Hades2SaveTypedValue)
    case saveContainer(String)

    init?(_ value: Any) {
        if let text = value as? String {
            self = .string(text)
            return
        }
        if let object = value as? [String: Any], object["saveContainer"] != nil {
            guard object.count == 1, let name = object["saveContainer"] as? String,
                  ["header", "payload", "main"].contains(name) else { return nil }
            self = .saveContainer(name)
            return
        }
        if let object = value as? [String: Any],
           let typed = Hades2SaveTypedValue(object),
           typed.kind == "string" || (typed.kind == "number" && object["encoding"] as? String == "nonfinite"
               && ["inf", "-inf"].contains(object["value"] as? String ?? "")) {
            self = .typed(typed)
            return
        }
        guard let number = value as? NSNumber else { return nil }
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            self = .boolean(number.boolValue)
        } else if let integer = value as? Int {
            self = .integer(integer)
        } else {
            let scalar = number.doubleValue
            guard scalar.isFinite else { return nil }
            if scalar.rounded() == scalar, scalar >= Double(Int.min),
               scalar < Double(Int.max) {
                self = .integer(Int(scalar))
            } else {
                self = .number(scalar)
            }
        }
    }

    var jsonValue: Any {
        switch self {
        case .string(let value): return value
        case .integer(let value): return value
        case .number(let value): return value
        case .boolean(let value): return value
        case .typed(let value): return value.object
        case .saveContainer(let name): return ["saveContainer": name]
        }
    }
}

struct Hades2SaveEditorConstraints: Equatable {
    let minimum: Double?
    let maximum: Double?
    let integer: Bool
}

struct Hades2SaveEditorCoverage: Identifiable, Equatable {
    let id: String
    let discoverability: String
    let understanding: String
    let write: String
    let reasonCode: String
}

struct Hades2SaveEditorChange: Identifiable, Equatable {
    let entryID: String
    let domain: String
    let rawID: String
    let operation: String
    let name: String?
    let before: AnyHashable?
    let after: AnyHashable?
    let beforeDisplay: String?
    let afterDisplay: String?

    var id: String { entryID }
}

struct Hades2SaveEditorAction: Identifiable, Equatable {
    let entryID: String
    let entityID: String
    let entityName: String
    let domain: String
    let rawID: String
    let name: String
    let englishName: String
    let operation: String
    let before: AnyHashable?
    let after: AnyHashable?
    let valueType: String
    let mutationKinds: [String]
    let constraints: Hades2SaveEditorConstraints?
    let choices: [String]
    let choiceNames: [String: String]
    let effects: [Hades2SaveEditorChange]
    var baselineGeneration = ""
    var typedBefore: Hades2SaveTypedValue? = nil
    var typedAfter: Hades2SaveTypedValue? = nil
    var beforePresent = true
    var afterPresent = true
    var hostName: String? = nil
    var content: [String] = []

    var id: String { entryID }

    var editorEntry: Hades2SaveEditorEntry {
        Hades2SaveEditorEntry(
            id: entryID,
            domain: domain,
            rawID: rawID,
            path: [],
            displayName: name,
            englishName: englishName,
            value: before,
            valueType: valueType,
            editable: true,
            mutationKinds: mutationKinds,
            group: nil,
            entityID: entityID,
            entityName: entityName,
            choices: choices,
            choiceNames: choiceNames,
            constraints: constraints,
            childCount: nil,
            pathAmbiguous: false,
            investigationStatus: nil,
            investigationSnippet: nil,
            investigationSourceStatus: nil,
            investigationReason: nil,
            discoveryState: nil,
            discoveryReasonCode: nil,
            discoveryReason: nil,
            typedValue: typedAfter ?? typedBefore,
            baselineGeneration: baselineGeneration
        )
    }
}

struct Hades2SaveEditorApplyReceipt: Equatable {
    let source: String
    let target: String
    let hot: Bool
    let runtimeReloaded: Bool
    let previousSnapshotID: String
    let fileCount: Int
}

struct Hades2SaveEditorEntry: Identifiable, Equatable {
    let id: String
    let domain: String
    let rawID: String
    let path: [Hades2SaveEditorPathComponent]
    let displayName: String
    let englishName: String
    let value: AnyHashable?
    let valueType: String
    let editable: Bool
    let mutationKinds: [String]
    let group: String?
    let entityID: String?
    let entityName: String?
    let choices: [String]
    let choiceNames: [String: String]
    let constraints: Hades2SaveEditorConstraints?
    let childCount: Int?
    let pathAmbiguous: Bool
    let investigationStatus: String?
    let investigationSnippet: String?
    let investigationSourceStatus: String?
    let investigationReason: String?
    let discoveryState: String?
    let discoveryReasonCode: String?
    let discoveryReason: String?
    var typedValue: Hades2SaveTypedValue? = nil
    var warning: String? = nil
    var content: [String] = []
    var hostID: String? = nil
    var hostName: String? = nil
    var baselineGeneration = ""

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.id == rhs.id
            && lhs.baselineGeneration == rhs.baselineGeneration
            && lhs.domain == rhs.domain
            && lhs.rawID == rhs.rawID
            && lhs.path == rhs.path
            && lhs.displayName == rhs.displayName
            && lhs.englishName == rhs.englishName
            && lhs.content == rhs.content
            && lhs.hostID == rhs.hostID
            && lhs.hostName == rhs.hostName
            && lhs.value == rhs.value
            && lhs.valueType == rhs.valueType
            && lhs.editable == rhs.editable
            && lhs.mutationKinds == rhs.mutationKinds
            && lhs.group == rhs.group
            && lhs.entityID == rhs.entityID
            && lhs.entityName == rhs.entityName
            && lhs.choices == rhs.choices
            && lhs.choiceNames == rhs.choiceNames
            && lhs.constraints == rhs.constraints
            && lhs.childCount == rhs.childCount
            && lhs.pathAmbiguous == rhs.pathAmbiguous
            && lhs.investigationStatus == rhs.investigationStatus
            && lhs.investigationSnippet == rhs.investigationSnippet
            && lhs.investigationSourceStatus == rhs.investigationSourceStatus
            && lhs.investigationReason == rhs.investigationReason
            && lhs.discoveryState == rhs.discoveryState
            && lhs.discoveryReasonCode == rhs.discoveryReasonCode
            && lhs.discoveryReason == rhs.discoveryReason
            && lhs.typedValue == rhs.typedValue
            && lhs.warning == rhs.warning
    }
}

struct Hades2NarrativeCondition: Identifiable {
    let id = UUID()
    let kind: String
    let label: String
    let evidence: String
    let observation: String?
    let children: [Hades2NarrativeCondition]

    init?(_ raw: [String: Any]) {
        guard let kind = raw["kind"] as? String,
              let label = raw["text"] as? String,
              let evidence = raw["evidence"] as? String,
              let nested = raw["children"] as? [[String: Any]] else { return nil }
        var parsed: [Hades2NarrativeCondition] = []
        for child in nested {
            guard let item = Hades2NarrativeCondition(child) else { return nil }
            parsed.append(item)
        }
        self.kind = kind
        self.label = label
        self.evidence = evidence
        observation = raw["observation"] as? String
        children = parsed
    }
}

struct Hades2NarrativeRequirements: Identifiable {
    let id = UUID()
    let line: Int
    let tree: Hades2NarrativeCondition

    init?(_ raw: [String: Any]) {
        guard let line = Hades2SaveInvestigationDetail.number(raw["line"]),
              let source = raw["tree"] as? [String: Any],
              let tree = Hades2NarrativeCondition(source) else { return nil }
        self.line = line
        self.tree = tree
    }
}

struct Hades2NarrativeSource: Identifiable {
    let id: String
    let file: String
    let line: Int
    let partner: Bool
    let requirements: [Hades2NarrativeRequirements]

    init?(_ raw: [String: Any]) {
        guard let file = raw["file"] as? String,
              let line = Hades2SaveInvestigationDetail.number(raw["line"]),
              let partner = raw["partner"] as? Bool,
              let requirements = raw["requirements"] as? [[String: Any]] else { return nil }
        var parsed: [Hades2NarrativeRequirements] = []
        for req in requirements {
            guard let item = Hades2NarrativeRequirements(req) else { return nil }
            parsed.append(item)
        }
        self.file = file
        self.line = line
        self.partner = partner
        self.requirements = parsed
        id = "\(file):\(line)"
    }
}

struct Hades2NarrativeLine: Identifiable {
    let id = UUID()
    let cueID: String
    let english: [String]
    let chinese: [String]
    let speaker: String
    let events: [String]

    init?(_ raw: [String: Any]) {
        guard let cueID = raw["cueId"] as? String,
              let english = raw["en"] as? [String],
              let chinese = raw["zhCN"] as? [String],
              let speaker = raw["speaker"] as? String,
              let events = raw["events"] as? [String] else { return nil }
        self.cueID = cueID
        self.english = english
        self.chinese = chinese
        self.speaker = speaker
        self.events = events
    }
}

struct Hades2SaveInvestigationDetail {
    let scene: String
    let status: String
    let sourceStatus: String
    let reason: String
    let blockReasonCode: String?
    let canStage: Bool
    let stageID: String
    let definitions: [Hades2NarrativeSource]
    let lines: [Hades2NarrativeLine]
    let sourceResolution: String
    let futureEligibility: String

    static func number(_ value: Any?) -> Int? {
        guard let value = value as? NSNumber,
              CFGetTypeID(value) != CFBooleanGetTypeID() else { return nil }
        return value.intValue
    }

    init?(_ raw: [String: Any]) {
        guard let scene = raw["scene"] as? String,
              let status = raw["status"] as? String,
              let sourceStatus = raw["sourceStatus"] as? String,
              let reason = raw["reason"] as? String,
              let canStage = raw["canStage"] as? Bool,
              let stageID = raw["stageID"] as? String,
              let sourceResolution = raw["sourceResolution"] as? String,
              let futureEligibility = raw["futureEligibility"] as? String,
              let sources = raw["definitions"] as? [[String: Any]],
              let cueLines = raw["lines"] as? [[String: Any]] else { return nil }
        var parsedSources: [Hades2NarrativeSource] = []
        var parsedLines: [Hades2NarrativeLine] = []
        for source in sources {
            guard let item = Hades2NarrativeSource(source) else { return nil }
            parsedSources.append(item)
        }
        for line in cueLines {
            guard let item = Hades2NarrativeLine(line) else { return nil }
            parsedLines.append(item)
        }
        self.scene = scene
        self.status = status
        self.sourceStatus = sourceStatus
        self.reason = reason
        blockReasonCode = raw["blockReasonCode"] as? String
        self.canStage = canStage
        self.stageID = stageID
        self.sourceResolution = sourceResolution
        self.futureEligibility = futureEligibility
        definitions = parsedSources
        lines = parsedLines
    }
}

struct Hades2SaveEditorFile: Identifiable, Equatable {
    let rootID: String
    let relativePath: String
    let profile: String
    let variant: String
    var id: String { rootID + "/" + relativePath }
    var identity: [String: String] { ["rootId": rootID, "relativePath": relativePath] }

    init?(_ row: [String: Any]) {
        guard let rootID = row["rootId"] as? String, !rootID.isEmpty,
              let relativePath = row["relativePath"] as? String, !relativePath.isEmpty,
              let profile = row["profile"] as? String,
              let variant = row["variant"] as? String else { return nil }
        self.rootID = rootID
        self.relativePath = relativePath
        self.profile = profile
        self.variant = variant
    }
}

struct Hades2SaveRetiredDraft: Identifiable {
    let id: String
    let name: String
    let text: String
}

final class Hades2SaveEditorModel: ObservableObject {
    static let pageSize = 100

    @Published private(set) var profile = ""
    @Published private(set) var relativePath = ""
    @Published private(set) var sourceFiles: [Hades2SaveEditorFile] = []
    @Published private(set) var writeTargets: [Hades2SaveEditorFile] = []
    @Published var selectedSourceID = ""
    @Published private(set) var selectedTargetID = ""
    @Published private(set) var sourceRelativePath = ""
    @Published private(set) var sourceRootID = ""
    @Published private(set) var sourceSHA256 = ""
    @Published private(set) var hasWriteTarget = false
    let snapshotID: String?
    @Published private(set) var workspaceID: String?
    @Published private(set) var baselineGeneration: String?
    private var selectedTargetIdentity: [String: String]?
    @Published private(set) var availableDomains: [Hades2SaveEditorDomain] = []
    @Published private(set) var coverage: [Hades2SaveEditorCoverage] = []
    @Published var selectedDomain: Hades2SaveEditorDomain = .entities
    @Published private(set) var selectedScope = "all"
    @Published private(set) var entityResults: [Hades2SaveEditorEntity] = []
    @Published private(set) var querying = false
    @Published private(set) var queryFailure: TrainerTextToken?
    @Published private(set) var detailFailure: TrainerTextToken?
    @Published var search = ""
    @Published private(set) var offset = 0
    @Published private(set) var total = 0
    @Published private(set) var items: [Hades2SaveEditorEntry] = []
    @Published private(set) var advancedPath: [Hades2SaveEditorPathComponent] = []
    @Published private(set) var discoveryFilter = "all"
    @Published private(set) var investigationFilter = "all"
    @Published private(set) var selectedInvestigationID: String?
    @Published private(set) var investigationDetail: Hades2SaveInvestigationDetail?
    @Published private(set) var investigationSourceStatus = "missing"
    @Published private(set) var pendingActions: [Hades2SaveEditorAction] = []
    @Published private(set) var pendingEffectCount = 0
    @Published private(set) var pendingPhysicalChangeCount = 0
    @Published private(set) var editRevision = 0
    private(set) var reconciledEntryIDs: Set<String>?
    @Published private(set) var busy = false
    @Published private(set) var operationFailures: [Hades2Command: TrainerTextToken] = [:]
    @Published private(set) var editFailures: [String: TrainerTextToken] = [:]
    @Published private(set) var textDrafts: [String: String] = [:]
    private(set) var continuousDraftEntryIDs: Set<String> = []
    @Published private(set) var typedDrafts: [String: String] = [:]
    @Published private(set) var membershipDrafts: [String: Hades2SaveAdvancedMembershipDraft] = [:]
    @Published private(set) var retiredDrafts: [Hades2SaveRetiredDraft] = []
    @Published private(set) var lastApplyReceipt: Hades2SaveEditorApplyReceipt?

    var pendingCount: Int { pendingActions.count }

    private let api: Hades2API
    private var language: TrainerPresentationLanguage = .zhCN
    private var pendingRequests = 0
    private var knownDisplayNames: [String: String] = [:]
    private var queryGeneration = 0
    private var detailGeneration = 0
    private var lastRequestedSearch: String?
    private var scheduledSearch: DispatchWorkItem?

    init(session: TrainerBackendSession, snapshotID: String? = nil) {
        api = Hades2API(session: session)
        self.snapshotID = snapshotID
    }

    func open(language: TrainerPresentationLanguage) {
        self.language = language
        lastApplyReceipt = nil
        invalidateDetail()
        refreshFiles(openDefault: true)
    }

    func refreshFiles(openDefault: Bool = false) {
        perform(.saveEditorInventory(snapshotID: snapshotID), operation: "hades2.saveEditor.operation.open",
                announceSuccess: false) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard let sources = result["sources"] as? [[String: Any]],
                  let targets = result["targets"] as? [[String: Any]] else {
                self.operationFailures[.saveEditorInventory] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            let decodedSources = sources.compactMap(Hades2SaveEditorFile.init)
            let decodedTargets = targets.compactMap(Hades2SaveEditorFile.init)
            guard decodedSources.count == sources.count, decodedTargets.count == targets.count else {
                self.operationFailures[.saveEditorInventory] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.sourceFiles = decodedSources
            self.writeTargets = decodedTargets
            self.operationFailures.removeValue(forKey: .saveEditorInventory)
            if openDefault, self.workspaceID == nil,
               let source = result["defaultSource"] as? [String: String],
               let selected = decodedSources.first(where: { $0.identity == source }) {
                self.selectedSourceID = selected.id
                let target = decodedTargets.first(where: { $0.identity == source })
                self.selectedTargetID = target?.id ?? ""
                self.selectedTargetIdentity = target?.identity
                self.openSelection()
            }
        }
    }

    func openSelection() {
        invalidateQuery()
        invalidateDetail()
        guard let source = sourceFiles.first(where: { $0.id == selectedSourceID }) else { return }
        let previousWorkspace = workspaceID
        lastApplyReceipt = nil
        perform(.saveEditorOpenSelection(snapshotID: snapshotID, source: source.identity, target: selectedTargetIdentity),
                operation: "hades2.saveEditor.operation.open") { [weak self] reply in
            guard let self else { return }
            guard reply.success, let result = reply.result else {
                self.restoreLoadedSourceSelection()
                return
            }
            self.continuousDraftEntryIDs = []
            guard self.applySummary(result) else {
                self.operationFailures[.saveEditorOpen] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                self.restoreLoadedSourceSelection()
                return
            }
            if let previousWorkspace, previousWorkspace != self.workspaceID {
                self.releaseWorkspace(previousWorkspace)
            }
            self.pendingActions = []
            self.retiredDrafts = []
            self.operationFailures = [:]
            self.editFailures = [:]
            self.textDrafts = [:]
            self.typedDrafts = [:]
            self.membershipDrafts = [:]
            self.pendingEffectCount = 0
            self.pendingPhysicalChangeCount = 0
            self.items = []
            self.entityResults = []
            self.knownDisplayNames = [:]
            self.selectedDomain = .entities
            self.selectedScope = "all"
            self.query(offset: 0)
        }
    }

    /// Native tool windows close only when blocking document requests finish.
    /// Queries may still be in flight; invalidate their captured ownership and
    /// release this workspace without affecting any other editor.
    func close() {
        scheduledSearch?.cancel()
        scheduledSearch = nil
        invalidateQuery()
        invalidateDetail()
        if let workspaceID { releaseWorkspace(workspaceID) }
        workspaceID = nil
        baselineGeneration = nil
        continuousDraftEntryIDs = []
        retiredDrafts = []
        operationFailures = [:]
        editFailures = [:]
        textDrafts = [:]
        typedDrafts = [:]
        membershipDrafts = [:]
    }

    private func releaseWorkspace(_ identifier: String) {
        api.request(.saveEditorClose, operation: "host.done", announceSuccess: false,
                    saveWorkspaceID: identifier)
    }

    private func restoreLoadedSourceSelection() {
        selectedSourceID = sourceRelativePath.isEmpty
            ? "" : sourceRootID + "/" + sourceRelativePath
    }

    func selectTarget(_ identifier: String) {
        guard let file = writeTargets.first(where: { $0.id == identifier }), !busy else { return }
        if workspaceID == nil {
            selectedTargetID = identifier
            selectedTargetIdentity = file.identity
            return
        }
        perform(.saveEditorTarget(file.identity), operation: "hades2.saveEditor.operation.target",
                announceSuccess: false) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard self.applySummary(result) else {
                self.operationFailures[.saveEditorTarget] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.lastApplyReceipt = nil
            self.operationFailures.removeValue(forKey: .saveEditorTarget)
        }
    }

    func setLanguage(_ language: TrainerPresentationLanguage) {
        guard self.language != language else { return }
        invalidateDetail()
        self.language = language
        guard !profile.isEmpty else { return }
        query(offset: offset)
        if !pendingActions.isEmpty { review() }
    }

    private func invalidateDetail() {
        detailGeneration += 1
        selectedInvestigationID = nil
        investigationDetail = nil
        detailFailure = nil
    }

    private func invalidateQuery() {
        scheduledSearch?.cancel()
        scheduledSearch = nil
        queryGeneration += 1
        querying = false
        queryFailure = nil
    }

    /// Text changes cancel superseded lookups immediately, then coalesce work.
    /// No source reload, draft replacement or Save authority transition occurs.
    func searchChanged() {
        // Return has already submitted this term. A later SwiftUI onChange
        // must not cancel its immediate query and re-delay the lookup.
        guard lastRequestedSearch != search else { return }
        guard !profile.isEmpty, workspaceID != nil else { return }
        invalidateQuery()
        querying = true
        let work = DispatchWorkItem { [weak self] in self?.query(offset: 0) }
        scheduledSearch = work
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(280), execute: work)
    }

    func selectScope(_ scope: String) {
        guard ["all", "story", "growth", "resources", "records"].contains(scope),
              availableDomains.contains(.entities) else { return }
        selectedScope = scope
        selectedDomain = .entities
        invalidateDetail()
        advancedPath = []
        query(offset: 0)
    }

    func query(offset requestedOffset: Int = 0) {
        guard !profile.isEmpty, workspaceID != nil else { return }
        scheduledSearch?.cancel()
        scheduledSearch = nil
        queryGeneration += 1
        let generation = queryGeneration
        let workspace = workspaceID
        let requestedDomain = selectedDomain
        let requestedScope = selectedScope
        let requestedSearch = search
        lastRequestedSearch = requestedSearch
        let requestedLanguage = language
        let boundedOffset = max(0, requestedOffset)
        let path = requestedDomain == .advanced
            ? advancedPath.map(\.jsonValue)
            : []
        let stateFilter: String
        switch requestedDomain {
        case .discover:
            stateFilter = discoveryFilter
        case .investigate:
            stateFilter = investigationFilter
        default:
            stateFilter = "all"
        }
        querying = true
        queryFailure = nil
        perform(
            .saveEditorQuery(
                domain: requestedDomain.rawValue,
                scope: requestedScope,
                search: requestedSearch,
                offset: boundedOffset,
                limit: Self.pageSize,
                path: path,
                language: requestedLanguage.rawValue,
                stateFilter: stateFilter
            ),
            operation: "hades2.saveEditor.operation.query",
            announceSuccess: false,
            occupy: false,
            presentFailure: false
        ) { [weak self] reply in
            guard let self, self.queryGeneration == generation,
                  self.workspaceID == workspace,
                  self.selectedDomain == requestedDomain,
                  self.selectedScope == requestedScope,
                  self.search == requestedSearch,
                  self.language == requestedLanguage else { return }
            self.querying = false
            guard reply.success, let result = reply.result else {
                if let error = reply.failure {
                    self.queryFailure = TrainerTextToken(
                        key: error.presentation,
                        arguments: error.presentationArguments
                    )
                } else {
                    self.queryFailure = TrainerTextToken(
                        key: "hades2.saveEditor.error.invalidResponse"
                    )
                }
                return
            }
            guard let domain = result["domain"] as? String,
                  domain == requestedDomain.rawValue,
                  result["baselineGeneration"] as? String == self.baselineGeneration,
                  let total = Self.intValue(result["total"]),
                  let offset = Self.intValue(result["offset"]), offset == boundedOffset
            else {
                self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            var decoded: [Hades2SaveEditorEntry] = []
            var entities: [Hades2SaveEditorEntity] = []
            if requestedDomain == .entities {
                guard result["scope"] as? String == requestedScope,
                      let groups = result["entities"] as? [[String: Any]],
                      groups.count <= Self.pageSize else {
                    self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                    return
                }
                var identities = Set<String>()
                for group in groups {
                    guard let id = group["id"] as? String, !id.isEmpty,
                          let title = group["name"] as? String, !title.isEmpty,
                          let fields = group["items"] as? [[String: Any]],
                          !fields.isEmpty, identities.insert(id).inserted else {
                        self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                        return
                    }
                    let entries = fields.compactMap { Self.decodeEntry($0, baseline: self.baselineGeneration!) }
                    guard entries.count == fields.count, entries.allSatisfy({
                        ($0.entityID ?? "entry:" + $0.id) == id
                    }) else {
                        self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                        return
                    }
                    decoded.append(contentsOf: entries)
                    entities.append(Hades2SaveEditorEntity(id: id, title: title, entries: entries))
                }
            } else {
                guard let rows = result["items"] as? [[String: Any]] else {
                    self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                    return
                }
                decoded = rows.compactMap { Self.decodeEntry($0, baseline: self.baselineGeneration!) }
                guard decoded.count == rows.count else {
                    self.queryFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                    return
                }
                entities = Hades2SaveEditorEntityGrouping.entities(from: decoded)
            }
            self.total = total
            self.offset = offset
            self.items = decoded
            self.entityResults = entities
            self.investigationSourceStatus = result["sourceStatus"] as? String ?? "missing"
            if requestedDomain == .investigate,
               let selected = decoded.first(where: { $0.rawID == self.selectedInvestigationID }) {
                self.inspect(selected)
            } else {
                self.invalidateDetail()
            }
            for entry in decoded {
                self.knownDisplayNames[entry.id] = entry.displayName
            }
            self.queryFailure = nil
        }
    }

    func displayName(for change: Hades2SaveEditorChange) -> String {
        change.name ?? knownDisplayNames[change.entryID] ?? change.rawID
    }

    func submitSearch() {
        invalidateQuery()
        invalidateDetail()
        query(offset: 0)
    }

    func setDiscoveryFilter(_ value: String) {
        guard ["all", "observed", "absent", "editable", "readOnly", "ambiguous", "unsupported", "unknown"].contains(value) else { return }
        discoveryFilter = value
        query(offset: 0)
    }

    func setInvestigationFilter(_ value: String) {
        guard ["all", "recorded", "notRecorded", "ambiguous", "unknown"].contains(value) else { return }
        investigationFilter = value
        invalidateDetail()
        query(offset: 0)
    }

    func inspect(_ entry: Hades2SaveEditorEntry) {
        guard (selectedDomain == .entities || selectedDomain == .investigate
               || selectedDomain == .discover),
              entry.domain == "investigate", entry.baselineGeneration == baselineGeneration,
              let workspace = workspaceID else { return }
        detailGeneration += 1
        let generation = detailGeneration
        let requestedLanguage = language
        let scene = entry.rawID
        selectedInvestigationID = scene
        investigationDetail = nil
        detailFailure = nil
        perform(
            .saveEditorDetail(entryID: entry.id, language: requestedLanguage.rawValue),
            operation: "hades2.saveEditor.operation.detail", announceSuccess: false,
            occupy: false, presentFailure: false
        ) { [weak self] reply in
            guard let self,
                  self.detailGeneration == generation,
                  self.workspaceID == workspace,
                  self.language == requestedLanguage,
                  self.selectedInvestigationID == scene else { return }
            guard reply.success, let result = reply.result else {
                self.detailFailure = reply.failure.map {
                    TrainerTextToken(key: $0.presentation, arguments: $0.presentationArguments)
                } ?? TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            guard result["baselineGeneration"] as? String == entry.baselineGeneration,
                  let detail = Hades2SaveInvestigationDetail(result),
                  detail.scene == scene else {
                self.detailFailure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.investigationDetail = detail
            self.detailFailure = nil
        }
    }

    func selectDomain(_ domain: Hades2SaveEditorDomain) {
        guard availableDomains.contains(domain) else { return }
        if domain == .entities { selectScope("all"); return }
        selectedDomain = domain
        invalidateDetail()
        discoveryFilter = "all"
        investigationFilter = "all"
        search = ""
        advancedPath = []
        query(offset: 0)
    }

    func openDiscoveryEntry(_ entry: Hades2SaveEditorEntry) {
        guard selectedDomain == .discover else { return }
        invalidateDetail()
        discoveryFilter = "all"

        if entry.domain == Hades2SaveEditorDomain.advanced.rawValue {
            selectedDomain = .advanced
            advancedPath = Array(entry.path.dropLast())
            search = entry.rawID
            query(offset: 0)
            return
        }

        guard let domain = Hades2SaveEditorDomain(rawValue: entry.domain),
              domain != .discover else { return }
        selectedDomain = domain
        advancedPath = []
        search = entry.rawID
        if domain == .investigate {
            investigationFilter = "all"
        }
        query(offset: 0)
    }

    func enterAdvanced(_ entry: Hades2SaveEditorEntry) {
        guard selectedDomain == .advanced,
              entry.domain == Hades2SaveEditorDomain.advanced.rawValue,
              entry.childCount != nil,
              !entry.pathAmbiguous
        else { return }
        advancedPath = entry.path
        search = ""
        query(offset: 0)
    }

    func leaveAdvanced() {
        guard selectedDomain == .advanced, !advancedPath.isEmpty else { return }
        advancedPath.removeLast()
        search = ""
        query(offset: 0)
    }

    func nextPage() {
        let next = offset + Self.pageSize
        guard next < total else { return }
        query(offset: next)
    }

    func previousPage() {
        guard offset > 0 else { return }
        query(offset: max(0, offset - Self.pageSize))
    }

    func parsedTextDraft(for entry: Hades2SaveEditorEntry, text: String) -> Any? {
        if entry.valueType == "string" { return text }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if entry.valueType == "enum" { return entry.choices.contains(trimmed) ? trimmed : nil }
        guard !trimmed.isEmpty else { return nil }
        if entry.constraints?.integer == true || entry.valueType == "integer" {
            guard let value = Int(trimmed) else { return nil }
            if let minimum = entry.constraints?.minimum, Double(value) < minimum { return nil }
            if let maximum = entry.constraints?.maximum, Double(value) > maximum { return nil }
            return value
        }
        if entry.valueType == "number" {
            guard let value = TrainerJSONNumericInput.number(trimmed) else { return nil }
            if let minimum = entry.constraints?.minimum, value < minimum { return nil }
            if let maximum = entry.constraints?.maximum, value > maximum { return nil }
            return value
        }
        if entry.valueType == "boolean" {
            if trimmed == "true" { return true }
            if trimmed == "false" { return false }
            return nil
        }
        return entry.valueType == "string" ? trimmed : nil
    }

    /// Completing a Save field only stages a valid value in the open document.
    /// Invalid/busy drafts remain visible for correction; Apply stays explicit.
    func completeTextEdit(_ entry: Hades2SaveEditorEntry, text: String, changed: Bool = true) -> String {
        guard changed else { return text }
        guard owns(entry.baselineGeneration) else { return text }
        guard !busy else {
            editFailures[entry.id] = TrainerTextToken(key: "hades2.saveEditor.unavailableDraft")
            return text
        }
        guard entry.editable, !entry.mutationKinds.isEmpty,
              let value = parsedTextDraft(for: entry, text: text) else {
            editFailures[entry.id] = TrainerTextToken(key: "hades2.saveEditor.invalidDraft")
            return text
        }
        stage(entryID: entry.id, operation: entry.mutationKinds.contains("setEnum") ? "setEnum" : "set", value: value, baseline: entry.baselineGeneration)
        return text
    }

    func loadAdvancedValue(
        _ entry: Hades2SaveEditorEntry,
        language requestedLanguage: TrainerPresentationLanguage,
        completion: @escaping (Hades2SaveAdvancedDetail?, TrainerTextToken?) -> Void
    ) {
        guard entry.domain == "advanced", owns(entry.baselineGeneration), let workspace = workspaceID else { return }
        perform(.saveEditorDetail(entryID: entry.id, language: requestedLanguage.rawValue),
                operation: "hades2.saveEditor.operation.detail", announceSuccess: false,
                occupy: false, presentFailure: false) { [weak self] reply in
            guard let self, self.workspaceID == workspace else { return }
            guard reply.success, let result = reply.result,
                  result["baselineGeneration"] as? String == entry.baselineGeneration,
                  let detail = Hades2SaveAdvancedDetail(result), detail.entryID == entry.id else {
                completion(nil, reply.failure.map {
                    TrainerTextToken(key: $0.presentation, arguments: $0.presentationArguments)
                } ?? TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse"))
                return
            }
            completion(detail, nil)
        }
    }

    func completeTypedEdit(_ entry: Hades2SaveEditorEntry, text: String, changed: Bool = true) -> String {
        guard changed else { return text }
        guard owns(entry.baselineGeneration) else { return text }
        typedDrafts[entry.id] = text
        guard !busy else {
            editFailures[entry.id] = TrainerTextToken(key: "hades2.saveEditor.unavailableDraft")
            return text
        }
        guard entry.editable, entry.mutationKinds.contains("set"),
              let value = Hades2SaveTypedValue(text: text) else {
            editFailures[entry.id] = TrainerTextToken(key: "hades2.saveEditor.invalidDraft")
            return text
        }
        stage(entryID: entry.id, operation: "set", value: value.object, baseline: entry.baselineGeneration)
        return value.json
    }

    func retainMembershipDraft(_ draft: Hades2SaveAdvancedMembershipDraft, for entryID: String, baseline: String) {
        guard owns(baseline) else { return }
        membershipDrafts[entryID] = draft
    }

    func retainTextDraft(_ text: String, for entry: Hades2SaveEditorEntry) {
        guard owns(entry.baselineGeneration) else { return }
        textDrafts[entry.id] = text
    }

    func retireDrafts(_ drafts: [String: String], baseline: String?) {
        guard let baseline else { return }
        for (entryID, text) in drafts.sorted(by: { $0.key < $1.key }) {
            let id = baseline + ":" + entryID
            guard !retiredDrafts.contains(where: { $0.id.hasPrefix(id + ":") && $0.text == text }) else { continue }
            retiredDrafts.append(Hades2SaveRetiredDraft(id: id + ":" + String(retiredDrafts.count),
                name: knownDisplayNames[entryID] ?? entryID, text: text))
        }
    }

    private func reconcileEdits(_ entryIDs: Set<String>?, preservingTypedDrafts: Bool = false) {
        if let entryIDs {
            if !preservingTypedDrafts {
                for entryID in entryIDs { typedDrafts.removeValue(forKey: entryID); textDrafts.removeValue(forKey: entryID) }
            }
        } else {
            textDrafts = [:]
            typedDrafts = [:]
            membershipDrafts = [:]
        }
        reconciledEntryIDs = entryIDs
        editRevision += 1
    }

    private func owns(_ baseline: String?) -> Bool {
        workspaceID != nil && baseline != nil && baseline == baselineGeneration
    }

    func stage(entryID: String, operation: String, value: Any?, baseline: String) {
        guard owns(baseline), !busy else { return }
        lastApplyReceipt = nil
        let requestedLanguage = language
        let workspace = workspaceID
        let stagedValue: Any?
        if entryID.hasPrefix("advanced:") || entryID.hasPrefix("save-container:"),
           let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
           number.doubleValue == 0, number.doubleValue.sign == .minus {
            stagedValue = Hades2SaveTypedValue(["luaType": "number", "value": number])!.object
        } else { stagedValue = value }
        perform(
            .saveEditorStage(
                entryID: entryID,
                operation: operation,
                value: stagedValue,
                language: requestedLanguage.rawValue
            ),
            operation: "hades2.saveEditor.operation.stage",
            announceSuccess: false,
            presentFailure: false
        ) { [weak self] reply in
            guard let self, self.workspaceID == workspace else { return }
            var acknowledged = false
            // Inline controls still restore their acknowledged projection on
            // refusal; the structure editor retains its explicit typed input
            // so reopening can correct a backend-only codec/conflict error.
            defer { self.reconcileEdits([entryID], preservingTypedDrafts: !acknowledged) }
            guard reply.success, let result = reply.result else {
                self.editFailures[entryID] = reply.failure.map {
                    TrainerTextToken(key: $0.presentation, arguments: $0.presentationArguments)
                } ?? TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            guard self.applyReview(result) else {
                self.editFailures[entryID] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.editFailures.removeValue(forKey: entryID)
            acknowledged = true
            if self.language != requestedLanguage { self.review() }
        }
    }

    func unstage(entryID: String, baseline: String) {
        guard owns(baseline), !busy else { return }
        let requestedLanguage = language
        let workspace = workspaceID
        perform(
            .saveEditorUnstage(entryID: entryID, language: requestedLanguage.rawValue),
            operation: "hades2.saveEditor.operation.unstage",
            announceSuccess: false,
            presentFailure: false
        ) { [weak self] reply in
            guard let self, self.workspaceID == workspace else { return }
            guard reply.success, let result = reply.result else {
                self.editFailures[entryID] = reply.failure.map {
                    TrainerTextToken(key: $0.presentation, arguments: $0.presentationArguments)
                } ?? TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            guard self.applyReview(result) else {
                self.editFailures[entryID] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.editFailures.removeValue(forKey: entryID)
            self.reconcileEdits([entryID])
            if self.language != requestedLanguage { self.review() }
        }
    }

    func review() {
        let requestedLanguage = language
        let workspace = workspaceID
        perform(
            .saveEditorReview(language: requestedLanguage.rawValue),
            operation: "hades2.saveEditor.operation.review",
            announceSuccess: false,
            occupy: false
        ) { [weak self] reply in
            guard let self,
                  self.workspaceID == workspace,
                  self.language == requestedLanguage,
                  reply.success, let result = reply.result else { return }
            guard self.applyReview(result) else {
                self.operationFailures[.saveEditorReview] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.operationFailures.removeValue(forKey: .saveEditorReview)
        }
    }

    func cancel(baseline: String?) {
        guard owns(baseline), !busy else { return }
        let requestedLanguage = language
        let workspace = workspaceID
        perform(
            .saveEditorCancel(language: requestedLanguage.rawValue),
            operation: "hades2.saveEditor.operation.cancel",
            announceSuccess: false
        ) { [weak self] reply in
            guard let self, self.workspaceID == workspace,
                  reply.success, let result = reply.result else { return }
            guard self.applyReview(result) else {
                self.operationFailures[.saveEditorCancel] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.editFailures = [:]
            self.reconcileEdits(nil)
            self.operationFailures.removeValue(forKey: .saveEditorCancel)
        }
    }

    func apply(baseline: String?) {
        guard owns(baseline), !busy, !pendingActions.isEmpty, hasWriteTarget else { return }
        let appliedOffset = offset
        let source = sourceRootID + "/" + sourceRelativePath
        let target = selectedTargetID
        let workspace = workspaceID
        lastApplyReceipt = nil
        perform(
            .saveEditorApply,
            operation: "hades2.saveEditor.operation.apply",
            draftEntryIDs: Array(Set(textDrafts.keys).union(typedDrafts.keys).union(membershipDrafts.keys))
        ) { [weak self] reply in
            guard let self, self.workspaceID == workspace,
                  reply.success, let result = reply.result else { return }
            guard let receipt = self.decodeApplyReceipt(
                result,
                source: source,
                target: target
            ) else {
                self.operationFailures[.saveEditorApply] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            guard let nextBaseline = result["baselineGeneration"] as? String,
                  !nextBaseline.isEmpty, nextBaseline != baseline,
                  let continuousIDs = result["continuousDraftEntryIds"] as? [String] else {
                self.operationFailures[.saveEditorApply] = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.invalidateQuery()
            self.invalidateDetail()
            let continuous = Set(continuousIDs)
            self.continuousDraftEntryIDs = continuous
            self.retireDrafts(self.textDrafts.filter { !continuous.contains($0.key) }, baseline: baseline)
            self.retireDrafts(self.typedDrafts.filter { !continuous.contains($0.key) }, baseline: baseline)
            self.retireDrafts(self.membershipDrafts.filter { !continuous.contains($0.key) }
                .mapValues { $0.keyType + ": " + $0.key + "\n" + $0.value }, baseline: baseline)
            self.textDrafts = self.textDrafts.filter { continuous.contains($0.key) }
            self.typedDrafts = self.typedDrafts.filter { continuous.contains($0.key) }
            self.membershipDrafts = self.membershipDrafts.filter { continuous.contains($0.key) }
            self.baselineGeneration = nextBaseline
            self.items = []
            self.entityResults = []
            self.pendingActions = []
            self.pendingEffectCount = 0
            self.pendingPhysicalChangeCount = 0
            self.editFailures = self.editFailures.filter { continuous.contains($0.key) }
            self.lastApplyReceipt = receipt
            self.operationFailures.removeValue(forKey: .saveEditorApply)
            self.query(offset: appliedOffset)
        }
    }

    private func decodeApplyReceipt(
        _ result: [String: Any],
        source: String,
        target: String
    ) -> Hades2SaveEditorApplyReceipt? {
        guard result["applied"] as? Bool == true,
              let hot = result["hot"] as? Bool,
              let runtimeReloaded = result["runtimeReloaded"] as? Bool,
              let previousSnapshotID = result["previousSnapshotId"] as? String,
              !previousSnapshotID.isEmpty,
              let fileCount = Self.intValue(result["fileCount"]),
              fileCount > 0,
              let relativePath = result["relativePath"] as? String,
              !relativePath.isEmpty,
              relativePath == target.split(separator: "/", maxSplits: 1).last.map(String.init)
        else { return nil }
        return Hades2SaveEditorApplyReceipt(
            source: source,
            target: target,
            hot: hot,
            runtimeReloaded: runtimeReloaded,
            previousSnapshotID: previousSnapshotID,
            fileCount: fileCount
        )
    }

    private func applySummary(_ result: [String: Any]) -> Bool {
        guard let profile = result["profile"] as? String,
              let relativePath = result["relativePath"] as? String,
              let rawDomains = result["domains"] as? [String],
              let identifier = result["workspaceId"] as? String, !identifier.isEmpty,
              let baseline = result["baselineGeneration"] as? String, !baseline.isEmpty,
              let source = result["source"] as? [String: String],
              let sourceRoot = source["rootId"], let sourcePath = source["relativePath"],
              source["kind"] == (snapshotID == nil ? "currentFile" : "managedBackup"),
              source["snapshotId"] == snapshotID,
              let sourceSHA256 = result["sourceSHA256"] as? String,
              sourceSHA256.count == 64,
              sourceSHA256.allSatisfy({ "0123456789abcdef".contains($0) })
        else { return false }
        let targetID: String
        let targetSelected: Bool
        if let target = result["target"] as? [String: String],
           let root = target["rootId"], let path = target["relativePath"] {
            targetID = root + "/" + path
            targetSelected = true
        } else if result["target"] is NSNull {
            targetID = ""
            targetSelected = false
        } else { return false }

        var decodedCoverage: [Hades2SaveEditorCoverage] = []
        if let rawCoverage = result["coverage"] as? [[String: Any]] {
            for row in rawCoverage {
                guard let id = row["id"] as? String,
                      let discoverability = row["discoverability"] as? String,
                      let understanding = row["understanding"] as? String,
                      let write = row["write"] as? String,
                      let reasonCode = row["reasonCode"] as? String
                else { return false }
                decodedCoverage.append(
                    Hades2SaveEditorCoverage(
                        id: id,
                        discoverability: discoverability,
                        understanding: understanding,
                        write: write,
                        reasonCode: reasonCode
                    )
                )
            }
        }
        workspaceID = identifier
        baselineGeneration = baseline
        selectedTargetID = targetID
        selectedTargetIdentity = result["target"] as? [String: String]
        hasWriteTarget = targetSelected
        sourceRootID = sourceRoot
        sourceRelativePath = sourcePath
        self.sourceSHA256 = sourceSHA256
        self.profile = profile
        self.relativePath = relativePath
        availableDomains = rawDomains.compactMap(Hades2SaveEditorDomain.init(rawValue:))
        coverage = decodedCoverage
        return true
    }

    private func applyReview(_ result: [String: Any]) -> Bool {
        guard result["baselineGeneration"] as? String == baselineGeneration,
              let count = Self.intValue(result["count"]),
              let rows = result["changes"] as? [[String: Any]],
              let actionCount = Self.intValue(result["actionCount"]),
              let effectCount = Self.intValue(result["effectCount"]),
              let physicalChangeCount = Self.intValue(result["physicalChangeCount"]),
              let rawActions = result["actions"] as? [[String: Any]],
              count == rows.count,
              physicalChangeCount == rows.count,
              physicalChangeCount == actionCount + effectCount,
              actionCount == rawActions.count
        else { return false }

        func decodeChange(_ row: [String: Any]) -> Hades2SaveEditorChange? {
            guard let entryID = row["id"] as? String,
                  let domain = row["domain"] as? String,
                  let rawID = row["rawId"] as? String,
                  let operation = row["operation"] as? String
            else { return nil }
            return Hades2SaveEditorChange(
                entryID: entryID,
                domain: domain,
                rawID: rawID,
                operation: operation,
                name: row["name"] as? String,
                before: Self.hashableScalar(row["before"]),
                after: Self.hashableScalar(row["after"]),
                beforeDisplay: row["beforeDisplay"] as? String,
                afterDisplay: row["afterDisplay"] as? String
            )
        }

        let changes = rows.compactMap(decodeChange)
        guard changes.count == rows.count else { return false }

        var actions: [Hades2SaveEditorAction] = []
        var decodedEffectCount = 0
        for row in rawActions {
            guard let entryID = row["entryId"] as? String,
                  let identity = row["id"] as? String, identity == entryID,
                  let entityID = row["entityId"] as? String, !entityID.isEmpty,
                  let entityName = row["entityName"] as? String, !entityName.isEmpty,
                  let domain = row["domain"] as? String,
                  let rawID = row["rawId"] as? String,
                  let name = row["name"] as? String, !name.isEmpty,
                  let englishName = row["englishName"] as? String, !englishName.isEmpty,
                  let operation = row["operation"] as? String,
                  let valueType = row["valueType"] as? String,
                  let mutationKinds = row["mutationKinds"] as? [String],
                  let rawEffects = row["effects"] as? [[String: Any]]
            else { return false }

            let constraints: Hades2SaveEditorConstraints?
            if let raw = row["constraints"] as? [String: Any], !raw.isEmpty {
                constraints = Hades2SaveEditorConstraints(
                    minimum: Self.doubleValue(raw["min"]),
                    maximum: Self.doubleValue(raw["max"]),
                    integer: raw["integer"] as? Bool ?? false
                )
            } else {
                constraints = nil
            }
            let effects = rawEffects.compactMap(decodeChange)
            guard effects.count == rawEffects.count else { return false }
            decodedEffectCount += effects.count
            actions.append(Hades2SaveEditorAction(
                entryID: entryID,
                entityID: entityID,
                entityName: entityName,
                domain: domain,
                rawID: rawID,
                name: name,
                englishName: englishName,
                operation: operation,
                before: Self.hashableScalar(row["before"]),
                after: Self.hashableScalar(row["after"]),
                valueType: valueType,
                mutationKinds: mutationKinds,
                constraints: constraints,
                choices: row["choices"] as? [String] ?? [],
                choiceNames: row["choiceNames"] as? [String: String] ?? [:],
                effects: effects,
                baselineGeneration: baselineGeneration!,
                typedBefore: row["typedBefore"].flatMap(Hades2SaveTypedValue.init),
                typedAfter: row["typedAfter"].flatMap(Hades2SaveTypedValue.init),
                beforePresent: row["beforePresent"] as? Bool ?? true,
                afterPresent: row["afterPresent"] as? Bool ?? true,
                hostName: row["hostName"] as? String,
                content: row["content"] as? [String] ?? []
            ))
        }
        guard decodedEffectCount == effectCount else { return false }

        pendingActions = actions
        pendingEffectCount = effectCount
        pendingPhysicalChangeCount = physicalChangeCount
        return true
    }

    private func perform(
        _ request: Hades2Request,
        operation: String,
        announceSuccess: Bool = true,
        occupy: Bool = true,
        presentFailure: Bool = true,
        draftEntryIDs: [String]? = nil,
        reply: @escaping (BackendReply) -> Void
    ) {
        let ownsWorkspace = request.command != .saveEditorOpen && request.command != .saveEditorInventory
        let requestWorkspaceID = ownsWorkspace ? workspaceID : nil
        let requestBaseline = ownsWorkspace ? baselineGeneration : nil
        if occupy {
            pendingRequests += 1
            busy = true
        }
        api.request(
            request,
            operation: operation,
            announceSuccess: announceSuccess,
            saveWorkspaceID: requestWorkspaceID,
            saveBaselineGeneration: requestBaseline,
            saveDraftEntryIDs: draftEntryIDs,
            reply: { [weak self] backendReply in
                guard let self, !ownsWorkspace || (self.workspaceID == requestWorkspaceID
                    && self.baselineGeneration == requestBaseline) else { return }
                if presentFailure, (!ownsWorkspace || self.workspaceID == requestWorkspaceID),
                   !backendReply.success,
                   let backendFailure = backendReply.failure {
                    self.operationFailures[request.command] = TrainerTextToken(
                        key: backendFailure.presentation,
                        arguments: backendFailure.presentationArguments
                    )
                }
                reply(backendReply)
            },
            completion: { [weak self] _ in
                guard let self, occupy else { return }
                self.pendingRequests = max(0, self.pendingRequests - 1)
                self.busy = self.pendingRequests > 0
            }
        )
    }

    private static func decodeEntry(_ row: [String: Any], baseline: String) -> Hades2SaveEditorEntry? {
        guard let id = row["id"] as? String,
              let domain = row["domain"] as? String,
              let rawID = row["rawId"] as? String,
              let displayName = row["name"] as? String,
              let englishName = row["englishName"] as? String,
              let valueType = row["valueType"] as? String,
              let editable = row["editable"] as? Bool,
              let mutationKinds = row["mutationKinds"] as? [String],
              let rawPath = row["path"] as? [Any]
        else { return nil }

        let path = rawPath.compactMap(Hades2SaveEditorPathComponent.init(_:))
        guard path.count == rawPath.count else { return nil }

        let constraints: Hades2SaveEditorConstraints?
        if let raw = row["constraints"] as? [String: Any] {
            constraints = Hades2SaveEditorConstraints(
                minimum: doubleValue(raw["min"]),
                maximum: doubleValue(raw["max"]),
                integer: raw["integer"] as? Bool ?? false
            )
        } else {
            constraints = nil
        }

        return Hades2SaveEditorEntry(
            id: id,
            domain: domain,
            rawID: rawID,
            path: path,
            displayName: displayName,
            englishName: englishName,
            value: hashableScalar(row["value"]),
            valueType: valueType,
            editable: editable,
            mutationKinds: mutationKinds,
            group: row["group"] as? String,
            entityID: row["entityId"] as? String,
            entityName: row["entityName"] as? String,
            choices: row["choices"] as? [String] ?? [],
            choiceNames: row["choiceNames"] as? [String: String] ?? [:],
            constraints: constraints,
            childCount: intValue(row["childCount"]),
            pathAmbiguous: row["pathAmbiguous"] as? Bool ?? false,
            investigationStatus: row["status"] as? String,
            investigationSnippet: row["snippet"] as? String,
            investigationSourceStatus: row["sourceStatus"] as? String,
            investigationReason: row["reason"] as? String,
            discoveryState: row["state"] as? String,
            discoveryReasonCode: (row["reasonCode"] as? String) ?? (row["blockReasonCode"] as? String),
            discoveryReason: (row["readOnlyReason"] as? String)
                ?? (row["blockReasonDiagnostic"] as? String)
                ?? (row["reason"] as? String),
            typedValue: row["typedValue"].flatMap(Hades2SaveTypedValue.init),
            warning: row["warning"] as? String,
            content: row["content"] as? [String] ?? [],
            hostID: row["hostId"] as? String,
            hostName: row["hostName"] as? String,
            baselineGeneration: baseline
        )
    }

    private static func hashableScalar(_ value: Any?) -> AnyHashable? {
        guard let value, !(value is NSNull) else { return nil }
        if let text = value as? String { return AnyHashable(text) }
        guard let number = value as? NSNumber else { return nil }
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            return AnyHashable(number.boolValue)
        }
        let scalar = number.doubleValue
        if scalar == 0, scalar.sign == .minus { return AnyHashable(scalar) }
        if let integer = value as? Int { return AnyHashable(integer) }
        return scalar.isFinite ? AnyHashable(scalar) : nil
    }

    private static func intValue(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        if let integer = value as? Int { return integer }
        let scalar = number.doubleValue
        guard scalar.isFinite, scalar.rounded() == scalar,
              scalar >= Double(Int.min), scalar < Double(Int.max) else { return nil }
        return Int(scalar)
    }

    private static func doubleValue(_ value: Any?) -> Double? {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        let scalar = number.doubleValue
        return scalar.isFinite ? scalar : nil
    }
}
