import Foundation
import CoreFoundation

struct Hades2FieldPatch<Value> {
    let isPresent: Bool
    let value: Value?

    static var absent: Hades2FieldPatch<Value> { .init(isPresent: false, value: nil) }
    static func present(_ value: Value?) -> Hades2FieldPatch<Value> { .init(isPresent: true, value: value) }
}

struct Hades2StatSnapshot {
    let value: Double?
    let target: Double?
    let locked: Bool
}

struct Hades2BoonRaritySnapshot {
    let target: String?
    let forceLegendary: Bool?
    let forceDuo: Bool?
}

enum Hades2ActionOutcome: String {
    case completed
    case accepted
    case opened
    case failed
    case outcomeUnknown = "outcome_unknown"
}

struct Hades2ActionReceipt: Equatable {
    let requestID: String
    let command: String
    let outcome: Hades2ActionOutcome
    let error: String?
}

struct Hades2PresentationReference: Equatable {
    let key: String
    let arguments: [String]
}

/// One Modify Exit catalog entry (#832): a reward or a room type. The game's
/// own selection rules arrive as `warning` and never disable an entry; only
/// what the resident cannot build is `enabled == false` with a `reason`.
struct Hades2WorldActionTarget: Identifiable, Equatable {
    let kind: String
    let id: String
    let enabled: Bool
    let reason: String?
    let warning: String?
    let acceptsReward: Bool

    init(kind: String, id: String, enabled: Bool = true, reason: String? = nil,
         warning: String? = nil, acceptsReward: Bool = false) {
        self.kind = kind
        self.id = id
        self.enabled = enabled
        self.reason = reason
        self.warning = warning
        self.acceptsReward = acceptsReward
    }

    var idValue: String { kind + ":" + id }
    var isRoom: Bool { kind == "roomCategory" }
}

/// What one Apply sends: a room type plus an optional reward. Its `id` is the
/// Target menu's selection value.
struct Hades2WorldExitChoice: Equatable {
    let room: String
    let reward: String?

    init(room: String, reward: String? = nil) {
        self.room = room
        self.reward = reward
    }

    init?(id: String) {
        let parts = id.split(separator: ">", maxSplits: 1, omittingEmptySubsequences: false)
        guard let room = parts.first, !room.isEmpty else { return nil }
        if parts.count == 2 {
            guard !parts[1].isEmpty else { return nil }
            self.init(room: String(room), reward: String(parts[1]))
        } else {
            self.init(room: String(room))
        }
    }

    var id: String { reward.map { room + ">" + $0 } ?? room }
}

/// The game's lease on one exit, as the resident reports it.
struct Hades2WorldActionLease: Equatable {
    let room: String
    let reward: String?
    let leaseToken: String

    var choice: Hades2WorldExitChoice { Hades2WorldExitChoice(room: room, reward: reward) }
}

struct Hades2WorldExit: Identifiable, Equatable {
    let doorToken: String
    let objectID: Int
    let ordinal: Int
    let roomName: String
    /// The door's current room type ("combat", "story", ...), or empty when
    /// the region does not build that type (an intro, a boss).
    let roomKind: String
    let reward: String
    /// The current room's own reward rule (e.g. `room_no_reward`): a warning
    /// on an in-place reward edit.
    let rewardWarning: String?
    let targets: [Hades2WorldActionTarget]
    let activeLease: Hades2WorldActionLease?

    init(doorToken: String, objectID: Int, ordinal: Int, roomName: String, roomKind: String = "",
         reward: String, rewardWarning: String? = nil, targets: [Hades2WorldActionTarget],
         activeLease: Hades2WorldActionLease?) {
        self.doorToken = doorToken
        self.objectID = objectID
        self.ordinal = ordinal
        self.roomName = roomName
        self.roomKind = roomKind
        self.reward = reward
        self.rewardWarning = rewardWarning
        self.targets = targets
        self.activeLease = activeLease
    }

