import Foundation

struct Hades2FieldPatch<Value> {
    let isPresent: Bool
    let value: Value?

    static var absent: Hades2FieldPatch<Value> { .init(isPresent: false, value: nil) }
    static func present(_ value: Value?) -> Hades2FieldPatch<Value> { .init(isPresent: true, value: value) }
}

struct Hades2StatSnapshot {
    let value: Double?
    let locked: Bool
}

struct Hades2BoonRaritySnapshot {
    let target: String?
    let multiplier: Double?
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
    let nextRoomReward: Hades2FieldPatch<String>
    let rerolls: Hades2FieldPatch<Double>
    let rerollsLocked: Bool?

    let warningText: Hades2FieldPatch<String>
    let boons: [BoonOption]?
    let statSupport: [String: Bool]?
    let statAvailable: [String: Bool]?
    let stats: [String: Hades2StatSnapshot]?
    let profiles: [TrainerProfile]?
    let diagnostics: [DiagnosticCheck]?
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
    let spellChargeCost: Hades2FieldPatch<Double>
    let money: Hades2FieldPatch<Double>
    let runCount: Hades2FieldPatch<Int>
    let elements: [ElementCount]?
    let currentRunTraits: [CurrentRunTrait]?
    let currentRunTraitIdentityScope: String?
    let currentRunTraitIdentityPersistent: Bool?
    let resources: [MaterialResource]?
    let lastAction: Hades2ActionReceipt?
    let error: String?

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
        gameSpeed = Self.number(payload["gameSpeed"])
        damageMultiplier = Self.number(payload["damageMultiplier"])
        moneyLocked = payload["moneyLocked"] as? Bool
        moneyMultiplier = Self.number(payload["moneyMultiplier"])
        resourceMultiplier = Self.number(payload["resourceMultiplier"])

        if let row = payload["boonRarity"] as? [String: Any] {
            boonRarity = Hades2BoonRaritySnapshot(
                target: row["target"] as? String,
                multiplier: Self.number(row["multiplier"]),
                forceLegendary: row["forceLegendary"] as? Bool,
                forceDuo: row["forceDuo"] as? Bool
            )
        } else { boonRarity = nil }
        nextRoomReward = Self.field(payload, "nextRoomReward", String.self)
        rerolls = Self.numberField(payload, "rerolls")
        rerollsLocked = payload["rerollsLocked"] as? Bool

        if let warnings = payload["warnings"] {
            warningText = .present((warnings as? [String])?.joined(separator: "\n"))
        } else if let warning = payload["warning"] {
            warningText = .present(warning as? String)
        } else {
            warningText = .absent
        }

        let rewardRows = (payload["rewards"] as? [[String: Any]]) ?? (payload["boons"] as? [[String: Any]])
        boons = rewardRows?.compactMap(Self.decodeBoon)
        statSupport = Self.boolMap(payload["statSupport"])
        statAvailable = Self.boolMap(payload["statAvailable"])
        if let rows = payload["stats"] as? [String: Any] {
            stats = rows.reduce(into: [:]) { result, entry in
                guard let row = entry.value as? [String: Any] else { return }
                result[entry.key] = Hades2StatSnapshot(value: Self.number(row["value"]), locked: row["locked"] as? Bool ?? false)
            }
        } else { stats = nil }

        profiles = (payload["profiles"] as? [[String: Any]])?.compactMap(Self.decodeProfile)
        diagnostics = (payload["checks"] as? [[String: Any]])?.compactMap(Self.decodeDiagnostic)
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
        spellChargeCost = Self.numberField(payload, "spellChargeCost")
        money = Self.numberField(payload, "money")
        runCount = Self.field(payload, "runCount", Int.self)
        elements = (payload["elements"] as? [[String: Any]])?.compactMap(Self.decodeElement)
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
        error = payload["error"] as? String
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
            sortSection: row["sortSection"] as? Int ?? Int.max,
            sortGroup: row["sortGroup"] as? Int ?? Int.max,
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }

    private static func decodeProfile(_ row: [String: Any]) -> TrainerProfile? {
        guard let name = row["name"] as? String else { return nil }
        return TrainerProfile(name: name, updatedAt: row["updatedAt"] as? String ?? "")
    }

    private static func decodeDiagnostic(_ row: [String: Any]) -> DiagnosticCheck? {
        guard let name = row["name"] as? String else { return nil }
        return DiagnosticCheck(name: name, ok: row["ok"] as? Bool ?? false, detail: String(describing: row["detail"] ?? ""))
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
        guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return ElementCount(id: id, name: name, count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false)
    }

    private static func decodeResource(_ row: [String: Any]) -> MaterialResource? {
        guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return MaterialResource(
            id: id, name: name, englishName: row["englishName"] as? String ?? "",
            count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false,
            sectionTitle: row["sectionTitle"] as? String ?? "",
            englishSectionTitle: row["englishSectionTitle"] as? String ?? "Resources",
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }
}
