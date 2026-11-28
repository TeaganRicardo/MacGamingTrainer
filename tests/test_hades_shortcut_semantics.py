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
        lease = {
            "room": params["room"],
            "leaseToken": "lease-exit-1",
        }
        if "reward" in params:
            lease["reward"] = params["reward"]
        state["world"]["doors"][0]["activeLease"] = lease
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
    elif cmd == "set_feature":
        params = req.get("params", {})
        feature = params.get("feature")
        features = state.setdefault("features", {})
        if feature == "gameSpeed":
            features["gameSpeed"] = {"desired": params["value"], "actual": params["value"], "active": True}
        else:
            features[feature] = params.get("value")
        state_path.write_text(json.dumps(state), encoding="utf-8")
    elif cmd == "disable_all":
        state["features"] = {}
        state["activeFeatures"] = {}
        state["dormantFeatures"] = {}
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
        check(ordered.count == 24 && Set(ordered).count == 24, "expected 24 distinct Hades shortcuts")
        check(ordered.last == .disableAll, "disableAll must stay last in registry")
        let expectedBoons: [HadesShortcutAction] = [
            .boonRarityEnabled, .openSellTraits, .acquireChaosPair, .acquireExactBoon,
        ]
        check(HadesWorkbenchCatalog.shortcutActions(in: .boons) == expectedBoons,
              "boons shortcuts must match visible workbench order")
        let expectedResources: [HadesShortcutAction] = [
            .moneyMultiplierEnabled, .resourceMultiplierEnabled, .generateFishing,
        ]
        check(HadesWorkbenchCatalog.shortcutActions(in: .resources) == expectedResources,
              "resources shortcuts must match visible workbench order")
        let expectedRooms: [HadesShortcutAction] = [
            .applyWorldExit, .applyWorldOccurrence, .generateChamberObject, .generateChaosGate,
            .spawnOlympian, .spawnPickup, .spawnSpecial,
        ]
        check(HadesWorkbenchCatalog.shortcutActions(in: .rooms) == expectedRooms,
              "rooms shortcuts must match visible workbench order")

        let defaultLayout = HadesShortcutStore.defaultLayout()
        check(defaultLayout[.disableAll] == TrainerHotkeyLayout.disableAllChord,
              "disableAll default chord drifted from Control+Option+Backspace")
        check(defaultLayout[.decreaseGameSpeed]?.displayText == "⌃⌥−", "decreaseGameSpeed default chord")
        check(defaultLayout[.increaseGameSpeed]?.displayText == "⌃⌥+", "increaseGameSpeed default chord")
        check(defaultLayout[.boonRarityEnabled]?.displayText == "⌃⌥8", "boonRarityEnabled default chord")
        check(defaultLayout[.openSellTraits]?.displayText == "⌃⌥9", "openSellTraits default chord")
        check(defaultLayout[.acquireChaosPair]?.displayText == "⌃⌥0", "acquireChaosPair default chord")
        check(defaultLayout[.acquireExactBoon]?.displayText == "⌃⌥Q", "acquireExactBoon default chord")
        check(defaultLayout[.moneyMultiplierEnabled]?.displayText == "⌃⌥W", "moneyMultiplierEnabled default chord")
        check(defaultLayout[.resourceMultiplierEnabled]?.displayText == "⌃⌥E", "resourceMultiplierEnabled default chord")
        check(defaultLayout[.generateFishing]?.displayText == "⌃⌥R", "generateFishing default chord")
        check(defaultLayout[.applyWorldExit]?.displayText == "⌃⌥T", "applyWorldExit default chord")
        check(defaultLayout[.applyWorldOccurrence]?.displayText == "⌃⌥Y", "applyWorldOccurrence default chord")
        check(defaultLayout[.generateChamberObject]?.displayText == "⌃⌥U", "generateChamberObject default chord")
        check(defaultLayout[.generateChaosGate]?.displayText == "⌃⌥I", "generateChaosGate default chord")
        check(defaultLayout[.spawnOlympian]?.displayText == "⌃⌥O", "spawnOlympian default chord")
        check(defaultLayout[.spawnPickup]?.displayText == "⌃⌥P", "spawnPickup default chord")
        check(defaultLayout[.spawnSpecial]?.displayText == "⌃⌥A", "spawnSpecial default chord")
        check(Set(defaultLayout.values.map(TrainerHotkeyLayout.identity)).count == 24,
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

        // 3. Real HadesTrainerModel room shortcut dispatch & hotkey audio feedback.
        var playedSounds: [TrainerHotkeyFeedback] = []
        let session = TrainerBackendSession(client: BackendClient(process:
            BackendProcess(executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10)))
        let model = makeFixtureModel(HadesGameModule.self, session: session,
            logSink: TrainerLogSink(url: worker.deletingLastPathComponent().appendingPathComponent("fixture.log")),
            backendScriptURL: worker) {
            HadesTrainerModel(services: $0, defaults: InMemoryDefaults(), hotkeyFeedback: { playedSounds.append($0) })
        }
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

        // Dispatch open_sell_traits via shortcut when allowed, and reject when unavailable.
        let beforeSell = sentCommands().count
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.openSellTraits.rawValue)
        wait("openSellTraits shortcut dispatched") {
            !model.busy && sentCommands().count == beforeSell + 1 && playedSounds.count == 1
        }
        check(sentCommands().last?["command"] as? String == "open_sell_traits" && playedSounds == [.completed],
              "openSellTraits shortcut did not dispatch with .completed sound")

        // When room targets disappear, shortcuts refuse with warning without calling backend.
        var emptyState = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
        emptyState["canOpenSellTraits"] = false
        emptyState["world"] = [
            "roomId": "run:room:2", "doors": [], "canFish": false,
            "canChaos": false, "objects": [], "occurrenceTargets": [],
        ]
        try JSONSerialization.data(withJSONObject: emptyState).write(to: stateURL, options: .atomic)
        model.refreshFromHost()
        wait("empty room state observed") { !model.busy && model.world?.roomId == "run:room:2" }

        let beforeRefused = sentCommands().count
        for action in [HadesShortcutAction.openSellTraits, .applyWorldExit, .applyWorldOccurrence, .generateChamberObject] {
            model.performShortcut(action.rawValue)
            pump(0.03)
            let toneOK = model.feedback?.tone == .warning
            check(model.feedback?.text.key == "hades.shortcut.unavailable" && toneOK,
                  "unavailable shortcut \(action.rawValue) missed warning feedback")
        }
        check(sentCommands().count == beforeRefused, "refused room/sell shortcut reached backend")

        // 4. Hotkey audio feedback for toggles (.enabled/.deferred/.unconfirmed/.disabled), game speed, and disableAll.
        var stateObj = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
        func writeStateAndRefresh(_ mutate: (inout [String: Any]) -> Void) throws {
            mutate(&stateObj)
            try JSONSerialization.data(withJSONObject: stateObj).write(to: stateURL, options: .atomic)
            model.refreshFromHost()
            wait("refreshed state") { !model.busy }
        }

        // 4a. Toggle ON -> .enabled when activeFeatures reports true.
        playedSounds.removeAll()
        stateObj["activeFeatures"] = ["invincibility": true]
        try JSONSerialization.data(withJSONObject: stateObj).write(to: stateURL, options: .atomic)
        model.performShortcut(HadesShortcutAction.invincibility.rawValue)
        wait("invincibility ON settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.enabled], "expected .enabled sound, got \(playedSounds)")

        // 4b. Toggle OFF -> .disabled.
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.invincibility.rawValue)
        wait("invincibility OFF settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.disabled], "expected .disabled sound, got \(playedSounds)")

        // 4c. Toggle ON -> .deferred when dormantFeatures reports true.
        playedSounds.removeAll()
        stateObj["activeFeatures"] = [:]
        stateObj["dormantFeatures"] = ["fullGodGauge": true]
        try JSONSerialization.data(withJSONObject: stateObj).write(to: stateURL, options: .atomic)
        model.performShortcut(HadesShortcutAction.fullGodGauge.rawValue)
        wait("fullGodGauge dormant ON settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.deferred], "expected .deferred sound when dormant, got \(playedSounds)")

        // 4d. Toggle ON while connected+heroReady with neither active nor dormant -> .unconfirmed + notice.
        playedSounds.removeAll()
        stateObj["activeFeatures"] = [:]
        stateObj["dormantFeatures"] = [:]
        try JSONSerialization.data(withJSONObject: stateObj).write(to: stateURL, options: .atomic)
        model.performShortcut(HadesShortcutAction.infiniteAmmo.rawValue)
        wait("infiniteAmmo unconfirmed ON settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.unconfirmed], "expected .unconfirmed sound, got \(playedSounds)")
        check(model.feedback?.text.key == "hades.shortcut.unconfirmed" && model.feedback?.tone == .information,
              "expected hades.shortcut.unconfirmed notice, got \(String(describing: model.feedback))")

        // 4e. Game speed +/- -> .completed, clamped -> .rejected.
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.increaseGameSpeed.rawValue)
        wait("increaseGameSpeed settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.completed], "expected .completed for increaseGameSpeed, got \(playedSounds)")
        try writeStateAndRefresh { state in
            state["features"] = ["gameSpeed": ["desired": 0.0, "actual": 0.0, "active": false]]
        }
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.decreaseGameSpeed.rawValue)
        pump(0.03)
        check(playedSounds == [.rejected], "expected .rejected when speed clamped at 0.0, got \(playedSounds)")

        // 4f. Disable All shortcut -> .disabled on success, and .deferred when disconnected toggle.
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.disableAll.rawValue)
        wait("disableAll shortcut settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.disabled], "expected .disabled for disableAll, got \(playedSounds)")

        try writeStateAndRefresh { state in
            state["connected"] = false
            state["heroReady"] = false
            state["features"] = [:]
            state["activeFeatures"] = [:]
            state["dormantFeatures"] = [:]
        }
        playedSounds.removeAll()
        model.performShortcut(HadesShortcutAction.invincibility.rawValue)
        wait("offline toggle settled") { !model.busy && playedSounds.count == 1 }
        check(playedSounds == [.deferred], "expected .deferred for offline toggle ON, got \(playedSounds)")

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
        "canOpenSellTraits": True,
        "target": {"heroId": "run:hero:1"},
        "world": {
            "roomId": "run:room:1",
            "doors": [{
                "id": "door:1",
                "doorToken": "fixture-exit:1",
                "number": 1,
                "roomName": "A_Combat02",
                "roomKind": "combat",
                "reward": "RoomRewardMoneyDrop",
                "targets": [
                    {"kind": "reward", "id": "RoomRewardMaxHealthDrop", "enabled": True},
                    {"kind": "roomCategory", "id": "combat", "enabled": True, "acceptsReward": True},
                ],
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
        harness_sources=[
            ROOT / "tests/fixtures/swift/TrainerBackendFixture.swift",
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            main_path,
        ],
        output=binary,
        cwd=ROOT,
    )
    result = subprocess.run([str(binary), PYTHON, str(worker_path)], cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"hades-shortcuts failed ({result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}")
    assert "hades_shortcut_semantics_ok" in result.stdout, result.stdout
    print(result.stdout.strip())
