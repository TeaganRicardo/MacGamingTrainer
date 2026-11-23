"""Verify D4 in Hades I: Profiles save and restore shortcuts while older profiles keep bindings unchanged."""

MGT_PLATFORM = "macos"
MGT_INPUTS = (
    "Sources/Core/",
    "Sources/Hades/",
)

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from swift_test_compiler import compile_swift_test

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades I Profile shortcut parity test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

WORKER = r'''
import json, pathlib, sys
log_path = pathlib.Path(__file__).with_suffix(".commands.jsonl")
state_path = pathlib.Path(__file__).with_suffix(".state.json")

for raw in sys.stdin:
    req = json.loads(raw)
    cmd = req["command"]
    params = req.get("params", {})
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(req, sort_keys=True) + "\n")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if cmd == "save_profile":
        state.setdefault("profiles", {})[params["name"]] = {
            "shortcuts": params.get("shortcuts"),
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
        result = {
            "profiles": [{"name": name, "updatedAt": "2026-11-23T00:00:00+00:00"} for name in sorted(state["profiles"])],
        }
    elif cmd == "load_profile":
        entry = state.get("profiles", {}).get(params["name"], {})
        result = dict(state["baseState"])
        result["profiles"] = [{"name": name, "updatedAt": "2026-11-23T00:00:00+00:00"} for name in sorted(state.get("profiles", {}))]
        if "shortcuts" in entry and entry["shortcuts"] is not None:
            result["shortcuts"] = entry["shortcuts"]
    else:
        result = {} if cmd == "catalog" else dict(state["baseState"])
    print(json.dumps({
        "type": "result",
        "id": req["id"],
        "protocolVersion": 6,
        "moduleProtocolVersion": MODULE_VERSION,
        "gameID": "hades",
        "ok": True,
        "result": result,
    }), flush=True)
'''

HARNESS = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fail(message) }
}

func wait(_ message: String, timeout: TimeInterval = 4, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))
    }
    check(condition(), message)
}

@MainActor
@main struct HadesProfileShortcutsMain {
    static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
        let defaults = InMemoryDefaults()
        let session = TrainerBackendSession(client: BackendClient(process:
            BackendProcess(executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        let model = makeFixtureModel(HadesGameModule.self, session: session,
            logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("test.log")),
            backendScriptURL: worker) {
            HadesTrainerModel(services: $0, defaults: defaults)
        }
        defer { session.stop(suppressTerminationError: true) }

        wait("backend ready") { model.backendAvailable && !model.busy }
        let defaultChord = HadesShortcutAction.invincibility.defaultChord
        let customChord = HotkeyChord(
            keyCode: 99,
            modifiers: HotkeyChord.controlModifier | HotkeyChord.commandModifier,
            keyLabel: "F3"
        )
        check(model.setShortcut(.invincibility, chord: customChord) == .applied, "failed to customize shortcut")
        check(model.shortcutText(.invincibility) == customChord.displayText, "custom shortcut text did not update")

        // 1. Save Profile captures the custom shortcut snapshot, and reset/load restores it.
        var saveResult: Bool?
        model.saveProfile("CustomKeys") { ok in saveResult = ok }
        wait("saveProfile did not complete") { saveResult == true && !model.busy }
        model.resetShortcuts()
        check(model.shortcutText(.invincibility) == defaultChord.displayText, "reset did not restore default")

        model.loadProfile("CustomKeys")
        wait("loadProfile did not restore shortcuts") {
            !model.busy && model.shortcutText(.invincibility) == customChord.displayText
        }
        let requests = try String(contentsOf: commandLog, encoding: .utf8)
            .split(separator: "\n")
            .compactMap { line -> [String: Any]? in
                guard let data = line.data(using: .utf8) else { return nil }
                return try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            }
        let saveReq = requests.first { ($0["command"] as? String) == "save_profile" }
        let sentShortcuts = (saveReq?["params"] as? [String: Any])?["shortcuts"] as? [String: Any]
        check(sentShortcuts?["_layoutVersion"] as? Int == 1 && sentShortcuts?["invincibility"] != nil,
              "save_profile omitted versioned shortcut payload")

        // 2. Legacy Hades I Profile without shortcuts (or empty {}) leaves current bindings intact (D4).
        model.loadProfile("LegacyEmpty")
        wait("legacy load finished") { !model.busy }
        check(model.shortcutText(.invincibility) == customChord.displayText,
              "legacy Hades I Profile without shortcuts reset existing bindings")

        // 3. Unsupported future _layoutVersion warns without disturbing existing shortcuts.
        model.loadProfile("FutureLayout")
        wait("future layout warning not surfaced") {
            !model.busy && model.profileShortcutWarning?.key == "hades.error.profileShortcutLayoutUnsupported"
        }
        check(model.profileShortcutWarning?.arguments == ["9"], "wrong layout version argument")
        check(model.shortcutText(.invincibility) == customChord.displayText,
              "unsupported shortcut layout version altered active bindings")
        model.clearProfileShortcutWarning()
        check(model.profileShortcutWarning == nil, "warning did not clear")

        print("hades_profile_shortcuts_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-profile-shortcuts-") as td:
    folder = Path(td)
    worker_path = folder / "worker.py"
    module_ver = json.loads((ROOT / "Backend/games/hades/module.json").read_text())["protocolVersion"]
    worker_path.write_text(WORKER.replace("MODULE_VERSION", str(module_ver)), encoding="utf-8")
    worker_path.with_suffix(".state.json").write_text(
        json.dumps(
            {
                "baseState": {
                    "connected": False,
                    "pid": None,
                    "heroReady": False,
                    "health": None,
                    "maxHealth": None,
                    "money": None,
                    "rerolls": None,
                    "target": None,
                },
                "profiles": {
                    "LegacyEmpty": {"shortcuts": {}},
                    "FutureLayout": {
                        "shortcuts": {
                            "_layoutVersion": 9,
                            "invincibility": {"keyCode": 18, "modifiers": 6144, "keyLabel": "1"},
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    main_path = folder / "main.swift"
    main_path.write_text(HARNESS, encoding="utf-8")
    binary = folder / "hades-profile-shortcuts"
    compile_swift_test(
        games=("hades",),
        harness_sources=[
            ROOT / "tests/fixtures/swift/TrainerBackendFixture.swift",
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            main_path,
        ],
        output=binary,
        cwd=ROOT,
    )
    result = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "hades_profile_shortcuts_ok" in result.stdout, result.stdout
    print(result.stdout.strip())
