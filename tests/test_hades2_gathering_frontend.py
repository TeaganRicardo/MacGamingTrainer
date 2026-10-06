import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != 'darwin':
    raise SystemExit('macOS-only Hades gathering model/view seam')

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
PYTHON = shutil.which('python3')

WORKER = r'''
import argparse, json, pathlib, sys
p = argparse.ArgumentParser(); p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
probabilities = {}
generated = None
trace = pathlib.Path(__file__).with_suffix('.trace')
for raw in sys.stdin:
 req = json.loads(raw)
 with trace.open('a') as out: out.write(json.dumps(req) + '\n')
 state = {'connected': True, 'status': 'ready', 'scene': 'run', 'gatheringProbabilities': probabilities,
          'gatheringTargets': {name: {'available': True, 'scopeToken': 'observed-' + name} for name in ('flora', 'mining', 'digging', 'shades', 'fishing')}}
 if req['command'] == 'set_gathering_desired':
  family, value = req['params']['family'], req['params']['probability']
  if value is None: probabilities.pop(family, None)
  else: probabilities[family] = value
 elif req['command'] == 'generate_gathering':
  assert req['params'] == {'family': 'flora', 'scopeToken': 'observed-flora'}
  generated = req['id']
  state['gatheringTargets']['flora'] = {'available': False, 'reason': 'hades2.gathering.unavailable.existing'}
  state['lastAction'] = {'requestId': generated, 'command': 'generate_gathering', 'outcome': 'completed'}
 elif req['command'] == 'status' and generated:
  state['status'] = 'restart_required'
  state['gatheringTargets'] = {}
  state['lastAction'] = {'requestId': generated, 'command': 'generate_gathering', 'outcome': 'outcome_unknown'}
 reply = {'type': 'result', 'id': req['id'], 'protocolVersion': 6, 'moduleProtocolVersion': 13, 'gameID': args.game, 'ok': True, 'result': state}
 print(json.dumps(reply), flush=True)
'''
HARNESS = r'''
import AppKit
import Foundation
import SwiftUI
func check(_ value: @autoclosure () -> Bool, _ message: String) { if !value() { fatalError(message) } }
func pump(_ time: TimeInterval) { RunLoop.current.run(until: Date().addingTimeInterval(time)) }
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
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python, argumentsPrefix: ["-u"])))
        let model = Hades2TrainerModel(session: session, logSink: TrainerLogSink(url: temporary.appendingPathComponent("log")),
            backendScriptURL: worker, runLogDirectoryURL: temporary.appendingPathComponent("no-real-game-log"))
        wait { model.backendAvailable && !model.busy && model.canGenerateGathering(.flora) }
        check(model.gatheringProbabilities.isEmpty && model.gatheringTargets.count == 5, "Native defaults or five observed targets missing")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let host = NSHostingView(rootView: Hades2GameModule.makeContent(model: model).environmentObject(localization))
        host.frame = NSRect(x: 0, y: 0, width: 1100, height: 2200)
        host.layoutSubtreeIfNeeded()
        model.setGatheringProbability(.mining, custom: true, text: "25.5")
        wait { !model.busy && model.gatheringProbabilities[.mining] == 25.5 }
        model.setGatheringProbability(.mining, custom: true, text: "101")
        pump(0.1)
        check(model.gatheringProbabilities[.mining] == 25.5, "invalid percentage replaced accepted configuration")
        model.setGatheringProbability(.mining, custom: false, text: "")
        wait { !model.busy && model.gatheringProbabilities.isEmpty }
        model.generateGathering(.flora)
        wait { !model.busy && model.feedbackNotice?.text.key == "hades2.receipt.completed" }
        check(!model.canGenerateGathering(.flora), "completed generation retained stale target")
        let notice = model.feedbackNotice!.text
        let zh = localization.string(notice)
        localization.language = .en
        check(localization.string(notice) != zh, "generation receipt did not localize live")
        check(localization.string("hades2.gathering.family.flora") == "Flora", "native label did not resolve registry")
        localization.language = .zhCN
        check(localization.string("hades2.gathering.family.flora") == "植物", "native bilingual identity drift")
        for (family, expected) in [(Hades2GatheringFamily.mining, "矿藏"), (.digging, "挖掘点"), (.shades, "迷途暗灵"), (.fishing, "钓鱼点")] {
            check(localization.string(family.titleKey) == expected, "native family label drift")
        }
        check(Hades2GameModule.presentationText(key: "hades2.gathering.collection.mining", arguments: [], language: .en).contains("Crescent Pick"), "native tool identity did not reach panel")
        model.generateGathering(.flora)
        pump(0.1)
        let trace = try String(contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"), encoding: .utf8)
        let rows = trace.split(separator: "\n").map { try! JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any] }
        check(rows.filter { $0["command"] as? String == "generate_gathering" }.count == 1, "generation replayed")
        check(rows.filter { $0["command"] as? String == "set_gathering_desired" }.count == 2, "invalid edit sent or Native restore did not send")
        check(!rows.contains { $0["command"] as? String == "status" }, "generation automatically polled")
        check(!Hades2StatePatch([:]).gatheringTargets.isPresent, "sparse envelope cleared observation")
        check(Hades2StatePatch(["gatheringTargets": ["flora": ["available": true, "scopeToken": ""]]]).gatheringTargets.value?[.flora] == nil, "invalid scope became actionable")
        check(Hades2StatePatch(["gatheringProbabilities": ["flora": 101]]).gatheringProbabilities.value == nil, "invalid probability decoded")
        model.refreshFromHost()
        wait { !model.busy && model.status == "restart_required" }
        check(model.errorText.key == "hades2.receipt.rerollOutcomeUnknown" && !model.canGenerateGathering(.flora), "uncertain generation lost restart instruction or stayed actionable")
        model.generateGathering(.mining)
        pump(0.1)
        session.stop(suppressTerminationError: true)
        print("hades2_gathering_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-gathering-frontend-') as td:
    td = Path(td)
    main, binary, worker = td / 'main.swift', td / 'reroll', td / 'worker.py'
    main.write_text(HARNESS); worker.write_text(WORKER)
    home = td / 'home'; home.mkdir()
    generated = td / 'ActiveGame.generated.swift'
    subprocess.run([PYTHON, str(ROOT / 'Tools/generate_game_binding.py'), 'hades2', str(generated)], check=True)
    sources = sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted((ROOT / 'Sources/Hades2').rglob('*.swift'))
    subprocess.run([SWIFTC, '-parse-as-library', '-whole-module-optimization', *map(str, sources),
                    str(ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift'), str(generated), str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary), PYTHON, str(worker)], env=dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home)), check=True, timeout=30)
