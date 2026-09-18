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

enum ShortcutAction: String, CaseIterable, Identifiable {
    case godMode, infiniteHealth, infiniteMana, instantCastCooldown, hexAlwaysReady
    case infiniteAmmo, damageEnabled, autoMiniGames, gardenQoL
    case boonRarityEnabled, forceLegendary, forceDuo
    case moneyMultiplierEnabled, resourceMultiplierEnabled
    case applyNextRoomReward, spawnOlympian, spawnPickup, spawnSpecial
    case disableAll
    var id: String { rawValue }
    static let uiOrder: [ShortcutAction] = [
        .godMode,.infiniteHealth,.infiniteMana,.instantCastCooldown,.hexAlwaysReady,
        .infiniteAmmo,.damageEnabled,.autoMiniGames,.gardenQoL,
        .boonRarityEnabled,.forceLegendary,.forceDuo,
        .moneyMultiplierEnabled,.resourceMultiplierEnabled,
        .spawnOlympian,.spawnPickup,.spawnSpecial,.applyNextRoomReward,.disableAll,
    ]
    static let legacyDigitActions: [ShortcutAction] = [
        .godMode,.infiniteHealth,.infiniteMana,.instantCastCooldown,.hexAlwaysReady,
        .infiniteAmmo,.damageEnabled,.autoMiniGames,.moneyMultiplierEnabled,.disableAll,
    ]
    var title: String { rawValue }
}

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
        str(ROOT / 'Sources/Hades2/Services/Hades2ShortcutStore.swift'),
        str(main), '-o', str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
