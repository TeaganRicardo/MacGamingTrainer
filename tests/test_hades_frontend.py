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
workspaces={};next_workspace=0
files=[{'rootId':'fixture','relativePath':f'Profile{n}.sav','profile':f'Profile{n}','variant':''} for n in (1,2)]
values={'resources':25,'progression':False,'equipment':1,'relationships':1,'narrative':'Fixture dialogue',
    'statistics':4,'history':2,'advancedScalar':3,'advanced':{'luaType':'table','arraySize':0,'hashSize':1,'entries':[
        {'key':{'luaType':'string','value':'unknown'},'value':{'luaType':'number','value':3}}]}}
def typed(value):
    if isinstance(value,dict):return value
    return {'luaType':'boolean' if type(value) is bool else ('number' if isinstance(value,(int,float)) else 'string'),'value':value}
def save_row(domain,workspace,full=False):
    cn=workspace.get('language')=='zh-CN'
    row={'id':'entry:'+domain,'name':{'resources':'Gems','progression':'Mirror pair','equipment':'Aspect',
        'statistics':'Runs Completed','advanced':'Unknown Table','advancedScalar':'Advanced Scalar'}.get(domain,domain),
        'englishName':domain,'group':'Saved fields','groupId':'fixture-group','owner':'Fixture Owner','ownerId':'fixture-owner','valueType':typed(workspace['values'][domain])['luaType'],
        'displayValue':str(workspace['values'][domain]),'typedValue':typed(workspace['values'][domain]),
        'editable':True,'operations':['set','unset']+(['append'] if domain=='advanced' else []),'hasChildren':domain=='advanced'}
    if domain=='equipment':row['choices']=[{'name':'Zagreus','value':typed(1)},{'name':'Nemesis','value':typed(2)}]
    if domain=='advanced':row['warning']='Unknown native impact'
    return row
def review(workspace):
    actions=[]
    for entry,intent in workspace['pending'].items():
        domain=entry.split(':')[1];value=intent.get('value');row=save_row(domain,workspace)
        actions.append({'id':entry,'name':row['name'],'before':str(workspace['values'][domain]),'after':str(value),
            'operation':intent['operation'],'valueType':row['valueType'],
            'typedValue':value.get('value') if intent['operation']=='append' else value,
            'typedKey':value.get('key') if intent['operation']=='append' else None,'effects':[
                {'id':'linked:rank','name':'Linked rank','before':'0','after':'1'}] if domain=='equipment' else []})
    return {'actions':actions,'count':len(actions),'effectCount':sum(len(a['effects']) for a in actions)}
def summary(workspace):
    return {'workspaceId':workspace['id'],'source':workspace['source'],'sourceSHA256':workspace['sha'],
        'target':workspace.get('target'),'domains':[domain for domain in values if domain!='advancedScalar'],'review':review(workspace)}
