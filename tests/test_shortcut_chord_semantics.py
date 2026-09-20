from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
swiftc = shutil.which('swiftc')
if not swiftc:
    print('shortcut_chord_semantics_skipped_no_swiftc')
    raise SystemExit(0)

harness = r'''
import Foundation

precondition(ShortcutAction.uiOrder.count == ShortcutAction.allCases.count)
precondition(Set(ShortcutAction.uiOrder.map(\.rawValue)) == Set(ShortcutAction.allCases.map(\.rawValue)))
precondition(Set(ShortcutAction.uiOrder.map(\.rawValue)).count == ShortcutAction.uiOrder.count)
precondition(ShortcutAction.uiOrder.count <= 35, "default shortcut namespace 1-9/A-Z is exhausted")


func makeDefaults(_ suffix: String) -> UserDefaults {
    let suite = "mgt.shortcut.tests.\(suffix).\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defaults.removePersistentDomain(forName: suite)
    return defaults
}

func unique(_ store: Hades2ShortcutStore) -> Bool {
    let values = ShortcutAction.uiOrder.map { "\(store.chord($0).keyCode):\(store.chord($0).modifiers)" }
    return Set(values).count == values.count
}



func shortcutKey(_ action: ShortcutAction) -> String {
    "shortcut.action.\(action.rawValue)"
}

func seedV3Defaults(_ defaults: UserDefaults, godModeOverride: Int? = nil) {
    defaults.set(3, forKey: "shortcut.layoutVersion")
    let legacy: [ShortcutAction: Int] = [
        .godMode: 1, .infiniteHealth: 2, .infiniteMana: 3, .instantCastCooldown: 4,
        .hexAlwaysReady: 5, .infiniteAmmo: 6, .damageEnabled: 7, .autoMiniGames: 8,
        .moneyMultiplierEnabled: 9, .disableAll: 0,
    ]
    for (action, digit) in legacy {
        defaults.set(action == .godMode ? (godModeOverride ?? digit) : digit, forKey: shortcutKey(action))
    }
}

func seedKnownBrokenV4Defaults(_ defaults: UserDefaults) {
    defaults.set(4, forKey: "shortcut.layoutVersion")
    let clean = Hades2ShortcutStore.defaultLayout()
    for action in ShortcutAction.uiOrder {
        defaults.set(clean[action]!.payload, forKey: shortcutKey(action))
    }
    defaults.set(clean[.moneyMultiplierEnabled]!.payload, forKey: shortcutKey(.gardenQoL))
    defaults.set(HotkeyChord.controlOptionDigit(9)!.payload, forKey: shortcutKey(.moneyMultiplierEnabled))
    defaults.set(HotkeyChord.controlOptionDigit(0)!.payload, forKey: shortcutKey(.disableAll))
}

let migratedV3DefaultsStore = makeDefaults("migrated-v3-defaults")
seedV3Defaults(migratedV3DefaultsStore)
let migratedV3Defaults = Hades2ShortcutStore(defaults: migratedV3DefaultsStore)
precondition(ShortcutAction.uiOrder.map { migratedV3Defaults.chord($0).keyLabel } ==
    ["1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J"])

let migratedV3CustomStore = makeDefaults("migrated-v3-custom")
seedV3Defaults(migratedV3CustomStore, godModeOverride: 0)
let migratedV3Custom = Hades2ShortcutStore(defaults: migratedV3CustomStore)
precondition(migratedV3Custom.chord(.godMode).keyLabel == "0")
precondition(migratedV3Custom.chord(.infiniteHealth).keyLabel == "2")
precondition(migratedV3Custom.chord(.gardenQoL).keyLabel == "9")
precondition(migratedV3Custom.chord(.moneyMultiplierEnabled).keyLabel == "D")
precondition(migratedV3Custom.chord(.disableAll).keyLabel == "J")
precondition(unique(migratedV3Custom))

let brokenV4Store = makeDefaults("broken-v4-defaults")
seedKnownBrokenV4Defaults(brokenV4Store)
let repairedV4 = Hades2ShortcutStore(defaults: brokenV4Store)
precondition(ShortcutAction.uiOrder.map { repairedV4.chord($0).keyLabel } ==
    ["1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J"])

let defaults = Hades2ShortcutStore(defaults: makeDefaults("defaults"))
precondition(ShortcutAction.uiOrder.map { defaults.chord($0).keyLabel } ==
    ["1","2","3","4","5","6","7","8","9","A","B","C","D","E","F","G","H","I","J"])
precondition(unique(defaults))
precondition(defaults.chord(.spawnOlympian).keyLabel == "F")
precondition(defaults.chord(.spawnPickup).keyLabel == "G")
precondition(defaults.chord(.spawnSpecial).keyLabel == "H")
precondition(defaults.chord(.applyNextRoomReward).keyLabel == "I")
precondition(defaults.chord(.disableAll).keyLabel == "J")

var full = Hades2ShortcutStore(defaults: makeDefaults("full"))
var profile = full.payload()
profile[ShortcutAction.godMode.rawValue] = full.chord(.infiniteHealth).payload
profile[ShortcutAction.infiniteHealth.rawValue] = full.chord(.godMode).payload
full.applyProfile(profile)
precondition(full.chord(.godMode).keyLabel == "2" && full.chord(.infiniteHealth).keyLabel == "1")
precondition(unique(full))

var partial = Hades2ShortcutStore(defaults: makeDefaults("partial"))
let wanted = partial.chord(.infiniteHealth)
partial.applyProfile([ShortcutAction.godMode.rawValue: wanted.payload])
precondition(partial.chord(.godMode) == wanted && partial.chord(.infiniteHealth) != wanted)
precondition(unique(partial))

var partialWithExistingOverride = Hades2ShortcutStore(defaults: makeDefaults("partial-existing-override"))
let custom = HotkeyChord(keyCode: 18, modifiers: HotkeyChord.commandModifier, keyLabel: "1")
precondition(partialWithExistingOverride.set(.infiniteHealth, chord: custom) == nil)
partialWithExistingOverride.applyProfile([ShortcutAction.godMode.rawValue: custom.payload])
precondition(partialWithExistingOverride.chord(.godMode) == custom)
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
        str(ROOT / 'Sources/Hades2/Hades2Types.swift'),
        str(ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift'),
        str(main), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
