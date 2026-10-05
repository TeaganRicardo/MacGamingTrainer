import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != 'darwin':
    raise SystemExit('macOS-only Hades choice reroll model/view seam')

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which('swiftc')
PYTHON = shutil.which('python3')

WORKER = r'''
import argparse, json, pathlib, sys
p = argparse.ArgumentParser(); p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
reroll = None
observations = 0
trace = pathlib.Path(__file__).with_suffix('.trace')
for raw in sys.stdin:
    req = json.loads(raw)
    with trace.open('a') as out: out.write(json.dumps(req) + '\n')
    state = {'connected': True, 'status': 'ready', 'scene': 'run', 'rerolls': 10,
             'choiceReroll': {'available': True, 'menuToken': 'observed-menu', 'cost': 1}}
    if req['command'] == 'reroll_choice':
        assert req['params'] == {'menuToken': 'observed-menu', 'expectedCost': 1}
        reroll = req['id']
        state['choiceReroll'] = {'available': False, 'reason': 'hades2.reroll.transition'}
        state['lastAction'] = {'requestId': reroll, 'command': 'reroll_choice', 'outcome': 'accepted'}
    elif req['command'] == 'status' and reroll:
        observations += 1
        state['choiceReroll'] = {'available': True, 'menuToken': 'next-menu', 'cost': 2}
        state['lastAction'] = {'requestId': reroll, 'command': 'reroll_choice', 'outcome': 'completed'}
    reply = {'type': 'result', 'id': req['id'], 'protocolVersion': 6,
             'moduleProtocolVersion': 12, 'gameID': args.game, 'ok': True, 'result': state}
    if observations > 1:
        state['status'] = 'restart_required'
        state['choiceReroll'] = {'available': False, 'reason': 'hades2.error.outcomeUnknownGeneric'}
        state['lastAction']['outcome'] = 'outcome_unknown'
        reply['ok'] = False; reply['state'] = reply.pop('result')
        reply['error'] = {'code': 'outcome_unknown', 'presentation': 'hades2.error.outcomeUnknownGeneric'}
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
        wait { model.backendAvailable && !model.busy && model.canRerollCurrentChoice }
        check(model.choiceReroll?.cost == 1, "observed native cost did not reach the actual model")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let host = NSHostingView(rootView: Hades2GameModule.makeContent(model: model).environmentObject(localization))
        host.frame = NSRect(x: 0, y: 0, width: 1100, height: 1600)
        host.layoutSubtreeIfNeeded()
        model.rerollCurrentChoice()
        wait { !model.busy && model.feedbackNotice?.text.key == "hades2.receipt.accepted" }
        check(!model.canRerollCurrentChoice, "accepted action retained a writable old target")
        let accepted = model.feedbackNotice!
        let zh = localization.string(accepted.text)
        localization.language = .en
        check(localization.string(accepted.text) != zh, "reroll receipt did not localize live")
        model.rerollCurrentChoice()
        pump(0.25)
        let trace = try String(contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"), encoding: .utf8)
        let rows = trace.split(separator: "\n").map { try! JSONSerialization.jsonObject(with: Data($0.utf8)) as! [String: Any] }
        check(rows.filter { $0["command"] as? String == "reroll_choice" }.count == 1, "accepted reroll automatically replayed")
        check(!rows.contains { $0["command"] as? String == "status" }, "accepted reroll automatically polled")
        model.refreshFromHost()
        wait { !model.busy && model.feedbackNotice?.text.key == "hades2.receipt.completed" }
        check(model.canRerollCurrentChoice && model.choiceReroll?.cost == 2, "explicit observation did not publish next target/cost")
        check(Hades2StatePatch([:]).choiceReroll.isPresent == false, "sparse envelope cleared the observation")
        check(Hades2StatePatch(["choiceReroll": ["available": true, "cost": -1, "menuToken": "bad"]]).choiceReroll.value == nil,
              "invalid target became actionable")
        model.refreshFromHost()
        wait { !model.busy && model.status == "restart_required" }
        check(model.errorText.key == "hades2.receipt.rerollOutcomeUnknown", "reroll receipt hid the required game restart behind reconnect guidance")
        check(model.feedbackNotice?.text == model.errorText && !model.canRerollCurrentChoice && !model.canOpenNativeBoonScreen,
              "late uncertain receipt did not retain recovery guidance and block further actions")
        localization.language = .zhCN
        let restartChinese = localization.string(model.errorText)
        localization.language = .en
        check(restartChinese.contains("重新启动 Hades II") && localization.string(model.errorText).contains("restart Hades II"),
              "late uncertain recovery did not resolve an explicit bilingual game restart instruction")
        model.rerollCurrentChoice()
        pump(0.1)
        let finalTrace = try String(contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"), encoding: .utf8)
        check(finalTrace.split(separator: "\n").filter { $0.contains("reroll_choice") }.count == 1, "late unknown action replayed")
        session.stop(suppressTerminationError: true)
        print("hades2_choice_reroll_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-choice-reroll-frontend-') as td:
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
