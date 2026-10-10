import Foundation
import CoreFoundation
import Combine

enum Hades2SaveEditorDomain: String, CaseIterable, Identifiable {
    case overview
    case discover
    case resources
    case playerStats
    case progression
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

    init?(_ value: Any) {
        if let text = value as? String {
            self = .string(text)
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

    var id: String { entryID }
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

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.id == rhs.id
            && lhs.domain == rhs.domain
            && lhs.rawID == rhs.rawID
            && lhs.path == rhs.path
            && lhs.displayName == rhs.displayName
            && lhs.englishName == rhs.englishName
            && lhs.value == rhs.value
            && lhs.valueType == rhs.valueType
            && lhs.editable == rhs.editable
            && lhs.mutationKinds == rhs.mutationKinds
            && lhs.group == rhs.group
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

final class Hades2SaveEditorModel: ObservableObject {
    static let pageSize = 100

    @Published private(set) var profile = ""
    @Published private(set) var relativePath = ""
    @Published private(set) var availableDomains: [Hades2SaveEditorDomain] = []
    @Published private(set) var coverage: [Hades2SaveEditorCoverage] = []
    @Published var selectedDomain: Hades2SaveEditorDomain = .discover
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
    @Published private(set) var pendingChanges: [Hades2SaveEditorChange] = []
    @Published private(set) var busy = false
    @Published private(set) var failure: TrainerTextToken?

    var pendingCount: Int { pendingChanges.count }

    private let api: Hades2API
    private var language: TrainerPresentationLanguage = .zhCN
    private var pendingRequests = 0
    private var knownDisplayNames: [String: String] = [:]

    init(session: TrainerBackendSession) {
        api = Hades2API(session: session)
    }

    func open(language: TrainerPresentationLanguage) {
        self.language = language
        failure = nil
        selectedInvestigationID = nil
        investigationDetail = nil
        perform(.saveEditorOpen, operation: "hades2.saveEditor.operation.open") { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard self.applySummary(result) else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.selectedDomain = .discover
            self.query(offset: 0)
        }
    }

    func setLanguage(_ language: TrainerPresentationLanguage) {
        guard self.language != language else { return }
        self.language = language
        guard !profile.isEmpty else { return }
        query(offset: offset)
    }

    func query(offset requestedOffset: Int = 0) {
        guard !profile.isEmpty else { return }
        let boundedOffset = max(0, requestedOffset)
        let path = selectedDomain == .advanced
            ? advancedPath.map(\.jsonValue)
            : []
        let stateFilter: String
        switch selectedDomain {
        case .discover:
            stateFilter = discoveryFilter
        case .investigate:
            stateFilter = investigationFilter
        default:
            stateFilter = "all"
        }
        perform(
            .saveEditorQuery(
                domain: selectedDomain.rawValue,
                search: search,
                offset: boundedOffset,
                limit: Self.pageSize,
                path: path,
                language: language.rawValue,
                stateFilter: stateFilter
            ),
            operation: "hades2.saveEditor.operation.query",
            announceSuccess: false
        ) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard let domain = result["domain"] as? String,
                  domain == self.selectedDomain.rawValue,
                  let total = Self.intValue(result["total"]),
                  let offset = Self.intValue(result["offset"]),
                  let rows = result["items"] as? [[String: Any]]
            else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            var decoded: [Hades2SaveEditorEntry] = []
            decoded.reserveCapacity(rows.count)
            for row in rows {
                guard let entry = Self.decodeEntry(row) else {
                    self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                    return
                }
                decoded.append(entry)
            }
            self.total = total
            self.offset = offset
            self.items = decoded
            self.investigationSourceStatus = result["sourceStatus"] as? String ?? "missing"
            if self.selectedDomain == .investigate,
               let selected = decoded.first(where: { $0.rawID == self.selectedInvestigationID }) {
                self.inspect(selected)
            } else {
                self.selectedInvestigationID = nil
                self.investigationDetail = nil
            }
            for entry in decoded {
                self.knownDisplayNames[entry.id] = entry.displayName
            }
            self.failure = nil
        }
    }

    func displayName(for change: Hades2SaveEditorChange) -> String {
        change.name ?? knownDisplayNames[change.entryID] ?? change.rawID
    }

    func submitSearch() {
        selectedInvestigationID = nil
        investigationDetail = nil
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
        selectedInvestigationID = nil
        investigationDetail = nil
        query(offset: 0)
    }

    func inspect(_ entry: Hades2SaveEditorEntry) {
        guard selectedDomain == .investigate, entry.domain == "investigate" else { return }
        selectedInvestigationID = entry.rawID
        investigationDetail = nil
        perform(
            .saveEditorDetail(entryID: entry.id, language: language.rawValue),
            operation: "hades2.saveEditor.operation.detail", announceSuccess: false
        ) { [weak self] reply in
            guard let self, self.selectedInvestigationID == entry.rawID,
                  reply.success, let result = reply.result else { return }
            guard let detail = Hades2SaveInvestigationDetail(result),
                  detail.scene == entry.rawID else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.investigationDetail = detail
            self.failure = nil
        }
    }

    func selectDomain(_ domain: Hades2SaveEditorDomain) {
        guard availableDomains.contains(domain) else { return }
        selectedDomain = domain
        selectedInvestigationID = nil
        investigationDetail = nil
        discoveryFilter = "all"
        investigationFilter = "all"
        search = ""
        advancedPath = []
        query(offset: 0)
    }

    func openDiscoveryEntry(_ entry: Hades2SaveEditorEntry) {
        guard selectedDomain == .discover else { return }
        selectedInvestigationID = nil
        investigationDetail = nil
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

    func stage(entryID: String, operation: String, value: Any?) {
        perform(
            .saveEditorStage(entryID: entryID, operation: operation, value: value),
            operation: "hades2.saveEditor.operation.stage",
            announceSuccess: false
        ) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard self.applyReview(result) else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.failure = nil
        }
    }

    func review() {
        perform(
            .saveEditorReview,
            operation: "hades2.saveEditor.operation.review",
            announceSuccess: false
        ) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard self.applyReview(result) else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.failure = nil
        }
    }

    func cancel() {
        perform(
            .saveEditorCancel,
            operation: "hades2.saveEditor.operation.cancel",
            announceSuccess: false
        ) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard self.applyReview(result) else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.failure = nil
        }
    }

