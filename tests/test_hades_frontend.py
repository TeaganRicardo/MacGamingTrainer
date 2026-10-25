"""Hades I typed payloads, native numeric drafts and captured-hero requests."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != 'darwin':
    print('hades_frontend_macos_only')
    raise SystemExit(0)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
from core.protocol import HOST_PROTOCOL_VERSION

WORKER = r'''
import argparse,json,pathlib,sys,time
parser=argparse.ArgumentParser();parser.add_argument('--game');args=parser.parse_args()
folder=pathlib.Path(__file__).parent
for raw in sys.stdin:
    request=json.loads(raw)
    with (folder/'commands.jsonl').open('a') as stream:stream.write(json.dumps(request)+'\n')
    state=json.loads((folder/'state.json').read_text())
    command=request['command'];params=request.get('params',{})
    if command=='catalog':result=json.loads((folder/'catalog.json').read_text())
    elif command=='disconnect':result={**state,'connected':False,'heroReady':False}
    else:
        if command=='set_value':state[params['field']]=params['value'];(folder/'state.json').write_text(json.dumps(state))
        result=state
    time.sleep(.02)
    reply={'type':'result','id':request['id'],'protocolVersion':HOST_VERSION,
        'moduleProtocolVersion':MODULE_VERSION,'gameID':args.game,'ok':True,'result':result}
    if command=='status' and state.get('fixtureError'):
        reply.update(ok=False,error={'code':'fixture','presentation':state['fixtureError']},state=state)
        reply.pop('result')
    print(json.dumps(reply),flush=True)
'''

HARNESS = r'''
import AppKit
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}
func fields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}
func pump(_ seconds: TimeInterval = 0.1) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}
func wait(_ message: String = "fixture request did not complete", _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(5)
    while !condition() && Date() < deadline { pump(0.02) }
    check(condition(), message)
}
@main struct Main {
    @MainActor static func main() throws {
        _ = NSApplication.shared
        let folder=URL(fileURLWithPath:CommandLine.arguments[1])
        let python=URL(fileURLWithPath:CommandLine.arguments[2])
        let stateURL=folder.appendingPathComponent("state.json")
        let commandsURL=folder.appendingPathComponent("commands.jsonl")
        func commands() -> [[String:Any]] {
            let text=(try? String(contentsOf:commandsURL,encoding:.utf8)) ?? ""
            return text.split(separator:"\n").compactMap { try? JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any] }
        }
        func updateState(hero: String, health: Double) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["health"]=health;state["target"]=["heroId":hero]
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        func setFixtureError(_ error: String?) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["fixtureError"]=error
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        func setConnection(_ connected: Bool, heroReady: Bool) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["connected"]=connected;state["heroReady"]=heroReady
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        let defaults=InMemoryDefaults()
        let session=TrainerBackendSession(client:BackendClient(process:BackendProcess(executableURL:python,forceKillDelay:0.1)))
        let model=HadesTrainerModel(session:session,backendScriptURL:folder.appendingPathComponent("worker.py"),defaults:defaults,
            logSink:TrainerLogSink(url:folder.appendingPathComponent("trainer.log")))
        wait { model.connected && !model.catalog.isEmpty && !model.busy }
        check(model.heroReady && model.health==50,"catalog reply erased runtime observation")
        check(model.features["invincibility"] == .boolean(true),"boolean feature was decoded as a number")
        check(model.features["damageMultiplier"] == .number(2),"numeric feature decoding failed")
        check(model.catalog.contains { $0.matches("Zeus 闪电") },"catalog search did not combine bilingual fields")
        let nativeTrait=HadesCurrentTrait(instanceId:"special:1",name:"GodModeTrait",rarity:"Common",level:1,
            canEdit:false,canRemove:false,limitation:"specialOwner")
        check(model.traitName(nativeTrait,language:.en)=="Deus Ex Machina","special native effect lost its official English name")
        check(model.traitName(nativeTrait,language:.zhCN)=="天外飞仙","special native effect lost its official Chinese name")
        let unknown=HadesCurrentTrait(instanceId:"special:2",name:"FixtureUnknownTrait",rarity:"Common",level:1,
            canEdit:false,canRemove:false,limitation:"unknownTrait")
        check(model.traitName(unknown,language:.en)=="Unrecognized Effect","unknown native ID leaked into the effect label")

        var store=HadesShortcutStore(defaults:defaults)
        let clash=store.chord(.heal)
        check(store.set(.invincibility,chord:HotkeyChord(keyCode:clash.keyCode,modifiers:clash.modifiers,keyLabel:"different label")) == .heal,
            "physical shortcut conflict depended on display label")
        let custom=HotkeyChord(keyCode:99,modifiers:HotkeyChord.controlModifier | HotkeyChord.commandModifier,keyLabel:"F3")
        check(store.set(.invincibility,chord:custom)==nil,"valid shortcut failed")
        check(HadesShortcutStore(defaults:defaults).chord(.invincibility)==custom,"shortcut override was not persisted")
        check(store.set(.disableAll,chord:custom) == .disableAll,"panic shortcut was reassigned")
        store.reset()
        check(HadesShortcutStore(defaults:defaults).chord(.invincibility)==HadesShortcutAction.invincibility.defaultChord,"shortcut reset failed")

        let localization=TrainerLocalizationStore(defaults:InMemoryDefaults())
        localization.language = .en
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1150,height:2400),styleMask:[.titled],backing:.buffered,defer:false)
        window.isReleasedWhenClosed=false
        let host=NSHostingView(rootView:HadesTrainerView(model:model).environmentObject(localization))
        window.contentView=host;host.frame=NSRect(x:0,y:0,width:1150,height:2400)
        host.layoutSubtreeIfNeeded();pump()
        guard let field=fields(in:host).first(where:{$0.accessibilityLabel()=="Life"}),
              let coordinator=field.delegate as? TrainerTextField.Coordinator else { fatalError("native health control missing") }
        check(field.stringValue=="50","native control did not show observation")
        coordinator.begin();field.stringValue="70"
        coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:field))
        try updateState(hero:"run:hero:1",health:60)
        model.refreshFromHost();wait { !model.busy && model.health==60 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="70","background status replaced focused native draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field))
        wait { !model.busy && model.health==70 }
        let sent=commands().filter { $0["command"] as? String == "set_value" }
        check(sent.count==1,"native commit did not send exactly one mutation")
        let params=sent[0]["params"] as! [String:Any]
        check((params["target"] as? [String:String])?["heroId"]=="run:hero:1","numeric commit lost its captured hero")
        check(params["field"] as? String == "health" && params["value"] as? Double == 70,"numeric commit changed the wrong value")

        coordinator.begin();field.stringValue="80"
        coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:field))
        try updateState(hero:"run:hero:2",health:30)
        model.refreshFromHost();wait { !model.busy && model.health==30 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="80","hero replacement erased focused draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field));pump()
        check(commands().filter { $0["command"] as? String == "set_value" }.count==1,"stale draft mutated replacement hero")
        check(model.localError=="hades.error.staleHero","stale draft lacked actionable feedback")
        try updateState(hero:"run:hero:2",health:31)
        model.refreshFromHost();wait { !model.busy && model.health==31 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="31","unfocused native value did not refresh")
        let count=commands().count
        _=model.setNumber(.damageMultiplier,text:"nan");pump()
        check(commands().count==count,"invalid multiplier crossed the backend boundary")
        localization.language = .zhCN;host.layoutSubtreeIfNeeded();pump()
        check(fields(in:host).contains { $0.accessibilityLabel()=="生命值" },"language switch failed to relabel native fields")
        check(commands().count==count,"language switch performed a runtime operation")
        for connected in [true,false] {
            try setConnection(connected,heroReady:false)
            model.refreshFromHost();wait { !model.busy && model.connected==connected && !model.heroReady }
            check(model.hostActionsEnabled && !model.canMutate,"offline shortcut fixture retained a hero")
            let disabled=commands().filter { $0["command"] as? String == "disable_all" }.count
            model.performShortcut(HadesShortcutAction.disableAll.rawValue)
            wait("Disable All shortcut did not dispatch without a hero (connected=\(connected))") {
                !model.busy && commands().filter { $0["command"] as? String == "disable_all" }.count==disabled+1
            }
            check(model.feedback?.text.key == (connected ? "host.backend.notice.completed" : "hades.disableAllPending"),
                "Disable All feedback did not distinguish native cleanup from detached desired reset")
            let afterDisable=commands().count
            model.performShortcut(HadesShortcutAction.heal.rawValue);pump()
            check(commands().count==afterDisable,"a hero shortcut ran without a hero")
        }
        try setConnection(true,heroReady:true)
        model.refreshFromHost();wait { !model.busy && model.canMutate }
        for key in ["hades.error.outcomeUnknown","hades.error.restartRequired","hades.error.debuggerProtocol"] {
            try setFixtureError(key)
            model.refreshFromHost();wait { !model.busy && model.backendStatus.error==key }
            check(!model.connected && !model.heroReady && model.target==nil && !model.canMutate,
                "unsafe runtime error retained mutation authority: \(key)")
            let afterFailure=commands().count
            model.setFeature(.invincibility,value:true);model.heal()
            model.setValue("health",value:100,target:HadesHeroTarget(heroId:"run:hero:2"));pump()
            check(commands().count==afterFailure,"unsafe runtime error allowed a subsequent mutation: \(key)")
            try setFixtureError(nil)
            model.toggleConnectionFromHost();wait { model.connected && !model.busy && model.backendStatus.error.isEmpty }
            check(model.canMutate && model.target?.heroId=="run:hero:2","explicit reconnect did not restore current-hero authority")
        }
        var malformed=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        malformed.removeValue(forKey:"heroReady")
        try JSONSerialization.data(withJSONObject:malformed).write(to:stateURL,options:.atomic)
        model.refreshFromHost();wait { !model.busy && !model.connected }
        check(model.localError=="hades.error.protocol" && !model.canMutate,"malformed observation retained mutation authority")
        var complete=false
        model.prepareForTermination { complete=true }
        wait { complete }
        window.close()
        print("hades_frontend_native_drafts_and_target_ownership_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-hades-frontend-') as directory:
    folder = Path(directory)
    (folder / 'worker.py').write_text(WORKER.replace('HOST_VERSION', str(HOST_PROTOCOL_VERSION)).replace(
        'MODULE_VERSION', str(json.loads((ROOT / 'Backend/games/hades/module.json').read_text())['protocolVersion'])))
    (folder / 'main.swift').write_text(HARNESS)
    (folder / 'state.json').write_text(json.dumps({'connected': True, 'pid': 42, 'heroReady': True,
        'health': 50, 'maxHealth': 100, 'money': 25, 'rerolls': 3, 'target': {'heroId': 'run:hero:1'},
        'features': {'invincibility': True, 'damageMultiplier': 2}, 'resources': {'Gems': 12}, 'traits': []}))
    data = json.loads((ROOT / 'Backend/games/hades/catalog.json').read_text())
    selected = next(row for row in data['entries'] if row['id'] == 'AmmoBoltTrait')
    (folder / 'catalog.json').write_text(json.dumps({'catalog': [selected], 'resourceCatalog': data['resources'],
        'traitNames': data['traitNames']}))
    generated = folder / 'ActiveGame.generated.swift'
    subprocess.run([sys.executable, str(ROOT / 'Tools/generate_game_binding.py'), 'hades', str(generated)], check=True, cwd=ROOT)
    sources = sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted((ROOT / 'Sources/Hades').rglob('*.swift')) + [
        ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift', generated, folder / 'main.swift']
    subprocess.run([shutil.which('swiftc'), '-parse-as-library', *map(str, sources), '-o', str(folder / 'frontend')], check=True, cwd=ROOT)
    proc = subprocess.run([str(folder / 'frontend'), str(folder), sys.executable], capture_output=True, text=True, timeout=35)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
