import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != 'darwin':
    raise SystemExit('macOS-only Chaos Gate model/view seam')

ROOT = Path(__file__).resolve().parents[1]
PYTHON, SWIFTC = shutil.which('python3'), shutil.which('swiftc')
WORKER = r'''
import argparse, json, pathlib, sys
p = argparse.ArgumentParser(); p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
probability = None
trace = pathlib.Path(__file__).with_suffix('.trace')
for line in sys.stdin:
 req = json.loads(line)
 with trace.open('a') as out: out.write(json.dumps(req) + '\n')
 if req['command'] == 'set_chaos_gate_desired':
  assert set(req['params']) == {'probability'}
  probability = req['params']['probability']
 state = {'connected': True, 'status': 'ready', 'scene': 'run',
          'chaosGateProbability': probability, 'gatheringProbabilities': {'mining': 25}}
 if req['command'] == 'status': state.pop('chaosGateProbability')
 if req['command'] == 'reset_desired': probability = None; state['chaosGateProbability'] = None
 print(json.dumps({'type': 'result', 'id': req['id'], 'protocolVersion': 6, 'moduleProtocolVersion': 13,
                   'gameID': args.game, 'ok': True, 'result': state}), flush=True)
'''
HARNESS = r'''
import AppKit
import Foundation
import SwiftUI
func check(_ value: @autoclosure () -> Bool, _ message: String) { if !value() { fatalError(message) } }
func pump() { RunLoop.current.run(until: Date().addingTimeInterval(0.02)) }
func wait(_ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    while !predicate(), Date() < deadline { pump() }
    check(predicate(), "worker/model did not reach expected state")
}
@main struct Main {
    @MainActor static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let temp = worker.deletingLastPathComponent()
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python, argumentsPrefix: ["-u"])))
        let model = Hades2TrainerModel(session: session, logSink: TrainerLogSink(url: temp.appendingPathComponent("log")),
            backendScriptURL: worker, runLogDirectoryURL: temp.appendingPathComponent("no-game-log"))
        wait { model.backendAvailable && !model.busy && model.protocolCompatible }
        check(model.chaosGateProbability == nil, "default is not Native")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let host = NSHostingView(rootView: Hades2GameModule.makeContent(model: model).environmentObject(localization))
        host.frame = NSRect(x: 0, y: 0, width: 1100, height: 2400); host.layoutSubtreeIfNeeded()
        model.setChaosGateProbability(custom: true, text: "0")
        wait { !model.busy && model.chaosGateProbability == 0 }
        model.setChaosGateProbability(custom: true, text: "25.5")
        wait { !model.busy && model.chaosGateProbability == 25.5 }
        model.setChaosGateProbability(custom: true, text: "100")
        wait { !model.busy && model.chaosGateProbability == 100 }
        for invalid in ["101", "-1", "nan", "inf", ""] { model.setChaosGateProbability(custom: true, text: invalid) }
        model.refreshFromHost(); wait { !model.busy }
        check(model.chaosGateProbability == 100, "sparse status erased accepted setting")
        check(model.gatheringProbabilities[.mining] == 25, "Chaos setting erased Gathering state")
        check(localization.string("hades2.chaosGate.title") == "混沌之门", "HealthGate Chinese identity drift")
        localization.language = .en
        check(localization.string("hades2.chaosGate.title") == "Chaos Gate", "HealthGate English identity drift")
        let explanation = localization.string("hades2.chaosGate.explanation")
        check(explanation.contains("newly created") && explanation.contains("0%") && explanation.contains("100%"), "conditional/future-room bounds missing")
        model.setChaosGateProbability(custom: false, text: "")
        wait { !model.busy && model.chaosGateProbability == nil }
        let trace = try String(contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"), encoding: .utf8)
        let requests = trace.split(separator: "\n").map { try! JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any] }
        let sets = requests.filter { $0["command"] as? String == "set_chaos_gate_desired" }
        check(sets.count == 4 && (sets.last?["params"] as? [String: Any])?["probability"] is NSNull, "invalid edit sent or Native restore omitted explicit null")
        check(requests.filter { $0["command"] as? String == "status" }.count == 1, "setting automatically polled")
        check(!requests.contains { $0["command"] as? String == "generate_gathering" }, "setting fabricated a generation intent")
        check(!Hades2StatePatch([:]).chaosGateProbability.isPresent, "absent field became null")
        check(Hades2StatePatch(["chaosGateProbability": NSNull()]).chaosGateProbability.isPresent, "explicit null became absent")
        for invalid: Any in [true, -1, 101, Double.nan, Double.infinity, "25"] {
            check(Hades2StatePatch(["chaosGateProbability": invalid]).chaosGateProbability.value == nil, "invalid probability decoded")
        }
        session.stop(suppressTerminationError: true)
        print("hades2_chaos_gate_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-chaos-gate-frontend-') as directory:
    temp = Path(directory)
    main, worker, binary = temp / 'main.swift', temp / 'worker.py', temp / 'fixture'
    main.write_text(HARNESS); worker.write_text(WORKER)
    home = temp / 'home'; home.mkdir()
    generated = temp / 'ActiveGame.generated.swift'
    subprocess.run([PYTHON, str(ROOT / 'Tools/generate_game_binding.py'), 'hades2', str(generated)], check=True)
    sources = sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted((ROOT / 'Sources/Hades2').rglob('*.swift'))
    subprocess.run([SWIFTC, '-parse-as-library', '-whole-module-optimization', *map(str, sources),
                    str(ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift'), str(generated), str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary), PYTHON, str(worker)], env=dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home)), check=True, timeout=30)