    var id: String { doorToken }
    var roomTargets: [Hades2WorldActionTarget] { targets.filter(\.isRoom) }
    var rewardTargets: [Hades2WorldActionTarget] { targets.filter { $0.kind == "reward" } }

    /// A reward under this room type edits the door's current room in place.
    func isCurrentRoom(_ room: String) -> Bool {
        room == "current" || room == roomName || (!roomKind.isEmpty && room == roomKind)
    }

    /// "Any reward" under a room type is a reservation that lets the game pick
    /// the reward; under "current" it would change nothing.
    func offersAnyReward(_ room: Hades2WorldActionTarget) -> Bool {
        room.acceptsReward && room.id != "current"
    }

    func isEnabled(_ choice: Hades2WorldExitChoice) -> Bool {
        guard let room = roomTargets.first(where: { $0.id == choice.room }), room.enabled else { return false }
        guard let reward = choice.reward else { return !room.acceptsReward || offersAnyReward(room) }
        return room.acceptsReward && rewardTargets.contains { $0.id == reward && $0.enabled }
    }

    /// First enabled reward for the door's own room type that it does not
    /// already hold, else the first enabled choice in menu order.
    var defaultChoice: Hades2WorldExitChoice? {
        let rooms = roomTargets.filter(\.enabled)
        if let current = rooms.first(where: { $0.acceptsReward && isCurrentRoom($0.id) }),
           let reward = rewardTargets.first(where: { $0.enabled && $0.id != self.reward }) {
            return Hades2WorldExitChoice(room: current.id, reward: reward.id)
        }
        for room in rooms {
            if !room.acceptsReward { return Hades2WorldExitChoice(room: room.id) }
            if let reward = rewardTargets.first(where: \.enabled) {
                return Hades2WorldExitChoice(room: room.id, reward: reward.id)
            }
            if offersAnyReward(room) { return Hades2WorldExitChoice(room: room.id) }
        }
        return nil
    }
}

struct Hades2WorldOccurrenceLease: Equatable {
    let target: String
    let leaseToken: String
}

struct Hades2WorldActionsSnapshot: Equatable {
    let exits: [Hades2WorldExit]
    let occurrence: Hades2WorldOccurrenceLease?
}

/// Typed boundary between the untyped JSON transport envelope and Hades UI
/// state. All backend field names are centralized here instead of being spread
/// through the ObservableObject and Views.
struct Hades2StatePatch {
    let connected: Bool?
    let pid: Hades2FieldPatch<Int>
    let version: String?
    let status: String?
    let scene: String?
    let capabilities: [String: Bool]?
    let activeFeatures: [String: Bool]?
    let dormantFeatures: [String: Bool]?
    let featureSupport: [String: Bool]?
    let featureErrors: Hades2FieldPatch<[String: String]>
    let featureErrorPresentations: Hades2FieldPatch<[String: Hades2PresentationReference]>
    let desiredFeatures: [Hades2FeatureKey: Bool]?

    let gameSpeed: Double?
    let damageMultiplier: Double?
    let moneyLocked: Bool?
    let moneyMultiplier: Double?
    let resourceMultiplier: Double?
    let boonRarity: Hades2BoonRaritySnapshot?
    let occurrenceTargets: [Hades2OccurrenceTarget]?
    let worldActions: Hades2FieldPatch<Hades2WorldActionsSnapshot>
    let rerolls: Hades2FieldPatch<Double>
    let rerollsLocked: Bool?
    let gatheringProbabilities: Hades2FieldPatch<[Hades2GatheringFamily: Double]>
    let chaosGateProbability: Hades2FieldPatch<Double>
    let chaosGateTarget: Hades2FieldPatch<Hades2GatheringTarget>
    let facilityOptions: Hades2FieldPatch<[Hades2ChamberFacility]>
    let facilityReason: Hades2FieldPatch<String>
    let gatheringTargets: Hades2FieldPatch<[Hades2GatheringFamily: Hades2GatheringTarget]>
    let gardenScopeToken: Hades2FieldPatch<String>

