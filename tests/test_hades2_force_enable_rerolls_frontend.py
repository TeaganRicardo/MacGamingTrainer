import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != 'darwin':
    raise SystemExit('macOS-only Force Enable Rerolls model/view seam')

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
PYTHON = shutil.which('python3')

WORKER = r'''
import argparse, json, pathlib, sys
p = argparse.ArgumentParser(); p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
enabled = False
trace = pathlib.Path(__file__).with_suffix('.trace')
for raw in sys.stdin:
    req = json.loads(raw)
    with trace.open('a') as out:
        out.write(json.dumps(req) + '\n')
    if req['command'] == 'set_desired':
        assert req['params'] == {'feature': 'forceEnableRerolls', 'value': (not enabled)}
        enabled = not enabled
    state = {
        'connected': True,
        'status': 'ready',
        'scene': 'run',
        'capabilities': {'setFeature': True},
        'desiredFeatures': {'forceEnableRerolls': enabled},
        'activeFeatures': {'forceEnableRerolls': enabled},
        'featureSupport': {'forceEnableRerolls': True},
        'rerolls': 10,
    }
    reply = {
        'type': 'result',
        'id': req['id'],
        'protocolVersion': 6,
        'moduleProtocolVersion': 13,
        'gameID': args.game,
        'ok': True,
        'result': state,
    }
    print(json.dumps(reply), flush=True)
'''

HARNESS = r'''
import AppKit
import Foundation
import SwiftUI

func check(_ value: @autoclosure () -> Bool, _ message: String) {
    if !value() { fatalError(message) }
}
func pump(_ time: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(time))
}
func wait(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    while !predicate(), Date() < deadline { pump(0.02) }
    check(predicate(), "worker/model did not reach expected state")
}

@main struct Main {
    @MainActor static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let temporary = worker.deletingLastPathComponent()
        let session = TrainerBackendSession(
            client: BackendClient(
                process: BackendProcess(executableURL: python, argumentsPrefix: ["-u"])
            )
        )
        let model = Hades2TrainerModel(
            session: session,
            logSink: TrainerLogSink(url: temporary.appendingPathComponent("log")),
            backendScriptURL: worker,
            runLogDirectoryURL: temporary.appendingPathComponent("no-real-game-log")
        )

        wait { model.backendAvailable && !model.busy }
        check(!model.forceEnableRerolls, "force rerolls unexpectedly enabled")
        check(ShortcutAction.forceEnableRerolls.featureKey == .forceEnableRerolls,
              "shortcut identity does not route to the durable feature")

        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let host = NSHostingView(
            rootView: Hades2GameModule.makeContent(model: model).environmentObject(localization)
        )
        host.frame = NSRect(x: 0, y: 0, width: 1100, height: 1600)
        host.layoutSubtreeIfNeeded()

        check(localization.string(
            TrainerTextToken(key: "hades2.feature.forceEnableRerolls")
        ) == "强制启用重骰", "Chinese product label drifted")
        localization.language = .en
        check(localization.string(
            TrainerTextToken(key: "hades2.feature.forceEnableRerolls")
        ) == "Force Enable Rerolls", "English product label drifted")

        model.feature(.forceEnableRerolls, value: true)
        wait { !model.busy && model.forceEnableRerolls
            && model.activeFeatures["forceEnableRerolls"] == true }
        check(model.rerolls == 10, "feature enablement changed observed reroll currency")

        model.feature(.forceEnableRerolls, value: false)
        wait { !model.busy && !model.forceEnableRerolls
            && model.activeFeatures["forceEnableRerolls"] == false }

        let trace = try String(
            contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"),
            encoding: .utf8
        )
        let rows = trace.split(separator: "\n").map {
            try! JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any]
        }
        let desired = rows.filter { $0["command"] as? String == "set_desired" }
        check(desired.count == 2, "durable toggle did not use exactly two desired-state writes")
        check(!rows.contains { $0["command"] as? String == "reroll_choice" },
              "obsolete Trainer-issued reroll command was emitted")
        check(!trace.contains("choiceReroll") && !trace.contains("menuToken"),
              "obsolete observed reroll transaction leaked into Host traffic")

        session.stop(suppressTerminationError: true)
        print("hades2_force_enable_rerolls_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-force-enable-rerolls-frontend-') as td:
    td = Path(td)
    main = td / 'main.swift'
    binary = td / 'force-rerolls'
    worker = td / 'worker.py'
    main.write_text(HARNESS)
    worker.write_text(WORKER)
    home = td / 'home'
    home.mkdir()
    generated = td / 'ActiveGame.generated.swift'
    subprocess.run([
        PYTHON, str(ROOT / 'Tools/generate_game_binding.py'),
        'hades2', str(generated),
    ], check=True)
    sources = sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted(
        (ROOT / 'Sources/Hades2').rglob('*.swift')
    )
    subprocess.run([
        SWIFTC, '-parse-as-library', '-whole-module-optimization',
        *map(str, sources),
        str(ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift'),
        str(generated), str(main), '-o', str(binary),
    ], check=True)
    subprocess.run([
        str(binary), PYTHON, str(worker),
    ], env=dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home)),
       check=True, timeout=30)
