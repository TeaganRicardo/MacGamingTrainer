"""Exercise the Hades input admission seam without starting or attaching to the game."""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades repeated-action model test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc and python3 required")

worker = r'''
import argparse, json, pathlib, sys, time
parser = argparse.ArgumentParser()
parser.add_argument("--game", required=True)
args = parser.parse_args()
log = pathlib.Path(__file__).with_suffix(".commands.jsonl")
enable_count = 0
for line in sys.stdin:
    request = json.loads(line)
    with log.open("a", encoding="utf-8") as file:
        file.write(json.dumps(request, sort_keys=True) + "\n")
    # Special reward deliberately exceeds the old fixed 0.26s wait:
    # dispatch logging happens before this delay and before Host completion.
    if request["command"] == "spawn_reward" and request["params"].get("reward") == "SpecialDrop":
        time.sleep(0.45)
    elif request["command"] in ("spawn_reward", "set_desired", "set_boon_rarity_desired"):
        time.sleep(0.16)
    observed = {"connected": True}
    success = True
    if request["command"] == "set_desired":
        feature = request["params"]["feature"]
        value = request["params"]["value"]
        observed["desiredFeatures"] = {feature: value}
        if feature == "gameSpeed":
            observed["gameSpeed"] = value
        if feature == "invincibility" and value:
            enable_count += 1
            if enable_count == 3:
                success = False
                observed["desiredFeatures"] = {feature: False}
    if request["command"] == "set_boon_rarity_desired":
        success = False
        observed["boonRarity"] = {
            "target": "Epic", "multiplier": 100,
            "forceLegendary": False, "forceDuo": False,
        }
    response = {
        "type": "result", "id": request["id"], "protocolVersion": 6,
        "moduleProtocolVersion": 16, "gameID": args.game, "ok": success,
        "result" if success else "state": observed,
    }
    if not success:
        response["error"] = {
            "code": "invalid_request", "presentation": "hades2.error.invalidRequest",
            "diagnostic": "synthetic rejected request",
        }
    print(json.dumps(response), flush=True)
'''

