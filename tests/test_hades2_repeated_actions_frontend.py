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
for line in sys.stdin:
    request = json.loads(line)
    with log.open("a", encoding="utf-8") as file:
        file.write(json.dumps(request, sort_keys=True) + "\n")
    # Force a reproducible busy interval longer than a fast input burst.
    if request["command"] in ("spawn_reward", "set_desired"):
        time.sleep(0.16)
    observed = {"connected": True}
    if request["command"] == "set_desired":
        observed["desiredFeatures"] = {
            request["params"]["feature"]: request["params"]["value"],
        }
    print(json.dumps({
        "type": "result", "id": request["id"], "protocolVersion": 6,
        "moduleProtocolVersion": 14, "gameID": args.game, "ok": True,
        "result": observed,
    }), flush=True)
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
func makeReward(_ id: String) -> BoonOption {
    BoonOption(
        id: id, name: id, englishName: id, category: "Pickup",
        englishCategory: "Pickup", kind: "consumable", group: "pickup",
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
        pump(0.85)
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
        pump(0.45)
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
        pump(0.72)
        let toggles = loggedCommands(at: logURL).filter {
            ($0["command"] as? String) == "set_desired"
        }
        let values = toggles.compactMap {
            ($0["params"] as? [String: Any])?["value"] as? Bool
        }
        check(values == [true, false, true],
              "rapid toggles lost or inverted an intent: \(values)")
        check(model.invincibility, "final desired state did not follow the last shortcut")

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