def save_command(command,params,state):
    global next_workspace
    suffix=command.removeprefix('save_editor_')
    if suffix=='inventory':return {'sources':files,'targets':files,'defaultSource':{'rootId':'fixture','relativePath':state.get('activeSave','Profile1.sav')}}
    if suffix=='open':
        next_workspace+=1;identifier='workspace:'+str(next_workspace)
        source={'kind':'managedBackup' if params.get('snapshotId') else 'currentFile',**params.get('source',files[0])}
        if params.get('snapshotId'):source['snapshotId']=params['snapshotId']
        data=json.loads(json.dumps(values))
        if source['kind']=='currentFile' and (folder/'installed.json').exists():data=json.loads((folder/'installed.json').read_text())
        workspace={'id':identifier,'source':source,'target':params.get('target'), 'sha':'installed-sha' if (folder/'installed.json').exists() and source['kind']=='currentFile' else 'original-sha','values':data,'pending':{}}
        workspaces[identifier]=workspace;return summary(workspace)
    workspace=workspaces[params['workspaceId']]
    workspace['language']=params.get('language','en')
    if suffix=='target':workspace['target']=params['target'];return summary(workspace)
    if suffix=='close':del workspaces[params['workspaceId']];return {'closed':True}
    if suffix=='query':
        row=save_row(params['domain'],workspace)
        rows=[row]+([save_row('advancedScalar',workspace)] if params['domain']=='advanced' else [])
        return {'rows':rows,'total':len(rows),'offset':0,'limit':len(rows),'breadcrumbs':[], 'parentId':params.get('parentId')}
    if suffix=='detail':return {'row':save_row(params['entryId'].split(':')[1],workspace,True)}
    if suffix=='stage':
        if params.get('value',{}).get('value')==999:raise ValueError('Fixture rejected this edit; prior changes retained.')
        workspace['pending'][params['entryId']]={'operation':params['operation'],'value':params.get('value')}
        return review(workspace)
    if suffix=='unstage':workspace['pending'].pop(params['entryId'],None);return review(workspace)
    if suffix=='cancel':workspace['pending'].clear();return review(workspace)
    if suffix=='review':return review(workspace)
    if suffix=='apply':
        if state.get('editorApplyFailure'):raise OSError('Fixture recovery required')
        for entry,intent in workspace['pending'].items():workspace['values'][entry.split(':')[1]]=intent['value']
        workspace['pending'].clear();(folder/'installed.json').write_text(json.dumps(workspace['values']))
        return {'applied':True,'verified':True,'runtimeReloaded':False,'installedSHA256':'installed-sha','hot':True,
            'source':workspace['source'],'sourceSHA256':workspace['sha'],'target':workspace['target'],'previousSnapshotId':'fixture-prewrite'}