    let warningText: Hades2FieldPatch<String>
    let boons: [BoonOption]?
    let nativeRarityOrder: [String]?
    let statSupport: [String: Bool]?
    let statAvailable: [String: Bool]?
    let stats: [String: Hades2StatSnapshot]?
    let profiles: [TrainerProfile]?
    let diagnostics: [Hades2DiagnosticCheck]?
    let diagnosticsPassed: Int?
    let diagnosticsTotal: Int?
    let shortcuts: [String: Any]?

    let health: Hades2FieldPatch<Double>
    let maxHealth: Hades2FieldPatch<Double>
    let healthLocked: Bool?
    let mana: Hades2FieldPatch<Double>
    let maxMana: Hades2FieldPatch<Double>
    let manaLocked: Bool?
    let armor: Hades2FieldPatch<Double>
    let armorLocked: Bool?
    let spellCharge: Hades2FieldPatch<Double>
    let biomeTime: Hades2FieldPatch<Double>
    let biomeTimeLocked: Bool?
    let spellChargeCost: Hades2FieldPatch<Double>
    let money: Hades2FieldPatch<Double>
    let runCount: Hades2FieldPatch<Int>
    let elements: [ElementCount]?
    let currentRunTraits: [CurrentRunTrait]?
    let currentRunTraitIdentityScope: String?
    let currentRunTraitIdentityPersistent: Bool?
    let resources: [MaterialResource]?
    let lastAction: Hades2ActionReceipt?

