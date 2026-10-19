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
precondition(ShortcutAction.allCases.count <= 35, "default shortcut namespace 1-9/A-Z is exhausted")
precondition(Hades2ShortcutStore.defaultLayout().count == ShortcutAction.allCases.count)
precondition(ShortcutAction.allCases.last == .disableAll)

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

func legacyShortcutKey(_ action: ShortcutAction) -> String {
    action == .invincibility ? "shortcut.action.godMode" : shortcutKey(action)
}

func seedV3Defaults(_ defaults: UserDefaults, invincibilityOverride: Int? = nil) {
    defaults.set(3, forKey: "shortcut.layoutVersion")
    let legacy: [ShortcutAction: Int] = [
        .invincibility: 1, .infiniteHealth: 2, .infiniteMana: 3, .instantCastCooldown: 4,
        .hexAlwaysReady: 5, .infiniteAmmo: 6, .damageEnabled: 7, .autoMiniGames: 8,
        .moneyMultiplierEnabled: 9, .disableAll: 0,
    ]
    for (action, digit) in legacy {
        defaults.set(action == .invincibility ? (invincibilityOverride ?? digit) : digit, forKey: legacyShortcutKey(action))
    }
}

let legacyV4Order: [ShortcutAction] = [
    .invincibility, .infiniteHealth, .infiniteMana, .instantCastCooldown, .hexAlwaysReady,
    .infiniteAmmo, .damageEnabled, .autoMiniGames, .gardenQoL, .boonRarityEnabled,
    .forceEnableRerolls, .forceLegendary, .forceDuo, .moneyMultiplierEnabled,
    .resourceMultiplierEnabled, .spawnOlympian, .spawnPickup, .spawnSpecial,
    .applyNextRoomReward, .disableAll,
]

func legacyV4DefaultLayout() -> [ShortcutAction: HotkeyChord] {
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
    defaults.set(clean[.moneyMultiplierEnabled]!.payload, forKey: legacyShortcutKey(.gardenQoL))
    defaults.set(HotkeyChord.controlOptionDigit(9)!.payload, forKey: legacyShortcutKey(.moneyMultiplierEnabled))
    defaults.set(HotkeyChord.controlOptionDigit(0)!.payload, forKey: legacyShortcutKey(.disableAll))
}

let migratedV3DefaultsStore = makeDefaults()
seedV3Defaults(migratedV3DefaultsStore)
let migratedV3Defaults = Hades2ShortcutStore(defaults: migratedV3DefaultsStore)
func matchesDerivedDefaults(_ store: Hades2ShortcutStore) -> Bool {
    ShortcutAction.allCases.enumerated().allSatisfy { index, action in
        guard let expected = HotkeyChord.controlOptionDefault(index: index) else { return false }
        return store.chord(action) == expected
    }
}

precondition(matchesDerivedDefaults(migratedV3Defaults))

let migratedV3CustomStore = makeDefaults()
seedV3Defaults(migratedV3CustomStore, invincibilityOverride: 0)
let migratedV3Custom = Hades2ShortcutStore(defaults: migratedV3CustomStore)
precondition(migratedV3Custom.chord(.invincibility).keyLabel == "0")
precondition(migratedV3Custom.chord(.infiniteHealth).keyLabel == "2")
precondition(migratedV3Custom.chord(.gardenQoL).keyLabel == "9")
precondition(migratedV3Custom.chord(.moneyMultiplierEnabled).keyLabel == "E")
precondition(migratedV3Custom.chord(.disableAll).keyLabel == "T")
precondition(unique(migratedV3Custom))

let brokenV4Store = makeDefaults()
seedKnownBrokenV4Defaults(brokenV4Store)
let repairedV4 = Hades2ShortcutStore(defaults: brokenV4Store)
precondition(matchesDerivedDefaults(repairedV4))

let defaults = Hades2ShortcutStore(defaults: makeDefaults())
precondition(matchesDerivedDefaults(defaults))
precondition(unique(defaults))
precondition(defaults.chord(.generateFlora) == HotkeyChord.controlOptionDefault(index: ShortcutAction.allCases.firstIndex(of: .generateFlora)!)!)
precondition(defaults.chord(.generateFishing) == HotkeyChord.controlOptionDefault(index: ShortcutAction.allCases.firstIndex(of: .generateFishing)!)!)
precondition(defaults.chord(.applyNextOccurrence) == HotkeyChord.controlOptionDefault(index: ShortcutAction.allCases.firstIndex(of: .applyNextOccurrence)!)!)
precondition(defaults.chord(.disableAll).keyLabel == "T")

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
        str(ROOT / 'Sources/Hades2/Generated/Hades2Feature.generated.swift'),
        str(ROOT / 'Sources/Hades2/Hades2Types.swift'),
        str(ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift'),
        str(ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift'),
        str(main), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
