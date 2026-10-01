import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required for invincibility shortcut migration test")

harness = r"""
import Foundation

// The store only needs the UserDefaults surface, so the harness injects an
// in-memory implementation. A real `UserDefaults(suiteName:)` here would
// materialize an `mgt.invincibility.shortcut.*` plist in the user's
// ~/Library/Preferences on every run: cfprefsd keeps an empty domain file
// behind even after removePersistentDomain, so cleanup cannot undo it.
final class InMemoryDefaults: UserDefaults {
    private var storage: [String: Any] = [:]
    override func object(forKey defaultName: String) -> Any? { storage[defaultName] }
    override func string(forKey defaultName: String) -> String? { storage[defaultName] as? String }
    override func set(_ value: Any?, forKey defaultName: String) { storage[defaultName] = value }
    override func removeObject(forKey defaultName: String) { storage.removeValue(forKey: defaultName) }
    override func integer(forKey defaultName: String) -> Int { storage[defaultName] as? Int ?? 0 }
}

let defaults = InMemoryDefaults()
defaults.set(5, forKey: "shortcut.layoutVersion")

let legacy = HotkeyChord(
    keyCode: 7,
    modifiers: HotkeyChord.commandModifier | HotkeyChord.shiftModifier,
    keyLabel: "X"
)
defaults.set(legacy.payload, forKey: "shortcut.action.godMode")

let store = Hades2ShortcutStore(defaults: defaults)
precondition(store.chord(.invincibility) == legacy)
precondition(defaults.integer(forKey: "shortcut.layoutVersion") == 6)
precondition(defaults.object(forKey: "shortcut.action.godMode") == nil)
precondition(defaults.object(forKey: "shortcut.action.invincibility") != nil)
precondition(store.payload()["invincibility"] != nil)
precondition(store.payload()["godMode"] == nil)

print("invincibility_shortcut_migration_ok")
"""

with tempfile.TemporaryDirectory(prefix="mgt-invincibility-shortcut-") as td:
    main = Path(td) / "main.swift"
    main.write_text(harness, encoding="utf-8")
    binary = Path(td) / "shortcut-migration-test"
    subprocess.run([
        swiftc,
        str(ROOT / "Sources/Core/Input/HotkeyChord.swift"),
        str(ROOT / "Sources/Hades2/Hades2Types.swift"),
        str(ROOT / "Sources/Hades2/Services/Hades2ShortcutStore.swift"),
        str(main),
        "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
