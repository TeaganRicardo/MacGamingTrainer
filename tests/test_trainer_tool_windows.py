"""Native tool-window reuse and close ownership with isolated content."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != "darwin":
    raise SystemExit("macOS-only native tool-window test")
ROOT = Path(__file__).resolve().parents[1]
SWIFT = shutil.which("swiftc")
assert SWIFT

HARNESS = r'''
import AppKit
import SwiftUI

@main
struct Main {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        let store = TrainerToolWindowStore()
        var factories = 0
        var closed: [String] = []
        var allowFirstClose = false
        let first = store.open(id: "first", title: "First", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(canClose: { allowFirstClose }, onClose: { closed.append("first") }) {
                Text("first draft").frame(width: 450, height: 300)
            }
        }
        let originalContent = first.contentView
        let reused = store.open(id: "first", title: "First", localization: localization, theme: .standard) {
            fatalError("Reopening an existing entry recreated its document")
        }
        precondition(first === reused && first.contentView === originalContent)
        let second = store.open(id: "second", title: "Second", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(onClose: { closed.append("second") }) {
                Text("second draft").frame(width: 400, height: 250)
            }
        }
        precondition(first !== second && factories == 2)
        precondition(first.sheetParent == nil && second.sheetParent == nil)
        precondition(first.isVisible && second.isVisible)
        first.performClose(nil)
        precondition(first.isVisible && closed.isEmpty, "busy tools must retain their native window")
        allowFirstClose = true
        first.performClose(nil)
        precondition(closed == ["first"] && second.isVisible, "closing one tool closed another tool")
        let reopened = store.open(id: "first", title: "Fresh", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(onClose: { closed.append("fresh") }) {
                Text("fresh document").frame(width: 450, height: 300)
            }
        }
        precondition(reopened !== first && factories == 3, "a closed entry retained its prior document")
        second.performClose(nil)
        reopened.performClose(nil)
        precondition(closed == ["first", "second", "fresh"])
        print("trainer_tool_windows_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-tool-windows-") as directory:
    root = Path(directory)
    main = root / "main.swift"
    main.write_text(HARNESS)
    binary = root / "windows"
    sources = ["Sources/Core/Runtime/TrainerJSON.swift", "Sources/Core/Runtime/BackendProcess.swift", "Sources/Core/Runtime/BackendClient.swift",
               "Sources/Core/Host/TrainerLocalization.swift", "Sources/Core/UI/TrainerTheme.swift",
               "Sources/Core/UI/TrainerToolWindows.swift", "tests/fixtures/swift/InMemoryDefaults.swift"]
    subprocess.run([SWIFT, "-parse-as-library", *[str(ROOT / path) for path in sources],
                    str(main), "-o", str(binary)], check=True)
    env = dict(os.environ, HOME=str(root / "home"))
    (root / "home").mkdir()
    result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "trainer_tool_windows_ok" in result.stdout
    print(result.stdout.strip())
