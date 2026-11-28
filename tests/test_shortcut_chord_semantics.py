import shutil
import subprocess
import tempfile
from pathlib import Path
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
swiftc = shutil.which('swiftc')
if not swiftc:
    raise SystemExit('swiftc required for shortcut chord semantics test')

harness = r'''
import Foundation

precondition(Set(ShortcutAction.allCases.map(\.rawValue)).count == ShortcutAction.allCases.count)
precondition(ShortcutAction.allCases.count <= HotkeyChord.defaultShortcutCapacity)
precondition(Hades2ShortcutStore.defaultLayout().count == ShortcutAction.allCases.count)
precondition(ShortcutAction.allCases.last == .disableAll)
precondition(HotkeyChord.defaultShortcut(index: 9)?.displayText == "⌃⌥0")
precondition(HotkeyChord.defaultShortcut(index: 10)?.displayText == "⌃⌥Q")
precondition(HotkeyChord.defaultShortcut(index: 35)?.displayText == "⌃⌥M")
precondition(HotkeyChord.defaultShortcut(index: 36)?.displayText == "⌃⌥⇧1")
precondition(HotkeyChord.defaultShortcut(index: 72)?.displayText == "⌃⌥⌘1")
precondition(HotkeyChord.defaultShortcut(index: 108)?.displayText == "⌃⌥⇧⌘1")
precondition(HotkeyChord.defaultShortcut(index: HotkeyChord.defaultShortcutCapacity - 1)?.displayText == "⌃⌥⇧⌘M")
precondition(Hades2ShortcutStore.defaultLayout()[.disableAll]?.displayText == "⌃⌥⌫", "disable all keeps one fixed panic chord")
precondition(Hades2ShortcutStore.controlOptionDefault(index: 9)?.displayText == "⌃⌥A", "legacy v4 defaults must remain frozen")
precondition(HotkeyChord.defaultShortcut(index: HotkeyChord.defaultShortcutCapacity) == nil)
let generatedDefaults = (0..<HotkeyChord.defaultShortcutCapacity).compactMap(HotkeyChord.defaultShortcut(index:))
precondition(Set(generatedDefaults.map { "\($0.keyCode):\($0.modifiers)" }).count == HotkeyChord.defaultShortcutCapacity)

// InMemoryDefaults (tests/fixtures/swift) keeps this harness off the real
// preferences directory; a real suite there cannot be cleaned up afterwards.
func makeDefaults() -> UserDefaults { InMemoryDefaults() }

final class RecordingDefaults: UserDefaults {
    private let inner = InMemoryDefaults()
    var events: [String] = []

    override func object(forKey defaultName: String) -> Any? { inner.object(forKey: defaultName) }
    override func string(forKey defaultName: String) -> String? { inner.string(forKey: defaultName) }
    override func integer(forKey defaultName: String) -> Int { inner.integer(forKey: defaultName) }
    override func set(_ value: Any?, forKey defaultName: String) {
        events.append("set:\(defaultName)")
        inner.set(value, forKey: defaultName)
    }
    override func removeObject(forKey defaultName: String) {
        events.append("remove:\(defaultName)")
        inner.removeObject(forKey: defaultName)
    }
}

func unique(_ store: Hades2ShortcutStore) -> Bool {
    let values = ShortcutAction.allCases.map { "\(store.chord($0).keyCode):\(store.chord($0).modifiers)" }
    return Set(values).count == values.count
}



func shortcutKey(_ action: ShortcutAction) -> String {
    "hades2.shortcut.action.\(action.rawValue)"
}

func unprefixedShortcutKey(_ action: ShortcutAction) -> String {
    "shortcut.action.\(action.rawValue)"
}

func legacyShortcutKey(_ identity: String) -> String {
    "shortcut.action.\(identity == "invincibility" ? "godMode" : identity)"
}

func legacyShortcutKey(_ action: ShortcutAction) -> String {
    action == .invincibility ? "shortcut.action.godMode" : unprefixedShortcutKey(action)
}

func seedV3Defaults(_ defaults: UserDefaults, invincibilityOverride: Int? = nil) {
    defaults.set(3, forKey: "shortcut.layoutVersion")
    let legacy: [String: Int] = [
        "invincibility": 1, "infiniteHealth": 2, "infiniteMana": 3, "instantCastCooldown": 4,
        "hexAlwaysReady": 5, "infiniteAmmo": 6, "damageEnabled": 7, "autoMiniGames": 8,
        "moneyMultiplierEnabled": 9, "disableAll": 0,
    ]
    for (identity, digit) in legacy {
        defaults.set(identity == "invincibility" ? (invincibilityOverride ?? digit) : digit, forKey: legacyShortcutKey(identity))
    }
}

let legacyV4Order: [String] = [
    "invincibility", "infiniteHealth", "infiniteMana", "instantCastCooldown", "hexAlwaysReady",
    "infiniteAmmo", "damageEnabled", "autoMiniGames", "gardenQoL", "boonRarityEnabled",
    "forceEnableRerolls", "forceLegendary", "forceDuo", "moneyMultiplierEnabled",
    "resourceMultiplierEnabled", "spawnOlympian", "spawnPickup", "spawnSpecial",
    "applyNextRoomReward", "disableAll",
]

func legacyV4DefaultLayout() -> [String: HotkeyChord] {
    Dictionary(uniqueKeysWithValues: legacyV4Order.enumerated().compactMap { index, action in
        Hades2ShortcutStore.controlOptionDefault(index: index).map { (action, $0) }
    })
}

func seedKnownBrokenV4Defaults(_ defaults: UserDefaults) {
    defaults.set(4, forKey: "shortcut.layoutVersion")
    let clean = legacyV4DefaultLayout()
    for action in legacyV4Order {
        defaults.set(clean[action]!.payload, forKey: legacyShortcutKey(action))
    }
    defaults.set(clean["moneyMultiplierEnabled"]!.payload, forKey: legacyShortcutKey("gardenQoL"))
    defaults.set(HotkeyChord.controlOptionDigit(9)!.payload, forKey: legacyShortcutKey(.moneyMultiplierEnabled))
    defaults.set(HotkeyChord.controlOptionDigit(0)!.payload, forKey: legacyShortcutKey(.disableAll))
}

let migratedV3DefaultsStore = makeDefaults()
seedV3Defaults(migratedV3DefaultsStore)
let migratedV3Defaults = Hades2ShortcutStore(defaults: migratedV3DefaultsStore)
func matchesDerivedDefaults(_ store: Hades2ShortcutStore) -> Bool {
    Hades2ShortcutStore.defaultLayout().allSatisfy { action, expected in store.chord(action) == expected }
}

precondition(matchesDerivedDefaults(migratedV3Defaults))

let migratedV3CustomStore = makeDefaults()
seedV3Defaults(migratedV3CustomStore, invincibilityOverride: 0)
let migratedV3Custom = Hades2ShortcutStore(defaults: migratedV3CustomStore)
precondition(migratedV3Custom.chord(.invincibility).keyLabel == "0")
precondition(migratedV3Custom.chord(.infiniteHealth).keyLabel == "2")
precondition(migratedV3Custom.chord(.infiniteAmmo).keyLabel == "9")
precondition(migratedV3Custom.chord(.moneyMultiplierEnabled) == Hades2ShortcutStore.defaultLayout()[.moneyMultiplierEnabled])
let disableAllIndex = ShortcutAction.allCases.firstIndex(of: .disableAll)!
let disableAllDefault = Hades2ShortcutStore.defaultLayout()[.disableAll]!
precondition(migratedV3Custom.chord(.disableAll) == disableAllDefault)
precondition(unique(migratedV3Custom))

let brokenV4Store = makeDefaults()
seedKnownBrokenV4Defaults(brokenV4Store)
let repairedV4 = Hades2ShortcutStore(defaults: brokenV4Store)
precondition(matchesDerivedDefaults(repairedV4))

let defaults = Hades2ShortcutStore(defaults: makeDefaults())
precondition(matchesDerivedDefaults(defaults))
precondition(unique(defaults))
precondition(defaults.chord(.disableAll) == disableAllDefault)
// The panic chord is reserved: another action cannot claim it and push the
// panic key onto some arbitrary free slot.
var reservedStore = Hades2ShortcutStore(defaults: makeDefaults())
precondition(reservedStore.set(.spawnPickup, chord: disableAllDefault) == .disableAll,
             "the disable-all chord must be reserved")
precondition(reservedStore.chord(.disableAll) == disableAllDefault)
precondition(TrainerHotkeyLayout.disableAllChord == disableAllDefault)
let samePhysical = HotkeyChord(keyCode: 51, modifiers: disableAllDefault.modifiers, keyLabel: "Backspace")
precondition(TrainerHotkeyLayout.isDisableAllChord(samePhysical))
precondition(reservedStore.set(.spawnPickup, chord: samePhysical) == .disableAll,
             "physical identity must win over display label")
let unrelatedChord = HotkeyChord(keyCode: 98, modifiers: HotkeyChord.commandModifier, keyLabel: "F4")
precondition(reservedStore.set(.disableAll, chord: unrelatedChord) == .disableAll,
             "Disable All cannot be rebound even to an unused key")
precondition(reservedStore.set(.disableAll, chord: samePhysical) == nil)
precondition(reservedStore.chord(.disableAll) == disableAllDefault)
precondition(reservedStore.payload()["disableAll"] == nil)
let coreOrder: [ShortcutAction] = [.invincibility, .disableAll, .infiniteHealth]
let coreDefaults = TrainerHotkeyLayout.defaultLayout(
    orderedActions: coreOrder, dedicated: [.disableAll: disableAllDefault]
)
precondition(coreDefaults[.invincibility] == HotkeyChord.defaultShortcut(index: 0))
precondition(coreDefaults[.infiniteHealth] == HotkeyChord.defaultShortcut(index: 1))
let coreResolved = TrainerHotkeyLayout.resolvedLayout(
    orderedActions: coreOrder, defaults: coreDefaults,
    overrides: [.infiniteHealth: coreDefaults[.invincibility]!],
    locked: [.disableAll: disableAllDefault]
)
precondition(coreResolved[.infiniteHealth] == coreDefaults[.invincibility])
precondition(coreResolved[.invincibility] == coreDefaults[.infiniteHealth])
precondition(coreResolved[.disableAll] == disableAllDefault)
precondition(defaults.payload()["_layoutVersion"] as? Int == 1)
precondition(defaults.payload()["invincibility"] == nil)
let common: [ShortcutAction] = [.invincibility, .infiniteHealth, .infiniteMana, .infiniteMoney,
    .infiniteRerolls, .forceEnableRerolls, .instantCastCooldown, .hexAlwaysReady, .infiniteAmmo, .autoMiniGames]
precondition(Array(Hades2WorkbenchCatalog.orderedShortcutActions.prefix(10)) == common)
precondition(Hades2WorkbenchCatalog.shortcutActions(in: .common).filter { !$0.isSpeedAdjustment } == common)
precondition(common.map { defaults.chord($0).displayText } == ["⌃⌥1", "⌃⌥2", "⌃⌥3", "⌃⌥4", "⌃⌥5", "⌃⌥6", "⌃⌥7", "⌃⌥8", "⌃⌥9", "⌃⌥0"])
precondition(!ShortcutAction.allCases.contains { $0.rawValue == "damageEnabled" })
precondition(defaults.payload()["damageEnabled"] == nil)
precondition(defaults.chord(.decreaseGameSpeed).displayText == "⌃⌥−")
precondition(defaults.chord(.increaseGameSpeed).displayText == "⌃⌥+")
let retiredStore = makeDefaults()
retiredStore.set(6, forKey: "shortcut.layoutVersion")
retiredStore.set(HotkeyChord(keyCode: 7, modifiers: HotkeyChord.commandModifier, keyLabel: "X").payload, forKey: "shortcut.action.gardenQoL")
retiredStore.set(HotkeyChord(keyCode: 7, modifiers: HotkeyChord.commandModifier, keyLabel: "X").payload, forKey: "shortcut.action.damageEnabled")
let retired = Hades2ShortcutStore(defaults: retiredStore)
precondition(retiredStore.object(forKey: "shortcut.action.gardenQoL") == nil)
precondition(retiredStore.object(forKey: "shortcut.action.damageEnabled") == nil)
precondition(ShortcutAction(rawValue: "gardenQoL") == nil)
precondition(ShortcutAction(rawValue: "damageEnabled") == nil)
precondition(retired.payload()["gardenQoL"] == nil)
precondition(retired.payload()["damageEnabled"] == nil)

// Legacy Profiles serialized every derived chord. Loading their untouched
// layout should reflow to current visible order, while a real custom chord survives.
let legacyDefaults = legacyV4DefaultLayout()
var legacyDefaultProfile: [String: Any] = [:]
for action in legacyV4Order {
    legacyDefaultProfile[action] = legacyDefaults[action]!.payload
}
var migratedLegacyProfile = Hades2ShortcutStore(defaults: makeDefaults())
let seedCustom = HotkeyChord(keyCode: 7, modifiers: HotkeyChord.commandModifier, keyLabel: "X")
var futureVersionStore = Hades2ShortcutStore(defaults: makeDefaults())
let futureVersionOriginal = futureVersionStore.chord(.invincibility)
let futureVersionResult = futureVersionStore.applyProfile([
    "_layoutVersion": 2,
    ShortcutAction.invincibility.rawValue: seedCustom.payload,
])
precondition(futureVersionResult == .unsupportedLayoutVersion(2))
precondition(futureVersionStore.chord(.invincibility) == futureVersionOriginal)
precondition(futureVersionStore.payload()["invincibility"] == nil)
precondition(migratedLegacyProfile.set(.invincibility, chord: seedCustom) == nil)
migratedLegacyProfile.applyProfile(legacyDefaultProfile)
precondition(matchesDerivedDefaults(migratedLegacyProfile))

var legacyCustomProfile = legacyDefaultProfile
legacyCustomProfile[ShortcutAction.invincibility.rawValue] = seedCustom.payload
var migratedCustomProfile = Hades2ShortcutStore(defaults: makeDefaults())
migratedCustomProfile.applyProfile(legacyCustomProfile)
precondition(migratedCustomProfile.chord(.invincibility) == seedCustom)
precondition(unique(migratedCustomProfile))

// Python's Hades2ProfileService strips retired v4 keys and rewrites "applyNextRoomReward"
// to "applyWorldExit". That canonicalized v4 payload must still count as a complete legacy
// layout so computed v4 defaults re-derive rather than pinning applyWorldExit's v4 chord.
var pythonMigratedV4Profile: [String: Any] = [:]
for (index, rawAction) in legacyV4Order.enumerated() {
    let key = rawAction == "applyNextRoomReward" ? "applyWorldExit" : rawAction
    guard ShortcutAction(rawValue: key) != nil else { continue }
    pythonMigratedV4Profile[key] = Hades2ShortcutStore.controlOptionDefault(index: index)!.payload
}
pythonMigratedV4Profile[ShortcutAction.invincibility.rawValue] = seedCustom.payload
var migratedFromPythonV4 = Hades2ShortcutStore(defaults: makeDefaults())
let priorCustomWorldExit = HotkeyChord(keyCode: 8, modifiers: HotkeyChord.commandModifier, keyLabel: "C")
precondition(migratedFromPythonV4.set(.applyWorldExit, chord: priorCustomWorldExit) == nil)
migratedFromPythonV4.applyProfile(pythonMigratedV4Profile)
precondition(migratedFromPythonV4.chord(.applyWorldExit) == Hades2ShortcutStore.defaultLayout()[.applyWorldExit])
precondition(migratedFromPythonV4.chord(.invincibility) == seedCustom)
precondition(unique(migratedFromPythonV4))

// Historical v3 Profiles stripped by Python (`_RETIRED_SHORTCUT_ACTIONS` removes
// `"damageEnabled"`) must still match as a complete legacy layout so existing
// overrides are replaced cleanly by the v3 Profile.
let legacyV3Digits: [String: Int] = [
    "invincibility": 1, "infiniteHealth": 2, "infiniteMana": 3, "instantCastCooldown": 4,
    "hexAlwaysReady": 5, "infiniteAmmo": 6, "autoMiniGames": 8,
    "moneyMultiplierEnabled": 9, "disableAll": 0,
]
let legacyV3StrippedProfile: [String: Any] = Dictionary(uniqueKeysWithValues: legacyV3Digits.map { action, digit in
    (action, HotkeyChord.controlOptionDigit(digit)!.payload as Any)
})
var migratedV3Profile = Hades2ShortcutStore(defaults: makeDefaults())
precondition(migratedV3Profile.set(.infiniteHealth, chord: seedCustom) == nil)
migratedV3Profile.applyProfile(legacyV3StrippedProfile)
precondition(matchesDerivedDefaults(migratedV3Profile))

var currentDefaultProfile = Hades2ShortcutStore(defaults: makeDefaults()).payload()
var resetByCurrentProfile = Hades2ShortcutStore(defaults: makeDefaults())
precondition(resetByCurrentProfile.set(.invincibility, chord: seedCustom) == nil)
resetByCurrentProfile.applyProfile(currentDefaultProfile)
precondition(matchesDerivedDefaults(resetByCurrentProfile))

var full = Hades2ShortcutStore(defaults: makeDefaults())
var profile = full.payload()
profile[ShortcutAction.invincibility.rawValue] = full.chord(.infiniteHealth).payload
profile[ShortcutAction.infiniteHealth.rawValue] = full.chord(.invincibility).payload
full.applyProfile(profile)
precondition(full.chord(.invincibility).keyLabel == "2" && full.chord(.infiniteHealth).keyLabel == "1")
precondition(unique(full))

var partial = Hades2ShortcutStore(defaults: makeDefaults())
let wanted = partial.chord(.infiniteHealth)
partial.applyProfile([ShortcutAction.invincibility.rawValue: wanted.payload])
precondition(partial.chord(.invincibility) == wanted && partial.chord(.infiniteHealth) != wanted)
precondition(unique(partial))

var partialWithExistingOverride = Hades2ShortcutStore(defaults: makeDefaults())
let custom = HotkeyChord(keyCode: 18, modifiers: HotkeyChord.commandModifier, keyLabel: "1")
precondition(partialWithExistingOverride.set(.infiniteHealth, chord: custom) == nil)
partialWithExistingOverride.applyProfile([ShortcutAction.invincibility.rawValue: custom.payload])
precondition(partialWithExistingOverride.chord(.invincibility) == custom)
precondition(partialWithExistingOverride.chord(.infiniteHealth) != custom)
precondition(unique(partialWithExistingOverride))

// Versioned preferences and Profile imports must never restore a stale panic
// reassignment. Valid non-reserved explicit overrides remain in place across v6 -> v7 migration
// and v7 reload.
let migratedV6Preferences = makeDefaults()
migratedV6Preferences.set(6, forKey: "shortcut.layoutVersion")
migratedV6Preferences.set(unrelatedChord.payload, forKey: unprefixedShortcutKey(.disableAll))
migratedV6Preferences.set(samePhysical.payload, forKey: unprefixedShortcutKey(.spawnPickup))
migratedV6Preferences.set(custom.payload, forKey: unprefixedShortcutKey(.invincibility))
let migratedFromV6 = Hades2ShortcutStore(defaults: migratedV6Preferences)
precondition(migratedFromV6.chord(.disableAll) == disableAllDefault)
precondition(migratedFromV6.chord(.invincibility) == custom)
precondition(migratedFromV6.chord(.spawnPickup) == Hades2ShortcutStore.defaultLayout()[.spawnPickup])
precondition(migratedV6Preferences.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(migratedV6Preferences.object(forKey: "shortcut.layoutVersion") == nil)
precondition(migratedV6Preferences.object(forKey: unprefixedShortcutKey(.invincibility)) == nil)
precondition(migratedV6Preferences.object(forKey: shortcutKey(.invincibility)) != nil)
precondition(migratedV6Preferences.object(forKey: shortcutKey(.disableAll)) == nil)
precondition(migratedV6Preferences.object(forKey: shortcutKey(.spawnPickup)) == nil)
precondition(unique(migratedFromV6))

let savedPreferences = makeDefaults()
savedPreferences.set(8, forKey: "hades2.shortcut.layoutVersion")
savedPreferences.set(unrelatedChord.payload, forKey: shortcutKey(.disableAll))
savedPreferences.set(samePhysical.payload, forKey: shortcutKey(.spawnPickup))
savedPreferences.set(custom.payload, forKey: shortcutKey(.invincibility))
let reloaded = Hades2ShortcutStore(defaults: savedPreferences)
precondition(reloaded.chord(.disableAll) == disableAllDefault)
precondition(reloaded.chord(.invincibility) == custom)
precondition(reloaded.chord(.spawnPickup) == Hades2ShortcutStore.defaultLayout()[.spawnPickup])
precondition(savedPreferences.object(forKey: shortcutKey(.disableAll)) == nil)
precondition(savedPreferences.object(forKey: shortcutKey(.spawnPickup)) == nil)
precondition(unique(reloaded))

// #821 / #828: v6 -> v8 and v7 -> v8 migrations must write new version & canonical keys before deleting legacy keys,
// and an interrupted migration with both v8 and leftover v6 keys must keep custom v8 bindings.
let orderedDefaults = RecordingDefaults()
orderedDefaults.set(6, forKey: "shortcut.layoutVersion")
orderedDefaults.set(custom.payload, forKey: unprefixedShortcutKey(.invincibility))
orderedDefaults.set(seedCustom.payload, forKey: "shortcut.action.gardenQoL")
orderedDefaults.events.removeAll()
let orderedMigrated = Hades2ShortcutStore(defaults: orderedDefaults)
precondition(orderedMigrated.chord(.invincibility) == custom)
let v8SetIndex = orderedDefaults.events.firstIndex(of: "set:hades2.shortcut.layoutVersion")!
let legacyVersionRemoveIndex = orderedDefaults.events.firstIndex(of: "remove:shortcut.layoutVersion")!
precondition(v8SetIndex < legacyVersionRemoveIndex)
for (index, event) in orderedDefaults.events.enumerated() where event.hasPrefix("remove:shortcut.action.") {
    precondition(v8SetIndex < index, "v8 marker must be written before removing \(event)")
}

let v7OrderedDefaults = RecordingDefaults()
let legacyWorldExitKey = "hades2.shortcut.action." + "applyNextRoomReward"
v7OrderedDefaults.set(7, forKey: "hades2.shortcut.layoutVersion")
v7OrderedDefaults.set(custom.payload, forKey: legacyWorldExitKey)
v7OrderedDefaults.events.removeAll()
let v7Migrated = Hades2ShortcutStore(defaults: v7OrderedDefaults)
precondition(v7Migrated.chord(.applyWorldExit) == custom)
precondition(v7OrderedDefaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(v7OrderedDefaults.object(forKey: legacyWorldExitKey) == nil)
let v7ToV8MarkerIndex = v7OrderedDefaults.events.firstIndex(of: "set:hades2.shortcut.layoutVersion")!
let worldExitWriteIndex = v7OrderedDefaults.events.firstIndex(of: "set:hades2.shortcut.action.applyWorldExit")!
let worldExitRemoveIndex = v7OrderedDefaults.events.firstIndex(of: "remove:" + legacyWorldExitKey)!
precondition(worldExitWriteIndex < worldExitRemoveIndex)
precondition(v7ToV8MarkerIndex < worldExitRemoveIndex)

let futureVersionDefaults = makeDefaults()
futureVersionDefaults.set(99, forKey: "hades2.shortcut.layoutVersion")
futureVersionDefaults.set(custom.payload, forKey: legacyWorldExitKey)
futureVersionDefaults.set(custom.payload, forKey: shortcutKey(.disableAll))
var futureVersionStoreFromDefaults = Hades2ShortcutStore(defaults: futureVersionDefaults)
precondition(futureVersionDefaults.integer(forKey: "hades2.shortcut.layoutVersion") == 99)
precondition(futureVersionDefaults.object(forKey: legacyWorldExitKey) != nil)
precondition(futureVersionDefaults.object(forKey: shortcutKey(.disableAll)) != nil)
_ = futureVersionStoreFromDefaults.set(.invincibility, chord: seedCustom)
precondition(futureVersionDefaults.object(forKey: shortcutKey(.invincibility)) == nil)

let interruptedDefaults = makeDefaults()
interruptedDefaults.set(Hades2ShortcutStore.currentLayoutVersion, forKey: "hades2.shortcut.layoutVersion")
interruptedDefaults.set(custom.payload, forKey: shortcutKey(.invincibility))
interruptedDefaults.set(6, forKey: "shortcut.layoutVersion")
interruptedDefaults.set(seedCustom.payload, forKey: unprefixedShortcutKey(.invincibility))
interruptedDefaults.set(seedCustom.payload, forKey: "shortcut.action.gardenQoL")
let interruptedRecovered = Hades2ShortcutStore(defaults: interruptedDefaults)
precondition(interruptedRecovered.chord(.invincibility) == custom)
precondition(interruptedDefaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(interruptedDefaults.object(forKey: "shortcut.layoutVersion") == nil)
precondition(interruptedDefaults.object(forKey: unprefixedShortcutKey(.invincibility)) == nil)
precondition(interruptedDefaults.object(forKey: "shortcut.action.gardenQoL") == nil)

// v7 store with already-deleted shortcut.layoutVersion but leftover unprefixed keys must preserve v7 bindings.
let v7WorldExitChord = HotkeyChord(keyCode: 9, modifiers: HotkeyChord.commandModifier, keyLabel: "V")
let v7LeftoverDefaults = makeDefaults()
v7LeftoverDefaults.set(7, forKey: "hades2.shortcut.layoutVersion")
v7LeftoverDefaults.set(custom.payload, forKey: shortcutKey(.invincibility))
v7LeftoverDefaults.set(v7WorldExitChord.payload, forKey: legacyWorldExitKey)
v7LeftoverDefaults.set(seedCustom.payload, forKey: "shortcut.action.godMode")
v7LeftoverDefaults.set(seedCustom.payload, forKey: "shortcut.action.gardenQoL")
let v7LeftoverMigrated = Hades2ShortcutStore(defaults: v7LeftoverDefaults)
precondition(v7LeftoverMigrated.chord(.invincibility) == custom)
precondition(v7LeftoverMigrated.chord(.applyWorldExit) == v7WorldExitChord)
precondition(v7LeftoverDefaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(v7LeftoverDefaults.object(forKey: "shortcut.action.godMode") == nil)
precondition(v7LeftoverDefaults.object(forKey: "shortcut.action.gardenQoL") == nil)
precondition(v7LeftoverDefaults.object(forKey: legacyWorldExitKey) == nil)

// v7 store with stale v5 marker and unprefixed keys must keep committed v7 overrides over v5.
let v7WithStaleV5Defaults = makeDefaults()
v7WithStaleV5Defaults.set(7, forKey: "hades2.shortcut.layoutVersion")
v7WithStaleV5Defaults.set(custom.payload, forKey: shortcutKey(.invincibility))
v7WithStaleV5Defaults.set(5, forKey: "shortcut.layoutVersion")
v7WithStaleV5Defaults.set(seedCustom.payload, forKey: "shortcut.action.godMode")
let v7StaleV5Migrated = Hades2ShortcutStore(defaults: v7WithStaleV5Defaults)
precondition(v7StaleV5Migrated.chord(.invincibility) == custom)
precondition(v7WithStaleV5Defaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(v7WithStaleV5Defaults.object(forKey: "shortcut.layoutVersion") == nil)
precondition(v7WithStaleV5Defaults.object(forKey: "shortcut.action.godMode") == nil)

var imported = Hades2ShortcutStore(defaults: makeDefaults())
let applied = imported.applyProfile([
    "_layoutVersion": 1,
    "disableAll": unrelatedChord.payload,
    "spawnPickup": samePhysical.payload,
    "infiniteHealth": custom.payload,
    "applyNextRoomReward": seedCustom.payload,
])
precondition(applied == .applied)
precondition(imported.chord(.disableAll) == disableAllDefault)
precondition(imported.chord(.infiniteHealth) == custom)
precondition(imported.chord(.applyWorldExit) == seedCustom)
precondition(imported.payload()["disableAll"] == nil && imported.payload()["spawnPickup"] == nil)
precondition(unique(imported))

precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":Int(UInt32.max)+1,"keyLabel":"1"]) == nil)
precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":1,"keyLabel":"1"]) == nil)
precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":6144,"keyLabel":"\n"]) == nil)

// Reset is a storage operation, not a visual reflow. It removes explicit
// overrides and persists the current derived layout across a new store.
let resetDefaults = makeDefaults()
var resetStore = Hades2ShortcutStore(defaults: resetDefaults)
let resetChord = HotkeyChord(keyCode: 7, modifiers: HotkeyChord.commandModifier, keyLabel: "X")
precondition(resetStore.set(.infiniteHealth, chord: resetChord) == nil)
precondition(resetDefaults.object(forKey: shortcutKey(.infiniteHealth)) != nil)
resetStore.resetToDefaults()
precondition(matchesDerivedDefaults(resetStore) && unique(resetStore))
precondition(resetStore.chord(.disableAll) == disableAllDefault)
precondition(resetDefaults.object(forKey: shortcutKey(.infiniteHealth)) == nil)
precondition(resetStore.payload().keys.sorted() == ["_layoutVersion"])
precondition(matchesDerivedDefaults(Hades2ShortcutStore(defaults: resetDefaults)))
// Reset remains meaningful after a Profile import and does not remove Profiles.
precondition(resetStore.applyProfile(["_layoutVersion": 1, "infiniteHealth": resetChord.payload]) == .applied)
precondition(resetStore.chord(.infiniteHealth) == resetChord)
resetStore.resetToDefaults()
precondition(matchesDerivedDefaults(resetStore))

// Version 8 -> 9 migration preserves surviving custom overrides, retires forceLegendary
// and forceDuo AFTER updating the layout version, shifts subsequent defaults cleanly,
// and refuses v10+ schemas without overwriting.
let v8Defaults = makeDefaults()
v8Defaults.set(8, forKey: "hades2.shortcut.layoutVersion")
let v8HealthChord = HotkeyChord(keyCode: 4, modifiers: HotkeyChord.commandModifier, keyLabel: "H")
v8Defaults.set(v8HealthChord.payload, forKey: shortcutKey(.infiniteHealth))
v8Defaults.set(HotkeyChord(keyCode: 11, modifiers: HotkeyChord.commandModifier, keyLabel: "B").payload,
               forKey: "hades2.shortcut.action.forceLegendary")
v8Defaults.set(HotkeyChord(keyCode: 8, modifiers: HotkeyChord.commandModifier, keyLabel: "C").payload,
               forKey: "hades2.shortcut.action.forceDuo")
let migratedV8 = Hades2ShortcutStore(defaults: v8Defaults)
precondition(v8Defaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion)
precondition(v8Defaults.object(forKey: "hades2.shortcut.action.forceLegendary") == nil)
precondition(v8Defaults.object(forKey: "hades2.shortcut.action.forceDuo") == nil)
precondition(migratedV8.chord(.infiniteHealth) == v8HealthChord)
precondition(migratedV8.chord(.openSellTraits) == Hades2ShortcutStore.defaultLayout()[.openSellTraits])
precondition(unique(migratedV8))
let futureStoreDefaults = makeDefaults()
futureStoreDefaults.set(Hades2ShortcutStore.currentLayoutVersion + 1, forKey: "hades2.shortcut.layoutVersion")
futureStoreDefaults.set(v8HealthChord.payload, forKey: shortcutKey(.infiniteHealth))
futureStoreDefaults.set(HotkeyChord(keyCode: 11, modifiers: HotkeyChord.commandModifier, keyLabel: "B").payload,
                        forKey: "hades2.shortcut.action.forceLegendary")
let _ = Hades2ShortcutStore(defaults: futureStoreDefaults)
precondition(futureStoreDefaults.integer(forKey: "hades2.shortcut.layoutVersion") == Hades2ShortcutStore.currentLayoutVersion + 1)
precondition(futureStoreDefaults.object(forKey: "hades2.shortcut.action.forceLegendary") != nil,
             "future shortcut schema must not be modified or cleaned up")

// Legacy Profiles containing retired forceLegendary/forceDuo keys still import cleanly.
var retiredKeyProfileStore = Hades2ShortcutStore(defaults: makeDefaults())
precondition(retiredKeyProfileStore.applyProfile([
    "_layoutVersion": 1,
    "forceLegendary": HotkeyChord(keyCode: 11, modifiers: HotkeyChord.commandModifier, keyLabel: "B").payload,
    "forceDuo": HotkeyChord(keyCode: 8, modifiers: HotkeyChord.commandModifier, keyLabel: "C").payload,
    "infiniteHealth": v8HealthChord.payload,
]) == .applied)
precondition(retiredKeyProfileStore.chord(.infiniteHealth) == v8HealthChord)

// Generic Core TrainerShortcutStore<Action> works for non-game action enums with namespaced keys.
enum SampleShortcutAction: String, CaseIterable, Hashable {
    case alpha, beta, disableAll
}
let sampleDefaultsLayout = TrainerHotkeyLayout.defaultLayout(
    orderedActions: SampleShortcutAction.allCases,
    dedicated: [.disableAll: TrainerHotkeyLayout.disableAllChord]
)
let samplePrefs = makeDefaults()
var sampleStore = TrainerShortcutStore<SampleShortcutAction>(
    orderedActions: SampleShortcutAction.allCases,
    defaultLayout: sampleDefaultsLayout,
    lockedActions: [.disableAll: TrainerHotkeyLayout.disableAllChord],
    storage: TrainerShortcutStorage(
        moduleID: "sample",
        defaults: samplePrefs
    )
)
let sampleCustom = HotkeyChord(keyCode: 8, modifiers: HotkeyChord.commandModifier, keyLabel: "C")
precondition(sampleStore.set(.alpha, chord: sampleCustom) == nil)
precondition(samplePrefs.object(forKey: "sample.shortcut.alpha") != nil)
precondition(sampleStore.set(.beta, chord: sampleCustom) == .alpha)
precondition(sampleStore.set(.alpha, chord: sampleDefaultsLayout[.alpha]!) == nil)
precondition(samplePrefs.object(forKey: "sample.shortcut.alpha") == nil, "setting default chord should elide override")

print("shortcut_chord_semantics_ok")
'''