    init(_ payload: [String: Any]) {
        connected = payload["connected"] as? Bool
        pid = Self.field(payload, "pid", Int.self)
        version = payload["version"] as? String
        status = payload["status"] as? String
        scene = payload["scene"] as? String
        capabilities = Self.boolMap(payload["capabilities"])
        activeFeatures = Self.boolMap(payload["activeFeatures"])
        dormantFeatures = Self.boolMap(payload["dormantFeatures"])
        featureSupport = Self.boolMap(payload["featureSupport"])
        featureErrors = Self.stringMapField(payload, "featureErrors")
        featureErrorPresentations = Self.textTokenMapField(payload, "featureErrorPresentations")
        desiredFeatures = Self.featureMap(payload["desiredFeatures"])
        gardenScopeToken = Self.field(payload, "gardenScopeToken", String.self)
        gameSpeed = Self.number(payload["gameSpeed"])
        damageMultiplier = Self.number(payload["damageMultiplier"])
        moneyLocked = payload["moneyLocked"] as? Bool
        moneyMultiplier = Self.number(payload["moneyMultiplier"])
        resourceMultiplier = Self.number(payload["resourceMultiplier"])

        if let row = payload["boonRarity"] as? [String: Any] {
            boonRarity = Hades2BoonRaritySnapshot(
                target: row["target"] as? String,
                forceLegendary: row["forceLegendary"] as? Bool,
                forceDuo: row["forceDuo"] as? Bool
            )
        } else { boonRarity = nil }
        if payload.keys.contains("worldActions") {
            worldActions = .present(Self.decodeWorldActions(payload["worldActions"]))
        } else {
            worldActions = .absent
        }
        occurrenceTargets = (payload["occurrenceTargets"] as? [[String: Any]])?.compactMap { row in
            guard let id = row["id"] as? String, !id.isEmpty,
                  let kind = row["kind"] as? String, !kind.isEmpty,
                  let sourceID = row["sourceId"] as? String, !sourceID.isEmpty else { return nil }
            return Hades2OccurrenceTarget(id: id, kind: kind, sourceID: sourceID)
        }
        rerolls = Self.numberField(payload, "rerolls")
        rerollsLocked = payload["rerollsLocked"] as? Bool
        if let raw = payload["chaosGateProbability"] {
            let value = CFGetTypeID(raw as CFTypeRef) == CFBooleanGetTypeID() ? nil : Self.number(raw)
            chaosGateProbability = .present(value.flatMap { $0.isFinite && (0...100).contains($0) ? $0 : nil })
        } else { chaosGateProbability = .absent }

        if let values = payload["gatheringProbabilities"] as? [String: Any] {
            var decoded: [Hades2GatheringFamily: Double] = [:]
            var valid = true
            for (key, raw) in values {
                guard let family = Hades2GatheringFamily(rawValue: key), let value = Self.number(raw), (0...100).contains(value) else { valid = false; break }
                decoded[family] = value
            }
            gatheringProbabilities = .present(valid ? decoded : nil)
        } else { gatheringProbabilities = payload.keys.contains("gatheringProbabilities") ? .present(nil) : .absent }
        if let row = payload["chaosGateTarget"] as? [String: Any],
           let available = row["available"] as? Bool {
            let token = row["scopeToken"] as? String
            if !available || (token?.isEmpty == false && (token?.count ?? 0) <= 128) {
                chaosGateTarget = .present(.init(available: available, scopeToken: token,
                                                reason: row["reason"] as? String))
            } else {
                chaosGateTarget = .present(nil)
            }
        } else {
            chaosGateTarget = payload.keys.contains("chaosGateTarget") ? .present(nil) : .absent
        }
        if let rows = payload["facilityOptions"] as? [[String: Any]] {
            let options = rows.compactMap { row -> Hades2ChamberFacility? in
                guard let id = row["id"] as? String, !id.isEmpty, id.count <= 48,
                      let label = row["labelKey"] as? String,
                      !label.isEmpty, label.count <= 100,
                      let token = row["scopeToken"] as? String,
                      !token.isEmpty, token.count <= 128 else { return nil }
                return .init(id: id, labelKey: label, scopeToken: token)
            }
            facilityOptions = .present(options)
        } else {
            facilityOptions = payload.keys.contains("facilityOptions") ? .present(nil) : .absent
        }
        facilityReason = Self.field(payload, "facilityReason", String.self)
        if let values = payload["gatheringTargets"] as? [String: Any] {
            var decoded: [Hades2GatheringFamily: Hades2GatheringTarget] = [:]
            for (key, raw) in values {
                guard let family = Hades2GatheringFamily(rawValue: key), let row = raw as? [String: Any], let available = row["available"] as? Bool else { continue }
                let token = row["scopeToken"] as? String
                guard !available || (token?.isEmpty == false && (token?.count ?? 0) <= 128) else { continue }
                decoded[family] = .init(available: available, scopeToken: token, reason: row["reason"] as? String)
            }
            gatheringTargets = .present(decoded)
        } else { gatheringTargets = payload.keys.contains("gatheringTargets") ? .present(nil) : .absent }

        if let warnings = payload["warnings"] {
            warningText = .present((warnings as? [String])?.joined(separator: "\n"))
        } else if let warning = payload["warning"] {
            warningText = .present(warning as? String)
        } else {
            warningText = .absent
        }

        let rewardRows = (payload["rewards"] as? [[String: Any]]) ?? (payload["boons"] as? [[String: Any]])
        boons = rewardRows?.compactMap(Self.decodeBoon)
        nativeRarityOrder = payload["nativeRarityOrder"] as? [String]
        statSupport = Self.boolMap(payload["statSupport"])
        statAvailable = Self.boolMap(payload["statAvailable"])
        if let rows = payload["stats"] as? [String: Any] {
            stats = rows.reduce(into: [:]) { result, entry in
                guard let row = entry.value as? [String: Any] else { return }
                result[entry.key] = Hades2StatSnapshot(
                    value: Self.number(row["value"]),
                    target: Self.number(row["target"]),
                    locked: row["locked"] as? Bool ?? false
                )
            }
        } else { stats = nil }

        profiles = (payload["profiles"] as? [[String: Any]])?.compactMap(Self.decodeProfile)
        diagnostics = (payload["checks"] as? [[String: Any]])?.compactMap(Hades2DiagnosticCheck.decode)
        diagnosticsPassed = payload["passed"] as? Int
        diagnosticsTotal = payload["total"] as? Int
        shortcuts = payload["shortcuts"] as? [String: Any]

        health = Self.numberField(payload, "health")
        maxHealth = Self.numberField(payload, "maxHealth")
        healthLocked = payload["healthLocked"] as? Bool
        mana = Self.numberField(payload, "mana")
        maxMana = Self.numberField(payload, "maxMana")
        manaLocked = payload["manaLocked"] as? Bool
        armor = Self.numberField(payload, "armor")
        armorLocked = payload["armorLocked"] as? Bool
        spellCharge = Self.numberField(payload, "spellCharge")
        biomeTime = Self.numberField(payload, "biomeTime")
        biomeTimeLocked = payload["biomeTimeLocked"] as? Bool
        spellChargeCost = Self.numberField(payload, "spellChargeCost")
        money = Self.numberField(payload, "money")
        runCount = Self.field(payload, "runCount", Int.self)
        var elementIDs = Set<String>()
        elements = (payload["elements"] as? [[String: Any]])?.compactMap { row in
            guard let element = Self.decodeElement(row), elementIDs.insert(element.id).inserted else { return nil }
            return element
        }
        currentRunTraits = (payload["currentRunTraits"] as? [[String: Any]])?.compactMap(Self.decodeCurrentRunTrait)
        currentRunTraitIdentityScope = payload["currentRunTraitIdentityScope"] as? String
        currentRunTraitIdentityPersistent = payload["currentRunTraitIdentityPersistent"] as? Bool
        resources = (payload["resources"] as? [[String: Any]])?.compactMap(Self.decodeResource)
        if let row = payload["lastAction"] as? [String: Any],
           let requestID = row["requestId"] as? String,
           let command = row["command"] as? String,
           let outcomeRaw = row["outcome"] as? String,
           let outcome = Hades2ActionOutcome(rawValue: outcomeRaw) {
            lastAction = Hades2ActionReceipt(
                requestID: requestID,
                command: command,
                outcome: outcome,
                error: row["error"] as? String
            )
        } else {
            lastAction = nil
        }
    }

