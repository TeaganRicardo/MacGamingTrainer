import Foundation

/// Typed Hades Host-command caller adapter. Wire command identity and Host
/// timeout metadata are generated from the backend command contract; Hades
/// domain request shapes and JSON parameter construction stay type-safe here.
enum Hades2Request {
    case scan, status, disconnect, launch, disableAll, runtimeReset, resetDesired
    case connect(probeRuntime: Bool, recoverLostAttach: Bool)
    case setDesired(feature: String, value: Any)
    case setVital(vital: String, field: String, value: Double)
    case setCounter(counter: String, value: Double)
    case lockVital(vital: String, locked: Bool)
    case setResource(resource: String, amount: Int)
    case lockResource(resource: String, locked: Bool)
    case setRerolls(amount: Int)
    case lockRerolls(locked: Bool)
    case setGathering(family: Hades2GatheringFamily, probability: Double?)
    case setChaosGate(probability: Double?)
    case generateGathering(family: Hades2GatheringFamily, scopeToken: String)
    case matureGarden(scopeToken: String)
    case setStat(stat: String, locked: Bool, value: Any?)
    case setElement(element: String, amount: Int)
    case lockElement(element: String, locked: Bool)
    case setBoonRarity(target: String, multiplier: Double, forceLegendary: Bool, forceDuo: Bool)
    case setNextRoomReward(String?)
    case setNextOccurrence(String?)
    case spawnReward(String)
    case acquireChaosPair(blessing: String, curse: String)
    case openSellTraits
    case setTraitLevel(CurrentRunTrait, targetLevel: Int)
    case setTraitRarity(CurrentRunTrait, rarity: String)
    case setTraitRemainingUses(CurrentRunTrait, targetRemainingUses: Int)
    case expireTrait(CurrentRunTrait)
    case removeTrait(CurrentRunTrait)
    case advanceTraitLifecycle(CurrentRunTrait)
    case openSpecialChoice(source: String)
    case saveEditorOpen
    case saveEditorInventory(snapshotID: String?)
    case saveEditorOpenSelection(snapshotID: String?, source: [String: String], target: [String: String]?)
    case saveEditorTarget([String: String])
    case saveEditorQuery(domain: String, scope: String, search: String, offset: Int, limit: Int, path: [Any], language: String, stateFilter: String)
    case saveEditorDetail(entryID: String, language: String)
    case saveEditorStage(entryID: String, operation: String, value: Any?, language: String)
    case saveEditorUnstage(entryID: String, language: String)
    case saveEditorReview(language: String)
    case saveEditorCancel(language: String)
    case saveEditorApply
    case saveEditorClose
    case listProfiles
    case saveProfile(name: String, shortcuts: [String: Any])
    case loadProfile(String)
    case deleteProfile(String)
    case diagnostics, exportDiagnostics
    case prepare, restore

    var command: Hades2Command {
        switch self {
        case .scan: return .scan
        case .status: return .status
        case .connect(_, _): return .connect
        case .disconnect: return .disconnect
        case .launch: return .launch
        case .disableAll: return .disableAll
        case .runtimeReset: return .runtimeReset
        case .resetDesired: return .resetDesired
        case .setDesired: return .setDesired
        case .setVital: return .setVital
        case .setCounter: return .setCounter
        case .lockVital: return .lockVital
        case .setResource: return .setResource
        case .lockResource: return .lockResource
        case .setRerolls: return .setRerolls
        case .lockRerolls: return .lockRerolls
        case .setGathering: return .setGatheringDesired
        case .setChaosGate: return .setChaosGateDesired
        case .generateGathering: return .generateGathering
        case .matureGarden: return .matureGarden
        case .setStat: return .setStat
        case .setElement: return .setElement
        case .lockElement: return .lockElement
        case .setBoonRarity: return .setBoonRarityDesired
        case .setNextRoomReward: return .setNextRoomRewardDesired
        case .setNextOccurrence: return .setNextOccurrenceDesired
        case .spawnReward: return .spawnReward
        case .acquireChaosPair: return .acquireChaosPair
        case .openSellTraits: return .openSellTraits
        case .setTraitLevel: return .setTraitLevel
        case .setTraitRarity: return .setTraitRarity
        case .setTraitRemainingUses: return .setTraitRemainingUses
        case .expireTrait: return .expireTrait
        case .removeTrait: return .removeTrait
        case .advanceTraitLifecycle: return .advanceTraitLifecycle
        case .openSpecialChoice: return .openSpecialChoice
        case .saveEditorOpen: return .saveEditorOpen
        case .saveEditorInventory: return .saveEditorInventory
        case .saveEditorOpenSelection: return .saveEditorOpen
        case .saveEditorTarget: return .saveEditorTarget
        case .saveEditorQuery: return .saveEditorQuery
        case .saveEditorDetail: return .saveEditorDetail
        case .saveEditorStage: return .saveEditorStage
        case .saveEditorUnstage: return .saveEditorUnstage
        case .saveEditorReview: return .saveEditorReview
        case .saveEditorCancel: return .saveEditorCancel
        case .saveEditorApply: return .saveEditorApply
        case .saveEditorClose: return .saveEditorClose
        case .listProfiles: return .listProfiles
        case .saveProfile: return .saveProfile
        case .loadProfile: return .loadProfile
        case .deleteProfile: return .deleteProfile
        case .diagnostics: return .diagnostics
        case .exportDiagnostics: return .exportDiagnostics
        case .prepare: return .prepare
        case .restore: return .restore
        }
    }


