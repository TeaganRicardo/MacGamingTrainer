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
    'statistics':4.123456789012345,'history':2,'shiftA':11,'shiftB':22,'shiftC':33,'narrativeNyx':True,'narrativeNyxShared':False,'narrativeAchilles':False,'advancedScalar':3,'advanced':{'luaType':'table','arraySize':0,'hashSize':1,'entries':[
        {'key':{'luaType':'string','value':'unknown'},'value':{'luaType':'number','value':3}}]}}
def typed(value):
    if isinstance(value,dict):return value
    return {'luaType':'boolean' if type(value) is bool else ('number' if isinstance(value,(int,float)) else 'string'),'value':value}
def entry_domain(identifier,workspace):
    if identifier.startswith('p:'):
        _,baseline,index=identifier.split(':')
        if baseline!=workspace['baseline']:raise ValueError('Old physical occurrence')
        return workspace['physical'][int(index)]
    return identifier.split(':')[1]
def save_row(domain,workspace,full=False):
    cn=workspace.get('language')=='zh-CN'
    identifier=('p:'+workspace['baseline']+':'+str(workspace['physical'].index(domain))) if domain.startswith('shift') else 'entry:'+domain
    row={'id':identifier,'baselineGeneration':workspace['baseline'],'name':{'resources':'Gems','progression':'Mirror pair','equipment':'Aspect',
        'statistics':'Gameplay Time','advanced':'Unknown Table','advancedScalar':'Advanced Scalar','shiftA':'Shift A','shiftB':'Shift B','shiftC':'Shift C'}.get(domain,domain),
        'englishName':domain,'group':'Saved fields','groupId':'fixture-group','owner':'Fixture Owner','ownerId':'fixture-owner','valueType':typed(workspace['values'][domain])['luaType'],
        'displayValue':str(workspace['values'][domain]),'typedValue':typed(workspace['values'][domain]),
        'editable':True,'operations':['set','unset']+(['append'] if domain=='advanced' else []),'hasChildren':domain=='advanced'}
    if domain=='equipment':row['choices']=[{'name':'Zagreus','value':typed(1)},{'name':'Nemesis','value':typed(2)}]
    if domain=='advanced':row['warning']='Unknown native impact'
    if domain.startswith('narrative') and domain!='narrative':
        nyx=domain!='narrativeAchilles'
        row.update(name='First Meeting',englishName='First Meeting',owner=('倪克斯' if cn else 'Nyx') if nyx else ('阿喀琉斯' if cn else 'Achilles'),
            ownerId='npc:Nyx' if nyx else 'npc:Achilles',group='TextLinesRecord',groupId='scene:'+domain,
            content=[{'speaker':('倪克斯' if cn else 'Nyx') if nyx else 'Achilles',
                'text':('不要绝望，孩子。' if cn else 'Do not despair, child.') if nyx else 'Your training awaits.'}])
    return row
def review(workspace):
    actions=[]
    for entry,intent in workspace['pending'].items():
        domain=entry_domain(entry,workspace);value=intent.get('value');row=save_row(domain,workspace)
        actions.append({'id':entry,'name':row['name'],'before':str(workspace['values'][domain]),'after':str(value),
            'operation':intent['operation'],'valueType':row['valueType'],
            'typedValue':value.get('value') if intent['operation']=='append' else value,
            'typedKey':value.get('key') if intent['operation']=='append' else None,'effects':[
                {'id':'linked:rank','name':'Linked rank','before':'0','after':'1'}] if domain=='equipment' else []})
    return {'baselineGeneration':workspace['baseline'],'actions':actions,'count':len(actions),'effectCount':sum(len(a['effects']) for a in actions)}
def summary(workspace):
    return {'workspaceId':workspace['id'],'baselineGeneration':workspace['baseline'],'source':workspace['source'],'sourceSHA256':workspace['sha'],
        'target':workspace.get('target'),'domains':['resources','progression','equipment','relationships','narrative','statistics','history','advanced'],'review':review(workspace)}
