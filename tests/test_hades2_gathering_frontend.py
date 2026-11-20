MGT_PLATFORM = "macos"

from macos_fixture_policy import launch_fixture
from fixture_budgets.hades2_panels import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test
import json
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
import argparse, json, pathlib, sys, time
p = argparse.ArgumentParser(); p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
probabilities = {}
generated = None
garden_matured = False
trace = pathlib.Path(__file__).with_suffix('.trace')
offline = pathlib.Path(__file__).stem == "offline-preferences"
offline_scans = 0
for raw in sys.stdin:
 req = json.loads(raw)
 with trace.open('a') as out: out.write(json.dumps(req) + '\n')
 state = {'connected': True, 'status': 'ready', 'scene': 'run',
          'capabilities': {'matureGarden': not garden_matured}, 'gatheringProbabilities': probabilities,
          'gardenScopeToken': None if garden_matured else 'observed-garden',
          'gatheringTargets': {name: {'available': True, 'scopeToken': 'observed-' + name} for name in ('flora', 'mining', 'digging', 'shades', 'fishing')}}
 if req['command'] == 'mature_garden':
  assert req['params'] == {'scopeToken': 'observed-garden'}
  garden_matured = True
  state['capabilities']['matureGarden'] = False
  state['gardenScopeToken'] = None
  state['lastAction'] = {'requestId': req['id'], 'command': 'mature_garden', 'outcome': 'completed'}
 elif req['command'] == 'set_gathering_desired':
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
 if offline:
  if req['command'] == 'scan':
   offline_scans += 1
   state = {'connected': False, 'status': 'disconnected'}
   if offline_scans == 1: state['chaosGateProbability'] = 35
   else:
    state.update(pid=6161, warning='verified detached snapshot',
                 resources=[{'id': 'MetaCurrency', 'name': 'Ashes', 'locked': True, 'count': 52},
                            {'id': 'Ore', 'name': 'Ore', 'locked': False, 'count': None}],
                 elements=[{'id': 'Fire', 'name': 'Fire', 'locked': True, 'count': 10},
                           {'id': 'Water', 'name': 'Water', 'locked': False, 'count': None}])
  elif req['command'] == 'core.save.apply_staged':
   state = {'operation': {'applied': False}}
  else:
   release = pathlib.Path(__file__).with_suffix('.release')
   deadline = time.monotonic() + 5
   while not release.exists() and time.monotonic() < deadline:
    time.sleep(0.005)
   state = {'status': 'not_running', 'health': 999, 'gardenScopeToken': 'expired-garden'}
   if req['command'] == 'set_gathering_desired':
    state['gatheringProbabilities'] = probabilities
   elif req['command'] == 'set_chaos_gate_desired':
    state['chaosGateProbability'] = req['params']['probability']
   elif req['command'] == 'load_profile':
    state.update(healthLocked=True, moneyLocked=True, money=41, rerollsLocked=True, rerolls=3,
                 biomeTimeLocked=True, biomeTime=700, stats={'grasp': {'locked': True, 'target': 30, 'value': 999},
                                                          'dodge': {'locked': False, 'value': 999}},
                 resources=[{'id': 'MetaCurrency', 'name': 'Ashes', 'locked': True, 'count': 52},
                            {'id': 'Ore', 'name': 'Ore', 'locked': False, 'count': 999}],
                 elements=[{'id': 'Fire', 'name': 'Fire', 'locked': True, 'count': 10},
                           {'id': 'Water', 'name': 'Water', 'locked': False, 'count': 999}])
   elif req['command'] == 'diagnostics':
    state = {'checks': [{'name': 'Worker verified', 'ok': True, 'detail': 'fixture'}], 'passed': 1, 'total': 1}
 reply = {'type': 'result', 'id': req['id'], 'protocolVersion': 6, 'moduleProtocolVersion': __MGT_MODULE_PROTOCOL__, 'gameID': args.game, 'ok': True, 'result': state}
 print(json.dumps(reply), flush=True)