with tempfile.TemporaryDirectory() as td:
    main = Path(td) / 'main.swift'
    main.write_text(harness)
    binary = Path(td) / 'shortcut-test'
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only these
    # Foundation-level files.
    compile_swift_test(
        modules=[
            SwiftModule(SWIFT_CORE_MODULE, [
                ROOT / 'Sources/Core/Input/HotkeyChord.swift',
                ROOT / 'Sources/Core/Input/TrainerShortcutStore.swift',
                ROOT / 'Sources/Core/UI/TrainerSemanticIcon.swift',
                ROOT / 'Sources/Core/Cheats/TrainerCheatDefinition.swift',
                ROOT / 'Sources/Core/UI/TrainerWorkbenchSearch.swift',
            ]),
            SwiftModule('Hades2', [
                ROOT / 'Sources/Hades2/Generated/Hades2Feature.generated.swift',
                ROOT / 'Sources/Hades2/Hades2Types.swift',
                ROOT / 'Sources/Hades2/Hades2Cheats.swift',
                ROOT / 'Sources/Hades2/Services/Hades2WorkbenchNavigation.swift',
                ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift',
            ], (SWIFT_CORE_MODULE,)),
        ],
        harness_sources=[ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift', main],
        output=binary, flags=(), swiftc=swiftc, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True)