harness = r'''
import Foundation
import AppKit

func fail(_ detail: String) -> Never {
    fputs("FAIL: \(detail)\n", stderr)
    exit(1)
}
func check(_ value: @autoclosure () -> Bool, _ detail: String) {
    if !value() { fail(detail) }
}
func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}
func loggedCommands(at url: URL) -> [[String: Any]] {
    guard let contents = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return contents.split(separator: "\n").compactMap {
        try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
    }
}
@MainActor
func waitForIdle(_ model: Hades2TrainerModel, logURL: URL, phase: String) {
    let timeout: TimeInterval = 5.0
    let deadline = Date().addingTimeInterval(timeout)
    while (model.busy || !model.canAcceptRuntimeAction || !model.backendAvailable)
          && Date() < deadline {
        pump(0.02)
    }
    guard !model.busy && model.canAcceptRuntimeAction && model.backendAvailable else {
        let dispatched = loggedCommands(at: logURL).suffix(12).map { row in
            "\(row["command"] as? String ?? "?")#\(row["id"] as? String ?? "?")"
        }.joined(separator: ", ")
        fail("idle gate timeout [\(phase)] after \(timeout)s; busy=\(model.busy) "
             + "admissible=\(model.canAcceptRuntimeAction) backend=\(model.backendAvailable) "
             + "connected=\(model.connected) status=\(model.status) error=\(model.error) "
             + "dispatched=[\(dispatched)]")
    }
}
func makeReward(_ id: String, group: String = "pickup") -> BoonOption {
    BoonOption(
        id: id, name: id, englishName: id, category: "Pickup",
        englishCategory: "Pickup", kind: "consumable", group: group,
        targetID: id, officialName: true, sectionTitle: "Pickup",
        englishSectionTitle: "Pickup", sourceId: "Pickup",
        sourceName: "Pickup", sourceEnglishName: "Pickup",
        nativeChoice: false, nativeChoiceTitle: "",
        nativeChoiceEnglishTitle: "", acquisitionMode: "",
        sortSection: 1, sortGroup: 1, sortOrder: 1
    )
}

@main
struct Main {
    @MainActor
    static func main() throws {
        let args = CommandLine.arguments
        check(args.count == 3, "expected python and fake worker paths")
        let workerURL = URL(fileURLWithPath: args[2])
        let logURL = workerURL.deletingPathExtension().appendingPathExtension("commands.jsonl")
        let process = BackendProcess(
            executableURL: URL(fileURLWithPath: args[1]),
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        let model = Hades2TrainerModel(
            session: session,
            logSink: TrainerLogSink(
                url: workerURL.deletingLastPathComponent().appendingPathComponent("fixture.log")
            ),
            backendScriptURL: workerURL,
            runLogDirectoryURL: workerURL.deletingLastPathComponent()
        )
        model.hostTargetLifetimeChanged(
            observation: TrainerTargetObservation(isRunning: false, launchGeneration: 0)
        )
        let startupDeadline = Date().addingTimeInterval(5.0)
        while (!model.backendAvailable || model.busy || !model.canAcceptRuntimeAction)
              && Date() < startupDeadline { pump(0.04) }
        check(model.backendAvailable,
              "fake backend must become available; session.started=\(session.isStarted) running=\(session.isRunning) status=\(model.status) error=\(model.error)")
        pump(0.12)
        try? FileManager.default.removeItem(at: logURL)
        model.connected = true
        model.status = "ready"
        model.scene = "run"
        model.capabilities = ["spawnReward": true, "specialChoice": true]
        let reward = makeReward("MaxManaDropBig")
        model.boons = [reward]
        model.selectedPickupReward = reward.id

        check(model.canSpawnReward, "baseline spawn should be available")
        model.spawnBoon(reward.id)
        check(!model.canOpenSpecialChoice,
              "native-choice modal must remain exclusive while drop commands are pending")
        check(model.canSpawnReward,
              "GUI spawn must remain enabled while the first request is pending")
        model.spawnBoon(reward.id)
        model.spawnBoon(reward.id)
        check(model.canSpawnReward,
              "GUI spawn must remain enabled during a queued burst")
        // Disable All cannot overtake outstanding one-shot commands, nor may
        // it be queued behind them: its native GUI already forbids doing so.
        model.performShortcut(.disableAll)
        check(model.canSpawnReward,
              "rejected Disable All must not suppress pending repeatable spawns")
        waitForIdle(model, logURL: logURL, phase: "three GUI spawns")
        let disableRequests = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "disable_all"
        }
        check(disableRequests.isEmpty,
              "Disable All shortcut bypassed the outstanding-spawn barrier: \(disableRequests)")

        let spawned = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "spawn_reward"
        }
        check(spawned.count == 3,
              "the three presses must produce three non-coalesced commands; got \(spawned.count)")
        let ids = spawned.compactMap { $0["id"] as? String }
        check(Set(ids).count == 3, "repeated one-shots must have distinct request IDs")
        check(model.canSpawnReward, "button must be enabled again after the burst")

        // Hotkey actions use the same entrypoint as the Carbon callback.
        // A rapid repeated one-shot must not be dropped by a global busy guard.
        model.performShortcut(.spawnPickup)
        model.performShortcut(.spawnPickup)
        check(model.canSpawnReward, "shortcut burst must not disable GUI spawn")
        waitForIdle(model, logURL: logURL, phase: "two shortcut spawns")
        let repeated = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "spawn_reward"
        }
        check(repeated.count == 5,
              "two repeated shortcut presses must add two commands, got \(repeated.count)")

        // A non-spawn request remains an ordering barrier for GUI spawn.
        // This keeps native modals and unrelated owner changes safe.
        check(model.canEditDesired, "durable shortcuts require backend availability")
        model.performShortcut(.invincibility)
        check(!model.canSpawnReward,
              "unrelated pending desired update must retain the original admission barrier")
        model.performShortcut(.invincibility)
        check(!model.invincibility, "two hotkeys must toggle back before replies")
        let intervalEnd = Date().addingTimeInterval(0.48)
        while Date() < intervalEnd {
            pump(0.012)
            check(!model.invincibility,
                  "older acknowledgement overwrote a later hotkey's pending intent")
        }
        model.performShortcut(.invincibility)
        waitForIdle(model, logURL: logURL, phase: "three durable toggles")
        let toggles = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "set_desired"
        }
        let values = toggles.compactMap {
            ($0["params"] as? [String: Any])?["value"] as? Bool
        }
        check(values == [true, false, true],
              "rapid toggles lost or inverted an intent: \(values)")
        check(model.invincibility, "final desired state did not follow the last shortcut")

        // The backend may reject a later requested state while returning the
        // last authoritative desired value. Optimistic UI must reconcile it.
        model.performShortcut(.invincibility)
        waitForIdle(model, logURL: logURL, phase: "explicit toggle disable")
        check(!model.invincibility, "explicit disable did not settle")
        model.performShortcut(.invincibility)
        waitForIdle(model, logURL: logURL, phase: "rejected feature enable")
        check(!model.invincibility,
              "rejected enable retained an optimistic value against the backend's explicit state")

        model.performShortcut(.forceLegendary)
        waitForIdle(model, logURL: logURL, phase: "rejected boon rarity")
        check(!model.boonForceLegendary,
              "failed boon rarity edit retained an optimistic forced legendary value")

        // Speed keys may arrive faster than replies. The first acknowledgement
        // cannot overwrite the newer desired value used by the next key press.
        model.gameSpeed = 1.0
        model.performShortcut(.increaseGameSpeed)
        model.performShortcut(.increaseGameSpeed)
        check(abs(model.gameSpeed - 1.2) < 0.0001, "speed shortcut burst did not accumulate")
        let speedReplyWindow = Date().addingTimeInterval(0.40)
        while Date() < speedReplyWindow {
            pump(0.012)
            check(abs(model.gameSpeed - 1.2) < 0.0001,
                  "older speed acknowledgement overwrote the later pending intent")
        }
        waitForIdle(model, logURL: logURL, phase: "two speed increases")
        model.performShortcut(.decreaseGameSpeed)
        waitForIdle(model, logURL: logURL, phase: "one speed decrease")
        check(abs(model.gameSpeed - 1.1) < 0.0001, "speed decrease used stale input")
        let speedValues = loggedCommands(at: logURL).filter {
            ($0["params"] as? [String: Any])?["feature"] as? String == "gameSpeed"
        }.compactMap { ($0["params"] as? [String: Any])?["value"] as? Double }
        check(speedValues.count == 3 && abs(speedValues[0] - 1.1) < 0.0001
              && abs(speedValues[1] - 1.2) < 0.0001 && abs(speedValues[2] - 1.1) < 0.0001,
              "speed keys did not preserve the ordered desired values: \(speedValues)")

        // Applying a next-room reward mints a consumption identity. A double
        // shortcut press must not mint a second token while the first is pending.
        model.selectedNextRoomReward = reward.id
        model.performShortcut(.applyNextRoomReward)
        model.performShortcut(.applyNextRoomReward)
        waitForIdle(model, logURL: logURL, phase: "next-room token update")
        let nextRoomRequests = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "set_next_room_reward_desired"
        }
        check(nextRoomRequests.count == 1,
              "rapid hotkey duplicated a next-room consumption token: \(nextRoomRequests.count)")

        // Route the normal special-reward shortcut through the actual typed
        // backend boundary. A source-string assertion cannot prove dispatch.
        let specialReward = makeReward("SpecialDrop", group: "special")
        model.boons = [reward, specialReward]
        model.selectedSpecialReward = specialReward.id
        check(model.canPerformSelectedSpecialReward, "ordinary special reward should be available")
        model.performShortcut(.spawnSpecial)
        waitForIdle(model, logURL: logURL, phase: "slow special-reward spawn")
        let specials = loggedCommands(at: logURL).filter {
            guard ($0["command"] as? String) == "spawn_reward",
                  let params = $0["params"] as? [String: Any] else { return false }
            return (params["reward"] as? String) == specialReward.id
        }
        check(specials.count == 1,
              "special-reward shortcut bypassed typed spawn dispatch: \(specials)")

        // Preserve the supported idle success path as well as rejecting
        // Disable All during a burst.
        check(model.canAcceptRuntimeAction, "idle Disable All should be admissible")
        model.performShortcut(.disableAll)
        waitForIdle(model, logURL: logURL, phase: "idle Disable All")
        let acceptedDisable = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "disable_all"
        }
        check(acceptedDisable.count == 1,
              "idle Disable All should produce exactly one backend request")

        session.stop()
        pump(0.10)
        print("hades2_repeated_actions_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-repeat-actions-") as td:
    root = Path(td)
    worker_path = root / "fake_worker.py"
    swift_path = root / "main.swift"
    binding_path = root / "ActiveGame.generated.swift"
    binary_path = root / "repeat_action_harness"
    home_path = root / "home"
    home_path.mkdir()
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    swift_path.write_text(textwrap.dedent(harness), encoding="utf-8")
    subprocess.run(
        [PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(binding_path)],
        check=True, cwd=ROOT,
    )
    sources = [
        *sorted((ROOT / "Sources/Core").rglob("*.swift")),
        *sorted((ROOT / "Sources/Hades2").rglob("*.swift")),
        binding_path,
        swift_path,
    ]
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary_path)],
        check=True, cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home_path)
    result = subprocess.run(
        [str(binary_path), PYTHON, str(worker_path)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.strip())
