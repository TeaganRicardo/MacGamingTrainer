import shutil
import subprocess
import tempfile
from pathlib import Path
from swift_test_compiler import SWIFT_CORE_MODULE, SwiftModule, compile_swift_test

ROOT = Path(__file__).resolve().parents[1]
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required for invincibility shortcut migration test")

harness = r"""
import Foundation

// InMemoryDefaults (tests/fixtures/swift) keeps this harness off the real
// preferences directory; a real suite there cannot be cleaned up afterwards.
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
    # Portable: the Linux lane has no SwiftUI/AppKit, so this compiles only these
    # Foundation-level files.
    compile_swift_test(
        modules=[
            SwiftModule(SWIFT_CORE_MODULE, [
                ROOT / "Sources/Core/Input/HotkeyChord.swift",
                ROOT / "Sources/Core/UI/TrainerSemanticIcon.swift",
                ROOT / "Sources/Core/UI/TrainerWorkbenchSearch.swift",
            ]),
            SwiftModule("Hades2", [
                ROOT / "Sources/Hades2/Generated/Hades2Feature.generated.swift",
                ROOT / "Sources/Hades2/Hades2Types.swift",
                ROOT / "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift",
                ROOT / "Sources/Hades2/Services/Hades2ShortcutStore.swift",
            ], (SWIFT_CORE_MODULE,)),
        ],
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", main],
        output=binary, flags=(), swiftc=swiftc, cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True)