    private static func boolMap(_ value: Any?) -> [String: Bool]? {
        guard let values = value as? [String: Any] else { return nil }
        return values.reduce(into: [:]) { result, entry in
            if let value = entry.value as? Bool { result[entry.key] = value }
        }
    }

    private static func featureMap(_ value: Any?) -> [Hades2FeatureKey: Bool]? {
        guard let values = value as? [String: Any] else { return nil }
        return values.reduce(into: [:]) { result, entry in
            guard let key = Hades2FeatureKey(rawValue: entry.key), let value = entry.value as? Bool else { return }
            result[key] = value
        }
    }

    private static func stringMap(_ value: Any?) -> [String: String]? {
        guard let values = value as? [String: Any] else { return nil }
        return values.reduce(into: [:]) { result, entry in
            if let value = entry.value as? String { result[entry.key] = value }
        }
    }

    private static func stringMapField(_ payload: [String: Any], _ key: String) -> Hades2FieldPatch<[String: String]> {
        guard payload.keys.contains(key) else { return .absent }
        return .present(stringMap(payload[key]))
    }

    private static func textTokenMapField(
        _ payload: [String: Any],
        _ key: String
    ) -> Hades2FieldPatch<[String: Hades2PresentationReference]> {
        guard payload.keys.contains(key) else { return .absent }
        guard let values = payload[key] as? [String: Any] else { return .present(nil) }
        let tokens = values.reduce(into: [String: Hades2PresentationReference]()) { result, entry in
            guard let row = entry.value as? [String: Any],
                  let presentation = row["presentation"] as? String,
                  !presentation.isEmpty else { return }
            let arguments = (row["arguments"] as? [Any] ?? []).compactMap { value -> String? in
                if let value = value as? String { return value }
                if let value = value as? Bool { return value ? "true" : "false" }
                if let value = value as? NSNumber { return value.stringValue }
                return nil
            }
            result[entry.key] = Hades2PresentationReference(key: presentation, arguments: arguments)
        }
        return .present(tokens)
    }

    private static func number(_ value: Any?) -> Double? {
        if let value = value as? Double { return value }
        if let value = value as? Int { return Double(value) }
        return nil
    }