'''
HARNESS = r'''
import AppKit
import Foundation
import SwiftUI
func check(_ value: @autoclosure () -> Bool, _ message: String) { if !value() { fatalError(message) } }
func pump(_ time: TimeInterval) { RunLoop.current.run(until: Date().addingTimeInterval(time)) }
func wait(_ message: String = "worker/model did not reach expected state", _ predicate: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    while !predicate(), Date() < deadline { pump(0.02) }
    check(predicate(), message)
}
@main struct Main {
    @MainActor static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let temporary = worker.deletingLastPathComponent()
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(executableURL: python, argumentsPrefix: ["-u"])))
        let model = makeFixtureModel(Hades2GameModule.self, session: session,
            logSink: TrainerLogSink(url: temporary.appendingPathComponent("log")),
            backendScriptURL: worker) {
            Hades2TrainerModel(services: $0, runLogDirectoryURL: temporary.appendingPathComponent("no-real-game-log"),
                shortcutDefaults: InMemoryDefaults())
        }

        wait { model.backendAvailable && !model.busy && model.canGenerateGathering(.flora) }
        check(model.gatheringProbabilities.isEmpty && model.gatheringTargets.count == 5, "Native defaults or five observed targets missing")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let host = NSHostingView(rootView: Hades2GameModule.makeContent(model: model).environmentObject(localization))
        host.frame = NSRect(x: 0, y: 0, width: 1100, height: 2200)
        host.layoutSubtreeIfNeeded()

        check(model.canMatureGarden && model.gardenScopeToken == "observed-garden", "observed garden must enable its explicit action")
        model.performShortcut(.matureGarden)
        model.performShortcut(.matureGarden)
        wait { !model.busy && !model.canMatureGarden }
        check(model.gardenScopeToken == nil, "native maturity must clear the obsolete target")
        let requests = try String(contentsOf: worker.deletingPathExtension().appendingPathExtension("trace"), encoding: .utf8)
        check(requests.split(separator: "\n").filter { $0.contains("mature_garden") }.count == 1, "pending garden shortcut must not duplicate the one-shot")
        check(model.noticeText.key == "hades2.receipt.completed"
              && model.noticeText.arguments == ["hades2.garden.title"], "garden action must publish its completed receipt")

        let generation = model.editGeneration
        check(model.completeTextEdit(.gathering(.flora), text: "", changed: false, generation: generation).isEmpty,
              "Native focus/blur changed the display into an implied 100%")
        check(model.completeTextEdit(.gathering(.flora), text: "100", generation: generation) == "100",
              "explicit 100% was not accepted from Native")
        wait { !model.busy && model.gatheringProbabilities[.flora] == 100 }
        model.setGatheringProbability(.flora, probability: nil)
        wait { !model.busy && model.gatheringProbabilities[.flora] == nil }
        model.setGatheringProbability(.mining, probability: 0)
        wait { !model.busy && model.gatheringProbabilities[.mining] == 0 }
        model.setGatheringProbability(.mining, probability: 25.5)
        wait { !model.busy && model.gatheringProbabilities[.mining] == 25.5 }
        model.setGatheringProbability(.mining, probability: 101)
        pump(0.1)
        check(model.gatheringProbabilities[.mining] == 25.5, "invalid percentage replaced accepted configuration")
        model.setGatheringProbability(.mining, probability: nil)
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
        check(rows.filter { $0["command"] as? String == "set_gathering_desired" }.count == 5, "invalid edit sent or Native restore did not send")
        check(!rows.contains { $0["command"] as? String == "status" }, "generation automatically polled")
        check(!Hades2StatePatch([:]).gatheringTargets.isPresent, "sparse envelope cleared observation")
        check(Hades2StatePatch(["gatheringTargets": ["flora": ["available": true, "scopeToken": ""]]]).gatheringTargets.value?[.flora] == nil, "invalid scope became actionable")
        check(Hades2StatePatch(["gatheringProbabilities": ["flora": 101]]).gatheringProbabilities.value == nil, "invalid probability decoded")
        model.refreshFromHost()
        wait { !model.busy && model.status == "restart_required" }
        check(model.errorText.key == "hades2.receipt.outcomeUnknown" && !model.canGenerateGathering(.flora), "uncertain generation lost restart instruction or stayed actionable")
        model.generateGathering(.mining)
        pump(0.1)
        check(model.canEditDesired && !model.canGenerateGathering(.mining),
              "missing room owner also blocked durable probability editing")
        model.setGatheringProbability(.mining, probability: 70)
        wait { !model.busy && model.gatheringProbabilities[.mining] == 70 }
        session.stop(suppressTerminationError: true)

        // Start a real Context with an offline model. The worker holds the
        // durable edit replies while the monitor discovers a target without
        // a launch grant. Desired acknowledgments must survive that boundary.
        let preferenceWorker = temporary.appendingPathComponent("offline-preferences.py")
        try FileManager.default.copyItem(at: worker, to: preferenceWorker)
        let preferenceSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: python, argumentsPrefix: ["-u"])))
        var target = TrainerTargetObservation(isRunning: false, launchGeneration: 0)
        let monitor = TrainerTargetProcessMonitor(snapshot: { target })
        let context = TrainerGameContext<Hades2GameModule>(session: preferenceSession,
            backendScriptURL: preferenceWorker, logSink: TrainerLogSink(url: temporary.appendingPathComponent("offline.log")),
            targetMonitor: monitor) {
            Hades2TrainerModel(services: $0, runLogDirectoryURL: temporary.appendingPathComponent("offline-run-log"),
                shortcutDefaults: InMemoryDefaults())
        }
        defer { preferenceSession.stop() }
        let offlineModel = context.model
        wait("offline preferences did not load") {
            !offlineModel.connected && !offlineModel.busy && offlineModel.chaosGateProbability == 35
        }
        let preferenceTrace = preferenceWorker.deletingPathExtension().appendingPathExtension("trace")
        let preferenceRelease = preferenceWorker.deletingPathExtension().appendingPathExtension("release")
        offlineModel.setGatheringProbability(.mining, probability: 55)
        wait("offline probability request did not start") {
            (try? String(contentsOf: preferenceTrace, encoding: .utf8))?.contains("set_gathering_desired") == true
        }
        offlineModel.setChaosGateProbability(nil)
        offlineModel.loadProfile("Fixture locks")
        target = .init(isRunning: true, launchGeneration: 0, processIdentifier: 6161)
        monitor.refresh()
        // This request is admitted against current presence, but dispatches
        // before a verified PID projection. Its sparse reply still carries
        // state from the worker's previous projection.
        offlineModel.setGatheringProbability(.fishing, probability: 70)
        offlineModel.runDiagnostics()
        try Data().write(to: preferenceRelease)
        wait("offline acknowledgments did not complete") { !offlineModel.busy }
        check(offlineModel.gatheringProbabilities == [.mining: 55, .fishing: 70] && offlineModel.chaosGateProbability == nil,
              "target discovery discarded an acknowledged offline desired probability")
        check(offlineModel.healthLocked && offlineModel.rerollsLocked && offlineModel.rerolls == 3
                && offlineModel.moneyLocked && offlineModel.money == 41 && offlineModel.biomeTimeLocked
                && offlineModel.graspLocked && offlineModel.graspValue == 30,
              "target discovery discarded a durable profile lock")
        check(offlineModel.resources.map(\.id) == ["MetaCurrency"] && offlineModel.elements.map(\.id) == ["Fire"]
                && offlineModel.resources.first?.count == 52 && offlineModel.elements.first?.count == 10,
              "resource or element lock projection lost its target or adopted stale unlocked rows")
        check(offlineModel.status == "disconnected" && offlineModel.health == nil && offlineModel.biomeTime == nil
                && offlineModel.dodgeValue == nil && offlineModel.gardenScopeToken == nil,
              "a durable acknowledgment restored runtime data from the prior observation")
        check(offlineModel.diagnosticsPassed == 1 && offlineModel.diagnostics.first?.name == "Worker verified",
              "a diagnostics reply was discarded while its worker had no verified target baseline")
        offlineModel.refreshFromHost()
        wait("a current full detached snapshot was rejected") {
            !offlineModel.busy && offlineModel.warning == "verified detached snapshot"
        }
        check(offlineModel.resources.map(\.id) == ["MetaCurrency"] && offlineModel.elements.map(\.id) == ["Fire"],
              "unobserved resource or element appeared as zero in the detached snapshot")
        print("hades2_gathering_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-gathering-frontend-') as td:
    td = Path(td)
    main, binary, worker = td / 'main.swift', td / 'reroll', td / 'worker.py'
    main.write_text(HARNESS); worker.write_text(WORKER.replace("__MGT_MODULE_PROTOCOL__", str(json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["protocolVersion"])))
    home = td / 'home'; home.mkdir()
    compile_swift_test(
        games=('hades2',),
        harness_sources=[
            ROOT / "tests/fixtures/swift/TrainerBackendFixture.swift",
            ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift',
            main,
        ],
        output=binary,
        swiftc=SWIFTC,
    )
    launch_fixture([str(binary), PYTHON, str(worker)], env=dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home)), check=True, journey='native.hades2_gathering_frontend', budgets=JOURNEY_BUDGETS)
