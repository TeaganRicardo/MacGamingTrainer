"""Hades I 21-shortcut catalog, conflict/reflow rules, bilingual labels, and room-shortcut dispatch."""

MGT_PLATFORM = "macos"

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from swift_test_compiler import compile_swift_test

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades I shortcut/workbench semantics")

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
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(req, sort_keys=True) + "\n")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if cmd == "apply_world_exit":
        params = req.get("params", {})
        state["world"]["doors"][0]["activeLease"] = {
            "kind": params["kind"],
            "target": params["targetID"],
            "leaseToken": "lease-exit-1",
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
    elif cmd == "cancel_world_exit":
        state["world"]["doors"][0]["activeLease"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
    elif cmd == "apply_world_occurrence":
        params = req.get("params", {})
        state["world"]["occurrence"] = {
            "target": params["targetID"],
            "leaseToken": "lease-occ-1",
        }
        state_path.write_text(json.dumps(state), encoding="utf-8")
    elif cmd == "cancel_world_occurrence":
        state["world"]["occurrence"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")
    reply = {
        "type": "result",
        "id": req["id"],
        "protocolVersion": 6,
        "moduleProtocolVersion": MODULE_VERSION,
        "gameID": "hades",
        "ok": True,
        "result": {} if cmd == "catalog" else state,
    }
    print(json.dumps(reply), flush=True)
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

func pump(_ seconds: TimeInterval = 0.05) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func wait(_ message: String, timeout: TimeInterval = 4, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline { pump(0.02) }
    check(condition(), message)
}

@MainActor
@main struct HadesShortcutSemanticsMain {
    static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
        let stateURL = worker.deletingPathExtension().appendingPathExtension("state.json")

        // 1. Catalog order, derived defaults, conflict refusal, disableAll lock, and reflow.
        let ordered = HadesWorkbenchCatalog.orderedShortcutActions
        check(ordered.count == 21 && Set(ordered).count == 21, "expected 21 distinct Hades shortcuts")
        check(ordered.last == .disableAll, "disableAll must stay last in registry")
        let expectedRooms: [HadesShortcutAction] = [
            .applyWorldExit, .applyWorldOccurrence, .generateChamberObject, .generateChaosGate,
            .spawnOlympian, .spawnPickup, .spawnSpecial,
        ]
        check(HadesWorkbenchCatalog.shortcutActions(in: .rooms) == expectedRooms,
              "rooms shortcuts must match visible workbench order")

        let defaultLayout = HadesShortcutStore.defaultLayout()
        check(defaultLayout[.disableAll] == TrainerHotkeyLayout.disableAllChord,
              "disableAll default chord drifted from Control+Option+Backspace")
        check(defaultLayout[.generateFishing]?.displayText == "⌃⌥Q", "fishing should remain Ctrl+Opt+Q")
        check(defaultLayout[.applyWorldExit]?.displayText == "⌃⌥W", "applyWorldExit default chord")
        check(defaultLayout[.applyWorldOccurrence]?.displayText == "⌃⌥E", "applyWorldOccurrence default chord")
        check(defaultLayout[.generateChamberObject]?.displayText == "⌃⌥R", "generateChamberObject default chord")
        check(defaultLayout[.generateChaosGate]?.displayText == "⌃⌥T", "generateChaosGate default chord")
        check(defaultLayout[.spawnOlympian]?.displayText == "⌃⌥Y", "spawnOlympian default chord")
        check(defaultLayout[.spawnPickup]?.displayText == "⌃⌥U", "spawnPickup default chord")
        check(defaultLayout[.spawnSpecial]?.displayText == "⌃⌥I", "spawnSpecial default chord")
        check(Set(defaultLayout.values.map(TrainerHotkeyLayout.identity)).count == 21,
              "default chords collided")

        // Stale stored disableAll override or collision with another action is evicted cleanly.
        let seededDefaults = InMemoryDefaults()
        let customX = HotkeyChord(keyCode: 7, modifiers: HotkeyChord.commandModifier, keyLabel: "X")
        seededDefaults.set(customX.payload, forKey: "hades.shortcut.disableAll")
        seededDefaults.set(TrainerHotkeyLayout.disableAllChord.payload, forKey: "hades.shortcut.applyWorldExit")
        seededDefaults.set(defaultLayout[.applyWorldOccurrence]!.payload, forKey: "hades.shortcut.generateChaosGate")
        var store = HadesShortcutStore(defaults: seededDefaults)
        check(store.chord(.disableAll) == TrainerHotkeyLayout.disableAllChord,
              "retired disableAll override won registration")
        check(store.chord(.applyWorldExit) != TrainerHotkeyLayout.disableAllChord,
              "another action claimed disableAll chord")
        check(store.chord(.generateChaosGate) == defaultLayout[.applyWorldOccurrence],
              "valid override for generateChaosGate lost during reflow")
        check(store.chord(.applyWorldOccurrence) != store.chord(.generateChaosGate),
              "reflow failed to move applyWorldOccurrence away from custom collision")
        check(store.set(.disableAll, chord: customX) == .disableAll,
              "disableAll accepted rebinding")
        check(store.set(.generateChamberObject, chord: TrainerHotkeyLayout.disableAllChord) == .disableAll,
              "reserved disableAll chord was reassigned")
        check(store.set(.generateChamberObject, chord: defaultLayout[.applyWorldExit]!) == .applyWorldExit,
              "conflicting assignment did not identify owning action")
        store.reset()
        check(store.chord(.generateChaosGate) == defaultLayout[.generateChaosGate],
              "reset did not restore derived layout")

        // 2. Active-language-first label resolution on HadesWorldReward (no "Zh · En" in English UI).
        let reward = HadesWorldReward(
            id: "ZeusUpgrade",
            kind: "boon",
            names: ["zh-CN": "宙斯", "en": "Zeus"],
            doorAllowed: true,
            group: .olympian,
            section: "olympians",
            sectionNames: nil
        )
        check(reward.label(for: .en) == "Zeus", "EN reward label leaked Chinese: \(reward.label(for: .en))")
        check(reward.label(for: .zhCN) == "宙斯 · Zeus", "ZH reward label lost bilingual pairing: \(reward.label(for: .zhCN))")
        let sameNameReward = HadesWorldReward(
            id: "Same",
            kind: "special",
            names: ["zh-CN": "Chaos", "en": "Chaos"],
            doorAllowed: true,
            group: .special,
            section: "special",
            sectionNames: nil
        )
        check(sameNameReward.label(for: .zhCN) == "Chaos", "duplicate zh/en reward label repeated itself")

        // 3. Real HadesTrainerModel room shortcut dispatch & gating.
        let session = TrainerBackendSession(client: BackendClient(process:
            BackendProcess(executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        let model = HadesTrainerModel(session: session, backendScriptURL: worker,
                                      defaults: InMemoryDefaults(),
                                      logSink: TrainerLogSink(gameID: "hades"))
        wait("model backend ready") { model.backendAvailable && model.connected && !model.busy }
        check(model.selectedChamberObject == "trove" && model.canSelectChamberObject,
              "model did not select initial chamber object")

        func sentCommands() -> [[String: Any]] {
            guard let raw = try? String(contentsOf: commandLog, encoding: .utf8) else { return [] }
            return raw.split(separator: "\n").compactMap {
                try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
            }
        }

        // Dispatch generate_chamber_object via global shortcut on chosen object ("purge").
        model.selectedChamberObject = "purge"
        let beforeObject = sentCommands().count
        model.performShortcut(HadesShortcutAction.generateChamberObject.rawValue)
        wait("generateChamberObject shortcut dispatched") {
            !model.busy && sentCommands().count == beforeObject + 1
        }
        let objectCmd = sentCommands().last!
        check(objectCmd["command"] as? String == "generate_chamber_object"
              && (objectCmd["params"] as? [String: Any])?["object"] as? String == "purge"
              && (objectCmd["params"] as? [String: Any])?["roomId"] as? String == "run:room:1",
              "generateChamberObject shortcut sent wrong params: \(objectCmd)")

        // Dispatch apply_world_exit then cancel_world_exit on toggle via shortcut.
        let beforeExit = sentCommands().count
        model.performShortcut(HadesShortcutAction.applyWorldExit.rawValue)
        wait("applyWorldExit shortcut dispatched") {
            !model.busy && sentCommands().count == beforeExit + 1 && model.selectedWorldExitLease != nil
        }
        check(sentCommands().last?["command"] as? String == "apply_world_exit", "expected apply_world_exit")
        model.performShortcut(HadesShortcutAction.applyWorldExit.rawValue)
        wait("cancel_world_exit via shortcut") {
            !model.busy && sentCommands().count == beforeExit + 2 && model.selectedWorldExitLease == nil
        }
        check(sentCommands().last?["command"] as? String == "cancel_world_exit", "expected cancel_world_exit")

        // Dispatch apply_world_occurrence then cancel_world_occurrence via shortcut.
        let beforeOcc = sentCommands().count
        model.performShortcut(HadesShortcutAction.applyWorldOccurrence.rawValue)
        wait("applyWorldOccurrence shortcut dispatched") {
            !model.busy && sentCommands().count == beforeOcc + 1 && model.worldOccurrenceLease != nil
        }
        check(sentCommands().last?["command"] as? String == "apply_world_occurrence", "expected apply_world_occurrence")
        model.performShortcut(HadesShortcutAction.applyWorldOccurrence.rawValue)
        wait("cancel_world_occurrence via shortcut") {
            !model.busy && sentCommands().count == beforeOcc + 2 && model.worldOccurrenceLease == nil
        }
        check(sentCommands().last?["command"] as? String == "cancel_world_occurrence", "expected cancel_world_occurrence")

        // When room targets disappear, shortcuts refuse with warning without calling backend.
        var emptyState = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
        emptyState["world"] = [
            "roomId": "run:room:2", "doors": [], "canFish": false,
            "canChaos": false, "objects": [], "occurrenceTargets": [],
        ]
        try JSONSerialization.data(withJSONObject: emptyState).write(to: stateURL, options: .atomic)
        model.refreshFromHost()
        wait("empty room state observed") { !model.busy && model.world?.roomId == "run:room:2" }

        let beforeRefused = sentCommands().count
        for action in [HadesShortcutAction.applyWorldExit, .applyWorldOccurrence, .generateChamberObject] {
            model.performShortcut(action.rawValue)
            pump(0.03)
            let toneOK = model.feedback?.tone == .warning
            check(model.feedback?.text.key == "hades.shortcut.unavailable" && toneOK,
                  "unavailable shortcut \(action.rawValue) missed warning feedback")
        }
        check(sentCommands().count == beforeRefused, "refused room shortcut reached backend")

        session.stop(suppressTerminationError: true)
        print("hades_shortcut_semantics_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-shortcuts-") as td:
    folder = Path(td)
    worker_path = folder / "worker.py"
    module_ver = json.loads((ROOT / "Backend/games/hades/module.json").read_text())["protocolVersion"]
    worker_path.write_text(WORKER.replace("MODULE_VERSION", str(module_ver)), encoding="utf-8")

    initial_state = {
        "connected": True,
        "pid": 42,
        "heroReady": True,
        "health": 50,
        "maxHealth": 100,
        "money": 25,
        "rerolls": 3,
        "target": {"heroId": "run:hero:1"},
        "world": {
            "roomId": "run:room:1",
            "doors": [{
                "id": "door:1",
                "doorToken": "fixture-exit:1",
                "number": 1,
                "reward": "RoomMoneyDrop",
                "targets": [{"kind": "reward", "id": "MaxHealthDrop"}],
            }],
            "canFish": True,
            "canChaos": True,
            "objects": ["trove", "purge"],
            "occurrenceTargets": [{"id": "charon", "kind": "shop", "sourceId": "charon"}],
        },
    }
    worker_path.with_suffix(".state.json").write_text(json.dumps(initial_state), encoding="utf-8")

    main_path = folder / "main.swift"
    main_path.write_text(HARNESS, encoding="utf-8")
    binary = folder / "hades-shortcuts"
    compile_swift_test(
        games=("hades",),
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift", main_path],
        output=binary,
        cwd=ROOT,
    )
    result = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, check=True, capture_output=True)
    assert "hades_shortcut_semantics_ok" in result.stdout, result.stdout
    print(result.stdout.strip())