def emit(reply):
    result=reply.get('result',{})
    event={key:reply[key] for key in ('id','ok','error') if key in reply}
    event.update(command=request['command'],baselineGeneration=result.get('baselineGeneration'))
    with (folder/'replies.jsonl').open('a') as stream:stream.write(json.dumps(event)+'\n')
    print(json.dumps(reply),flush=True)
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
        workspace={'id':identifier,'source':source,'target':params.get('target'), 'sha':'installed-sha' if (folder/'installed.json').exists() and source['kind']=='currentFile' else 'original-sha','values':data,'pending':{},'baseline':'baseline'+str(next_workspace)+'a','baselineVersion':0,'physical':['shiftA','shiftB','shiftC']}
        workspaces[identifier]=workspace;return summary(workspace)
    workspace=workspaces[params['workspaceId']]
    workspace['language']=params.get('language','en')
    if suffix in ('target','stage','unstage','cancel','apply') and params.get('baselineGeneration')!=workspace['baseline']:
        raise ValueError('This control belongs to an earlier document baseline. Refresh the editor before editing.')
    if suffix=='target':workspace['target']=params['target'];return summary(workspace)
    if suffix=='close':del workspaces[params['workspaceId']];return {'closed':True}
    if suffix=='query':
        if state.get('editorHoldQuery'):time.sleep(.3)
        row=save_row(params['domain'],workspace)
        rows=[row]+([save_row('advancedScalar',workspace)] if params['domain']=='advanced' else [])
        if params['domain']=='advanced' and state.get('editorShift'):rows=[save_row(key,workspace) for key in workspace['physical']]
        if params['domain']=='narrative':
            rows=[save_row(key,workspace) for key in ('narrativeNyx','narrativeNyxShared','narrativeAchilles')]
            if params.get('query'):
                def matches(item):
                    text=' '.join([item['name'],item['owner'],*(part for line in item.get('content',[]) for part in line.values()),
                        'Nyx 倪克斯 Do not despair, child. 不要绝望，孩子。' if item['ownerId']=='npc:Nyx' else 'Achilles 阿喀琉斯 Your training awaits.']).casefold()
                    return all(word.casefold() in text for word in params['query'].split())
                rows=[item for item in rows if matches(item)]
        baseline='old-replayed-baseline' if state.get('editorOldQueryReply') else workspace['baseline']
        return {'baselineGeneration':baseline,'rows':rows,'total':len(rows),'offset':0,'limit':len(rows),'breadcrumbs':[], 'parentId':params.get('parentId')}
    if suffix=='detail':return {'row':save_row(entry_domain(params['entryId'],workspace),workspace,True)}
    if suffix=='stage':
        if state.get('editorDelayTypedStage'):time.sleep(.2)
        if params.get('value',{}).get('value')==999:raise ValueError('Fixture rejected this edit; prior changes retained.')
        node=params.get('value',{})
        if params['operation']=='append':node=node.get('value',{})
        if node.get('luaType')=='table' and node['arraySize']+node['hashSize']!=len(node['entries']):
            raise ValueError('Typed Lua tables require ordered entries and matching allocation counts.')
        workspace['pending'][params['entryId']]={'operation':params['operation'],'value':params.get('value')}
        result=review(workspace)
        if state.get('editorOldReviewReply'):result['baselineGeneration']='old-replayed-baseline'
        return result
    if suffix=='unstage':workspace['pending'].pop(params['entryId'],None);return review(workspace)
    if suffix=='cancel':workspace['pending'].clear();return review(workspace)
    if suffix=='review':return review(workspace)
    if suffix=='apply':
        if state.get('editorApplyFailure'):raise OSError('Fixture recovery required')
        time.sleep(.1)
        removed=[]
        for entry,intent in workspace['pending'].items():
            domain=entry_domain(entry,workspace)
            if intent['operation']=='unset':removed.append(domain)
            else:workspace['values'][domain]=intent['value']
        workspace['physical']=[item for item in workspace['physical'] if item not in removed]
        workspace['baselineVersion']+=1;workspace['baseline']='baseline'+workspace['id'].split(':')[1]+'v'+str(workspace['baselineVersion'])
        workspace['pending'].clear();(folder/'installed.json').write_text(json.dumps(workspace['values']))
        return {'baselineGeneration':workspace['baseline'],'applied':True,'verified':True,'runtimeReloaded':False,'installedSHA256':'installed-sha','hot':True,
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
            emit({'type':'result','id':request['id'],'protocolVersion':HOST_VERSION,'moduleProtocolVersion':MODULE_VERSION,'gameID':args.game,'ok':False,'error':failure})
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
        reply.update(ok=False,error={'code':state.get('fixtureErrorCode','fixture'),'presentation':state['fixtureError']},state=state)
        reply.pop('result')
    emit(reply)
'''

HARNESS = r'''
import AppKit
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String, file: StaticString = #fileID, line: UInt = #line) {
    if !condition() { fatalError(message, file:file, line:line) }
}
func fields(in view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}
func accessibilityElements(in view: NSView) -> [NSObject] {
    var pending: [NSObject] = [view], visited: Set<ObjectIdentifier> = [], result: [NSObject] = []
    while let element=pending.popLast() {
        guard visited.insert(ObjectIdentifier(element)).inserted else { continue }
        result.append(element)
        let children=NSSelectorFromString("accessibilityChildren")
        if element.responds(to:children), let values=element.perform(children)?.takeUnretainedValue() as? [NSObject] { pending.append(contentsOf:values) }
        if let native=element as? NSView { pending.append(contentsOf:native.subviews.map { $0 as NSObject }) }
    }
    return result
}
func accessibilityString(_ element: NSObject, _ name: String) -> String? {
    let selector=NSSelectorFromString(name)
    guard element.responds(to:selector) else { return nil }
    return element.perform(selector)?.takeUnretainedValue() as? String
}
func accessibilityText(in view: NSView) -> [String] {
    accessibilityElements(in:view).flatMap { element in
        ["accessibilityLabel","accessibilityValue"].compactMap { accessibilityString(element,$0) }
    }
}
func accessibilityButton(named name: String, in view: NSView) -> NativeAccessibilityControl? {
    namedNativeControl(view,role:"AXButton",name:name)
}
func nativeHierarchy(in view: NSView) -> String {
    accessibilityElements(in:view).map { element in
        let attributes=["accessibilityRole","accessibilityLabel","accessibilityTitle","accessibilityValue","accessibilityIdentifier"]
            .compactMap { key in accessibilityString(element,key).map { key+"="+$0.debugDescription } }.joined(separator:" ")
        let control: String
        if let field=element as? NSTextField { control=" nativeField="+field.stringValue.debugDescription+" delegate="+String(describing:field.delegate)+" editing=\((field.delegate as? TrainerTextField.Coordinator)?.edit != nil)" }
        else if let editor=element as? NSTextView {
            control=" nativeTextView editable=\(editor.isEditable) selectable=\(editor.isSelectable) fieldEditor=\(editor.isFieldEditor) richText=\(editor.isRichText) importsGraphics=\(editor.importsGraphics)"
                + " quoteSubstitution=\(editor.isAutomaticQuoteSubstitutionEnabled) dashSubstitution=\(editor.isAutomaticDashSubstitutionEnabled)"
                + " textReplacement=\(editor.isAutomaticTextReplacementEnabled) spellingCorrection=\(editor.isAutomaticSpellingCorrectionEnabled) text="+editor.string.debugDescription
        }
        else { control="" }
        return String(describing:type(of:element))+" "+attributes+control
    }.joined(separator:"\n")
}
func requireNativeControl<T>(_ name: String, in view: NSView, file: StaticString = #fileID, line: UInt = #line, find: (NSView) -> T?) -> T {
    let deadline=Date().addingTimeInterval(5)
    repeat {
        view.layoutSubtreeIfNeeded()
        if let control=find(view) { return control }
        pump(0.02)
    } while Date() < deadline
    fatalError(name+" missing after rendering\n"+nativeHierarchy(in:view),file:file,line:line)
}
func pressNativeButton(named name: String, in view: NSView, file: StaticString = #fileID, line: UInt = #line) {
    let button=requireNativeControl("native accessibility button '"+name+"'",in:view,file:file,line:line) { accessibilityButton(named:name,in:$0) }
    check(button.enabled && button.press(),"native accessibility button '"+name+"' rejected Press\n"+nativeHierarchy(in:view),file:file,line:line)
}
func textViews(in view: NSView) -> [NSTextView] {
    (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(textViews)
}
func pump(_ seconds: TimeInterval = 0.1) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}
@main struct Main {
    @MainActor static func main() throws {
        _ = NSApplication.shared
        enableNativeAccessibility()
        let precisionCases: [Double] = [0, -0.0, 25, 1.2345678901234567, 123.45678901234567,
                                       .leastNonzeroMagnitude, .leastNormalMagnitude, .greatestFiniteMagnitude]
        for number in precisionCases {
            let text = HadesSaveValue.number(number).scalarText!
            check(Double(text)?.bitPattern == number.bitPattern, "Save Editor numeric text lost precision: " + text)
        }
        check(HadesSaveValue.number(25).scalarText == "25", "Save Editor integer text lost its compact form")
        let negativeZeroWire=HadesSaveValue.number(-0.0).object
        check(negativeZeroWire["encoding"] as? String == "ieee754" && negativeZeroWire["value"] as? String == "0000000000000080",
            "Save Editor numeric encoding lost the negative-zero sign")
        let negativeZeroInput=HadesSaveValue.inputJSON(#"{"luaType":"table","arraySize":0,"hashSize":1,"entries":[{"key":{"luaType":"string","value":"zero"},"value":{"luaType":"number","value":-0.0}}]}"#)
        check(negativeZeroInput == .table(arraySize:0,hashSize:1,entries:[.init(key:.string("zero"),value:.number(-0.0))]),
            "typed numeric input lost nested negative-zero bits before wire encoding")
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
        func setFixtureError(_ error: String?, code: String = "fixture") throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["fixtureError"]=error
            state["fixtureErrorCode"]=code
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        func setConnection(_ connected: Bool, heroReady: Bool) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["connected"]=connected;state["heroReady"]=heroReady
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        let defaults=InMemoryDefaults()
        let client=BackendClient(process:BackendProcess(executableURL:python,forceKillDelay:0.1))
        let session=TrainerBackendSession(client:client)
        let model=HadesTrainerModel(session:session,backendScriptURL:folder.appendingPathComponent("worker.py"),defaults:defaults,
            logSink:TrainerLogSink(url:folder.appendingPathComponent("trainer.log")))
        var diagnosticEditors: [(String,HadesSaveEditorModel)] = []
        var diagnosticWindows: [(String,NSWindow)] = []
        func fixtureDiagnostics() -> String {
            func json(_ value: Any) -> String {
                let data=try! JSONSerialization.data(withJSONObject:value,options:[.prettyPrinted,.sortedKeys])
                return String(data:data,encoding:.utf8)!
            }
            func journal(_ name:String) -> [[String:Any]] {
                let text=(try? String(contentsOf:folder.appendingPathComponent(name),encoding:.utf8)) ?? ""
                return text.split(separator:"\n").compactMap { try? JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any] }
            }
            let received=commands(), emitted=journal("replies.jsonl")
            let emittedIDs=Set(emitted.compactMap { $0["id"] as? String })
            let state=(try? String(contentsOf:stateURL,encoding:.utf8)) ?? "unreadable"
            let documents=diagnosticEditors.map { name, editor -> [String:Any] in
                ["name":name,"workspace":editor.workspaceID ?? "nil","baseline":editor.baselineGeneration ?? "nil",
                 "domain":editor.domain.rawValue,"search":editor.search,"busy":editor.busy,"applying":editor.applying,
                 "queryLoading":editor.queryLoading,"canEditRows":editor.canEditRows,"canApply":editor.canApply,
                 "target":editor.selectedTargetID,"reviewBaseline":editor.review.baselineGeneration,"reviewCount":editor.review.count,
                 "actions":editor.review.actions.map { ["id":$0.id,"operation":$0.operation,"value":$0.typedValue?.json ?? "nil","key":$0.typedKey?.json ?? "nil"] },
                 "editingRow":editor.editingRow?.id ?? "nil","editingTyped":editor.editingTyped,
                 "receiptBaseline":editor.receipt?.baselineGeneration ?? "nil","recoveryPath":editor.recoveryPath ?? "nil",
                 "failures":editor.failures.mapValues { ["key":$0.key,"arguments":$0.arguments] as [String:Any] },
                 "rows":editor.rows.map { ["id":$0.id,"baseline":$0.baselineGeneration,"value":$0.typedValue?.json ?? "nil","failedDraft":editor.hasFailedDraft($0)] as [String:Any] }]
            }
            let status=session.currentStatus
            let runtime: [String:Any] = ["running":client.isRunning,"started":client.isStarted,
                "inFlight":client.hasInFlightRequest,"queued":client.queuedRequestCount,"lifecycle":session.lifecycleID.uuidString,
                "sessionBusy":status.busy,"operation":status.operation.key,"error":status.error,"errorArguments":status.errorArguments,
                "trainerBusy":model.busy,"connected":model.connected,"heroReady":model.heroReady,"health":model.health,
                "canMutate":model.canMutate,"localError":model.localError]
            let windows=diagnosticWindows.map { name, window -> String in
                let responder=String(describing:window.firstResponder)
                let drafts=(window.contentView.map(fields) ?? []).filter { $0.delegate is TrainerTextField.Coordinator }.map {
                    "\($0.accessibilityLabel() ?? "unlabelled") value=\($0.stringValue.debugDescription) editing=\(($0.delegate as? TrainerTextField.Coordinator)?.edit != nil)"
                }.joined(separator:"\n")
                let sheet=window.attachedSheet.map { sheet in
                    "sheet firstResponder=\(String(describing:sheet.firstResponder))\n"+(sheet.contentView.map(nativeHierarchy) ?? "no content")
                } ?? "no attached sheet"
                return "\(name) visible=\(window.isVisible) firstResponder=\(responder)\nnative drafts:\n\(drafts)\n\(sheet)"
            }.joined(separator:"\n")
            let log=(try? String(contentsOf:folder.appendingPathComponent("trainer.log"),encoding:.utf8)) ?? ""
            return "backend/trainer:\n"+json(runtime)+"\ndocuments:\n"+json(documents)+"\nfixture state:\n"+state
                + "\nworker received without emitted reply:\n"+json(received.filter { !emittedIDs.contains($0["id"] as? String ?? "") })
                + "\nlast 12 worker requests:\n"+json(Array(received.suffix(12)))+"\nlast 12 emitted replies:\n"+json(Array(emitted.suffix(12)))
                + "\nwindows:\n"+windows+"\ntrainer log tail:\n"+log.split(separator:"\n").suffix(12).joined(separator:"\n")
        }
        // The outer Python harness retains only the last native phase if the
        // entire expanded fixture exceeds its global process budget.
        func recordPhase(_ stage: String) {
            try? (String(Date().timeIntervalSince1970)+" "+stage).write(
                to: folder.appendingPathComponent("native-phase.txt"), atomically: true, encoding: .utf8)
        }
        func wait(_ expectation: String, file: StaticString = #fileID, line: UInt = #line, _ condition: () -> Bool) {
            recordPhase("wait: "+expectation)
            let deadline=Date().addingTimeInterval(5)
            while !condition() && Date() < deadline { pump(0.02) }
            if !condition() { fatalError("Timed out after 5s waiting for "+expectation+"\n"+fixtureDiagnostics(),file:file,line:line) }
            recordPhase("passed: "+expectation)
        }
        wait("startup status/catalog replies: connected, catalog populated, trainer idle") { model.connected && !model.catalog.isEmpty && !model.busy }
        check(model.heroReady && model.health==50,"catalog reply erased runtime observation")
        model.listProfiles()
        wait("list_profiles reply: one profile, trainer idle") { !model.busy && model.profiles.count == 1 }
        check(model.connected && model.health==50,"profile inventory erased runtime state")
        check(model.profiles[0].name=="Fixture","Hades profile inventory did not decode")
        model.runDiagnostics()
        wait("diagnostics reply: one check, trainer idle") { !model.busy && model.diagnostics.count == 1 }
        check(model.diagnostics[0].ok && model.connected,"diagnostics payload replaced runtime authority")
        model.saveProfile("Fixture")
        wait("save_profile reply: trainer idle") { !model.busy }
        model.loadProfile("Fixture")
        wait("load_profile reply: trainer idle") { !model.busy }
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

        defaults.set(1, forKey:"hades.shortcut.heal")
        var store=HadesShortcutStore(defaults:defaults)
        check(defaults.object(forKey:"hades.shortcut.heal")==nil,"retired Heal shortcut preference was not removed")
        let clash=store.chord(.fullHealth)
        check(store.set(.invincibility,chord:HotkeyChord(keyCode:clash.keyCode,modifiers:clash.modifiers,keyLabel:"different label")) == .fullHealth,
            "physical shortcut conflict depended on display label")
        let custom=HotkeyChord(keyCode:99,modifiers:HotkeyChord.controlModifier | HotkeyChord.commandModifier,keyLabel:"F3")
        check(store.set(.invincibility,chord:custom)==nil,"valid shortcut failed")
        check(HadesShortcutStore(defaults:defaults).chord(.invincibility)==custom,"shortcut override was not persisted")
        let panic=TrainerHotkeyLayout.disableAllChord
        check(store.chord(.disableAll)==panic,"Disable All did not use the Core-owned panic chord")
        check(store.set(.disableAll,chord:custom) == .disableAll,"Disable All was editable")
        check(store.set(.disableAll,chord:panic)==nil,"reasserting the fixed chord should be harmless")
        let alternateLabel=HotkeyChord(keyCode:51,modifiers:panic.modifiers,keyLabel:"Backspace")
        check(store.set(.fullHealth,chord:alternateLabel) == .disableAll,
              "a display-label change bypassed the panic chord reservation")
        check(HadesShortcutStore(defaults:defaults).chord(.disableAll)==panic,"Disable All chord drifted after reload")
        let saved=InMemoryDefaults()
        saved.set(HotkeyChord(keyCode:98,modifiers:HotkeyChord.commandModifier,keyLabel:"F4").payload,
                  forKey:"hades.shortcut.disableAll")
        saved.set(alternateLabel.payload,forKey:"hades.shortcut.fullHealth")
        saved.set(custom.payload,forKey:"hades.shortcut.invincibility")
        let reloaded=HadesShortcutStore(defaults:saved)
        check(reloaded.chord(.disableAll)==panic && reloaded.chord(.invincibility)==custom,
              "saved overrides displaced the fixed chord or a valid choice")
        check(reloaded.chord(.fullHealth)==HadesShortcutAction.fullHealth.defaultChord,
              "an invalid reserved override survived reload")
        check(saved.object(forKey:"hades.shortcut.disableAll")==nil
              && saved.object(forKey:"hades.shortcut.fullHealth")==nil,
              "invalid panic-key preferences were not retired")
        let identities=HadesWorkbenchCatalog.orderedShortcutActions.map {
            TrainerHotkeyLayout.identity(reloaded.chord($0))
        }
        check(Set(identities).count==identities.count,"reloaded Hades I shortcuts collide")
        store.reset()
        check(HadesShortcutStore(defaults:defaults).chord(.invincibility)==HadesShortcutAction.invincibility.defaultChord,"shortcut reset failed")

        let localization=TrainerLocalizationStore(defaults:InMemoryDefaults())
        localization.language = .en
        localization.registerModulePresentation(prefix:HadesGameModule.presentationKeyPrefix,
            resolver:HadesGameModule.presentationText)
        check(HadesWorkbenchSection.visible == [.values,.common,.boons,.resources,.rooms,.management],
            "workbench order lost the implemented native rooms panel")
        check(HadesWorkbenchCatalog.orderedShortcutActions == [.invincibility,.fullHealth,.moneyNoDecrease,
            .rerollsNoDecrease,.fullGodGauge,.infiniteAmmo,.forceRerolls,.boonRarityEnabled,.generateFishing,.generateChaosGate,.disableAll],"shortcut order drifted from the visible workbench")
        check(HadesShortcutAction.invincibility.defaultChord.displayText=="⌃⌥1"
              && HadesShortcutAction.fullHealth.defaultChord.displayText=="⌃⌥2",
              "retiring Heal did not shift derived shortcuts forward")
        func searchFunctions(_ query: String) -> [HadesWorkbenchEntry] {
            HadesWorkbenchCatalog.matches(query,resources:model.resourceCatalog,worldTerms:model.worldTerms) { key in
                TrainerPresentationLanguage.allCases.map {
                    HadesGameModule.resolveText(key:key,language:$0,localization:localization)
                }
            }
        }
        check(searchFunctions("profile").contains { $0.section == .management && $0.id == "hades.manage.profiles" },
            "profile manager was absent from bilingual workbench discovery")
        let diagnosticsZh = HadesGameModule.resolveText(key:"hades.manage.diagnostics",language:.zhCN,localization:localization)
        let diagnosticsEn = HadesGameModule.resolveText(key:"hades.manage.diagnostics",language:.en,localization:localization)
        check(searchFunctions(diagnosticsZh).contains { $0.id == "hades.manage.diagnostics" }
              && searchFunctions(diagnosticsEn).contains { $0.id == "hades.manage.diagnostics" },
              "current diagnostics label was absent from bilingual workbench discovery")
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
        wait("boon rarity set_feature reply: request received, trainer idle") {
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
        wait("spawn_reward reply for current room: request received, trainer idle") { !model.busy && commands().contains { $0["command"] as? String == "spawn_reward" } }
        let worldArgs = commands().last { $0["command"] as? String == "spawn_reward" }?["params"] as? [String:Any]
        check(worldArgs?["roomId"] as? String == "run:room:1" && (worldArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1", "world mutation lost room/hero ownership")
        model.performShortcut(HadesShortcutAction.generateFishing.rawValue)
        wait("generate_fishing shortcut reply: request received, trainer idle") { !model.busy && commands().contains { $0["command"] as? String == "generate_fishing" } }
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1150,height:2400),styleMask:[.titled],backing:.buffered,defer:false)
        window.isReleasedWhenClosed=false
        let host=NSHostingView(rootView:HadesTrainerView(model:model).environmentObject(localization))
        window.contentView=host;host.frame=NSRect(x:0,y:0,width:1150,height:2400)
        diagnosticWindows.append(("trainer",window))
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
        model.refreshFromHost();wait("focused health draft: status observed health 60, trainer idle") { !model.busy && model.health==60 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="70","background status replaced focused native draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field))
        wait("native health set_value reply: health 70, trainer idle") { !model.busy && model.health==70 }
        let sent=commands().filter { $0["command"] as? String == "set_value" }
        check(sent.count==1,"native commit did not send exactly one mutation")
        let params=sent[0]["params"] as! [String:Any]
        check((params["target"] as? [String:String])?["heroId"]=="run:hero:1","numeric commit lost its captured hero")
        check(params["field"] as? String == "health" && params["value"] as? Double == 70,"numeric commit changed the wrong value")

        coordinator.begin();field.stringValue="80"
        coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:field))
        try updateState(hero:"run:hero:2",health:30)
        model.refreshFromHost();wait("hero replacement status: health 30, trainer idle") { !model.busy && model.health==30 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="80","hero replacement erased focused draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field));pump()
        check(commands().filter { $0["command"] as? String == "set_value" }.count==1,"stale draft mutated replacement hero")
        check(model.localError=="hades.error.staleHero","stale draft lacked actionable feedback")
        try updateState(hero:"run:hero:2",health:31)
        model.refreshFromHost();wait("unfocused health status: health 31, trainer idle") { !model.busy && model.health==31 };host.layoutSubtreeIfNeeded();pump()
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
        diagnosticEditors.append(("active",editor))
        let tools = TrainerToolWindowStore()
        var editorFactories = 0
        let editorWindow = tools.open(id:"hades-save-editor",title:"Hades Save Editor",localization:localization,theme:.standard) {
            editorFactories += 1
            return TrainerToolWindowContent(canClose:{ !editor.busy },onClose:editor.close) { HadesSaveEditorView(model:editor) }
        }
        diagnosticWindows.append(("active editor",editorWindow))
        wait("active save_editor inventory/open/query replies: pinned workspace, initial rows, editor idle") { editor.workspaceID != nil && !editor.busy && !editor.queryLoading && !editor.rows.isEmpty }
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
        editor.refreshInventory();wait("active save_editor_inventory reply after active-profile change") { !editor.busy }
        check(editor.workspaceID == pinnedWorkspace && editor.sourceSHA256 == pinnedSHA
            && editor.source?.relativePath == "Profile1.sav","active profile switch redirected a pinned document")
        guard let gemsField=fields(in:editorWindow.contentView!).first(where:{$0.accessibilityLabel()=="Gems"}),
              let gemsCoordinator=gemsField.delegate as? TrainerTextField.Coordinator else { fatalError("native save resource field missing") }
        gemsCoordinator.begin();gemsField.stringValue="80"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        editor.query();wait("active save_editor_query reply while native Gems draft focused") { !editor.queryLoading };editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(gemsField.stringValue == "80","query replaced a focused Save Editor draft")
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        check(!tools.canCloseAll,"Host allowed close/quit during a pending editor write")
        wait("native Gems 80 save_editor_stage/query replies: one acknowledged action, editor idle") { !editor.busy && editor.review.count == 1 && !editor.queryLoading }
        check(editor.review.actions.first?.typedValue == .number(80),"completed native input did not enter Changes")
        gemsCoordinator.begin();gemsField.stringValue="90"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        wait("native Gems revision save_editor_stage reply: acknowledged value 90") { !editor.busy && editor.review.actions.first?.typedValue == .number(90) }
        check(editor.review.count == 1,"revising a field duplicated the user action")
        editor.unstage("entry:resources",baseline:editor.baselineGeneration!);wait("resource save_editor_unstage reply: empty Changes") { !editor.busy && editor.review.count == 0 }
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(gemsField.stringValue == "25","removing an intent did not restore the source observation")
        editor.stage("entry:resources",operation:"set",value:HadesSaveValue.number(75).object,workspace:pinnedWorkspace,baseline:editor.baselineGeneration!)
        wait("resource 75 save_editor_stage reply: one acknowledged action") { !editor.busy && editor.review.count == 1 }
        editor.stage("entry:statistics",operation:"set",value:HadesSaveValue.number(999).object,workspace:pinnedWorkspace,baseline:editor.baselineGeneration!)
        wait("statistics 999 save_editor_stage rejection: row error, editor idle") { !editor.busy && editor.failures["entry:statistics"] != nil }
        check(editor.review.count == 1 && editor.review.actions[0].id == "entry:resources",
            "a rejected edit erased acknowledged pending work")
        editor.selectDomain(.progression);editor.selectDomain(.statistics)
        wait("rapid progression/statistics save_editor_query: current statistics row accepted") { !editor.queryLoading && editor.rows.first?.id == "entry:statistics" }
        let statsField=requireNativeControl("native precise statistics field",in:editorWindow.contentView!) {
            fields(in:$0).first(where:{$0.accessibilityLabel()=="Gameplay Time"})
        }
        guard let statsCoordinator=statsField.delegate as? TrainerTextField.Coordinator else {
            fatalError("native statistics input coordinator missing")
        }
        check(Double(statsField.stringValue) == 4.123456789012345,"native Save Editor initial value lost decimal precision")
        let beforeRoundedInteger=commands().count
        statsCoordinator.begin();statsField.stringValue="9007199254740993"
        statsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:statsField))
        statsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:statsField))
        pump()
        check(commands().count==beforeRoundedInteger && editor.failures["entry:statistics"] != nil,
            "an unrepresentable integer draft was silently rounded and staged")
        let preciseStatistic=123.45678901234567
        statsCoordinator.begin();statsField.stringValue=String(preciseStatistic)
        statsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:statsField))
        statsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:statsField))
        check(Double(statsField.stringValue) == preciseStatistic,"native Save Editor commit rounded its completed decimal draft")
        wait("precise native statistics save_editor_stage/query replies: two acknowledged actions") {
            !editor.busy && !editor.queryLoading && editor.review.count == 2
        }
        check(editor.review.actions.first(where:{$0.id=="entry:statistics"})?.typedValue == .number(preciseStatistic)
            && Double(statsField.stringValue) == preciseStatistic,"acknowledged Changes and native decimal input disagree")
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorOldReviewReply"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.stage("entry:equipment",operation:"set",value:HadesSaveValue.number(2).object,workspace:pinnedWorkspace,baseline:editor.baselineGeneration!)
        wait("old-baseline equipment save_editor_stage reply: rejected review, row error") { !editor.busy && editor.failures["entry:equipment"] != nil }
        check(editor.review.count == 2 && editor.review.baselineGeneration == editor.baselineGeneration && !editor.canApply,
            "a replayed old-baseline review replaced acknowledged Changes or enabled Apply")
        saveState["editorOldReviewReply"]=false
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.stage("entry:equipment",operation:"set",value:HadesSaveValue.number(2).object,workspace:pinnedWorkspace,baseline:editor.baselineGeneration!)
        wait("current-baseline equipment save_editor_stage reply: three acknowledged actions") { !editor.busy && editor.review.count == 3 }
        check(editor.review.effectCount == 1 && editor.review.actions.first(where:{$0.id=="entry:equipment"})?.effects.first?.name == "Linked rank",
            "linked equipment effects were hidden from Changes")
        editor.detail("entry:equipment");wait("equipment save_editor_detail reply: basket revision row") { !editor.busy && editor.editingRow?.id == "entry:equipment" }
        check(editor.editingRow?.choices?.count == 2,"basket revision lost native selection choices")
        editor.dismissDetail()
        wait("equipment sheet did not finish dismissal") { editorWindow.attachedSheet == nil }
        editor.selectDomain(.advanced);wait("Advanced save_editor_query reply: table row accepted") { !editor.queryLoading && editor.rows.first?.id == "entry:advanced" }
        let advanced=editor.rows.first!
        let beforeInvalidJSON=commands().count
        check(!editor.commitJSON(advanced,text:"3",workspace:pinnedWorkspace),"an untyped JSON fragment was accepted")
        check(!editor.commitJSON(advanced,text:#"{"luaType":"number","value":9007199254740993}"#,workspace:pinnedWorkspace),
            "typed JSON silently rounded an integer value")
        check(!editor.commitJSON(advanced,text:#"{"luaType":"table","arraySize":0,"hashSize":1,"entries":[{"key":{"luaType":"number","value":9007199254740993},"value":{"luaType":"nil"}}]}"#,workspace:pinnedWorkspace),
            "typed JSON silently rounded a nested integer key")
        check(!editor.commitJSON(advanced,text:HadesSaveValue.number(1).json,
            appendKey:#"{"luaType":"number","value":9007199254740993}"#,workspace:pinnedWorkspace),
            "typed append silently rounded its integer key")
        check(commands().count==beforeInvalidJSON,"invalid typed numeric input reached the backend")
        let raw=HadesSaveValue.table(arraySize:0,hashSize:2,entries:[
            .init(key:.string("unknown"),value:.number(8)),.init(key:.rawString("/wA="),value:.rawNumber("000000000000f87f"))])
        check(editor.commitJSON(advanced,text:raw.json,workspace:pinnedWorkspace),"typed Advanced value was rejected locally")
        wait("raw table save_editor_stage reply: four acknowledged actions") { !editor.busy && editor.review.count == 4 }
        check(editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedValue == raw,
            "Advanced editing lost raw strings, table metadata or IEEE bits")
        check(editor.commitJSON(advanced,text:HadesSaveValue.number(9).json,
            appendKey:HadesSaveValue.string("new-key").json,workspace:pinnedWorkspace),"typed append was rejected locally")
        wait("typed append save_editor_stage reply: acknowledged append operation") { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.operation == "append" }
        check(editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedKey == .string("new-key"),
            "append revision lost the physical typed key")
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorDelayTypedStage"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.detail("entry:advanced",typed:true)
        wait("typed rejection save_editor_detail reply and attached Advanced sheet") { !editor.busy && editor.editingRow?.id == "entry:advanced" && editorWindow.attachedSheet != nil }
        guard let rejectedSheet=editorWindow.attachedSheet, let rejectedContent=rejectedSheet.contentView else {
            fatalError("typed rejection sheet missing")
        }
        recordPhase("native typed rejection: locate AppKit controls")
        rejectedContent.layoutSubtreeIfNeeded();pump()
        let rejectedJSON=requireNativeControl("typed rejection sheet value NSTextView",in:rejectedContent) {
            textViews(in:$0).first(where:{$0.isEditable && !$0.isFieldEditor && $0.accessibilityLabel()==advanced.name})
        }
        let rejectedKey=requireNativeControl("typed rejection sheet append-key NSTextView",in:rejectedContent) {
            textViews(in:$0).first(where:{$0.isEditable && !$0.isFieldEditor && $0.accessibilityLabel()==HadesPresentation.text("hades.saveEditor.key",language:.en)})
        }
        _=requireNativeControl("typed rejection sheet Done accessibility button",in:rejectedContent) {
            accessibilityButton(named:localization.localized("host.done"),in:$0)
        }
        check(rejectedJSON.string == HadesSaveValue.number(9).json && rejectedKey.string == HadesSaveValue.string("new-key").json,
            "typed append sheet did not initialize its acknowledged value/key\n"+nativeHierarchy(in:rejectedContent))
        let draftKey=HadesSaveValue.string("retained-draft-key").json
        func replaceTypedJSON(_ value:String,field:NSTextView,window:NSWindow,file:StaticString = #fileID,line:UInt = #line) {
            check(!field.isRichText && !field.importsGraphics && !field.isAutomaticQuoteSubstitutionEnabled
                && !field.isAutomaticDashSubstitutionEnabled && !field.isAutomaticTextReplacementEnabled
                && !field.isAutomaticSpellingCorrectionEnabled,
                "typed JSON native control permits automatic text transformation\n"+nativeHierarchy(in:window.contentView!),file:file,line:line)
            check(field.frame.height >= field.enclosingScrollView!.contentSize.height,
                "typed JSON native text view does not cover its scroll viewport",file:file,line:line)
            check(window.makeFirstResponder(field),"typed JSON control did not acquire focus",file:file,line:line)
            field.selectAll(nil);field.insertText(value,replacementRange:field.selectedRange())
            let selection=field.selectedRange();pump(0.03)
            check(field.string == value && field.selectedRange() == selection && window.firstResponder === field,
                "native JSON insertion changed the literal draft, selection or focus\n"+nativeHierarchy(in:window.contentView!),file:file,line:line)
        }
        replaceTypedJSON(draftKey,field:rejectedKey,window:rejectedSheet)
        let rejectedValue = #"{"luaType":"table","arraySize":0,"hashSize":1,"entries":[]}"#
        replaceTypedJSON(rejectedValue,field:rejectedJSON,window:rejectedSheet)
        pressNativeButton(named:localization.localized("host.done"),in:rejectedContent)
        wait("native typed Done: save_editor_stage in flight") { editor.busy }
        check(editor.busy && editor.editingRow != nil && editorWindow.attachedSheet === rejectedSheet,
            "Done dismissed the typed draft before Stage acknowledgment")
        wait("native typed Done save_editor_stage rejection: allocation-count row error") { !editor.busy && editor.failures["entry:advanced"] != nil }
        check(editorWindow.attachedSheet === rejectedSheet && rejectedJSON.string == rejectedValue
            && rejectedKey.string == draftKey && editor.hasFailedDraft(advanced) && !editor.canApply,
            "asynchronous typed rejection lost JSON/key text or allowed Apply")
        check(editor.review.count == 4 && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedValue == .number(9)
            && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedKey == .string("new-key"),
            "typed rejection replaced acknowledged Changes")
        check(accessibilityText(in:rejectedContent).contains(where:{$0.contains("matching allocation counts")}),
            "the typed sheet hid its asynchronous rejection reason")
        recordPhase("native typed correction: replace JSON")
        let correctedJSON=HadesSaveValue.number(10).json
        replaceTypedJSON(correctedJSON,field:rejectedJSON,window:rejectedSheet)
        pressNativeButton(named:localization.localized("host.done"),in:rejectedContent)
        wait("native corrected Done: save_editor_stage in flight with both JSON inputs disabled") {
            editor.busy && !rejectedJSON.isEditable && !rejectedJSON.isSelectable
                && !rejectedKey.isEditable && !rejectedKey.isSelectable
        }
        check(editor.busy && editor.editingRow != nil && editorWindow.attachedSheet === rejectedSheet,
            "corrected typed input closed before matching acceptance")
        for field in [rejectedJSON,rejectedKey] {
            _=rejectedSheet.makeFirstResponder(field)
            check(rejectedSheet.firstResponder !== field && !field.isEditable && !field.isSelectable,
                "disabled typed JSON input accepted focus while Stage acknowledgment was pending\n"+nativeHierarchy(in:rejectedContent))
        }
        wait("corrected native Done save_editor_stage acceptance and sheet dismissal") {
            check(rejectedJSON.string == correctedJSON && rejectedKey.string == draftKey,
                "literal JSON/key drifted while awaiting Stage acknowledgment\n"+nativeHierarchy(in:rejectedContent))
            return !editor.busy && editor.editingRow == nil && editorWindow.attachedSheet == nil
        }
        check(editor.review.count == 4 && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedValue == .number(10)
            && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedKey == .string("retained-draft-key")
            && !editor.hasFailedDraft(advanced) && editor.canApply,
            "accepted typed correction lost its key, value or basket ownership, or left Apply blocked")
        editor.detail("entry:advanced",typed:true)
        wait("typed discard save_editor_detail reply and attached sheet") { !editor.busy && editor.editingRow != nil && editorWindow.attachedSheet != nil }
        guard let discardSheet=editorWindow.attachedSheet, let discardContent=discardSheet.contentView else {
            fatalError("typed discard sheet missing")
        }
        discardContent.layoutSubtreeIfNeeded();pump()
        let discardJSON=requireNativeControl("typed discard sheet value NSTextView",in:discardContent) {
            textViews(in:$0).first(where:{$0.isEditable && !$0.isFieldEditor && $0.accessibilityLabel()==advanced.name})
        }
        _=requireNativeControl("typed discard sheet Done accessibility button",in:discardContent) {
            accessibilityButton(named:localization.localized("host.done"),in:$0)
        }
        _=requireNativeControl("typed discard sheet Cancel accessibility button",in:discardContent) {
            accessibilityButton(named:localization.localized("host.cancel"),in:$0)
        }
        replaceTypedJSON(rejectedValue,field:discardJSON,window:discardSheet)
        pressNativeButton(named:localization.localized("host.done"),in:discardContent)
        wait("second native typed Done save_editor_stage rejection: retained failed draft") { !editor.busy && editor.hasFailedDraft(advanced) }
        pressNativeButton(named:localization.localized("host.cancel"),in:discardContent)
        wait("native typed Cancel: draft discarded and sheet dismissed") { editor.editingRow == nil && editorWindow.attachedSheet == nil }
        check(!editor.hasFailedDraft(advanced) && editor.canApply && editor.review.count == 4
            && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.typedValue == .number(10),
            "deliberate typed draft discard lost acknowledged Changes or left Apply blocked")
        saveState["editorDelayTypedStage"]=false
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        check(editor.commitJSON(advanced,text:raw.json,workspace:pinnedWorkspace),"revising append to table set failed")
        wait("raw table revision save_editor_stage reply: acknowledged set operation") { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advanced"})?.operation == "set" }
        editor.detail("entry:advancedScalar",typed:true)
        wait("Advanced scalar save_editor_detail reply and attached typed sheet") { !editor.busy && editor.editingRow?.id == "entry:advancedScalar" && editor.editingTyped
            && editorWindow.attachedSheet != nil }
        guard let typedSheet=editorWindow.attachedSheet, let typedContent=typedSheet.contentView else {
            fatalError("Advanced scalar typed sheet missing")
        }
        typedContent.layoutSubtreeIfNeeded();pump()
        guard let typedField=textViews(in:typedContent).first(where:{ $0.isEditable && !$0.isFieldEditor }) else {
            fatalError("Advanced scalar typed editor missing native text control")
        }
        let scalarText="typed-scalar -- “literal”"
        replaceTypedJSON(HadesSaveValue.string(scalarText).json,field:typedField,window:typedSheet)
        pump();pressNativeButton(named:localization.localized("host.done"),in:typedContent)
        wait("Advanced scalar native Done: acknowledged type change and sheet dismissal") {
            !editor.busy && editor.review.actions.first(where:{$0.id=="entry:advancedScalar"})?.typedValue == .string(scalarText)
                && editor.editingRow == nil && editorWindow.attachedSheet == nil
        }
        check(editor.review.count == 5,"Advanced scalar type change replaced unrelated intents")
        editor.detail("entry:advancedScalar")
        wait("typed scalar basket save_editor_detail reply and attached revision sheet") { !editor.busy && editor.editingRow != nil && editorWindow.attachedSheet != nil }
        check(editor.editingTyped,"basket revision forgot the scalar's typed editing route")
        pressNativeButton(named:localization.localized("host.cancel"),in:editorWindow.attachedSheet!.contentView!)
        wait("typed scalar revision native Cancel: sheet dismissed with draft cleanup") { editor.editingRow == nil && editorWindow.attachedSheet == nil }
        let backup=model.makeSaveEditorModel(snapshotID:"verified-fixture")
        diagnosticEditors.append(("backup",backup))
        backup.open(language:.en)
        wait("backup save_editor inventory/open/query replies: independent workspace ready") { backup.workspaceID != nil && !backup.busy && !backup.queryLoading }
        check(backup.source?.kind == "managedBackup" && backup.source?.snapshotId == "verified-fixture"
            && backup.workspaceID != editor.workspaceID,"backup document shared the active workspace")
        let backupID=backup.workspaceID
        editor.selectDomain(.resources);wait("pre-Apply resource save_editor_query reply: editable current rows") { !editor.queryLoading && editor.canEditRows }
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        guard let applyDraftField=fields(in:editorWindow.contentView!).first(where:{$0.accessibilityLabel()=="Gems"}),
              let applyDraftCoordinator=applyDraftField.delegate as? TrainerTextField.Coordinator else {
            fatalError("native pre-Apply draft field missing")
        }
        let preApplyBaseline=editor.baselineGeneration!
        let backupBaseline=backup.baselineGeneration
        let applyCount=commands().filter{$0["command"] as? String == "save_editor_apply"}.count
        applyDraftCoordinator.begin();applyDraftField.stringValue="76"
        applyDraftCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:applyDraftField))
        editor.apply(baseline:preApplyBaseline);pump()
        check(!editor.canApply && editor.baselineGeneration == preApplyBaseline && applyDraftField.stringValue == "76",
            "Apply discarded or crossed an unfinished focused draft")
        check(commands().filter{$0["command"] as? String == "save_editor_apply"}.count == applyCount,
            "Apply dispatched before native edit completion")
        applyDraftCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:applyDraftField))
        wait("pre-Apply native draft save_editor_stage reply: acknowledged Gems 76") { !editor.busy && editor.review.actions.first(where:{$0.id=="entry:resources"})?.typedValue == .number(76) }
        applyDraftCoordinator.begin();applyDraftField.stringValue="invalid"
        applyDraftCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:applyDraftField))
        applyDraftCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:applyDraftField))
        editor.apply(baseline:preApplyBaseline);pump()
        check(!editor.canApply && applyDraftField.stringValue == "invalid" && editor.baselineGeneration == preApplyBaseline,
            "invalid completed input was lost or permitted Apply")
        check(editor.review.actions.first(where:{$0.id=="entry:resources"})?.typedValue == .number(76)
            && backup.baselineGeneration == backupBaseline && backup.canEditRows,
            "invalid draft erased acknowledged work or locked another document")
        editor.stage("entry:equipment",operation:"set",value:HadesSaveValue.number(2).object,workspace:pinnedWorkspace,baseline:preApplyBaseline)
        wait("unrelated equipment save_editor_stage/query replies while invalid Gems draft remains") { !editor.busy && !editor.queryLoading };pump()
        check(applyDraftField.stringValue == "invalid" && !editor.canApply,
            "an unrelated completed edit replaced an invalid native draft")
        applyDraftCoordinator.begin();applyDraftField.stringValue="75"
        applyDraftCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:applyDraftField))
        applyDraftCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:applyDraftField))
        wait("corrected native Gems 75 save_editor_stage/query replies: Apply enabled") { !editor.busy && editor.canApply && !editor.queryLoading }
        let oldResourceRow=editor.rows.first!
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorHoldQuery"]=true;saveState["editorOldQueryReply"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.selectTarget("fixture/Profile2.sav",baseline:editor.baselineGeneration);wait("save_editor_target reply: explicit Profile2 target accepted") { !editor.busy && editor.selectedTargetID == "fixture/Profile2.sav" }
        editor.apply(baseline:editor.baselineGeneration);wait("active save_editor_apply reply: verified receipt accepted, editor idle") { !editor.busy && editor.receipt != nil }
        let countBeforeOldCommit=commands().filter{$0["command"] as? String == "save_editor_stage"}.count
        _=editor.commit(oldResourceRow,text:"888",workspace:pinnedWorkspace)
        check(!editor.canEditRows && !editor.canApply && editor.baselineGeneration != preApplyBaseline,
            "Apply receipt enabled controls before fresh matching rows")
        wait("post-Apply deliberately old save_editor_query reply completed") { !editor.queryLoading }
        check(!editor.canEditRows,"an old-baseline query reply enabled mutation controls")
        check(commands().filter{$0["command"] as? String == "save_editor_stage"}.count == countBeforeOldCommit,
            "old visible row queued a mutation during the post-Apply refresh gap")
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorHoldQuery"]=false;saveState["editorOldQueryReply"]=false
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        editor.query();wait("post-Apply current save_editor_query reply: matching baseline editable") { !editor.queryLoading && editor.canEditRows }
        _=editor.commit(oldResourceRow,text:"889",workspace:pinnedWorkspace);pump()
        check(commands().filter{$0["command"] as? String == "save_editor_stage"}.count == countBeforeOldCommit,
            "a stale native binding adopted the fresh baseline authority")

        check(editor.review.count == 0 && editor.sourceSHA256 == pinnedSHA && editor.workspaceID == pinnedWorkspace,
            "Apply replaced the fixed originally read document")
        check(editor.receipt?.target.relativePath == "Profile2.sav" && editor.receipt?.runtimeReloaded == false
            && editor.receipt?.previousSnapshotId == "fixture-prewrite","Apply receipt lost target, backup or runtime meaning")
        check(backup.workspaceID == backupID && backup.review.count == 0,"active Apply changed another document")
        editor.selectDomain(.resources);wait("verified candidate resource save_editor_query reply") { !editor.queryLoading }
        check(editor.rows.first?.typedValue == .number(75),"Apply did not refresh the verified candidate values")
        check(editor.workspaceID == pinnedWorkspace && editor.sourceSHA256 == pinnedSHA && backup.workspaceID == backupID,
            "post-Apply refresh retargeted an existing pinned document")
        editor.selectDomain(.statistics);wait("verified candidate precise statistics save_editor_query reply") { !editor.queryLoading }
        let installedStats=requireNativeControl("post-Apply precise statistics field",in:editorWindow.contentView!) {
            fields(in:$0).first(where:{$0.accessibilityLabel()=="Gameplay Time"})
        }
        check(editor.rows.first?.typedValue == .number(preciseStatistic) && Double(installedStats.stringValue) == preciseStatistic,
            "Apply reread changed the precise numeric value or its editable text")
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorShift"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        let shifted=model.makeSaveEditorModel()
        diagnosticEditors.append(("shifted",shifted))
        shifted.open(language:.en);wait("shifted save_editor inventory/open/query replies: current baseline editable") { shifted.canEditRows && !shifted.busy }
        shifted.selectDomain(.advanced);wait("shifted Advanced save_editor_query reply: three physical rows") { !shifted.queryLoading && shifted.rows.count == 3 }
        let shiftedWindow=tools.open(id:"hades-shifted-editor",title:"Shifted Save Editor",localization:localization,theme:.standard) {
            TrainerToolWindowContent(canClose:{ !shifted.busy },onClose:shifted.close) { HadesSaveEditorView(model:shifted) }
        }
        diagnosticWindows.append(("shifted editor",shiftedWindow))
        let oldA=shifted.rows[0], oldB=shifted.rows[1]
        let oldShiftBaseline=shifted.baselineGeneration!
        shifted.stage(oldA.id,operation:"unset",workspace:shifted.workspaceID,baseline:oldA.baselineGeneration)
        wait("shifted unset-A save_editor_stage/query replies: one acknowledged action") { !shifted.busy && !shifted.queryLoading && shifted.review.count == 1 }
        shiftedWindow.contentView?.layoutSubtreeIfNeeded();pump()
        guard let oldBField=fields(in:shiftedWindow.contentView!).first(where:{$0.accessibilityLabel()=="Shift B"}),
              let oldBCoordinator=oldBField.delegate as? TrainerTextField.Coordinator else {
            fatalError("native old-B occurrence control missing")
        }
        func completeOldB(_ text:String) {
            oldBCoordinator.begin();oldBField.stringValue=text
            oldBCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:oldBField))
            oldBCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:oldBField))
        }
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorHoldQuery"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        let shiftedStageCount=commands().filter{$0["command"] as? String == "save_editor_stage"}.count
        shifted.apply(baseline:oldShiftBaseline)
        completeOldB("900")
        wait("shifted save_editor_apply reply: verified new-baseline receipt") { shifted.receipt != nil && !shifted.busy }
        check(!shifted.canEditRows,"shifted document enabled old rows in its Apply/query gap")
        completeOldB("901")
        _=backup.commit(backup.rows.first!,text:"50",workspace:backup.workspaceID)
        wait("independent backup Gems 50 save_editor_stage reply during shifted refresh") { !backup.busy && backup.review.count == 1 }
        check(backup.baselineGeneration == backupBaseline && backup.canEditRows,
            "another document's Apply blocked or re-owned the backup edit")
        wait("shifted post-Apply save_editor_query reply: matching baseline editable") { !shifted.queryLoading && shifted.canEditRows }
        check(shifted.rows.map(\.name) == ["Shift B","Shift C"] && shifted.rows[1].typedValue == .number(33),
            "deleting A changed the saved value of shifted C")
        completeOldB("902");pump()
        check(commands().filter{$0["command"] as? String == "save_editor_stage"}.count == shiftedStageCount + 1,
            "old B was queued against C's reused physical occurrence")
        var rejectedOldBaseline=false
        session.send("save_editor_stage",params:["workspaceId":shifted.workspaceID!,"baselineGeneration":oldShiftBaseline,
            "entryId":oldB.id,"operation":"set","value":HadesSaveValue.number(903).object],
            operation:"hades.saveEditor.title",announceSuccess:false,reply:{ rejectedOldBaseline = !$0.success })
        wait("direct old-baseline save_editor_stage reply: server rejection callback") { rejectedOldBaseline }
        shifted.query();wait("shifted save_editor_query reply after old-ID rejection") { !shifted.queryLoading }
        check(shifted.rows[1].typedValue == .number(33),"server accepted an old physical ID against the new baseline")
        shiftedWindow.performClose(nil);pump()
        check(shifted.workspaceID == nil,"closing shifted document retained stale occurrence authority")
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorHoldQuery"]=false;saveState["editorShift"]=false
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)

        editor.selectDomain(.narrative);wait("narrative save_editor_query reply: three scenes across distinct owners") { !editor.queryLoading && editor.rows.count == 3 }
        check(Set(editor.rows.map(\.ownerId)).count == 2 && Set(editor.rows.map(\.name)).count == 1,
            "same-name scenes merged distinct character owners")
        check(editor.rows.first?.group == "TextLinesRecord" && editor.rows.first?.content?.first?.text == "Do not despair, child.",
            "native global narrative rows lost their source dialogue")
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(accessibilityText(in:editorWindow.contentView!).contains(where:{$0.contains("Do not despair, child.")}),
            "dialogue text was not directly exposed in the native owner card")
        editor.search="Nyx";editor.searchChanged()
        wait("Nyx typeahead save_editor_query reply: only two Nyx scenes") { !editor.queryLoading && editor.rows.count == 2 && editor.rows.allSatisfy{$0.ownerId == "npc:Nyx"} }
        check(!editor.rows.contains{$0.ownerId == "npc:Achilles"} && editor.search == "Nyx",
            "Nyx search included another character or lost the query")
        editor.search="不要绝望";editor.searchChanged()
        wait("Chinese dialogue typeahead save_editor_query reply: only two Nyx scenes") { !editor.queryLoading && editor.rows.count == 2 && editor.rows.allSatisfy{$0.ownerId == "npc:Nyx"} }
        editor.search="Nyx";editor.searchChanged();wait("restored Nyx typeahead save_editor_query reply: two scenes") { !editor.queryLoading && editor.rows.count == 2 }
        let played=editor.rows.first!
        editor.stage(played.id,operation:"set",value:HadesSaveValue.boolean(false).object,
            workspace:editor.workspaceID,baseline:played.baselineGeneration)
        wait("narrative Played save_editor_stage reply: one acknowledged action") { !editor.busy && editor.review.count == 1 }
        editor.detail(played.id,baseline:played.baselineGeneration);wait("narrative basket save_editor_detail reply: native Played row") { !editor.busy && editor.editingRow != nil }
        check(!editor.editingTyped && editor.editingRow?.content?.first?.speaker == "Nyx",
            "narrative basket revision lost the native Played control or scene content")
        editor.dismissDetail();pump()
        editor.unstage(played.id,baseline:played.baselineGeneration);wait("narrative save_editor_unstage reply: empty Changes") { !editor.busy && editor.review.count == 0 }
        localization.language = .zhCN
        wait("Chinese language save_editor_query/review replies: two localized Nyx scenes") { !editor.queryLoading && editor.rows.count == 2 && editor.rows.first?.content?.first?.speaker == "倪克斯" }
        check(editor.rows.first?.content?.first?.text == "不要绝望，孩子。" && editor.search == "Nyx",
            "language refresh lost bilingual visible dialogue search")
        localization.language = .en;editor.search="";editor.searchChanged()
        wait("English narrative clear-search save_editor_query reply: all three scenes") { !editor.queryLoading && editor.rows.count == 3 }
        backup.selectDomain(.resources);wait("backup resource save_editor_query reply before recovery journey") { !backup.queryLoading }
        _=backup.commit(backup.rows.first!,text:"50",workspace:backup.workspaceID)
        wait("backup resource save_editor_stage reply before recovery Apply") { !backup.busy && backup.review.count == 1 }
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorApplyFailure"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        backup.apply(baseline:backup.baselineGeneration);wait("backup save_editor_apply failure: visible recovery path, editor idle") { !backup.busy && backup.recoveryPath != nil }
        check(backup.review.count == 1 && !backup.canApply,"uncertain Apply lost edits or allowed automatic replay")
        check(backup.failures["apply"]?.arguments.first == "Fixture recovery required","failure did not carry actionable detail")
        let editorRequests=commands().filter { ($0["command"] as? String)?.hasPrefix("save_editor_") == true }
        check(editorRequests.allSatisfy { $0["fixtureGame"] as? String == "hades" },"Save Editor crossed its game context")
        backup.close();check(backup.workspaceID == nil,"closing a backup retained its workspace identity")
        editorWindow.performClose(nil);pump()
        check(editor.workspaceID == nil,"Host close did not release the active editor")
        wait("active save_editor_close received by worker for the originally pinned workspace") {
            commands().contains { $0["command"] as? String == "save_editor_close"
                && ($0["params"] as? [String:Any])?["workspaceId"] as? String == pinnedWorkspace }
        }
        print("hades_save_editor_native_control_journeys_ok")

        var lifetimeState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        lifetimeState["traits"]=[["instanceId":"effect:temporary:1","name":"TemporaryImprovedWeaponTrait",
            "rarity":"Common","level":1,"canEdit":true,"canRemove":true,"limitation":"",
            "remainingUses":3,"canSetUses":true,"canExpire":true]]
        try JSONSerialization.data(withJSONObject:lifetimeState).write(to:stateURL,options:.atomic)
        model.refreshFromHost();wait("temporary-effect status reply: three remaining uses") { !model.busy && model.traits.first?.remainingUses==3 }
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
        wait("native remaining-use set_trait_uses reply: six uses observed") { !model.busy && model.traits.first?.remainingUses==6 }
        host.layoutSubtreeIfNeeded();pump()
        check(usesField.stringValue=="6","remaining-use commit did not refresh observation")
        let usesRequests=commands().filter { $0["command"] as? String == "set_trait_uses" }
        let usesParams=usesRequests.last?["params"] as? [String:Any]
        check(usesRequests.count==1 && usesParams?["instanceId"] as? String == "effect:temporary:1"
            && (usesParams?["target"] as? [String:String])?["heroId"]=="run:hero:2",
            "remaining-use commit lost its selected effect or hero")
        for connected in [true,false] {
            try setConnection(connected,heroReady:false)
            model.refreshFromHost();wait("no-hero status reply: connected=\(connected), trainer idle") { !model.busy && model.connected==connected && !model.heroReady }
            check(model.hostActionsEnabled && !model.canMutate,"offline shortcut fixture retained a hero")
            let disabled=commands().filter { $0["command"] as? String == "disable_all" }.count
            model.performShortcut(HadesShortcutAction.disableAll.rawValue)
            wait("no-hero disable_all reply: request received, trainer idle (connected=\(connected))") {
                !model.busy && commands().filter { $0["command"] as? String == "disable_all" }.count==disabled+1
            }
            check(model.feedback?.text.key == (connected ? "host.backend.notice.completed" : "hades.disableAllPending"),
                "Disable All feedback did not distinguish native cleanup from detached desired reset")
            let afterDisable=commands().count
            model.performShortcut(HadesShortcutAction.generateFishing.rawValue);pump()
            check(commands().count==afterDisable,"a hero-owned shortcut ran without a hero")
        }
        try setConnection(true,heroReady:true)
        model.refreshFromHost();wait("restored hero status reply: trainer mutation authority") { !model.busy && model.canMutate }
        try setFixtureError("host.timeWarp.error.verifyFailed",code:"time_warp_verify_failed")
        model.refreshFromHost();wait("known Time Warp verification failure: trainer idle") { !model.busy && model.backendStatus.errorCode=="time_warp_verify_failed" }
        check(model.connected && model.canMutate,"a known verification failure discarded a trusted runtime")
        for (key,code) in [("hades.error.outcomeUnknown","outcome_unknown"),("hades.error.restartRequired","restart_required"),
                           ("hades.error.debuggerProtocol","debugger_protocol"),("hades.error.debuggerLost","debugger_lost"),
                           ("host.timeWarp.error.outcomeUnknown","outcome_unknown"),
                           ("host.timeWarp.error.restartRequired","restart_required")] {
            try setFixtureError(key,code:code)
            model.refreshFromHost();wait("unsafe status error reply: \(key), trainer idle") { !model.busy && model.backendStatus.error==key }
            check(!model.connected && !model.heroReady && model.target==nil && !model.canMutate,
                "unsafe runtime error retained mutation authority: \(key)")
            let afterFailure=commands().count
            model.setFeature(.invincibility,value:true)
            model.setValue("health",value:100,target:HadesHeroTarget(heroId:"run:hero:2"));pump()
            check(commands().count==afterFailure,"unsafe runtime error allowed a subsequent mutation: \(key)")
            try setFixtureError(nil)
            model.toggleConnectionFromHost();wait("explicit reconnect reply after \(key): connected and error cleared") { model.connected && !model.busy && model.backendStatus.error.isEmpty }
            check(model.canMutate && model.target?.heroId=="run:hero:2","explicit reconnect did not restore current-hero authority")
        }
        var malformed=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        malformed.removeValue(forKey:"heroReady")
        try JSONSerialization.data(withJSONObject:malformed).write(to:stateURL,options:.atomic)
        model.refreshFromHost();wait("malformed status reply: trainer idle and disconnected") { !model.busy && !model.connected }
        check(model.localError=="hades.error.protocol" && !model.canMutate,"malformed observation retained mutation authority")
        var complete=false
        model.prepareForTermination { complete=true }
        wait("prepareForTermination: backend shutdown completion") { complete }
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
        ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift', ROOT / 'tests/fixtures/swift/NativeAccessibility.swift',
        generated, folder / 'main.swift']
    subprocess.run([shutil.which('swiftc'), '-parse-as-library', *map(str, sources), '-o', str(folder / 'frontend')], check=True, cwd=ROOT)
    # The expanded native editor fixture already reached late checks after ~28s
    # on the previous head. Preserve the per-expectation 5s fail-fast limits;
    # use a separate bounded 65s budget for the whole fixture process.
    try:
        proc = subprocess.run([str(folder / 'frontend'), str(folder), sys.executable],
                              capture_output=True, text=True, timeout=65)
    except subprocess.TimeoutExpired as error:
        phase = folder / 'native-phase.txt'
        print('Native frontend exceeded 65s; last phase: ' +
              (phase.read_text(encoding='utf-8') if phase.exists() else '<no phase>'),
              file=sys.stderr)
        for filename in ('commands.jsonl', 'replies.jsonl', 'trainer.log'):
            journal = folder / filename
            if journal.exists():
                print(filename + ' tail:', file=sys.stderr)
                for line in journal.read_text(encoding='utf-8', errors='replace').splitlines()[-12:]:
                    print(line, file=sys.stderr)
        for stream in ('stdout', 'stderr'):
            captured = getattr(error, stream)
            if captured:
                print('Partial ' + stream + ':', file=sys.stderr)
                print(captured.decode(errors='replace') if isinstance(captured, bytes) else captured,
                      file=sys.stderr)
        raise SystemExit(1)
    if proc.returncode:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