for raw in sys.stdin:
    request=json.loads(raw)
    with (folder/'commands.jsonl').open('a') as stream:stream.write(json.dumps({**request,'fixtureGame':args.game})+'\n')
    state=json.loads((folder/'state.json').read_text())
    command=request['command'];params=request.get('params',{})
    if command.startswith('save_editor_'):
        try:result=save_command(command,params,state)
        except (ValueError,OSError) as error:
            failure={'code':'fixture_editor','presentation':'hades.saveEditor.error','arguments':[str(error)]}
            if isinstance(error,OSError):failure['recoveryPath']=str(folder/'recovery-copy')
            print(json.dumps({'type':'result','id':request['id'],'protocolVersion':HOST_VERSION,'moduleProtocolVersion':MODULE_VERSION,'gameID':args.game,'ok':False,'error':failure}),flush=True)
            continue
    elif command=='catalog':result=json.loads((folder/'catalog.json').read_text())
    elif command=='disconnect':result={**state,'connected':False,'heroReady':False}
    elif command in ('list_profiles','save_profile','delete_profile'):
        result={'profiles':[{'name':'Fixture','updatedAt':'2026-10-27T00:00:00+00:00'}] if command!='delete_profile' else []}
    elif command=='diagnostics':
        result={**state,'diagnostics':{'gameID':'hades','checks':[{'name':'hades.diagnostics.connection','ok':state['connected'],'detail':'42'}]}}
    else:
        if command=='set_value':state[params['field']]=params['value'];(folder/'state.json').write_text(json.dumps(state))
        if command=='set_trait_uses':
            for trait in state['traits']:
                if trait['instanceId']==params['instanceId']:trait['remainingUses']=params['uses']
            (folder/'state.json').write_text(json.dumps(state))
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
func textViews(in view: NSView) -> [NSTextView] {
    (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(textViews)
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
        model.listProfiles()
        wait { !model.busy && model.profiles.count == 1 }
        check(model.connected && model.health==50,"profile inventory erased runtime state")
        check(model.profiles[0].name=="Fixture","Hades profile inventory did not decode")
        model.runDiagnostics()
        wait { !model.busy && model.diagnostics.count == 1 }
        check(model.diagnostics[0].ok && model.connected,"diagnostics payload replaced runtime authority")
        model.saveProfile("Fixture")
        wait { !model.busy }
        model.loadProfile("Fixture")
        wait { !model.busy }
        let profileRequest=commands().last { $0["command"] as? String == "load_profile" }
        check((profileRequest?["params"] as? [String:Any])?["name"] as? String == "Fixture",
              "feature profile lost its game-owned command/name")
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
        check(store.set(.disableAll,chord:custom) == .invincibility,"Disable All conflict was not detected")
        let another=HotkeyChord(keyCode:98,modifiers:HotkeyChord.controlModifier | HotkeyChord.commandModifier,keyLabel:"F4")
        check(store.set(.disableAll,chord:another)==nil,"Disable All is incorrectly hardcoded")
        check(HadesShortcutStore(defaults:defaults).chord(.disableAll)==another,"Disable All override was not persisted")
        store.reset()
        check(HadesShortcutStore(defaults:defaults).chord(.invincibility)==HadesShortcutAction.invincibility.defaultChord,"shortcut reset failed")

        let localization=TrainerLocalizationStore(defaults:InMemoryDefaults())
        localization.language = .en
        localization.registerModulePresentation(prefix:HadesGameModule.presentationKeyPrefix,
            resolver:HadesGameModule.presentationText)
        check(HadesWorkbenchSection.visible == [.values,.common,.boons,.resources,.rooms,.management],
            "workbench order lost the implemented native rooms panel")
        check(HadesWorkbenchCatalog.orderedShortcutActions == [.heal,.invincibility,.fullHealth,.moneyNoDecrease,
            .rerollsNoDecrease,.fullGodGauge,.infiniteAmmo,.forceRerolls,.boonRarityEnabled,.generateFishing,.generateChaosGate,.disableAll],"shortcut order drifted from the visible workbench")
        func searchFunctions(_ query: String) -> [HadesWorkbenchEntry] {
            HadesWorkbenchCatalog.matches(query,resources:model.resourceCatalog,worldTerms:model.worldTerms) { key in
                TrainerPresentationLanguage.allCases.map {
                    HadesGameModule.resolveText(key:key,language:$0,localization:localization)
                }
            }
        }
        check(searchFunctions("profile").contains { $0.section == .management && $0.id == "hades.manage.profiles" },
            "profile manager was absent from bilingual workbench discovery")
        check(searchFunctions("诊断").contains { $0.id == "hades.manage.diagnostics" },
            "diagnostics were absent from bilingual workbench discovery")
        check(searchFunctions("disable").contains { $0.id == "shortcut.disableAll" },
            "Host-owned function names were not localized in search")
        check(HadesGameModule.resolveText(key:"host.disableAll",language:.zhCN,localization:localization) != "host.disableAll",
            "Host management label leaked raw localization key")
        check(searchFunctions("invincibility").contains { $0.section == .common && $0.id == "shortcut.invincibility" },
            "English workbench feature lookup failed")
        check(searchFunctions("无敌").contains { $0.id == "shortcut.invincibility" },
            "Chinese workbench feature lookup failed")
        check(searchFunctions("gem").contains { $0.section == .resources && $0.resource != nil },
            "resource search did not include bilingual catalog names")
        check(searchFunctions("稀有度").contains { $0.id == "shortcut.boonRarityEnabled"
            && $0.section == .boons }, "boon rarity function not localized to the effect area")
        let mutations = commands().filter { $0["command"] as? String == "set_feature" }.count
        model.performShortcut(HadesShortcutAction.boonRarityEnabled.rawValue)
        wait("boon rarity shortcut did not dispatch a supported native feature") {
            !model.busy && commands().filter { $0["command"] as? String == "set_feature" }.count == mutations + 1
        }
        let rarityRequest = commands().last { $0["command"] as? String == "set_feature" }
        let rarityArgs = rarityRequest?["params"] as? [String:Any]
        check(rarityArgs?["feature"] as? String == "boonRarityEnabled"
              && rarityArgs?["value"] as? Bool == true,
              "boon rarity shortcut lost the boolean feature semantics")
        check(searchFunctions("damage").contains { $0.requiresExpandedMetrics && $0.section == .values },
            "numeric search did not target expanded run metrics")
        check(searchFunctions("fishing").contains { $0.section == .resources }, "native fishing missing from discovery")
        check(searchFunctions("出口").contains { $0.section == .rooms }, "native exit actions missing from bilingual discovery")
        let beforeWorld = commands().count
        model.worldAction("spawn_reward",roomID:"old:room",params:["reward":"ZeusUpgrade"],operation:"hades.spawnReward")
        pump(); check(commands().count == beforeWorld && model.localError == "hades.error.staleRoom", "old-room intent crossed the backend")
        model.worldAction("spawn_reward",roomID:"run:room:1",params:["reward":"ZeusUpgrade"],operation:"hades.spawnReward")
        wait { !model.busy && commands().contains { $0["command"] as? String == "spawn_reward" } }
        let worldArgs = commands().last { $0["command"] as? String == "spawn_reward" }?["params"] as? [String:Any]
        check(worldArgs?["roomId"] as? String == "run:room:1" && (worldArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1", "world mutation lost room/hero ownership")
        model.performShortcut(HadesShortcutAction.generateFishing.rawValue)
        wait { !model.busy && commands().contains { $0["command"] as? String == "generate_fishing" } }
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1150,height:2400),styleMask:[.titled],backing:.buffered,defer:false)
        window.isReleasedWhenClosed=false
        let host=NSHostingView(rootView:HadesTrainerView(model:model).environmentObject(localization))
        window.contentView=host;host.frame=NSRect(x:0,y:0,width:1150,height:2400)
        host.layoutSubtreeIfNeeded();pump()
        check(fields(in:host).contains { $0.accessibilityLabel()==HadesPresentation.text("hades.money",language:.en) },
              "Obol metric missing from the compact run dashboard")
        model.numericControlsExpanded=true;host.layoutSubtreeIfNeeded();pump()
        check(fields(in:host).contains { $0.accessibilityLabel()==HadesPresentation.text("hades.damageMultiplier",language:.en) },
              "expanded run dashboard lost damage multiplier")
        model.numericControlsExpanded=false;host.layoutSubtreeIfNeeded();pump()
        let currentLife=localization.localized("host.input.currentValue",arguments:[
            HadesPresentation.text("hades.health",language:.en)])
        guard let field=fields(in:host).first(where:{$0.accessibilityLabel()==currentLife}),
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
        let currentLifeCN=localization.localized("host.input.currentValue",arguments:[
            HadesPresentation.text("hades.health",language:.zhCN)])
        check(fields(in:host).contains { $0.accessibilityLabel()==currentLifeCN },
            "language switch failed to relabel native fields")
        check(commands().count==count,"language switch performed a runtime operation")
        localization.language = .en;host.layoutSubtreeIfNeeded();pump()
        check(searchFunctions("存档编辑器").contains { $0.id == "hades.saveEditor.title" },
            "Save Editor was absent from bilingual Management discovery")
        check(HadesGameModule.managedBackupEditor != nil,"verified backups have no Hades editor factory")
        let editor = model.makeSaveEditorModel()
        let tools = TrainerToolWindowStore()
        var editorFactories = 0
        let editorWindow = tools.open(id:"hades-save-editor",title:"Hades Save Editor",localization:localization,theme:.standard) {
            editorFactories += 1
            return TrainerToolWindowContent(canClose:{ !editor.busy },onClose:editor.close) { HadesSaveEditorView(model:editor) }
        }
        wait { editor.workspaceID != nil && !editor.busy && !editor.queryLoading && !editor.rows.isEmpty }
        check(editor.source?.kind == "currentFile" && editor.source?.relativePath == "Profile1.sav",
            "active editor did not pin the explicitly read file")
        let pinnedWorkspace = editor.workspaceID
        let pinnedSHA = editor.sourceSHA256
        let reopenedWindow = tools.open(id:"hades-save-editor",title:"Hades Save Editor",localization:localization,theme:.standard) {
            fatalError("opening an existing tool replaced its document")
        }
        check(reopenedWindow === editorWindow && editorFactories == 1,"Host did not preserve tool identity")
        var saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["activeSave"]="Profile2.sav"
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.refreshInventory();wait { !editor.busy }
        check(editor.workspaceID == pinnedWorkspace && editor.sourceSHA256 == pinnedSHA
            && editor.source?.relativePath == "Profile1.sav","active profile switch redirected a pinned document")
        guard let gemsField=fields(in:editorWindow.contentView!).first(where:{$0.accessibilityLabel()=="Gems"}),
              let gemsCoordinator=gemsField.delegate as? TrainerTextField.Coordinator else { fatalError("native save resource field missing") }
        gemsCoordinator.begin();gemsField.stringValue="80"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        editor.query();wait { !editor.queryLoading };editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(gemsField.stringValue == "80","query replaced a focused Save Editor draft")
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        check(!tools.canCloseAll,"Host allowed close/quit during a pending editor write")
        wait { !editor.busy && editor.review.count == 1 && !editor.queryLoading }
        check(editor.review.actions.first?.typedValue == .number(80),"completed native input did not enter Changes")
        gemsCoordinator.begin();gemsField.stringValue="90"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        wait { !editor.busy && editor.review.actions.first?.typedValue == .number(90) }
        check(editor.review.count == 1,"revising a field duplicated the user action")
        editor.unstage("entry:resources");wait { !editor.busy && editor.review.count == 0 }
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(gemsField.stringValue == "25","removing an intent did not restore the source observation")
        editor.stage("entry:resources",operation:"set",value:HadesSaveValue.number(75).object,workspace:pinnedWorkspace)
        wait { !editor.busy && editor.review.count == 1 }
        editor.stage("entry:statistics",operation:"set",value:HadesSaveValue.number(999).object,workspace:pinnedWorkspace)
        wait { !editor.busy && editor.failures["entry:statistics"] != nil }
        check(editor.review.count == 1 && editor.review.actions[0].id == "entry:resources",
            "a rejected edit erased acknowledged pending work")
        editor.selectDomain(.progression);editor.selectDomain(.statistics)
        wait { !editor.queryLoading && editor.rows.first?.id == "entry:statistics" }
        let stats=editor.rows.first!
        _=editor.commit(stats,text:"12",workspace:pinnedWorkspace)
        wait { !editor.busy && editor.review.count == 2 }
        editor.stage("entry:equipment",operation:"set",value:HadesSaveValue.number(2).object,workspace:pinnedWorkspace)
        wait { !editor.busy && editor.review.count == 3 }
        check(editor.review.effectCount == 1 && editor.review.actions.first(where:{$0.id=="entry:equipment"})?.effects.first?.name == "Linked rank",
            "linked equipment effects were hidden from Changes")
        editor.detail("entry:equipment");wait { !editor.busy && editor.editingRow?.id == "entry:equipment" }
        check(editor.editingRow?.choices?.count == 2,"basket revision lost native selection choices")
        editor.dismissDetail()
        editor.selectDomain(.advanced);wait { !editor.queryLoading && editor.rows.first?.id == "entry:advanced" }
        let advanced=editor.rows.first!
        let raw=HadesSaveValue.table(arraySize:0,hashSize:2,entries:[
            .init(key:.string("unknown"),value:.number(8)),.init(key:.rawString("/wA="),value:.rawNumber("000000000000f87f"))])
        check(editor.commitJSON(advanced,text:raw.json,workspace:pinnedWorkspace),"typed Advanced value was rejected locally")
        wait { !editor.busy && editor.review.count == 4 }
        check(editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedValue == raw,
            "Advanced editing lost raw strings, table metadata or IEEE bits")
        check(editor.commitJSON(advanced,text:HadesSaveValue.number(9).json,
            appendKey:HadesSaveValue.string("new-key").json,workspace:pinnedWorkspace),"typed append was rejected locally")
        wait { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.operation == "append" }
        check(editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedKey == .string("new-key"),
            "append revision lost the physical typed key")
        check(editor.commitJSON(advanced,text:raw.json,workspace:pinnedWorkspace),"revising append to table set failed")
        wait { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.operation == "set" }
        editor.detail("entry:advancedScalar",typed:true)
        wait { !editor.busy && editor.editingRow?.id == "entry:advancedScalar" && editor.editingTyped
            && editorWindow.attachedSheet != nil }
        guard let typedSheet=editorWindow.attachedSheet, let typedContent=typedSheet.contentView else {
            fatalError("Advanced scalar typed sheet missing")
        }
        typedContent.layoutSubtreeIfNeeded();pump()
        guard let typedField=textViews(in:typedContent).first(where:{ $0.isEditable && !$0.isFieldEditor }),
              typedSheet.makeFirstResponder(typedField) else { fatalError("Advanced scalar typed editor missing native text control") }
        typedField.selectAll(nil)
        typedField.insertText(HadesSaveValue.string("typed-scalar").json,replacementRange:typedField.selectedRange())
        pump();typedSheet.makeFirstResponder(nil)
        wait { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advancedScalar"})?.typedValue == .string("typed-scalar") }
        check(editor.review.count == 5,"Advanced scalar type change replaced unrelated intents")
        editor.dismissDetail();pump()
        editor.detail("entry:advancedScalar")
        wait { !editor.busy && editor.editingRow != nil }
        check(editor.editingTyped,"basket revision forgot the scalar's typed editing route")
        editor.dismissDetail();pump()
        let backup=model.makeSaveEditorModel(snapshotID:"verified-fixture")
        backup.open(language:.en)
        wait { backup.workspaceID != nil && !backup.busy && !backup.queryLoading }
        check(backup.source?.kind == "managedBackup" && backup.source?.snapshotId == "verified-fixture"
            && backup.workspaceID != editor.workspaceID,"backup document shared the active workspace")
        let backupID=backup.workspaceID
        editor.selectTarget("fixture/Profile2.sav");wait { !editor.busy && editor.selectedTargetID == "fixture/Profile2.sav" }
        editor.apply();wait { !editor.busy && editor.receipt != nil && !editor.queryLoading }
        check(editor.review.count == 0 && editor.sourceSHA256 == pinnedSHA && editor.workspaceID == pinnedWorkspace,
            "Apply replaced the fixed originally read document")
        check(editor.receipt?.target.relativePath == "Profile2.sav" && editor.receipt?.runtimeReloaded == false
            && editor.receipt?.previousSnapshotId == "fixture-prewrite","Apply receipt lost target, backup or runtime meaning")
        check(backup.workspaceID == backupID && backup.review.count == 0,"active Apply changed another document")
        editor.selectDomain(.resources);wait { !editor.queryLoading }
        check(editor.rows.first?.typedValue == .number(75),"Apply did not refresh the verified candidate values")
        check(editor.workspaceID == pinnedWorkspace && editor.sourceSHA256 == pinnedSHA && backup.workspaceID == backupID,
            "post-Apply refresh retargeted an existing pinned document")
        backup.selectDomain(.resources);wait { !backup.queryLoading }
        _=backup.commit(backup.rows.first!,text:"50",workspace:backup.workspaceID)
        wait { !backup.busy && backup.review.count == 1 }
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorApplyFailure"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        backup.apply();wait { !backup.busy && backup.recoveryPath != nil }
        check(backup.review.count == 1 && !backup.canApply,"uncertain Apply lost edits or allowed automatic replay")
        check(backup.failures["apply"]?.arguments.first == "Fixture recovery required","failure did not carry actionable detail")
        let editorRequests=commands().filter { ($0["command"] as? String)?.hasPrefix("save_editor_") == true }
        check(editorRequests.allSatisfy { $0["fixtureGame"] as? String == "hades" },"Save Editor crossed its game context")
        backup.close();check(backup.workspaceID == nil,"closing a backup retained its workspace identity")
        editorWindow.performClose(nil);pump()
        check(editor.workspaceID == nil,"Host close did not release the active editor")
        check(commands().contains { $0["command"] as? String == "save_editor_close"
            && ($0["params"] as? [String:Any])?["workspaceId"] as? String == pinnedWorkspace },
            "closing a document did not close its original workspace")
        print("hades_save_editor_native_control_journeys_ok")

        var lifetimeState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        lifetimeState["traits"]=[["instanceId":"effect:temporary:1","name":"TemporaryImprovedWeaponTrait",
            "rarity":"Common","level":1,"canEdit":true,"canRemove":true,"limitation":"",
            "remainingUses":3,"canSetUses":true,"canExpire":true]]
        try JSONSerialization.data(withJSONObject:lifetimeState).write(to:stateURL,options:.atomic)
        model.refreshFromHost();wait { !model.busy && model.traits.first?.remainingUses==3 }
        host.layoutSubtreeIfNeeded();pump()
        let usesLabel=HadesPresentation.text("hades.remainingUses",language:localization.language)
        guard let usesField=fields(in:host).first(where:{$0.accessibilityLabel()==usesLabel}),
              let usesCoordinator=usesField.delegate as? TrainerTextField.Coordinator else {
            fatalError("native remaining-use control missing")
        }
        check(usesField.stringValue=="3","remaining-use observation missing")
        usesCoordinator.begin();usesField.stringValue="6"
        usesCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:usesField))
        usesCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:usesField))
        wait { !model.busy && model.traits.first?.remainingUses==6 }
        host.layoutSubtreeIfNeeded();pump()
        check(usesField.stringValue=="6","remaining-use commit did not refresh observation")
        let usesRequests=commands().filter { $0["command"] as? String == "set_trait_uses" }
        let usesParams=usesRequests.last?["params"] as? [String:Any]
        check(usesRequests.count==1 && usesParams?["instanceId"] as? String == "effect:temporary:1"
            && (usesParams?["target"] as? [String:String])?["heroId"]=="run:hero:2",
            "remaining-use commit lost its selected effect or hero")
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
    for language in ('en', 'zh-CN'):
        destination = folder / f'{language}.lproj'
        destination.mkdir()
        shutil.copy2(ROOT / 'Resources/Localization' / f'{language}.lproj' / 'Host.strings',
                     destination / 'Host.strings')
    (folder / 'state.json').write_text(json.dumps({'connected': True, 'pid': 42, 'heroReady': True,
        'health': 50, 'maxHealth': 100, 'money': 25, 'rerolls': 3, 'target': {'heroId': 'run:hero:1'},
        'features': {'invincibility': True, 'damageMultiplier': 2}, 'resources': {'Gems': 12}, 'traits': [],
        'world': {'roomId': 'run:room:1', 'doors': [], 'canFish': True, 'canChaos': True, 'objects': []}}))
    data = json.loads((ROOT / 'Backend/games/hades/catalog.json').read_text())
    selected = next(row for row in data['entries'] if row['id'] == 'AmmoBoltTrait')
    (folder / 'catalog.json').write_text(json.dumps({'catalog': [selected], 'resourceCatalog': data['resources'],
        'traitNames': data['traitNames'], 'worldRewards': list(json.loads(
            (ROOT / 'Backend/games/hades/world_catalog.json').read_text())['rewards'].values()),
        'worldTerms': json.loads((ROOT / 'Backend/games/hades/world_catalog.json').read_text())['terms']}))
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