    private static func field<Value>(_ payload: [String: Any], _ key: String, _ type: Value.Type) -> Hades2FieldPatch<Value> {
        guard payload.keys.contains(key) else { return .absent }
        return .present(payload[key] as? Value)
    }

    private static func numberField(_ payload: [String: Any], _ key: String) -> Hades2FieldPatch<Double> {
        guard payload.keys.contains(key) else { return .absent }
        return .present(number(payload[key]))
    }

    private static func decodeBoon(_ row: [String: Any]) -> BoonOption? {
        guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return BoonOption(
            id: id, name: name, englishName: row["englishName"] as? String ?? "",
            // A missing catalog label is not a name. Leave it empty so the view
            // resolves the default from the module's shipped presentation table.
            category: row["category"] as? String ?? "",
            englishCategory: row["englishCategory"] as? String ?? "",
            kind: row["kind"] as? String ?? "loot", group: row["group"] as? String ?? "pickup",
            targetID: row["trait"] as? String ?? id,
            officialName: row["officialName"] as? Bool ?? false,
            sectionTitle: row["sectionTitle"] as? String ?? "",
            englishSectionTitle: row["englishSectionTitle"] as? String ?? "",
            sourceId: row["sourceId"] as? String ?? "",
            sourceName: row["sourceName"] as? String ?? "",
            sourceEnglishName: row["sourceEnglishName"] as? String ?? "",
            nativeChoice: row["nativeChoice"] as? Bool ?? false,
            nativeChoiceTitle: row["nativeChoiceTitle"] as? String ?? "",
            nativeChoiceEnglishTitle: row["nativeChoiceEnglishTitle"] as? String ?? "",
            acquisitionMode: row["acquisitionMode"] as? String ?? "",
            rarities: row["rarities"] as? [String] ?? [],
            supportsLevel: row["supportsLevel"] as? Bool ?? false,
            sortSection: row["sortSection"] as? Int ?? Int.max,
            sortGroup: row["sortGroup"] as? Int ?? Int.max,
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }

    private static func decodeWorldActions(_ raw: Any?) -> Hades2WorldActionsSnapshot? {
        guard let row = raw as? [String: Any],
              let rawExits = row["exits"] as? [[String: Any]] else { return nil }
        let exits = rawExits.compactMap { exit -> Hades2WorldExit? in
            guard let doorToken = exit["doorToken"] as? String, !doorToken.isEmpty,
                  let objectID = number(exit["objectId"]).map(Int.init),
                  let ordinal = number(exit["ordinal"]).map(Int.init) else { return nil }
            let targets = (exit["targets"] as? [[String: Any]] ?? []).compactMap { target -> Hades2WorldActionTarget? in
                guard let kind = target["kind"] as? String, !kind.isEmpty,
                      let id = target["id"] as? String, !id.isEmpty else { return nil }
                return Hades2WorldActionTarget(
                    kind: kind, id: id,
                    enabled: target["enabled"] as? Bool ?? true,
                    reason: target["reason"] as? String,
                    warning: target["warning"] as? String,
                    acceptsReward: target["acceptsReward"] as? Bool ?? false
                )
            }
            let lease: Hades2WorldActionLease?
            if let value = exit["activeLease"] as? [String: Any],
               let room = value["room"] as? String, !room.isEmpty,
               let token = value["leaseToken"] as? String, !token.isEmpty {
                let reward = (value["reward"] as? String).flatMap { $0.isEmpty ? nil : $0 }
                lease = Hades2WorldActionLease(room: room, reward: reward, leaseToken: token)
            } else {
                lease = nil
            }
            return Hades2WorldExit(
                doorToken: doorToken,
                objectID: objectID,
                ordinal: ordinal,
                roomName: exit["roomName"] as? String ?? "",
                roomKind: exit["roomKind"] as? String ?? "",
                reward: exit["reward"] as? String ?? "",
                rewardWarning: exit["rewardWarning"] as? String,
                targets: targets,
                activeLease: lease
            )
        }
        let occurrence: Hades2WorldOccurrenceLease?
        if let value = row["occurrence"] as? [String: Any],
           let target = value["target"] as? String, !target.isEmpty,
           let token = value["leaseToken"] as? String, !token.isEmpty {
            occurrence = Hades2WorldOccurrenceLease(target: target, leaseToken: token)
        } else {
            occurrence = nil
        }
        return Hades2WorldActionsSnapshot(
            exits: exits.sorted { $0.ordinal < $1.ordinal },
            occurrence: occurrence
        )
    }

    private static func decodeProfile(_ row: [String: Any]) -> TrainerProfile? {
        guard let name = row["name"] as? String else { return nil }
        return TrainerProfile(name: name, updatedAt: row["updatedAt"] as? String ?? "")
    }

    private static func decodeCurrentRunTrait(_ row: [String: Any]) -> CurrentRunTrait? {
        guard
            let generationID = row["generationId"] as? String, !generationID.isEmpty,
            let runID = row["runId"] as? String, !runID.isEmpty,
            let instanceID = row["instanceId"] as? String, !instanceID.isEmpty,
            let name = row["name"] as? String, !name.isEmpty
        else { return nil }

        let levelCapability = TraitLevelCapability(
            rawValue: row["levelCapability"] as? String ?? TraitLevelCapability.none.rawValue
        ) ?? .none
        let rarityCapability = TraitRarityCapability(
            rawValue: row["rarityCapability"] as? String ?? TraitRarityCapability.none.rawValue
        ) ?? .none
        let removalCapability = TraitRemovalCapability(
            rawValue: row["removalCapability"] as? String ?? TraitRemovalCapability.none.rawValue
        ) ?? .none

        return CurrentRunTrait(
            generationID: generationID,
            runID: runID,
            instanceID: instanceID,
            name: name,
            displayName: row["displayName"] as? String ?? name,
            englishName: row["englishName"] as? String ?? name,
            family: row["family"] as? String ?? "",
            sourceID: row["sourceId"] as? String ?? "",
            sourceName: row["sourceName"] as? String ?? "",
            sourceEnglishName: row["sourceEnglishName"] as? String ?? "",
            level: row["level"] as? Int ?? 1,
            rarity: row["rarity"] as? String ?? "",
            availableRarities: row["availableRarities"] as? [String] ?? [],
            sameNameCount: row["sameNameCount"] as? Int ?? 1,
            remainingUses: number(row["remainingUses"]),
            lifecycleState: row["lifecycleState"] as? String ?? "",
            linkedTrait: row["linkedTrait"] as? String ?? "",
            linkedDisplayName: row["linkedDisplayName"] as? String ?? "",
            linkedEnglishName: row["linkedEnglishName"] as? String ?? "",
            canAdvanceLifecycle: row["canAdvanceLifecycle"] as? Bool ?? false,
            canSetRemainingUses: row["canSetRemainingUses"] as? Bool ?? false,
            canExpire: row["canExpire"] as? Bool ?? false,
            levelCapability: levelCapability,
            levelReason: row["levelReason"] as? String ?? "",
            rarityCapability: rarityCapability,
            rarityReason: row["rarityReason"] as? String ?? "",
            removalCapability: removalCapability,
            removalReason: row["removalReason"] as? String ?? "",
            removalScopeAllMatching: row["removalScopeAllMatching"] as? Bool ?? false,
            deferredIssue: row["deferredIssue"] as? Int
        )
    }

    private static func decodeElement(_ row: [String: Any]) -> ElementCount? {
        guard !(row["count"] is NSNull),
              let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return ElementCount(id: id, name: name, count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false)
    }

    private static func decodeResource(_ row: [String: Any]) -> MaterialResource? {
        guard !(row["count"] is NSNull),
              let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return MaterialResource(
            id: id, name: name, englishName: row["englishName"] as? String ?? "",
            count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false,
            sectionTitle: row["sectionTitle"] as? String ?? "",
            englishSectionTitle: row["englishSectionTitle"] as? String ?? "",
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }
}