    private static func traitTargetParams(_ trait: CurrentRunTrait) -> [String: Any] {
        var params: [String: Any] = [
            "generationId": trait.generationID,
            "runId": trait.runID,
            "instanceId": trait.instanceID,
            "trait": trait.name,
            "family": trait.family,
            "expectedLevel": trait.level,
            "expectedRarity": trait.rarity,
            "expectedSameNameCount": trait.sameNameCount,
        ]
        if let remainingUses = trait.remainingUses {
            params["expectedRemainingUses"] = remainingUses
        }
        return params
    }

    var params: [String: Any] {
        switch self {
        case .connect(let probeRuntime, let recoverLostAttach):
            return ["probeRuntime": probeRuntime, "recoverLostAttach": recoverLostAttach]
        case .setDesired(let feature, let value):
            return ["feature": feature, "value": value]
        case .setVital(let vital, let field, let value):
            return ["vital": vital, "field": field, "value": value]
        case .setCounter(let counter, let value):
            return ["counter": counter, "value": value]
        case .lockVital(let vital, let locked):
            return ["vital": vital, "locked": locked]
        case .setResource(let resource, let amount):
            return ["resource": resource, "amount": amount]
        case .lockResource(let resource, let locked):
            return ["resource": resource, "locked": locked]
        case .setRerolls(let amount):
            return ["amount": amount]
        case .lockRerolls(let locked):
            return ["locked": locked]
        case .setChaosGate(let probability):
            return ["probability": probability.map { $0 as Any } ?? NSNull()]
        case .setGathering(let family, let probability):
            return ["family": family.rawValue, "probability": probability.map { $0 as Any } ?? NSNull()]
        case .generateGathering(let family, let scopeToken):
            return ["family": family.rawValue, "scopeToken": scopeToken]
        case .matureGarden(let scopeToken):
            return ["scopeToken": scopeToken]
        case .setStat(let stat, let locked, let value):
            var result: [String: Any] = ["stat": stat, "locked": locked]
            if let value { result["value"] = value }
            return result
        case .setElement(let element, let amount):
            return ["element": element, "amount": amount]
        case .lockElement(let element, let locked):
            return ["element": element, "locked": locked]
        case .setBoonRarity(let target, let multiplier, let forceLegendary, let forceDuo):
            return ["target": target, "multiplier": multiplier, "forceLegendary": forceLegendary, "forceDuo": forceDuo]
        case .setNextRoomReward(let reward):
            return ["reward": reward ?? NSNull()]
        case .setNextOccurrence(let target):
            return ["target": target ?? NSNull()]
        case .spawnReward(let reward):
            return ["reward": reward]
        case .acquireChaosPair(let blessing, let curse):
            return ["blessing": blessing, "curse": curse]
        case .openSellTraits:
            return [:]
        case .setTraitLevel(let trait, let targetLevel):
            var params = Self.traitTargetParams(trait)
            params["targetLevel"] = targetLevel
            return params
        case .setTraitRarity(let trait, let rarity):
            var params = Self.traitTargetParams(trait)
            params["rarity"] = rarity
            return params
        case .setTraitRemainingUses(let trait, let targetRemainingUses):
            var params = Self.traitTargetParams(trait)
            params["targetRemainingUses"] = targetRemainingUses
            return params
        case .expireTrait(let trait):
            return Self.traitTargetParams(trait)
        case .removeTrait(let trait):
            return Self.traitTargetParams(trait)
        case .advanceTraitLifecycle(let trait):
            return Self.traitTargetParams(trait)
        case .openSpecialChoice(let source):
            return ["source": source]
        case .saveEditorInventory(let snapshotID):
            return snapshotID.map { ["snapshotId": $0] } ?? [:]
        case .saveEditorOpenSelection(let snapshotID, let source, let target):
            var params: [String: Any] = ["source": source]
            if let snapshotID { params["snapshotId"] = snapshotID }
            if let target { params["target"] = target }
            return params
        case .saveEditorTarget(let target):
            return ["target": target]
        case .saveEditorQuery(let domain, let scope, let search, let offset, let limit, let path, let language, let stateFilter):
            return [
                "domain": domain,
                "scope": scope,
                "search": search,
                "offset": offset,
                "limit": limit,
                "path": path,
                "language": language,
                "stateFilter": stateFilter,
            ]
        case .saveEditorDetail(let entryID, let language):
            return ["entryId": entryID, "language": language]
        case .saveEditorStage(let entryID, let operation, let value, let language):
            var result: [String: Any] = [
                "entryId": entryID, "operation": operation, "language": language,
            ]
            if let value { result["value"] = value }
            return result
        case .saveEditorUnstage(let entryID, let language):
            return ["entryId": entryID, "language": language]
        case .saveEditorReview(let language), .saveEditorCancel(let language):
            return ["language": language]
        case .saveProfile(let name, let shortcuts):
            return ["name": name, "shortcuts": shortcuts]
        case .loadProfile(let name), .deleteProfile(let name):
            return ["name": name]
        default:
            return [:]
        }
    }
}

final class Hades2API {
    private let session: TrainerBackendSession

    init(session: TrainerBackendSession) {
        self.session = session
    }

    func request(
        _ request: Hades2Request,
        operation: String,
        operationArguments: [String] = [],
        announceSuccess: Bool = true,
        saveWorkspaceID: String? = nil,
        started: (() -> Void)? = nil,
        reply: ((BackendReply) -> Void)? = nil,
        completion: ((Bool) -> Void)? = nil
    ) {
        var params = request.params
        if let saveWorkspaceID { params["workspaceId"] = saveWorkspaceID }
        session.send(
            request.command.rawValue,
            params: params,
            operation: operation,
            operationArguments: operationArguments,
            announceSuccess: announceSuccess,
            timeout: request.command.timeout,
            started: started,
            reply: reply,
            completion: completion
        )
    }
}
