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
    let featureErrors: [String: String]?

    let godMode: Bool?
    let infiniteHealth: Bool?
    let infiniteMana: Bool?
    let instantCastCooldown: Bool?
    let hexAlwaysReady: Bool?
    let infiniteAmmo: Bool?
    let autoMiniGames: Bool?
    let gardenQoL: Bool?
    let boonRarityEnabled: Bool?
    let damageEnabled: Bool?
    let gameSpeed: Double?
    let damageMultiplier: Double?
    let moneyLocked: Bool?
    let moneyMultiplier: Double?
    let moneyMultiplierEnabled: Bool?
    let resourceMultiplier: Double?
    let resourceMultiplierEnabled: Bool?
    let boonRarity: Hades2BoonRaritySnapshot?
    let nextRoomReward: Hades2FieldPatch<String>
    let rerolls: Hades2FieldPatch<Double>
    let rerollsLocked: Bool?

    let warningText: String?
    let boons: [BoonOption]?
    let statSupport: [String: Bool]?
    let statAvailable: [String: Bool]?
    let stats: [String: Hades2StatSnapshot]?
    let backups: [SaveBackup]?
    let profiles: [TrainerProfile]?
    let diagnostics: [DiagnosticCheck]?
    let diagnosticsPassed: Int?
    let diagnosticsTotal: Int?
    let pendingRestoreID: Hades2FieldPatch<String>
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
    let resources: [MaterialResource]?
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
        featureErrors = Self.stringMap(payload["featureErrors"])

        godMode = payload["godMode"] as? Bool
        infiniteHealth = payload["infiniteHealth"] as? Bool
        infiniteMana = payload["infiniteMana"] as? Bool
        instantCastCooldown = payload["instantCastCooldown"] as? Bool
        hexAlwaysReady = payload["hexAlwaysReady"] as? Bool
        infiniteAmmo = payload["infiniteAmmo"] as? Bool
        autoMiniGames = payload["autoMiniGames"] as? Bool
        gardenQoL = payload["gardenQoL"] as? Bool
        boonRarityEnabled = payload["boonRarityEnabled"] as? Bool
        damageEnabled = payload["damageEnabled"] as? Bool
        gameSpeed = Self.number(payload["gameSpeed"])
        damageMultiplier = Self.number(payload["damageMultiplier"])
        moneyLocked = payload["moneyLocked"] as? Bool
        moneyMultiplier = Self.number(payload["moneyMultiplier"])
        moneyMultiplierEnabled = payload["moneyMultiplierEnabled"] as? Bool
        resourceMultiplier = Self.number(payload["resourceMultiplier"])
        resourceMultiplierEnabled = payload["resourceMultiplierEnabled"] as? Bool

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

        if let warnings = payload["warnings"] as? [String] { warningText = warnings.joined(separator: "\n") }
        else { warningText = payload["warning"] as? String }

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

        backups = (payload["backups"] as? [[String: Any]])?.compactMap(Self.decodeBackup)
        profiles = (payload["profiles"] as? [[String: Any]])?.compactMap(Self.decodeProfile)
        diagnostics = (payload["checks"] as? [[String: Any]])?.compactMap(Self.decodeDiagnostic)
        diagnosticsPassed = payload["passed"] as? Int
        diagnosticsTotal = payload["total"] as? Int
        if payload.keys.contains("pendingRestore") {
            let row = payload["pendingRestore"] as? [String: Any]
            pendingRestoreID = .present(row?["backupId"] as? String)
        } else { pendingRestoreID = .absent }
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
        resources = (payload["resources"] as? [[String: Any]])?.compactMap(Self.decodeResource)
        error = payload["error"] as? String
    }

    private static func boolMap(_ value: Any?) -> [String: Bool]? {
        guard let values = value as? [String: Any] else { return nil }
        return values.reduce(into: [:]) { result, entry in
            if let value = entry.value as? Bool { result[entry.key] = value }
        }
    }

    private static func stringMap(_ value: Any?) -> [String: String]? {
        guard let values = value as? [String: Any] else { return nil }
        return values.reduce(into: [:]) { result, entry in
            if let value = entry.value as? String { result[entry.key] = value }
        }
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
            category: row["category"] as? String ?? "神祇祝福",
            kind: row["kind"] as? String ?? "loot", group: row["group"] as? String ?? "pickup",
            sectionTitle: row["sectionTitle"] as? String ?? "",
            sortSection: row["sortSection"] as? Int ?? Int.max,
            sortGroup: row["sortGroup"] as? Int ?? Int.max,
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }

    private static func decodeBackup(_ row: [String: Any]) -> SaveBackup? {
        guard let id = row["id"] as? String else { return nil }
        return SaveBackup(
            id: id, name: row["name"] as? String ?? id,
            createdAt: row["createdAt"] as? String ?? id, fileCount: row["fileCount"] as? Int ?? 0,
            runCount: row["runCount"] as? Int, hotBackup: row["hotBackup"] as? Bool ?? false,
            path: row["path"] as? String ?? "", valid: row["valid"] as? Bool ?? false,
            error: row["error"] as? String ?? ""
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

    private static func decodeElement(_ row: [String: Any]) -> ElementCount? {
        guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return ElementCount(id: id, name: name, count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false)
    }

    private static func decodeResource(_ row: [String: Any]) -> MaterialResource? {
        guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
        return MaterialResource(
            id: id, name: name, englishName: row["englishName"] as? String ?? "",
            count: number(row["count"]) ?? 0, locked: row["locked"] as? Bool ?? false,
            sectionTitle: row["sectionTitle"] as? String ?? "资源",
            sortOrder: row["sortOrder"] as? Int ?? Int.max
        )
    }
}
