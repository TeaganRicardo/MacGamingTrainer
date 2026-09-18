import Foundation

// Small Equatable snapshots keep SwiftUI observation shallow.  The main Hades
// view observes a handful of value objects instead of building a 50+ modifier
// generic chain, which is substantially easier for Swift's constraint solver.
struct Hades2ViewConnectionSnapshot: Equatable {
    let connected: Bool
    let money: Double?
    let rerolls: Double?
    let health: Double?
    let maxHealth: Double?
    let mana: Double?
    let maxMana: Double?
    let armor: Double?
    let spellCharge: Double?
}

struct Hades2ViewStatSnapshot: Equatable {
    let grasp: Double?
    let dodge: Double?
    let crit: Double?
    let chargeSpeed: Double?
    let moveSpeed: Double?
    let sprintSpeed: Double?
    let dashSpeed: Double?
    let attackSpeed: Double?
    let manaRegen: Double?
    let enemyDamage: Double?
    let enemyHealth: Double?
}

struct Hades2ViewConfigSnapshot: Equatable {
    let boonRarityMultiplier: Double
    let nextRoomReward: String?
    let elements: [ElementCount]
    let damageMultiplier: Double
    let moneyMultiplier: Double
    let resourceMultiplier: Double
}

struct Hades2ViewInputSnapshot: Equatable {
    let healthCurrent: String
    let healthMaximum: String
    let manaCurrent: String
    let manaMaximum: String
    let armorCurrent: String
    let spellCharge: String
    let coins: String
    let materialAmount: String
    let selectedMaterial: String
    let rerollAmount: String
    let multiplier: String
    let moneyFactor: String
    let materialFactor: String
}

struct Hades2ViewLockedStatInputSnapshot: Equatable {
    let grasp: String
    let dodge: String
    let crit: String
    let chargeSpeed: String
    let moveSpeed: String
    let sprintSpeed: String
    let dashSpeed: String
    let attackSpeed: String
    let manaRegen: String
    let enemyDamage: String
    let enemyHealth: String
}

struct Hades2ViewCatalogSnapshot: Equatable {
    let elementInputs: [String: String]
    let materialID: String?
    let boonRarityFactor: String
    let olympianIDs: [String]
    let pickupIDs: [String]
    let specialIDs: [String]
    let filteredResourceIDs: [String]
}
