import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades2 SwiftUI state-flow test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, pathlib, sys
p=argparse.ArgumentParser(); p.add_argument('--game', required=True); args=p.parse_args()
log_path=pathlib.Path(__file__).with_suffix('.commands.jsonl')
for raw in sys.stdin:
    req=json.loads(raw)
    with log_path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(req, sort_keys=True) + '\n')
    print(json.dumps({
        'type':'result','id':req['id'],'protocolVersion':6,
        'moduleProtocolVersion':5,'gameID':args.game,'ok':True,
        'result':{'connected':True},
    }), flush=True)
'''

harness = r'''
import AppKit
import Foundation
import SwiftUI

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func commands(at url: URL) -> [[String: Any]] {
    guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return text.split(separator: "\n").compactMap {
        try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
    }
}

@main
struct Main {
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 3 else { fail("expected python + worker") }
        let python = URL(fileURLWithPath: args[1])
        let worker = URL(fileURLWithPath: args[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")

        let process = BackendProcess(
            executableURL: python,
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        try session.start(
            descriptor: Hades2GameModule.descriptor,
            backendScriptURL: worker,
            applyPayload: { _ in },
            resetGameState: {},
            log: { _ in },
            onStatusChange: { _ in }
        )

        let model = Hades2GameModule.makeModel(session: session)
        let host = NSHostingView(rootView: Hades2TrainerView(model: model))
        host.frame = NSRect(x: 0, y: 0, width: 1200, height: 900)
        host.layoutSubtreeIfNeeded()
        pump(0.10)

        try? FileManager.default.removeItem(at: commandLog)

        model.connected = true
        model.capabilities = [
            "setVitals": true,
            "setResource": true,
            "setStats": true,
            "setElements": true,
        ]
        model.statSupport = ["dodge": true]
        model.statAvailable = ["dodge": true]
        model.health = 99.5
        model.maxHealth = 120.5
        model.mana = 44.5
        model.maxMana = 60.5
        model.armor = 7.5
        model.spellCharge = 12.5
        model.money = 123.5
        model.rerolls = 3.5
        model.dodgeValue = 12.345
        model.dodgeLocked = true
        model.damageMultiplier = 2.75
        model.moneyMultiplier = 3.5
        model.resourceMultiplier = 4.25
        model.boonRarityMultiplier = 135.5
        model.gameSpeed = 1.3
        model.elements = [ElementCount(id: "Fire", name: "火", count: 4.5, locked: false)]

        host.layoutSubtreeIfNeeded()
        pump(0.80)

        let passiveMutations = commands(at: commandLog).filter {
            guard let command = $0["command"] as? String else { return false }
            return command.hasPrefix("set_") || command.hasPrefix("lock_")
        }
        if !passiveMutations.isEmpty {
            fail("passive model projection emitted mutations: \(passiveMutations)")
        }

        // Model-level delayed-lock contract: unlocking a stat must cancel only
        // its own stale relock and leave the immediate unlock as the final intent.
        try? FileManager.default.removeItem(at: commandLog)
        model.setStat("dodge", text: "33.3", locked: true)
        model.setStat("dodge", text: "33.3", locked: false)
        pump(0.60)
        let statCommands = commands(at: commandLog).filter { ($0["command"] as? String) == "set_stat" }
        if statCommands.count != 1 { fail("unlock/relock emitted wrong set_stat count: \(statCommands)") }
        let params = statCommands[0]["params"] as? [String: Any]
        if params?["stat"] as? String != "dodge" || params?["locked"] as? Bool != false {
            fail("stale locked=true mutation survived unlock: \(statCommands)")
        }

        let editGeneration = model.editGeneration
        model.toggleConnectionFromHost()
        if model.editGeneration == editGeneration {
            fail("disconnect barrier did not invalidate editor drafts")
        }
        pump(0.20)

        session.stop()
        pump(0.20)
        print("hades2_view_state_flow_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-view-state-flow-") as td:
    td = Path(td)
    worker_path = td / "worker.py"
    main_path = td / "main.swift"
    binary = td / "view_state_flow"
    home = td / "home"
    home.mkdir()
    worker_path.write_text(textwrap.dedent(worker), encoding="utf-8")
    main_path.write_text(textwrap.dedent(harness), encoding="utf-8")

    generated = td / "ActiveGame.generated.swift"
    subprocess.run(
        [PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)],
        check=True,
        cwd=ROOT,
    )
    sources = (
        sorted((ROOT / "Sources/Core").rglob("*.swift"))
        + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
        + [generated, main_path]
    )
    subprocess.run(
        [SWIFTC, "-parse-as-library", *map(str, sources), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    env = dict(os.environ)
    env["HOME"] = str(home)
    proc = subprocess.run(
        [str(binary), PYTHON, str(worker_path)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
