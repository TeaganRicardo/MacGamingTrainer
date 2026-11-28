import Foundation

/// Typed Hades I Host-command caller adapter. Wire command identity, Host
/// timeout metadata, and trust/offline flags are generated from the backend
/// command contract (`Backend/games/hades/command_contract.py`).
enum HadesRequest {
    case status
    case connect
    case disconnect
    case launch
    case catalog
    case diagnostics
    case listProfiles
    case saveProfile(name: String, shortcuts: [String: Any]? = nil)
    case loadProfile(name: String)
    case deleteProfile(name: String)
    case setFeature(feature: String, value: Any)
    case setBoonRarity(target: String, forceLegendary: Bool, forceDuo: Bool)
    case setFishingChance(Double?)
    case setChaosGateChance(Double?)
    case disableAll
    case lockVital(vital: String, locked: Bool)
    case lockResource(resource: String, locked: Bool)
    case lockRerolls(locked: Bool)
    case setValue(field: String, value: Double)
    case setResource(resource: String, value: Double)
    case gainResource(resource: String, amount: Double)
    case spawnReward(String)
    case generateFishing
    case generateChaosGate
    case generateChamberObject(object: String)
    case applyWorldExit(doorToken: String, room: String, reward: String?)
    case cancelWorldExit(doorToken: String, leaseToken: String)
    case applyWorldOccurrence(targetID: String)
    case cancelWorldOccurrence(leaseToken: String)
    case addTrait(trait: String, rarity: String, level: Int)
    case updateTrait(instanceID: String, rarity: String, level: Int)
    case removeTrait(instanceID: String)
    case setTraitUses(instanceID: String, uses: Int)
    case expireTrait(instanceID: String)
    case refreshTrait(instanceID: String)
    case addChaosPair(blessing: String, curse: String, rarity: String, encounters: Int)
    case openSellTraits

    var command: HadesCommand {
        switch self {
        case .status: return .status
        case .connect: return .connect
        case .disconnect: return .disconnect
        case .launch: return .launch
        case .catalog: return .catalog
        case .diagnostics: return .diagnostics
        case .listProfiles: return .listProfiles
        case .saveProfile: return .saveProfile
        case .loadProfile: return .loadProfile
        case .deleteProfile: return .deleteProfile
        case .setFeature: return .setFeature
        case .setBoonRarity: return .setBoonRarity
        case .setFishingChance: return .setFishingChance
        case .setChaosGateChance: return .setChaosGateChance
        case .disableAll: return .disableAll
        case .lockVital: return .lockVital
        case .lockResource: return .lockResource
        case .lockRerolls: return .lockRerolls
        case .setValue: return .setValue
        case .setResource: return .setResource
        case .gainResource: return .gainResource
        case .spawnReward: return .spawnReward
        case .generateFishing: return .generateFishing
        case .generateChaosGate: return .generateChaosGate
        case .generateChamberObject: return .generateChamberObject
        case .applyWorldExit: return .applyWorldExit
        case .cancelWorldExit: return .cancelWorldExit
        case .applyWorldOccurrence: return .applyWorldOccurrence
        case .cancelWorldOccurrence: return .cancelWorldOccurrence
        case .addTrait: return .addTrait
        case .updateTrait: return .updateTrait
        case .removeTrait: return .removeTrait
        case .setTraitUses: return .setTraitUses
        case .expireTrait: return .expireTrait
        case .refreshTrait: return .refreshTrait
        case .addChaosPair: return .addChaosPair
        case .openSellTraits: return .openSellTraits
        }
    }

    var params: [String: Any] {
        switch self {
        case .saveProfile(let name, let shortcuts):
            guard let shortcuts else { return ["name": name] }
            return ["name": name, "shortcuts": shortcuts]
        case .loadProfile(let name), .deleteProfile(let name):
            return ["name": name]
        case .setFeature(let feature, let value):
            return ["feature": feature, "value": value]
        case .setBoonRarity(let target, let forceLegendary, let forceDuo):
            return ["target": target, "forceLegendary": forceLegendary, "forceDuo": forceDuo]
        case .setFishingChance(let value), .setChaosGateChance(let value):
            return ["chance": value.map { $0 as Any } ?? NSNull()]
        case .lockVital(let vital, let locked):
            return ["vital": vital, "locked": locked]
        case .lockResource(let resource, let locked):
            return ["resource": resource, "locked": locked]
        case .lockRerolls(let locked):
            return ["locked": locked]
        case .setValue(let field, let value):
            return ["field": field, "value": value]
        case .setResource(let resource, let value):
            return ["resource": resource, "value": value]
        case .gainResource(let resource, let amount):
            return ["resource": resource, "amount": amount]
        case .spawnReward(let reward):
            return ["reward": reward]
        case .generateChamberObject(let object):
            return ["object": object]
        case .applyWorldExit(let doorToken, let room, let reward):
            var payload: [String: Any] = ["doorToken": doorToken, "room": room]
            if let reward { payload["reward"] = reward }
            return payload
        case .cancelWorldExit(let doorToken, let leaseToken):
            return ["doorToken": doorToken, "leaseToken": leaseToken]
        case .applyWorldOccurrence(let targetID):
            return ["targetID": targetID]
        case .cancelWorldOccurrence(let leaseToken):
            return ["leaseToken": leaseToken]
        case .addTrait(let trait, let rarity, let level):
            return ["trait": trait, "rarity": rarity, "level": level]
        case .updateTrait(let instanceID, let rarity, let level):
            return ["instanceId": instanceID, "rarity": rarity, "level": level]
        case .removeTrait(let instanceID), .expireTrait(let instanceID), .refreshTrait(let instanceID):
            return ["instanceId": instanceID]
        case .setTraitUses(let instanceID, let uses):
            return ["instanceId": instanceID, "uses": uses]
        case .addChaosPair(let blessing, let curse, let rarity, let encounters):
            return ["blessing": blessing, "curse": curse, "rarity": rarity, "encounters": encounters]
        case .status, .connect, .disconnect, .launch, .catalog, .diagnostics, .listProfiles,
             .disableAll, .generateFishing, .generateChaosGate, .openSellTraits:
            return [:]
        }
    }
}
