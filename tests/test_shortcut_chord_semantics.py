import shutil
import subprocess
import tempfile
from pathlib import Path

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
precondition(HotkeyChord.controlOptionDefault(index: 9)?.displayText == "⌃⌥A", "legacy v4 defaults must remain frozen")
precondition(HotkeyChord.defaultShortcut(index: HotkeyChord.defaultShortcutCapacity) == nil)
let generatedDefaults = (0..<HotkeyChord.defaultShortcutCapacity).compactMap(HotkeyChord.defaultShortcut(index:))
precondition(Set(generatedDefaults.map { "\($0.keyCode):\($0.modifiers)" }).count == HotkeyChord.defaultShortcutCapacity)

// InMemoryDefaults (tests/fixtures/swift) keeps this harness off the real
// preferences directory; a real suite there cannot be cleaned up afterwards.
func makeDefaults() -> UserDefaults { InMemoryDefaults() }

func unique(_ store: Hades2ShortcutStore) -> Bool {
    let values = ShortcutAction.allCases.map { "\(store.chord($0).keyCode):\(store.chord($0).modifiers)" }
    return Set(values).count == values.count
}



func shortcutKey(_ action: ShortcutAction) -> String {
    "shortcut.action.\(action.rawValue)"
}

func legacyShortcutKey(_ identity: String) -> String {
    "shortcut.action.\(identity == "invincibility" ? "godMode" : identity)"
}

func legacyShortcutKey(_ action: ShortcutAction) -> String {
    action == .invincibility ? "shortcut.action.godMode" : shortcutKey(action)
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
        HotkeyChord.controlOptionDefault(index: index).map { (action, $0) }
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
// reassignment. Valid non-reserved explicit overrides remain in place.
let savedPreferences = makeDefaults()
savedPreferences.set(6, forKey: "shortcut.layoutVersion")
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

var imported = Hades2ShortcutStore(defaults: makeDefaults())
let applied = imported.applyProfile([
    "_layoutVersion": 1,
    "disableAll": unrelatedChord.payload,
    "spawnPickup": samePhysical.payload,
    "infiniteHealth": custom.payload,
])
precondition(applied == .applied)
precondition(imported.chord(.disableAll) == disableAllDefault)
precondition(imported.chord(.infiniteHealth) == custom)
precondition(imported.payload()["disableAll"] == nil && imported.payload()["spawnPickup"] == nil)
precondition(unique(imported))

precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":Int(UInt32.max)+1,"keyLabel":"1"]) == nil)
precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":1,"keyLabel":"1"]) == nil)
precondition(HotkeyChord(payload: ["keyCode":18,"modifiers":6144,"keyLabel":"\n"]) == nil)
print("shortcut_chord_semantics_ok")
'''

with tempfile.TemporaryDirectory() as td:
    main = Path(td) / 'main.swift'
    main.write_text(harness)
    binary = Path(td) / 'shortcut-test'
    subprocess.run([
        swiftc,
        str(ROOT / 'Sources/Core/Input/HotkeyChord.swift'),
        str(ROOT / 'Sources/Core/UI/TrainerSemanticIcon.swift'),
        str(ROOT / 'Sources/Core/UI/TrainerWorkbenchSearch.swift'),
        str(ROOT / 'Sources/Hades2/Generated/Hades2Feature.generated.swift'),
        str(ROOT / 'Sources/Hades2/Hades2Types.swift'),
        str(ROOT / 'Sources/Hades2/Services/Hades2WorkbenchNavigation.swift'),
        str(ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift'),
        str(ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift'),
        str(main), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