    func apply() {
        guard !pendingChanges.isEmpty else { return }
        let appliedOffset = offset
        perform(
            .saveEditorApply,
            operation: "hades2.saveEditor.operation.apply"
        ) { [weak self] reply in
            guard let self, reply.success, let result = reply.result else { return }
            guard result["applied"] as? Bool == true else {
                self.failure = TrainerTextToken(key: "hades2.saveEditor.error.invalidResponse")
                return
            }
            self.pendingChanges = []
            self.failure = nil
            self.query(offset: appliedOffset)
        }
    }

    private func applySummary(_ result: [String: Any]) -> Bool {
        guard let profile = result["profile"] as? String,
              let relativePath = result["relativePath"] as? String,
              let rawDomains = result["domains"] as? [String]
        else { return false }
        self.profile = profile
        self.relativePath = relativePath
        availableDomains = rawDomains.compactMap(Hades2SaveEditorDomain.init(rawValue:))

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
        coverage = decodedCoverage
        return true
    }

    private func applyReview(_ result: [String: Any]) -> Bool {
        guard let count = Self.intValue(result["count"]),
              let rows = result["changes"] as? [[String: Any]],
              count == rows.count
        else { return false }

        var changes: [Hades2SaveEditorChange] = []
        changes.reserveCapacity(rows.count)
        for row in rows {
            guard let entryID = row["id"] as? String,
                  let domain = row["domain"] as? String,
                  let rawID = row["rawId"] as? String,
                  let operation = row["operation"] as? String
            else { return false }
            changes.append(
                Hades2SaveEditorChange(
                    entryID: entryID,
                    domain: domain,
                    rawID: rawID,
                    operation: operation,
                    name: row["name"] as? String,
                    before: Self.hashableScalar(row["before"]),
                    after: Self.hashableScalar(row["after"])
                )
            )
        }
        pendingChanges = changes
        return true
    }

    private func perform(
        _ request: Hades2Request,
        operation: String,
        announceSuccess: Bool = true,
        reply: @escaping (BackendReply) -> Void
    ) {
        pendingRequests += 1
        busy = true
        api.request(
            request,
            operation: operation,
            announceSuccess: announceSuccess,
            reply: { [weak self] backendReply in
                if !backendReply.success, let backendFailure = backendReply.failure {
                    self?.failure = TrainerTextToken(
                        key: backendFailure.presentation,
                        arguments: backendFailure.presentationArguments
                    )
                }
                reply(backendReply)
            },
            completion: { [weak self] _ in
                guard let self else { return }
                self.pendingRequests = max(0, self.pendingRequests - 1)
                self.busy = self.pendingRequests > 0
            }
        )
    }

    private static func decodeEntry(_ row: [String: Any]) -> Hades2SaveEditorEntry? {
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
            discoveryReasonCode: row["reasonCode"] as? String,
            discoveryReason: row["reason"] as? String
        )
    }

    private static func hashableScalar(_ value: Any?) -> AnyHashable? {
        guard let value, !(value is NSNull) else { return nil }
        if let text = value as? String { return AnyHashable(text) }
        guard let number = value as? NSNumber else { return nil }
        if CFGetTypeID(number) == CFBooleanGetTypeID() {
            return AnyHashable(number.boolValue)
        }
        if let integer = value as? Int { return AnyHashable(integer) }
        let scalar = number.doubleValue
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
