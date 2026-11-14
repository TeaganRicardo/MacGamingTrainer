"""Hades I typed payloads, native numeric drafts and captured-hero requests."""
import json
import os
from pathlib import Path
from management_ui_harness import PROFILE_JOURNEY, DIAGNOSTICS_JOURNEY, MANAGEMENT_JOURNEY
from slider_ui_harness import SLIDER_JOURNEY
from visual_hierarchy_harness import VISUAL_HIERARCHY_JOURNEY
from room_picker_alignment_harness import ROOM_PICKER_ALIGNMENT_JOURNEY
from disclosure_ui_harness import DISCLOSURE_JOURNEY
from search_ui_harness import SEARCH_JOURNEY
from native_picker_harness import NATIVE_PICKER
from macos_fixture_policy import FixtureWatchdogExpired, launch_fixture
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
def progress(stage):
    with (folder/'worker-progress.log').open('a') as stream:
        stream.write(stage+'\\n')
workspaces={};next_workspace=0
profiles=[{"name":"Fixture","updatedAt":"Today"}]
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
        if state.pop('editorApplyLostReply',False):
            (folder/'state.json').write_text(json.dumps(state))
            sys.exit(7)
        return {'baselineGeneration':workspace['baseline'],'applied':True,'verified':True,'runtimeReloaded':False,'installedSHA256':'installed-sha','hot':True,
            'source':workspace['source'],'sourceSHA256':workspace['sha'],'target':workspace['target'],'previousSnapshotId':'fixture-prewrite'}

for raw in sys.stdin:
    request=json.loads(raw)
    progress('received '+request.get('command','unknown')+' '+request.get('id',''))
    with (folder/'commands.jsonl').open('a') as stream:stream.write(json.dumps({**request,'fixtureGame':args.game})+'\n')
    state=json.loads((folder/'state.json').read_text())
    progress('state-loaded '+request.get('command','unknown'))
    command=request['command'];params=request.get('params',{})
    if command=='save_profile' and params.get('name')=='Closing while saving':time.sleep(.2)
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
        if command=='save_profile' and params['name']!='__error__':
            profiles=[row for row in profiles if row['name']!=params['name']]+[{'name':params['name'],'updatedAt':'Today'}]
        if command=='delete_profile':profiles=[row for row in profiles if row['name']!=params['name']]
        result={'profiles':profiles}
    elif command=='diagnostics':
        checks=[{'name':'hades.diagnostics.connection','ok':state['connected'],'detail':'42'}]
        if state.get('diagnosticsMode')=='viewer':checks.append({'name':'hades.diagnostics.hero','ok':False,'detail':'Fixture caution'})
        if state.get('diagnosticsMode')=='empty':checks=[]
        result={**state,'diagnostics':{'gameID':'hades','checks':checks}}
    else:
        if command=='set_feature' and state.get('slowFeature'):time.sleep(.3)
        if command=='set_feature':
            feature=params.get('feature')
            if feature=='gameSpeed':
                state['features']['gameSpeed']={'desired':params['value'],'actual':params['value'],'active':True}
            else:
                state['features'][feature]=params['value']
                if feature=='moneyNoDecrease' and params['value']:
                    state['moneyLocked']=False;state['moneyLock']=None
                if feature=='rerollsNoDecrease' and params['value']:
                    state['rerollsLocked']=False;state['rerollsLock']=None
            (folder/'state.json').write_text(json.dumps(state))
        if command=='set_boon_rarity':
            state['boonRarityTarget']=params['target']
            (folder/'state.json').write_text(json.dumps(state))
        if command=='lock_vital':
            assert params.get('vital')=='health'
            state['healthLocked']=bool(params['locked'])
            state['healthLock']={'current':state['health'],'max':state['maxHealth']} if params['locked'] else None
            (folder/'state.json').write_text(json.dumps(state))
        if command=='lock_resource':
            assert params.get('resource')=='Money'
            state['moneyLocked']=bool(params['locked'])
            state['moneyLock']=state['money'] if params['locked'] else None
            (folder/'state.json').write_text(json.dumps(state))
        if command=='lock_rerolls':
            state['rerollsLocked']=bool(params['locked'])
            state['rerollsLock']=state['rerolls'] if params['locked'] else None
            (folder/'state.json').write_text(json.dumps(state))
        if command=='set_value':
            state[params['field']]=params['value']
            if params['field'] in ('health','maxHealth') and state.get('healthLocked'):
                state['health']=min(state['health'],state['maxHealth'])
                state['healthLock']={'current':state['health'],'max':state['maxHealth']}
            if params['field']=='money' and state.get('moneyLocked'):state['moneyLock']=params['value']
            if params['field']=='rerolls' and state.get('rerollsLocked'):state['rerollsLock']=params['value']
            (folder/'state.json').write_text(json.dumps(state))
        if command=='set_resource':
            state['resources'][params['resource']]=params['value']
            (folder/'state.json').write_text(json.dumps(state))
        if command=='set_trait_uses':
            for trait in state['traits']:
                if trait['instanceId']==params['instanceId']:trait['remainingUses']=params['uses']
            (folder/'state.json').write_text(json.dumps(state))
        result=state
    time.sleep(.02)
    reply={'type':'result','id':request['id'],'protocolVersion':HOST_VERSION,
        'moduleProtocolVersion':MODULE_VERSION,'gameID':args.game,'ok':True,'result':result}
    if command=='diagnostics' and state.get('diagnosticsMode')=='error':
        reply.update(ok=False,error={'code':'fixture_diagnostics','presentation':'Diagnostic fixture rejected.'})
        reply.pop('result')
    if command=='save_profile' and params.get('name')=='__error__':
        reply.update(ok=False,error={'code':'fixture_profile','presentation':'Profile fixture rejected.'})
        reply.pop('result')
    if command=='status' and state.get('fixtureError'):
        reply.update(ok=False,error={'code':state.get('fixtureErrorCode','fixture'),'presentation':state['fixtureError']},state=state)
        reply.pop('result')
    progress('before-emit '+command)
    emit(reply)
    progress('emitted '+command)
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
    @MainActor static func main() {
        let app=NSApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()
        // Run the unchanged synchronous journey from AppKit's event loop.
        // A main-queue block would prevent its nested native pumps from
        // receiving the module/backend callbacks queued on that same queue.
        Timer.scheduledTimer(withTimeInterval:0.01,repeats:false) { _ in
            MainActor.assumeIsolated {
                do { try exerciseJourney() }
                catch { fatalError("Hades I native fixture: " + String(describing:error)) }
                app.stop(nil)
                let wake=NSEvent.otherEvent(with:.applicationDefined,location:.zero,modifierFlags:[],
                    timestamp:ProcessInfo.processInfo.systemUptime,windowNumber:0,context:nil,
                    subtype:0,data1:0,data2:0)!
                app.postEvent(wake,atStart:false)
            }
        }
        app.run()
    }

    @MainActor static func exerciseJourney() throws {
        _ = NSApplication.shared
        check(NSApp.isRunning,"Hades I native journey did not enter the AppKit application event loop")
        enableNativeAccessibility()
        guard CommandLine.arguments.count == 4 else { fatalError("expected fixture directory, python and journey") }
        let journey = CommandLine.arguments[3]
        guard ["frontend", "recovery", "interlock", "management", "slider", "hierarchy", "disclosure", "search"].contains(journey) else { fatalError("unknown frontend journey: " + journey) }
        if journey == "hierarchy" {
            exerciseVisualHierarchy(descriptor: HadesGameModule.descriptor, presentation: HadesGameModule.presentation)
            exerciseRoomPickerAlignment()
            print("hades_visual_hierarchy_ok")
            return
        }
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
                "canMutate":model.canMutate,"currentIssues":model.currentIssues.map(\.id)]
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
                + "\nworker progress:\n"+((try? String(contentsOf:folder.appendingPathComponent("worker-progress.log"),encoding:.utf8)) ?? "no progress file")
                + "\nworker received without emitted reply:\n"+json(received.filter { !emittedIDs.contains($0["id"] as? String ?? "") })
                + "\nlast 12 worker requests:\n"+json(Array(received.suffix(12)))+"\nlast 12 emitted replies:\n"+json(Array(emitted.suffix(12)))
                + "\nwindows:\n"+windows+"\ntrainer log tail:\n"+log.split(separator:"\n").suffix(12).joined(separator:"\n")
        }
        // Each independently owned journey has its own process budget and
        // journal, so a slow sheet cannot consume the editor/lifecycle budget.
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
        func stopBackend() {
            var complete = false
            model.prepareForTermination { complete = true }
            wait("prepareForTermination: backend shutdown completion") { complete }
        }
        recordPhase("start: " + journey)
        wait("startup status/catalog replies: connected, catalog populated, trainer idle") { model.connected && !model.catalog.isEmpty && !model.busy }
        check(model.heroReady && model.health==50,"catalog reply erased runtime observation")
        if journey == "interlock" {
            // Start with a live, explicitly observed replacement hero. The
            // prior UI scenario originally reached this same live identity
            // after multiple unrelated AX/control exercises, and the shared
            // 45s watchdog expired before reconnect could be observed.
            try updateState(hero:"run:hero:2",health:50)
            model.refreshFromHost()
            wait("interlock setup: current hero observed") {
                !model.busy && model.canMutate && model.target?.heroId=="run:hero:2"
            }
        for (key,code) in [("hades.error.outcomeUnknown","outcome_unknown"),("hades.error.restartRequired","restart_required"),
                           ("hades.error.debuggerProtocol","debugger_protocol"),("hades.error.debuggerLost","debugger_lost"),
                           ("host.timeWarp.error.outcomeUnknown","outcome_unknown"),
                           ("host.timeWarp.error.restartRequired","restart_required")] {
            try setFixtureError(key,code:code)
            model.refreshFromHost();wait("unsafe status error reply: \(key), trainer idle") { !model.busy && model.backendStatus.error==key }
            check(!model.connected && !model.heroReady && model.target==nil && !model.canMutate,
                "unsafe runtime error retained mutation authority: \(key)")
            let afterFailure=commands().count
            if code == "outcome_unknown" {
                try setFixtureError(nil)
                try setConnection(false, heroReady: false)
                model.setFeature(.invincibility, value: true)
                wait("detached desired intent after unknown outcome") {
                    !model.busy && commands().count == afterFailure + 1 && model.isEnabled(.invincibility)
                }
                check(session.currentStatus.requiresTargetRestart,
                      "detached desired edit released unresolved runtime trust")
                let afterOfflineEdit = commands().count
                model.setValue("health",value:100,target:HadesHeroTarget(heroId:"run:hero:2"));pump()
                check(commands().count == afterOfflineEdit, "offline intent enabled a live mutation")
                session.targetLifetimeChanged()
                try setConnection(true, heroReady: true)
            } else {
                model.setFeature(.invincibility,value:true)
                model.setValue("health",value:100,target:HadesHeroTarget(heroId:"run:hero:2"));pump()
                check(commands().count==afterFailure,"unsafe runtime error allowed a subsequent mutation: \(key)")
            }
            try setFixtureError(nil)
            model.toggleConnectionFromHost();wait("explicit reconnect reply after \(key): connected and error cleared") { model.connected && !model.busy && model.backendStatus.error.isEmpty }
            check(model.canMutate && model.target?.heroId=="run:hero:2","explicit reconnect did not restore current-hero authority")
        }
        var malformed=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        malformed.removeValue(forKey:"heroReady")
        try JSONSerialization.data(withJSONObject:malformed).write(to:stateURL,options:.atomic)
        model.refreshFromHost();wait("malformed status reply: trainer idle and disconnected") { !model.busy && !model.connected }
        check(!model.canMutate && model.currentIssues.contains { $0.id=="observation" && $0.text.key=="hades.error.protocol" }
              && model.feedback?.text.key=="hades.error.protocol",
              "malformed observation retained mutation authority or lacked its current issue")
        malformed["heroReady"]=true
        try JSONSerialization.data(withJSONObject:malformed).write(to:stateURL,options:.atomic)
        model.refreshFromHost()
        wait("well-formed status resolves the protocol issue") {
            !model.busy && model.connected && !model.currentIssues.contains { $0.id=="observation" }
        }
            stopBackend()
            print("hades_runtime_interlock_journey_ok")
            return
        }
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
        if journey == "slider" {
            recordPhase("slider: real Hades workbench and backend")
            try exerciseModuleSlider(HadesTrainerView(model: model), localization: localization,
                sliderLabel: HadesPresentation.text("hades.gameSpeed", language: localization.language),
                fieldLabel: HadesPresentation.text("hades.gameSpeed", language: localization.language),
                gameID: "hades", mutation: "set_feature", currentValue: { model.number(.gameSpeed) },
                busy: { model.busy }, commands: commands, observe: { speed in
                    var state = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
                    var features = state["features"] as! [String: Any]
                    features["gameSpeed"] = ["desired": speed, "actual": speed, "active": true] as [String: Any]
                    state["features"] = features
                    try JSONSerialization.data(withJSONObject: state).write(to: stateURL, options: .atomic)
                    model.refreshFromHost()
                })
            stopBackend()
            return
        }
        if journey == "disclosure" {
            recordPhase("disclosure: real Hades dashboard and capability rows")
            try exerciseModuleDisclosure(HadesTrainerView(model: model), localization: localization, gameID: "hades",
                expanded: Binding(get: { model.numericControlsExpanded }, set: { model.numericControlsExpanded = $0 }),
                primaryLabel: { HadesPresentation.text("hades.money", language: $0) },
                expandedLabel: { HadesPresentation.text("hades.damageMultiplier", language: $0) },
                outsideLabel: { HadesPresentation.text("hades.gameSpeed", language: $0) },
                conditionalRole: "AXPopUpButton",
                conditionalLabel: { HadesPresentation.text("hades.chamberObject", language: $0) },
                busy: { model.busy }, commands: commands, observeAvailability: { count in
                    var state = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
                    var world = state["world"] as! [String: Any]
                    world["objects"] = Array(["trove", "well", "fishing"].prefix(count))
                    state["world"] = world
                    try JSONSerialization.data(withJSONObject: state).write(to: stateURL, options: .atomic)
                    model.refreshFromHost()
                })
            stopBackend()
            return
        }
        if journey == "search" {
            recordPhase("search: native focus and discovery")
            exerciseWorkbenchSearch(HadesHeaderActions(model: model), localization: localization,
                placeholder: { HadesPresentation.text("hades.workbench.search", language: localization.language) },
                emptyLabel: { HadesPresentation.text("hades.workbench.searchEmpty", language: localization.language) },
                query: { model.workbenchSearch }, matches: { query in
                    HadesWorkbenchCatalog.matches(query, resources: model.resourceCatalog, worldTerms: model.worldTerms) { key in
                        TrainerPresentationLanguage.allCases.map {
                            HadesGameModule.resolveText(key: key, language: $0, localization: localization)
                        }
                    }.map { (id: $0.id, destination: $0.section.id) }
                }, commands: commands)
            stopBackend()
            print("hades_workbench_search_native_ok")
            return
        }
        if journey == "management" {
            recordPhase("management: routing and layout")
            exerciseManagementRouting(localization: localization)
            let menuCatalog = HadesManagementCatalog.make(model: model, localization: localization)
            check(menuCatalog.additionalMaintenance.isEmpty && menuCatalog.saveEditor == nil && menuCatalog.saveManagement == nil,
                  "Hades app menu fabricated unavailable image or document commands")
            menuCatalog.profiles.perform()
            wait("profile menu routed to Hades") { !model.busy && model.profilesPresented && commands().last?["command"] as? String == "list_profiles" }
            model.profilesPresented = false
            menuCatalog.diagnostics.perform()
            wait("diagnostics menu routed to Hades") { !model.busy && model.diagnosticsPresented && commands().last?["command"] as? String == "diagnostics" }
            model.diagnosticsPresented = false
            var editorOpens = 0, backupOpens = 0
            let documentCatalog = HadesManagementCatalog.make(model: model, localization: localization,
                openSaveEditor: { editorOpens += 1 }, openSaveManagement: { backupOpens += 1 })
            documentCatalog.saveEditor?.perform(); documentCatalog.saveManagement?.perform()
            check(editorOpens == 1 && backupOpens == 1, "Hades optional document actions lost their original callbacks")
            // Per-action gates: a request in flight closes the commands that
            // start another request, while backend-owned Save tools stay open.
            recordPhase("management: per-action gates while a request runs")
            model.saveProfile("Closing while saving")
            wait("slow profile save in flight") { model.busy }
            check(documentCatalog.saveEditor?.isEnabled == true && documentCatalog.saveManagement?.isEnabled == true
                  && documentCatalog.shortcuts.isEnabled && documentCatalog.log.isEnabled,
                  "a running request closed Hades tools that start no request")
            check(!documentCatalog.refresh.isEnabled && !documentCatalog.profiles.isEnabled
                  && !documentCatalog.diagnostics.isEnabled && !documentCatalog.disableAll.isEnabled
                  && !model.canAcceptRuntimeAction,
                  "a running request admitted another Hades backend command")
            wait("slow profile save reply") { !model.busy && model.profiles.contains { $0.name == "Closing while saving" } }
            model.deleteProfile("Closing while saving")
            wait("gate fixture profile removed") { !model.busy && model.profiles.map(\.name) == ["Fixture"] }
            check(documentCatalog.refresh.isEnabled && documentCatalog.diagnostics.isEnabled && model.canAcceptRuntimeAction,
                  "idle Hades backend commands stayed closed")
            exerciseManagementLayout(content: {
                HadesManagementUtilities(model: model)
                    .environment(\.trainerManagementActions, TrainerManagementActions(openSaveManagement: {}))
            }, catalog: { HadesManagementCatalog.make(model: model, localization: localization,
                    openSaveEditor: {}, openSaveManagement: {}) }, localization: localization)
            exerciseManagementPageDismissal(HadesTrainerView(model: model), localization: localization,
                show: { model.diagnosticsPresented = true }, dismissed: { !model.diagnosticsPresented })
            exerciseModuleShortcutSheet(HadesTrainerView(model: model), localization: localization,
                show: { model.shortcutSettingsPresented = true }, isPresented: { model.shortcutSettingsPresented },
                chord: { model.shortcutText(.invincibility) }, commands: commands)
            recordPhase("management: profile workflow")
            model.profilesPresented = true
            exerciseProfileManager(
                HadesProfileManagerView(model: model),
                labels: .init(title: HadesPresentation.text("hades.manage.profiles", language: .en), explanation: "",
                    name: HadesPresentation.text("hades.profile.name", language: .en), picker: "",
                    save: HadesPresentation.text("hades.profile.save", language: .en),
                    load: HadesPresentation.text("hades.profile.load", language: .en),
                    empty: HadesPresentation.text("hades.profile.empty", language: .en)),
                localization: localization, inventory: { model.profiles.map(\.name) }, busy: { model.busy },
                dismissed: { !model.profilesPresented }, commands: commands
            )
            func setDiagnosticsMode(_ mode: String) throws {
                var state = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as! [String: Any]
                state["diagnosticsMode"] = mode
                try JSONSerialization.data(withJSONObject: state).write(to: stateURL, options: .atomic)
            }
            recordPhase("management: diagnostic workflow")
            try setDiagnosticsMode("viewer")
            model.runDiagnostics()
            wait("shared diagnostic viewer fixture") { !model.busy && model.diagnostics.count == 2 }
            model.diagnosticsPresented = true
            check(HadesPresentation.text("hades.diagnostics.rerun", language: .en) == "Run Again"
                  && HadesPresentation.text("hades.diagnostics.rerun", language: .zhCN) == "重新检测",
                  "Hades diagnostics lost the shared Run Again label")
            try exerciseDiagnostics(HadesDiagnosticsView(model: model), localization: localization,
                refreshTitle: HadesPresentation.text("hades.diagnostics.rerun", language: .en),
                exportTitle: HadesPresentation.text("hades.diagnostics.export", language: .en),
                checkName: HadesPresentation.text("hades.diagnostics.hero", language: .en),
                nonpassingStatus: "host.diagnostics.failed", busy: { model.busy }, count: { model.diagnostics.count },
                dismissed: { !model.diagnosticsPresented }, commands: commands, setMode: setDiagnosticsMode)
            stopBackend()
            model.profilesPresented = false; model.diagnosticsPresented = false
            let afterShutdown = commands().count
            wait("captured Hades commands disabled after backend shutdown") {
                !menuCatalog.refresh.isEnabled && !menuCatalog.profiles.isEnabled && !menuCatalog.diagnostics.isEnabled
            }
            menuCatalog.refresh.perform(); menuCatalog.profiles.perform(); menuCatalog.diagnostics.perform()
            pump()
            check(commands().count == afterShutdown && !model.profilesPresented && !model.diagnosticsPresented,
                  "captured Hades commands crossed their retired backend lifetime")
            recordPhase("passed: management")
            print("hades_management_native_workflows_ok")
            return
        }
        check(HadesWorkbenchSection.visible == [.values,.common,.boons,.resources,.rooms,.management],
            "workbench order lost the implemented native rooms panel")
        check(HadesWorkbenchCatalog.orderedShortcutActions == [.invincibility,.fullHealth,.moneyNoDecrease,
            .rerollsNoDecrease,.fullGodGauge,.infiniteAmmo,.forceRerolls,.decreaseGameSpeed,.increaseGameSpeed,
             .boonRarityEnabled,.generateFishing,.generateChaosGate,.spawnOlympian,.spawnPickup,.spawnSpecial,
             .acquireChaosPair,.acquireExactBoon,.disableAll],
              "shortcut order drifted from the visible workbench")
        check(HadesShortcutAction.invincibility.defaultChord.displayText=="⌃⌥1"
              && HadesShortcutAction.fullHealth.defaultChord.displayText=="⌃⌥2",
              "retiring Heal did not shift derived shortcuts forward")
        // The Generate rows follow the Chaos Gate, so earlier defaults keep their keys.
        check(HadesShortcutAction.generateFishing.defaultChord.displayText=="⌃⌥Q"
              && HadesShortcutAction.generateChaosGate.defaultChord.displayText=="⌃⌥W",
              "adding the Generate row shortcuts moved an existing default")
        check(HadesWorkbenchCatalog.shortcutActions(in:.rooms)==[.generateChaosGate,.spawnOlympian,.spawnPickup,.spawnSpecial],
              "Generate row shortcuts left the rooms section")
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
        let dynamicResources = [
            HadesResourceDefinition(id:"z-elixir",names:["en":"Élixir","zh-CN":"药水"]),
            HadesResourceDefinition(id:"a-elixir",names:["en":"Elixir","zh-CN":"药水"]),
        ]
        let dynamicWorld = ["z-door":["en":"Exit","zh-CN":"出口"],
                            "a-door":["en":"Exit","zh-CN":"出口"]]
        func dynamicSearch(_ query:String) -> [HadesWorkbenchEntry] {
            HadesWorkbenchCatalog.matches(query,resources:dynamicResources,worldTerms:dynamicWorld) { _ in [] }
        }
        check(dynamicSearch("ELIXIR 药水").map(\.id)==["resource.z-elixir","resource.a-elixir"],
              "dynamic bilingual resource aliases lost diacritics, multiple tokens or supplied order")
        check(dynamicSearch("EXIT 出口").map(\.id)==["world.a-door","world.z-door"],
              "dynamic world terms lost bilingual matching or stable destination order")
        check(dynamicSearch("elixir missing").isEmpty,"dynamic resources matched only part of the query")
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
        let targetMutations = commands().filter {
            $0["command"] as? String == "set_boon_rarity"
        }.count
        model.setBoonRarityTarget("Epic")
        wait("boon rarity target reply: Epic desired state observed") {
            !model.busy && model.boonRarityTarget == "Epic"
                && commands().filter {
                    $0["command"] as? String == "set_boon_rarity"
                }.count == targetMutations + 1
        }
        let targetArgs = commands().last {
            $0["command"] as? String == "set_boon_rarity"
        }?["params"] as? [String:Any]
        check(targetArgs?["target"] as? String == "Epic",
              "boon rarity target lost the selectable minimum-rarity semantics")
        let speedBefore = model.number(.gameSpeed)
        model.performShortcut(HadesShortcutAction.increaseGameSpeed.rawValue)
        wait("game speed increase shortcut reply") {
            !model.busy && abs(model.number(.gameSpeed) - min(10.0, speedBefore + 0.1)) < 0.0001
        }
        let retainedSpeed = model.number(.gameSpeed)
        model.hostTargetLifetimeChanged(observation: TrainerTargetObservation(
            isRunning: false, launchGeneration: 1, processIdentifier: nil
        ))
        check(!model.connected && !model.heroReady && model.boonRarityTarget == "Epic"
              && abs(model.number(.gameSpeed) - retainedSpeed) < 0.0001
              && model.features[HadesFeature.gameSpeed.rawValue]?.actualNumber == nil,
              "target loss erased desired feature state or retained stale speed observation")
        model.hostTargetLifetimeChanged(observation: TrainerTargetObservation(
            isRunning: true, launchGeneration: 2, processIdentifier: 42
        ))
        model.refreshFromHost()
        wait("status after target replacement restores runtime observation") {
            model.connected && !model.busy && model.boonRarityTarget == "Epic"
        }

        let beforeHealthLocks = commands().filter { $0["command"] as? String == "lock_vital" }.count
        model.lockHealth(true)
        wait("fixed health lock reply") {
            !model.busy && model.healthLocked
                && commands().filter { $0["command"] as? String == "lock_vital" }.count == beforeHealthLocks + 1
        }
        let healthLockArgs = commands().last { $0["command"] as? String == "lock_vital" }?["params"] as? [String:Any]
        check(healthLockArgs?["vital"] as? String == "health"
              && healthLockArgs?["locked"] as? Bool == true
              && (healthLockArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1",
              "fixed health lock lost its current hero owner")
        model.setValue("health", value: 42, target: model.target)
        wait("fixed health current edit reply") { !model.busy && model.health == 42 && model.healthLocked }
        model.setValue("maxHealth", value: 90, target: model.target)
        wait("fixed health maximum edit reply") { !model.busy && model.maxHealth == 90 && model.healthLocked }
        model.lockHealth(false)
        wait("fixed health unlock reply") { !model.busy && !model.healthLocked }

        let beforeMoneyLocks = commands().filter { $0["command"] as? String == "lock_resource" }.count
        model.lockMoney(true)
        wait("fixed gold lock reply") {
            !model.busy && model.moneyLocked
                && commands().filter { $0["command"] as? String == "lock_resource" }.count == beforeMoneyLocks + 1
        }
        let moneyLockArgs = commands().last { $0["command"] as? String == "lock_resource" }?["params"] as? [String:Any]
        check(moneyLockArgs?["resource"] as? String == "Money"
              && moneyLockArgs?["locked"] as? Bool == true
              && (moneyLockArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1",
              "fixed gold lock lost its current hero owner")
        model.lockMoney(false)
        wait("fixed gold unlock reply") { !model.busy && !model.moneyLocked }

        let beforeRerollLocks = commands().filter { $0["command"] as? String == "lock_rerolls" }.count
        model.lockRerolls(true)
        wait("fixed reroll lock reply") {
            !model.busy && model.rerollsLocked
                && commands().filter { $0["command"] as? String == "lock_rerolls" }.count == beforeRerollLocks + 1
        }
        let rerollLockArgs = commands().last { $0["command"] as? String == "lock_rerolls" }?["params"] as? [String:Any]
        check(rerollLockArgs?["locked"] as? Bool == true
              && (rerollLockArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1",
              "fixed reroll lock lost its current hero owner")
        model.lockRerolls(false)
        wait("fixed reroll unlock reply") { !model.busy && !model.rerollsLocked }

        check(searchFunctions("damage").contains { $0.requiresExpandedMetrics && $0.section == .values },
            "numeric search did not target expanded run metrics")
        check(searchFunctions("fishing").contains { $0.section == .resources }, "native fishing missing from discovery")
        check(searchFunctions("出口").contains { $0.section == .rooms }, "native exit actions missing from bilingual discovery")
        check(searchFunctions("角色奖励").contains { $0.id == "shortcut.spawnSpecial" && $0.section == .rooms }
              && searchFunctions("standard drops").contains { $0.id == "hades.spawn.pickupRewards" && $0.section == .rooms },
              "Generate reward rows missing from bilingual discovery")
        let beforeWorld = commands().count
        model.worldAction("spawn_reward",roomID:"old:room",params:["reward":"ZeusUpgrade"],operation:"hades.spawnReward")
        pump(); check(commands().count == beforeWorld && model.feedback?.text.key == "hades.error.staleRoom"
                      && model.feedback?.tone == .warning
                      && !model.currentIssues.contains { $0.text.key == "hades.error.staleRoom" },
                      "old-room intent crossed the backend or became a retained issue")
        let staleRoomNotice = model.feedback!.id
        model.worldAction("spawn_reward",roomID:"run:room:1",params:["reward":"ZeusUpgrade"],operation:"hades.spawnReward")
        wait("spawn_reward reply for current room: request received, trainer idle") { !model.busy && commands().contains { $0["command"] as? String == "spawn_reward" } }
        check(model.feedback?.id != staleRoomNotice && model.feedback?.text.key == "host.backend.notice.completed",
              "a completed room action left the earlier refusal as its feedback")
        let worldArgs = commands().last { $0["command"] as? String == "spawn_reward" }?["params"] as? [String:Any]
        check(worldArgs?["roomId"] as? String == "run:room:1" && (worldArgs?["target"] as? [String:String])?["heroId"] == "run:hero:1", "world mutation lost room/hero ownership")
        model.performShortcut(HadesShortcutAction.generateFishing.rawValue)
        wait("generate_fishing shortcut reply: request received, trainer idle") { !model.busy && commands().contains { $0["command"] as? String == "generate_fishing" } }
        let viewportHeight=min(CGFloat(780),NSScreen.main!.visibleFrame.height-80)
        let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1150,height:viewportHeight),styleMask:[.titled],backing:.buffered,defer:false)
        window.isReleasedWhenClosed=false
        // Keep the same real module and native editors mounted in a bounded
        // viewport. A full-height workbench window puts lower pointer targets
        // outside the screen even when their accessibility frames are nonempty.
        let host=NSHostingView(rootView:ScrollView {
            HadesTrainerView(model:model).frame(maxWidth:.infinity,alignment:.leading)
        }.environmentObject(localization))
        window.contentView=host;host.frame=NSRect(x:0,y:0,width:1150,height:viewportHeight)
        window.center()
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
        let manualSetValueBaseline = commands().filter { $0["command"] as? String == "set_value" }.count
        check(field.stringValue=="42","native control did not show the post-lock observation")
        coordinator.begin();field.stringValue="70"
        coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:field))
        try updateState(hero:"run:hero:1",health:60)
        model.refreshFromHost();wait("focused health draft: status observed health 60, trainer idle") { !model.busy && model.health==60 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="70","background status replaced focused native draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field))
        wait("native health set_value reply: health 70, trainer idle") { !model.busy && model.health==70 }
        let sent=commands().filter { $0["command"] as? String == "set_value" }
        check(sent.count==manualSetValueBaseline + 1,"native commit did not send exactly one mutation")
        let params=sent.last!["params"] as! [String:Any]
        check((params["target"] as? [String:String])?["heroId"]=="run:hero:1","numeric commit lost its captured hero")
        check(params["field"] as? String == "health" && params["value"] as? Double == 70,"numeric commit changed the wrong value")

        coordinator.begin();field.stringValue="80"
        coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:field))
        try updateState(hero:"run:hero:2",health:30)
        model.refreshFromHost();wait("hero replacement status: health 30, trainer idle") { !model.busy && model.health==30 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="80","hero replacement erased focused draft")
        coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:field));pump()
        check(commands().filter { $0["command"] as? String == "set_value" }.count==manualSetValueBaseline + 1,"stale draft mutated replacement hero")
        check(model.feedback?.text.key=="hades.error.staleHero" && model.feedback?.tone == .warning
              && !model.currentIssues.contains { $0.text.key=="hades.error.staleHero" },
              "stale draft lacked actionable feedback or became a retained issue")
        // Hades II's completion convention: a rejected edit restores the
        // observed value and keeps its field-local recovery cue.
        check(field.stringValue=="30" && (field as! TrainerTextField.Field).validationMessage
              == HadesPresentation.text("hades.error.staleHero",language:.en),
              "stale draft did not restore the replacement hero's observed value with its cue")
        try updateState(hero:"run:hero:2",health:31)
        model.refreshFromHost();wait("unfocused health status: health 31, trainer idle") { !model.busy && model.health==31 };host.layoutSubtreeIfNeeded();pump()
        check(field.stringValue=="31","unfocused native value did not refresh")
        // Drive the actual field editor, then the actual native rarity popup.
        // These are input/selection checks on a synthetic worker, not gameplay.
        func nativeEditor(_ field: NSTextField, _ failure: String) -> NSTextView {
            check(window.makeFirstResponder(field), failure + " refused focus")
            field.selectText(nil)
            pump(0.02)
            guard let editor = field.currentEditor() as? NSTextView else {
                fatalError(failure + " did not establish its AppKit field editor")
            }
            return editor
        }
        func enterNative(_ value: String) -> NSTextView {
            let editor=nativeEditor(field, "Hades I numeric field")
            editor.selectAll(nil); editor.insertText(value,replacementRange:editor.selectedRange())
            return editor
        }
        let nativeField=field as! TrainerTextField.Field
        let beforeInvalid=commands().count
        enterNative("-1").doCommand(by:#selector(NSResponder.insertNewline(_:)))
        pump()
        check(commands().count==beforeInvalid && model.health==31 && field.stringValue=="31",
              "Hades I invalid numeric completion dispatched or did not restore the observed value")
        check(nativeField.presentation == .invalid && nativeField.validationMessage == HadesPresentation.text("hades.input.invalid",language:.en)
              && nativeField.accessibilityHelp() == nativeField.validationMessage,
              "Hades I invalid field lacked local visible/accessibility feedback")
        let invalidMessage=HadesPresentation.text("hades.input.invalid",language:.en)
        check(model.feedback?.text.key=="hades.input.invalid" && model.feedback?.tone == .warning
              && !model.currentIssues.contains { $0.text.key=="hades.input.invalid" }
              && !nativeAccessibilityControls(host).contains { $0.role=="AXStaticText" && $0.text==invalidMessage },
              "a rejected Hades I value was not reported once, as its field state and one transient notice")
        enterNative("99").doCommand(by:#selector(NSResponder.cancelOperation(_:)))
        pump()
        check(commands().count==beforeInvalid && field.stringValue=="31" && nativeField.presentation == .invalid,
              "Escape committed a numeric draft or hid its previous rejection")
        enterNative("32").doCommand(by:#selector(NSResponder.insertNewline(_:)))
        window.makeFirstResponder(nil)
        wait("native Return corrected health exactly once") { !model.busy && model.health==32 }
        check(commands().filter { $0["command"] as? String == "set_value" }.count==manualSetValueBaseline + 2
              && nativeField.validationMessage==nil, "Hades I correction duplicated dispatch or retained its old error")
        let bilingualDraft=enterNative("33")
        localization.language = .zhCN
        window.setContentSize(NSSize(width:760,height:viewportHeight));window.center()
        host.layoutSubtreeIfNeeded();pump()
        check(bilingualDraft.string=="33" && field.currentEditor() === bilingualDraft,
              "bilingual narrow layout reset the focused Hades I draft")
        bilingualDraft.doCommand(by:#selector(NSResponder.cancelOperation(_:)))
        localization.language = .en;host.layoutSubtreeIfNeeded();pump()
        activateNativePickerWindow(window)
        let epic=HadesPresentation.text("hades.rarity.Epic",language:.en)
        let heroic=HadesPresentation.text("hades.rarity.Heroic",language:.en)
        let rarityLabel=HadesPresentation.text("hades.rarity",language:.en)
        func revealPicker(named title: String, value: String) -> NativeAccessibilityControl {
            guard let scroll=field.enclosingScrollView, let document=scroll.documentView else {
                fatalError("Hades I native workbench viewport missing")
            }
            func picker() -> NativeAccessibilityControl? {
                nativeAccessibilityControls(host).first {
                    $0.role=="AXPopUpButton" && nativePickerHasName($0,title) && $0.valueText==value
                }
            }
            nativePickerWait("Hades I picker fully inside its native viewport and screen") {
                host.layoutSubtreeIfNeeded()
                guard let current=picker(), !current.frame.isEmpty else { return false }
                let target=document.convert(window.convertFromScreen(current.frame),from:nil)
                _ = document.scrollToVisible(target)
                host.layoutSubtreeIfNeeded()
                let viewport=window.convertToScreen(scroll.contentView.convert(scroll.contentView.bounds,to:nil))
                return viewport.contains(current.frame)
                    && window.screen?.visibleFrame.contains(current.frame)==true
            }
            let result=picker()!
            print("hades_native_picker_visible title=\(title) frame=\(result.frame) window=\(window.frame)")
            return result
        }
        _ = field.scrollToVisible(field.bounds)
        nativePickerPump()
        let pickerDraft=enterNative("34")
        let popup=revealPicker(named:rarityLabel,value:heroic)
        let pickerWidth=popup.frame.width
        check(fields(in:host).contains { $0 === field } && field.currentEditor() === pickerDraft
              && pickerDraft.string=="34", "revealing the native picker replaced the focused numeric draft")
        // Match the Host's event order: its existing dismissal owner observes
        // the actual mouse-down immediately before AppKit routes that same
        // event to the native popup. A separate pre-call commits before the
        // helper's activation/layout work and is not this input sequence.
        var pickerMouseDowns=0
        do {
            let monitor=NSEvent.addLocalMonitorForEvents(matching:.leftMouseDown) { event in
                MainActor.assumeIsolated {
                    guard event.window === window else { return event }
                    pickerMouseDowns += 1
                    let result=TrainerTextEditingDismissal.handle(event,in:window)
                    check(result === event,"Hades I click-away consumed a native popup click")
                    return result
                }
            }
            check(monitor != nil,"Hades I native click-away monitor was not installed")
            defer { if let monitor { NSEvent.removeMonitor(monitor) } }
            selectNativePicker(popup,in:window,moving:-1,opening:.pointer)
        }
        check(pickerMouseDowns==1,"native picker click-away did not observe exactly one mouse-down")
        wait("native picker click-away health commit") { !model.busy && model.health==34 }
        let chosenRarity=nativeAccessibilityControls(host).first {
            $0.role=="AXPopUpButton" && nativePickerHasName($0,rarityLabel) && $0.valueText==epic
        }
        check(chosenRarity?.frame.width==pickerWidth,
              "native rarity selection did not display immediately within its width role")
        let pickerCommits=commands().filter { $0["command"] as? String == "set_value" }
        let pickerCommit=pickerCommits.last?["params"] as? [String:Any]
        check(pickerCommits.count==manualSetValueBaseline + 3 && pickerCommit?["field"] as? String == "health"
              && pickerCommit?["value"] as? Double == 34
              && (pickerCommit?["target"] as? [String:String])?["heroId"]=="run:hero:2",
              "native picker click-away duplicated or lost the numeric commit")
        let primaryName=model.catalog.first { $0.id=="ArtemisWeaponTrait" }!.name(language:"en")
        let secondaryName=model.catalog.first { $0.id=="ArtemisSecondaryTrait" }!.name(language:"en")
        let traitLabel=HadesPresentation.text("hades.selectTrait",language:.en)
        guard let choices=nativeAccessibilityControls(host).first(where:{
                  $0.role=="AXPopUpButton" && $0.label==traitLabel && $0.valueText==primaryName
              }),
              let oldLevel=fields(in:host).first(where:{
                  $0.accessibilityIdentifier()=="hades.acquisition.level"
              }) else {
            fatalError("Hades I selected-catalog native inputs missing")
        }
        let beforeSelection=commands().count
        _ = oldLevel.scrollToVisible(oldLevel.bounds)
        host.layoutSubtreeIfNeeded()
        nativePickerPump()
        let levelEditor=nativeEditor(oldLevel, "catalog level")
        levelEditor.selectAll(nil);levelEditor.insertText("7",replacementRange:levelEditor.selectedRange())
        // Native menu input can also begin through accessibility. Replacing
        // selection while the shared level field edits must retire the old
        // target-owned NSTextField and reset the new target's level.
        selectNativePicker(choices,in:window,moving:1,opening:.accessibility);pump()
        let newLevel=fields(in:host).first { $0.accessibilityIdentifier()=="hades.acquisition.level" }
        let catalogOwnerPassed=namedNativeControl(host,role:"AXPopUpButton",name:traitLabel)?.valueText==secondaryName
              && oldLevel.currentEditor()==nil && newLevel?.stringValue=="1" && commands().count==beforeSelection
        if !catalogOwnerPassed {
            // Preserve the original short-circuit result before diagnostics.
            // Active text comes from its editor: stringValue can validate edits.
            let mounted=fields(in:host)
            let actualSelection=namedNativeControl(host,role:"AXPopUpButton",name:traitLabel)?.valueText
            let afterSelection=commands()
            func identity(_ object: AnyObject?) -> String {
                object.map { String(describing:ObjectIdentifier($0)) } ?? "nil"
            }
            func snapshot(_ input: NSTextField?) -> [String:Any] {
                guard let input else { return ["present":false] }
                let editor=input.currentEditor()
                return ["present":true,"identity":identity(input),"editor":identity(editor),
                    "originalEditor":editor === levelEditor,"hasEditor":editor != nil,
                    "mounted":mounted.contains { $0 === input },"enabled":input.isEnabled,
                    "text":editor?.string ?? input.stringValue,
                    "textSource":editor == nil ? "unfocused control" : "owned native editor",
                    "ownerEditing":(input.delegate as? TrainerTextField.Coordinator)?.edit != nil,
                    "frame":input.window.map { NSStringFromRect($0.convertToScreen(input.convert(input.bounds,to:nil))) } ?? "unmounted"]
            }
            let oldState=snapshot(oldLevel), newState=snapshot(newLevel)
            let context: [String:Any] = [
                "originalPredicatePassed":catalogOwnerPassed,"stage":"after original short-circuit failure; no intervening pump",
                "popupMatches":actualSelection==secondaryName,"actualPopupValue":actualSelection ?? "nil",
                "expectedPopupValue":secondaryName,"oldHasNoEditor":oldState["hasEditor"] as? Bool == false,
                "newObservedTextIsOne":newState["text"] as? String == "1",
                "commandsUnchanged":afterSelection.count==beforeSelection,
                "oldField":oldState,"newField":newState,"originalEditor":identity(levelEditor),
                "matchingLevelFields":mounted.filter {
                    $0.accessibilityLabel()==HadesPresentation.text("hades.level",language:.en)
                }.map { snapshot($0) },
                "commandsBefore":beforeSelection,"commandsAfter":afterSelection.count,
                "commandsAdded":Array(afterSelection.dropFirst(beforeSelection))]
            let payload=(try? JSONSerialization.data(withJSONObject:context,options:[.sortedKeys]))
                ?? Data(String(describing:context).utf8)
            FileHandle.standardError.write(Data("HADES_CATALOG_OWNER_FAILURE ".utf8)+payload+Data("\n".utf8))
        }
        check(catalogOwnerPassed,
              "a catalog selection retained or submitted the previous target's numeric draft")
        window.setContentSize(NSSize(width:1150,height:viewportHeight));window.center();host.layoutSubtreeIfNeeded();pump()
        let count=commands().count
        let restoredMultiplier=model.completeTextEdit(.feature(.damageMultiplier),text:"nan",changed:true,target:nil) { _ in };pump()
        check(commands().count==count && restoredMultiplier=="2" && model.feedback?.text.key=="hades.input.invalid"
              && !model.currentIssues.contains { $0.text.key=="hades.input.invalid" },
              "invalid multiplier crossed the backend boundary, kept its draft or lacked its transient notice")
        localization.language = .zhCN;host.layoutSubtreeIfNeeded();pump()
        let currentLifeCN=localization.localized("host.input.currentValue",arguments:[
            HadesPresentation.text("hades.health",language:.zhCN)])
        check(fields(in:host).contains { $0.accessibilityLabel()==currentLifeCN },
            "language switch failed to relabel native fields")
        check(commands().count==count,"language switch performed a runtime operation")
        localization.language = .en;host.layoutSubtreeIfNeeded();pump()
        if journey == "frontend" {
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
        guard let profile1 = editor.sources.first(where: { $0.relativePath == "Profile1.sav" }),
              let profile2 = editor.sources.first(where: { $0.relativePath == "Profile2.sav" }) else {
            fatalError("Save Editor source fixtures missing")
        }
        let firstWorkspace = editor.workspaceID
        editor.selectedSourceID = profile2.id
        pump()
        wait("source picker automatically reads Profile2") {
            !editor.busy && !editor.queryLoading && editor.source?.relativePath == "Profile2.sav"
                && editor.workspaceID != firstWorkspace
        }
        editor.selectedSourceID = profile1.id
        pump()
        wait("source picker automatically reads Profile1") {
            !editor.busy && !editor.queryLoading && editor.source?.relativePath == "Profile1.sav"
        }
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
        let gemsField=requireNativeControl("native save resource field",in:editorWindow.contentView!) {
            fields(in:$0).first(where:{$0.accessibilityLabel()=="Gems"})
        }
        guard let gemsCoordinator=gemsField.delegate as? TrainerTextField.Coordinator else {
            fatalError("native save resource input coordinator missing")
        }
        gemsCoordinator.begin();gemsField.stringValue="80"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        editor.query();wait("active save_editor_query reply while native Gems draft focused") { !editor.queryLoading };editorWindow.contentView?.layoutSubtreeIfNeeded();pump()
        check(gemsField.stringValue == "80","query replaced a focused Save Editor draft")
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        check(!tools.canCloseAll,"Host allowed close/quit during a pending editor write")
        wait("native Gems 80 save_editor_stage/query replies: one acknowledged action, editor idle") { !editor.busy && editor.review.count == 1 && !editor.queryLoading }
        check(editor.review.actions.first?.typedValue == .number(80),"completed native input did not enter Changes")
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump(0.3)
        let applyTitle=HadesGameModule.resolveText(key:"hades.apply",localization:localization)
        guard let applyControl=namedNativeControl(editorWindow.contentView!,role:"AXButton",name:applyTitle) else {
            fatalError("revealed Changes has no native Apply action")
        }
        let editorBounds=editorWindow.convertToScreen(editorWindow.contentView!.bounds).insetBy(dx:-1,dy:-1)
        check(applyControl.frame.width > 0 && editorBounds.contains(applyControl.frame),
            "revealing Changes clipped its actionable native review area")
        gemsCoordinator.begin();gemsField.stringValue="90"
        gemsCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:gemsField))
        gemsCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:gemsField))
        wait("native Gems revision save_editor_stage reply: acknowledged value 90") { !editor.busy && editor.review.actions.first?.typedValue == .number(90) }
        check(editor.review.count == 1,"revising a field duplicated the user action")
        check(editorWindow.makeFirstResponder(gemsField),"could not focus Save row before review collapse")
        let retainedEditor=editorWindow.firstResponder
        editor.unstage("entry:resources",baseline:editor.baselineGeneration!);wait("resource save_editor_unstage reply: empty Changes") { !editor.busy && editor.review.count == 0 }
        editorWindow.contentView?.layoutSubtreeIfNeeded();pump(0.3)
        check(editorWindow.firstResponder === retainedEditor && gemsField.currentEditor()?.string == "90",
            "review collapse replaced a focused native Save draft")
        check(gemsField.visibleRect.contains(gemsField.bounds),"review reflow pushed focused Save input outside its viewport")
        check(namedNativeControl(editorWindow.contentView!,role:"AXButton",name:applyTitle) == nil,
            "collapsed Changes retained an actionable Apply control")
        let afterCollapse=commands().count
        editorWindow.makeFirstResponder(nil);pump()
        check(commands().count == afterCollapse,"ending an unchanged draft after review reflow staged another mutation")
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
        // Reuse the very same model after a close while its prior query
        // remains in flight. The late response must never re-own this model,
        // and a row captured before close cannot stage into the new document.
        let reusedModel = model.makeSaveEditorModel()
        reusedModel.open(language: .en)
        wait("reusable Hades editor opened") { reusedModel.workspaceID != nil && !reusedModel.busy && !reusedModel.queryLoading && !reusedModel.rows.isEmpty }
        let originalReusedWorkspace = reusedModel.workspaceID!
        let originalReusedRow = reusedModel.rows.first!
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorHoldQuery"]=true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        let priorQueryCount = commands().filter { $0["command"] as? String == "save_editor_query" }.count
        reusedModel.query()
        wait("delayed Hades query admitted") {
            commands().filter { $0["command"] as? String == "save_editor_query" }.count > priorQueryCount
        }
        reusedModel.close()
        check(reusedModel.workspaceID == nil && !reusedModel.queryLoading,
              "closing a pending query retained the retired document")
        saveState["editorHoldQuery"]=false
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        reusedModel.open(language: .en)
        wait("Hades editor reopened after a stale query") {
            reusedModel.workspaceID != nil && reusedModel.workspaceID != originalReusedWorkspace
                && !reusedModel.busy && !reusedModel.queryLoading && !reusedModel.rows.isEmpty
        }
        let postReopenWorkspace = reusedModel.workspaceID!
        let priorStageCount = commands().filter { $0["command"] as? String == "save_editor_stage" }.count
        _ = reusedModel.commit(originalReusedRow, text: "123", workspace: originalReusedWorkspace)
        pump(0.10)
        check(reusedModel.workspaceID == postReopenWorkspace
              && reusedModel.rows.allSatisfy { $0.baselineGeneration == reusedModel.baselineGeneration }
              && commands().filter { $0["command"] as? String == "save_editor_stage" }.count == priorStageCount,
              "late Hades response or stale row escaped the retired document baseline")
        let retainedReceipt = shifted.receipt?.installedSHA256
        let retainedSource = reusedModel.sourceSHA256
        let retainedRows = reusedModel.rows
        let oldWorkerGeneration = session.lifecycleID
        session.restart()
        wait("Hades worker replaced while independent documents remain open") {
            session.currentStatus.backendAvailable && !session.currentStatus.busy && session.lifecycleID != oldWorkerGeneration
        }
        check(!shifted.canEditRows && !reusedModel.canEditRows && !shifted.busy && !reusedModel.busy,
              "a replaced worker left a stale Hades document writable or busy")
        check(shifted.receipt?.installedSHA256 == retainedReceipt && retainedReceipt != nil
              && reusedModel.sourceSHA256 == retainedSource && reusedModel.rows == retainedRows,
              "worker replacement discarded a confirmed receipt or the retained source context")
        let beforeExpiredActions = commands().count
        _ = reusedModel.commit(originalReusedRow, text: "321", workspace: postReopenWorkspace)
        reusedModel.apply(baseline: reusedModel.baselineGeneration)
        shifted.close()
        pump(0.05)
        check(commands().count == beforeExpiredActions, "expired Hades stage/Apply/close reached a new worker")
        reusedModel.openSelection()
        wait("explicit Hades reread restores a new document") { reusedModel.canEditRows && !reusedModel.busy }
        let freshRow = reusedModel.rows.first!
        _ = reusedModel.commit(freshRow, text: "87", workspace: reusedModel.workspaceID)
        wait("fresh Hades edit staged before lost-reply Apply") { !reusedModel.busy && reusedModel.review.count == 1 }
        saveState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        saveState["editorApplyFailure"] = false
        saveState["editorApplyLostReply"] = true
        try JSONSerialization.data(withJSONObject:saveState).write(to:stateURL,options:.atomic)
        reusedModel.apply(baseline: reusedModel.baselineGeneration)
        wait("Hades lost Apply receipt exposes an unconfirmed result and releases busy") {
            !reusedModel.busy && reusedModel.failures["apply"]?.key == "host.save.error.applyUnconfirmed"
                && session.currentStatus.backendAvailable && !session.currentStatus.busy
        }
        check(!reusedModel.canEditRows && reusedModel.review.count == 1 && reusedModel.receipt == nil,
              "lost Hades Apply receipt was silently treated as success or replayable")
        reusedModel.close()
        print("hades_save_editor_native_control_journeys_ok")
        stopBackend()
        window.close()
        return
        }

        // Gathering and Chaos Gate place their shortcut before Generate, and the
        // fishing action explains its availability from the room observation.
        recordPhase("recovery: generate shortcut placement and fishing availability")
        let fishingTitle=HadesPresentation.text("hades.generateFishing",language:.en)
        func fishingButton() -> NativeAccessibilityControl? { accessibilityButton(named:fishingTitle,in:host) }
        func checkBadgePrecedes(_ chord: String, action name: String) {
            let badge=requireNativeControl("shortcut badge "+chord,in:host) { view in
                nativeAccessibilityControls(view).first { $0.role=="AXStaticText" && $0.text==chord }
            }
            let action=nativeAccessibilityControls(host).filter { $0.role=="AXButton" && $0.label==name }
                .min { abs($0.frame.midY-badge.frame.midY) < abs($1.frame.midY-badge.frame.midY) }
            check(action != nil && abs(action!.frame.midY-badge.frame.midY) < 12 && badge.frame.maxX <= action!.frame.minX,
                  "shortcut badge did not precede its row action: "+chord)
        }
        checkBadgePrecedes(model.shortcutText(.generateFishing),action:fishingTitle)
        checkBadgePrecedes(model.shortcutText(.generateChaosGate),action:HadesPresentation.text("hades.generate",language:.en))
        check(fishingButton()?.enabled==true && fishingButton()?.help==HadesPresentation.text("hades.fishingHelp",language:.en),
              "available fishing Generate lost its action help")
        func setFishing(_ available: Bool) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            var room=state["world"] as! [String:Any]
            room["canFish"]=available;state["world"]=room
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
            model.refreshFromHost()
        }
        try setFishing(false)
        wait("unavailable fishing explains its room reason") {
            host.layoutSubtreeIfNeeded()
            return !model.busy && model.world?.canFish==false && fishingButton()?.enabled==false
                && fishingButton()?.help==HadesPresentation.text("hades.fishing.unavailable.room",language:.en)
        }
        try setFishing(true)
        wait("restored fishing returns to its action help") {
            host.layoutSubtreeIfNeeded()
            return !model.busy && fishingButton()?.enabled==true
                && fishingButton()?.help==HadesPresentation.text("hades.fishingHelp",language:.en)
        }

        // Generate reward follows Hades II: one Core grouped row per world
        // catalog group with its sections and "中文 · English" labels, the
        // shortcut badge before Generate, and a shortcut acting on the selection
        // the row shows.
        recordPhase("recovery: Generate reward rows")
        let generateTitle=HadesPresentation.text("hades.generate",language:.en)
        func spawnRequests() -> [[String:Any]] { commands().filter { $0["command"] as? String == "spawn_reward" } }
        let rewardRows: [(HadesRewardGroup,String)] = [(.olympian,"hades.spawn.olympianBoons"),
            (.pickup,"hades.spawn.pickupRewards"),(.special,"hades.spawn.characterRewards")]
        func rewardPicker(_ key: String) -> NativeAccessibilityControl? {
            host.layoutSubtreeIfNeeded()
            let title=HadesPresentation.text(key,language:localization.language)
            return nativeAccessibilityControls(host).first { $0.role=="AXPopUpButton" && nativePickerHasName($0,title) }
        }
        /// The catalog's sections in order, each header "# title" then its "中文 · English" items.
        func expectedMenu(_ group: HadesRewardGroup, headers: [String]) -> [String] {
            let offered=model.rewards(in:group)
            let sections=offered.map(\.section).reduce(into:[String]()) { if !$0.contains($1) { $0.append($1) } }
            check(sections.count==headers.count,"Generate row sections drifted from the catalog: \(sections)")
            return zip(sections,headers).flatMap { section, header in
                ["# "+header]+offered.filter { $0.section==section }.map(\.bilingualName)
            }
        }
        func generateButton(near chord: String) -> NativeAccessibilityControl? {
            host.layoutSubtreeIfNeeded()
            guard let badge=nativeAccessibilityControls(host).first(where: { $0.role=="AXStaticText" && $0.text==chord }) else { return nil }
            return nativeAccessibilityControls(host).filter { $0.role=="AXButton" && $0.label==generateTitle }
                .min { abs($0.frame.midY-badge.frame.midY) < abs($1.frame.midY-badge.frame.midY) }
        }
        for (group,key) in rewardRows {
            let shown=model.rewards(in:group).first!
            let picker=requireNativeControl("Generate row picker "+key,in:host) { _ in rewardPicker(key) }
            check(model.selectedRewards[group]==shown.id && picker.valueText==shown.bilingualName && picker.enabled,
                  "Generate row did not show its first catalog reward bilingually: "+key+" value="+(picker.valueText ?? "nil"))
            checkBadgePrecedes(model.shortcutText(group.shortcut),action:generateTitle)
            check(generateButton(near:model.shortcutText(group.shortcut))?.enabled==true,"Generate row action unavailable: "+key)
        }
        check(HadesShortcutAction.spawnOlympian.defaultChord.displayText=="⌃⌥E"
              && HadesShortcutAction.spawnPickup.defaultChord.displayText=="⌃⌥R"
              && HadesShortcutAction.spawnSpecial.defaultChord.displayText=="⌃⌥T",
              "Generate row shortcuts did not take the next free derived defaults")
        // A real menu shows the catalog sections and moves the model-held
        // selection that both the button and the shortcut generate.
        let pickupExpected=expectedMenu(.pickup,headers:["Resources & Standard Drops","Meta Resources"])
        let gems=model.rewards(in:.pickup).first { $0.id=="GemDrop" }!
        let pickupMoves=pickupExpected.filter { !$0.hasPrefix("# ") }.firstIndex(of:gems.bilingualName)!
        let pickupMenu=selectNativePicker(rewardPicker("hades.spawn.pickupRewards")!,in:window,moving:pickupMoves,opening:.accessibility)
        check(pickupMenu==pickupExpected,"Generate row menu lost its catalog sections or bilingual items: \(pickupMenu)")
        wait("native pickup choice selects Gemstones") {
            model.selectedRewards[.pickup]=="GemDrop" && rewardPicker("hades.spawn.pickupRewards")?.valueText==gems.bilingualName
        }
        localization.language = .zhCN;host.layoutSubtreeIfNeeded();pump()
        let poseidon=model.rewards(in:.olympian)[1]
        let olympianMenu=selectNativePicker(rewardPicker("hades.spawn.olympianBoons")!,in:window,moving:1,opening:.accessibility)
        check(olympianMenu==expectedMenu(.olympian,headers:["奥林匹斯诸神"]),
              "Chinese Generate row lost its section title or 中文 · English items: \(olympianMenu)")
        wait("native Olympian choice selects the next god") {
            model.selectedRewards[.olympian]==poseidon.id && rewardPicker("hades.spawn.olympianBoons")?.valueText==poseidon.bilingualName
        }
        check(rewardPicker("hades.spawn.characterRewards")?.valueText=="卡俄斯 · Chaos",
              "the character-reward row lost Chaos's bilingual label")
        localization.language = .en;host.layoutSubtreeIfNeeded();pump()
        // The row button generates its shown selection in the observed room.
        let spawnBaseline=spawnRequests().count
        check(generateButton(near:model.shortcutText(.spawnOlympian))!.press(),"Olympian Generate refused native AX input")
        wait("native Olympian Generate reply") { !model.busy && spawnRequests().count==spawnBaseline+1 }
        let pressedArgs=spawnRequests().last?["params"] as? [String:Any]
        check(pressedArgs?["reward"] as? String==poseidon.id && pressedArgs?["roomId"] as? String=="run:room:1"
              && (pressedArgs?["target"] as? [String:String])?["heroId"]==model.target?.heroId
              && model.feedback?.text.key=="host.backend.notice.completed",
              "native Generate lost its selection, room or hero, or its completion notice")
        // The shortcut acts on the selection its row shows, with the same feedback.
        model.performShortcut(HadesShortcutAction.spawnPickup.rawValue)
        wait("pickup shortcut spawn reply") { !model.busy && spawnRequests().count==spawnBaseline+2 }
        let shortcutArgs=spawnRequests().last?["params"] as? [String:Any]
        check(shortcutArgs?["reward"] as? String=="GemDrop" && shortcutArgs?["roomId"] as? String=="run:room:1"
              && model.feedback?.text.key=="host.backend.notice.completed" && model.feedback?.tone == .success,
              "the pickup shortcut did not generate the row's shown selection with completion feedback")
        // Shortcut assignment follows Hades II: an unmodified key is a valid chord.
        var monitor: ((NSEvent) -> NSEvent?)?
        let capture=TrainerShortcutCaptureController(installMonitor: { handler in monitor=handler; return NSObject() },
                                                     removeMonitor: { _ in monitor=nil })
        capture.begin(actionID:HadesShortcutAction.spawnSpecial.rawValue) { actionID, chord in
            model.setShortcut(HadesShortcutAction(rawValue:actionID)!, chord:chord)
        }
        let plainKey=NSEvent.keyEvent(with:.keyDown,location:.zero,modifierFlags:[],timestamp:ProcessInfo.processInfo.systemUptime,
            windowNumber:window.windowNumber,context:nil,characters:"",charactersIgnoringModifiers:"",isARepeat:false,keyCode:97)!
        check(monitor?(plainKey)==nil,"shortcut capture forwarded an unmodified key")
        wait("unmodified Generate shortcut assignment") { capture.capturingActionID==nil }
        check(capture.issue==nil && model.shortcutText(.spawnSpecial)=="F6",
              "an unmodified shortcut was refused or not applied: \(String(describing:capture.issue))")
        checkBadgePrecedes("F6",action:generateTitle)
        model.resetShortcuts();host.layoutSubtreeIfNeeded();pump()
        check(model.shortcutText(.spawnSpecial)=="⌃⌥T","shortcut reset did not restore the derived default")

        // Core metric cards commit through Hades I's completion owner: a live
        // amount routes to the hero captured when its edit began, a multiplier
        // edits the durable desired value in its native unit.
        recordPhase("recovery: Core metric cards commit through their owners")
        func nativeCommit(_ input: NSTextField, _ value: String) {
            guard let coordinator=input.delegate as? TrainerTextField.Coordinator else {
                fatalError("native field lost its Core coordinator: "+(input.accessibilityLabel() ?? "unlabelled"))
            }
            coordinator.begin();input.stringValue=value
            coordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:input))
            coordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:input))
        }
        func requests(_ command: String) -> [[String:Any]] {
            commands().filter { $0["command"] as? String == command }
        }
        let moneyTitle=HadesPresentation.text("hades.money",language:.en)
        let moneyField=requireNativeControl("Core gold card field",in:host) { view in
            fields(in:view).first { $0.accessibilityLabel()==moneyTitle }
        }
        let liveHero=model.target!.heroId
        let moneyBaseline=requests("set_value").count
        nativeCommit(moneyField,"77")
        wait("Core gold card set_value reply: 77 observed") { !model.busy && model.money==77 }
        let moneyParams=requests("set_value").last?["params"] as? [String:Any]
        check(requests("set_value").count==moneyBaseline+1 && moneyParams?["field"] as? String == "money"
              && moneyParams?["value"] as? Double == 77
              && (moneyParams?["target"] as? [String:String])?["heroId"]==liveHero,
              "Core gold card commit lost its field, value or captured hero")
        host.layoutSubtreeIfNeeded();pump()
        check(moneyField.stringValue=="77","Core gold card did not show its committed observation")
        model.numericControlsExpanded=true;host.layoutSubtreeIfNeeded();pump()
        let dashTitle=HadesPresentation.text("hades.dashBonus",language:.en)
        let dashField=requireNativeControl("Core additional-dashes card field",in:host) { view in
            fields(in:view).first { $0.accessibilityLabel()==dashTitle }
        }
        check(dashField.stringValue=="0" && dashField.isEnabled,"multiplier card did not show its desired neutral value")
        nativeCommit(dashField,"3")
        wait("Core multiplier set_feature reply: three additional dashes") { !model.busy && model.number(.dashBonus)==3 }
        let dashParams=requests("set_feature").last?["params"] as? [String:Any]
        check(dashParams?["feature"] as? String == "dashBonus" && dashParams?["value"] as? Double == 3
              && dashParams?["target"] == nil,
              "Core multiplier commit lost its desired feature or carried a hero")
        let beforeFractionalDash=commands().count
        nativeCommit(dashField,"1.5");pump()
        check(commands().count==beforeFractionalDash && dashField.stringValue=="3"
              && model.feedback?.text.key=="hades.input.invalid",
              "a fractional dash count crossed its native unit or kept its rejected draft")
        model.numericControlsExpanded=false;host.layoutSubtreeIfNeeded();pump()

        // Common toggles use the shared Core phase model with per-phase help.
        recordPhase("recovery: feature toggle phases")
        func featureSwitch(_ feature: HadesFeature) -> NativeAccessibilityControl? {
            let title=HadesPresentation.text(feature.key,language:.en)
            return nativeAccessibilityControls(host).first {
                $0.label==title && ($0.role=="AXCheckBox" || $0.role=="AXSwitch")
            }
        }
        func phase(_ feature: HadesFeature) -> TrainerFeaturePhase { model.featurePresentation(feature).phase }
        func observeFeatures(active: [String:Bool], dormant: [String:Bool], slow: Bool = false) throws {
            var state=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
            state["activeFeatures"]=active;state["dormantFeatures"]=dormant;state["slowFeature"]=slow
            try JSONSerialization.data(withJSONObject:state).write(to:stateURL,options:.atomic)
        }
        func waitPhase(_ feature: HadesFeature, _ expected: TrainerFeaturePhase, help key: String?) {
            wait("\(feature.rawValue) reads as \(expected)") {
                host.layoutSubtreeIfNeeded()
                guard !model.busy, phase(feature)==expected, let control=featureSwitch(feature) else { return false }
                return key.map { control.help==localization.localized($0) } ?? true
            }
        }
        check(phase(.fullHealth) == .off,"a disabled feature did not read as off")
        try observeFeatures(active:[:],dormant:[:],slow:true)
        let lifeSwitch=requireNativeControl("Infinite Life native switch",in:host) { _ in featureSwitch(.fullHealth) }
        check(lifeSwitch.press(),"Infinite Life switch refused native AX input")
        wait("in-flight enable reads as pending") { model.busy && phase(.fullHealth) == .pending && model.isEnabled(.fullHealth) }
        waitPhase(.fullHealth,.mismatch,help:"host.feature.phase.mismatch")
        try observeFeatures(active:["fullHealth":true],dormant:[:]);model.refreshFromHost()
        waitPhase(.fullHealth,.active,help:nil)
        try observeFeatures(active:[:],dormant:["fullHealth":true]);model.refreshFromHost()
        waitPhase(.fullHealth,.waiting,help:"host.feature.phase.waiting")
        try setConnection(false,heroReady:false);model.refreshFromHost()
        waitPhase(.fullHealth,.detached,help:"host.feature.phase.detached")
        try setConnection(true,heroReady:true);try observeFeatures(active:[:],dormant:[:]);model.refreshFromHost()
        waitPhase(.fullHealth,.mismatch,help:"host.feature.phase.mismatch")
        check(featureSwitch(.fullHealth)!.press(),"Infinite Life switch refused native AX input")
        waitPhase(.fullHealth,.off,help:nil)
        check(requests("set_feature").suffix(2).compactMap { ($0["params"] as? [String:Any])?["value"] as? Bool } == [true,false],
              "the native switch did not send one enable and one disable intent")
        var worldState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        worldState["slowFeature"]=true
        worldState["world"]=[
            "roomId":"run:room:1",
            "doors":[[
                "id":"door:1","doorToken":"fixture-exit:1","number":1,"reward":"RoomMoneyDrop",
                "targets":[["kind":"reward","id":"MaxHealthDrop"]]
            ]],
            "canFish":true,"canChaos":true,"objects":[],
            "occurrenceTargets":[["id":"charon","kind":"shop","sourceId":"charon"]]
        ]
        try JSONSerialization.data(withJSONObject:worldState).write(to:stateURL,options:.atomic)
        model.refreshFromHost()
        wait("Hades world actions fixture observed") {
            !model.busy && model.canSelectWorldExit && model.canSelectWorldOccurrence
        }
        check(featureSwitch(.fullHealth)!.press(),"Infinite Life switch refused slow blocking press")
        wait("blocking request leaves canAcceptRuntimeAction false while keeping Hades world pickers interactive") {
            model.busy && !model.canAcceptRuntimeAction
        }
        check(model.canSelectWorldExit && model.canSelectWorldOccurrence,
              "blocking runtime action incorrectly disabled Hades world pickers")
        wait("slow feature reply completed before restoring fixture") { !model.busy }
        worldState["slowFeature"]=false
        worldState["world"]=["roomId":"run:room:1","doors":[],"canFish":true,"canChaos":true,"objects":[]]
        try JSONSerialization.data(withJSONObject:worldState).write(to:stateURL,options:.atomic)
        check(featureSwitch(.fullHealth)!.press(),"Infinite Life restore switch press failed")
        waitPhase(.fullHealth,.off,help:nil)

        // All seven permanent resources use independent Core numeric inputs.
        // No search or popup may gate direct editing, including while detached.
        recordPhase("recovery: directly visible Core permanent resource rows")
        let permanentResourceNames:[(String,String,String)] = [
            ("MetaPoints","Darkness","黑暗"), ("Gems","Gemstones","宝石"),
            ("LockKeys","Chthonic Key","冥府钥匙"), ("GiftPoints","Nectar","蜜露"),
            ("SuperGems","Diamonds","钻石"), ("SuperGiftPoints","Ambrosia","仙酒"),
            ("SuperLockKeys","Titan Blood","泰坦之血")
        ]
        func resourceField(_ id:String) -> NSTextField? {
            guard let resource=permanentResourceNames.first(where:{$0.0==id}) else { return nil }
            let primary=localization.language == .en ? resource.1 : resource.2
            let secondary=localization.language == .en ? resource.2 : resource.1
            return fields(in:host).first { $0.accessibilityLabel()=="\(primary) · \(secondary)" }
        }
        func checkAllResourceRows(observed:Bool) {
            host.layoutSubtreeIfNeeded();pump()
            for (id,_,_) in permanentResourceNames {
                let field=resourceField(id)
                check(field != nil,"missing always-visible resource input: \(id)")
                let expected=id=="Gems" && observed ? "12" : ""
                check(field?.stringValue==expected,
                      "unexpected resource observation: \(id), expected=\(expected)")
                check(field?.isEnabled == (id=="Gems" && observed),
                      "resource availability is inconsistent: \(id)")
            }
        }
        checkAllResourceRows(observed:true)
        let resourceBaseline=requests("set_resource").count
        nativeCommit(resourceField("Gems")!,"40")
        wait("Core resource row set_resource reply: 40 Gemstones observed") {
            !model.busy && model.resources["Gems"]==40
        }
        let resourceParams=requests("set_resource").last?["params"] as? [String:Any]
        check(requests("set_resource").count==resourceBaseline+1 && resourceParams?["resource"] as? String == "Gems"
              && resourceParams?["value"] as? Double == 40
              && (resourceParams?["target"] as? [String:String])?["heroId"]==liveHero,
              "Core resource commit lost its resource, amount or captured hero")
        host.layoutSubtreeIfNeeded();pump()
        check(resourceField("Gems")?.stringValue=="40","the Gems row did not refresh its committed count")
        localization.language = .zhCN;host.layoutSubtreeIfNeeded();pump()
        check(resourceField("Gems")?.accessibilityLabel()=="宝石 · Gemstones",
              "the Chinese resource label was not 中文 · English")
        for (id,_,_) in permanentResourceNames {
            check(resourceField(id) != nil,"language change hid permanent resource: \(id)")
        }
        localization.language = .en;host.layoutSubtreeIfNeeded();pump()
        let amountField=resourceField("Gems")!
        let amountCoordinator=amountField.delegate as! TrainerTextField.Coordinator
        amountCoordinator.begin();amountField.stringValue="41"
        amountCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:amountField))
        try updateState(hero:"run:hero:3",health:model.health ?? 1)
        model.refreshFromHost();wait("resource hero replacement status") { !model.busy && model.target?.heroId=="run:hero:3" }
        amountCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:amountField));pump()
        check(requests("set_resource").count==resourceBaseline+1 && amountField.stringValue=="40"
              && model.feedback?.text.key=="hades.error.staleHero",
              "a stale resource draft mutated the replacement hero or kept its draft")
        try updateState(hero:liveHero,health:model.health ?? 1)
        model.refreshFromHost();wait("resource editor hero restored") { !model.busy && model.target?.heroId==liveHero }
        for (id,_,_) in permanentResourceNames {
            check(resourceField(id) != nil,"editing a row hid permanent resource: \(id)")
        }

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
        let usesBefore=commands().filter { $0["command"] as? String == "set_trait_uses" }.count
        usesCoordinator.begin();usesField.stringValue="6"
        usesCoordinator.controlTextDidChange(Notification(name:NSControl.textDidChangeNotification,object:usesField))
        usesCoordinator.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:usesField))
        pump()
        check(commands().filter { $0["command"] as? String == "set_trait_uses" }.count==usesBefore,
              "remaining-use draft committed on blur instead of waiting for Apply")
        let usesFrame=window.convertToScreen(usesField.convert(usesField.bounds,to:nil))
        let applyTitle=HadesPresentation.text("hades.apply",language:localization.language)
        let applyCandidates=nativeAccessibilityControls(host).filter {
            $0.role=="AXButton" && $0.label==applyTitle && $0.enabled
        }
        guard let usesApply=applyCandidates.min(by:{
            abs($0.frame.midY-usesFrame.midY) < abs($1.frame.midY-usesFrame.midY)
        }), abs(usesApply.frame.midY-usesFrame.midY) < 50 else {
            fatalError("remaining-use Apply action missing beside its native field")
        }
        check(usesApply.press(),"remaining-use Apply refused native AX input")
        wait("native remaining-use set_trait_uses reply: six uses observed") { !model.busy && model.traits.first?.remainingUses==6 }
        host.layoutSubtreeIfNeeded();pump()
        check(usesField.stringValue=="6","remaining-use Apply did not refresh observation")
        let usesRequests=commands().filter { $0["command"] as? String == "set_trait_uses" }
        let usesParams=usesRequests.last?["params"] as? [String:Any]
        check(usesRequests.count==1 && usesParams?["instanceId"] as? String == "effect:temporary:1"
            && (usesParams?["target"] as? [String:String])?["heroId"]=="run:hero:2",
            "remaining-use commit lost its selected effect or hero")
        let feedbackVisibility = TrainerGamePageVisibility()
        let feedbackHost = NSHostingView(rootView: ManagementPageFixture(
            content: HadesGameModule.makeFeedback(model: model), visibility: feedbackVisibility)
            .environmentObject(localization))
        let feedbackWindow = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 150),
            styleMask: [.titled], backing: .buffered, defer: false)
        feedbackWindow.isReleasedWhenClosed = false
        feedbackWindow.contentView = feedbackHost
        feedbackWindow.makeKeyAndOrderFront(nil)
        func feedbackDismiss() -> NativeAccessibilityControl? {
            nativeAccessibilityControls(feedbackHost).first { $0.identifier == "host.feedback.dismiss" && $0.role == "AXButton" }
        }
        for connected in [true,false] {
            try setConnection(connected,heroReady:false)
            model.refreshFromHost();wait("no-hero status reply: connected=\(connected), trainer idle") { !model.busy && model.connected==connected && !model.heroReady }
            check(model.hostActionsEnabled && !model.canMutate,"offline shortcut fixture retained a hero")
            // Without an observation each live card reads "—" and refuses edits,
            // while the desired multiplier stays visible and editable.
            model.numericControlsExpanded=true;host.layoutSubtreeIfNeeded();pump()
            for label in [currentLife, localization.localized("host.input.maximumValue",arguments:[
                              HadesPresentation.text("hades.health",language:.en)]),
                          HadesPresentation.text("hades.money",language:.en), HadesPresentation.text("hades.rerolls",language:.en),
                          HadesPresentation.text("hades.godGauge",language:.en)] {
                let metric=fields(in:host).first { $0.accessibilityLabel()==label }
                check(metric?.stringValue=="" && metric?.placeholderString=="—" && metric?.isEnabled==false,
                      "\(label) fabricated a value or stayed editable without an observation (connected=\(connected))")
            }
            let desiredDash=fields(in:host).first { $0.accessibilityLabel()==HadesPresentation.text("hades.dashBonus",language:.en) }
            check(desiredDash?.stringValue=="3" && desiredDash?.isEnabled==true,
                  "the desired multiplier was hidden or gated by the missing hero (connected=\(connected))")
            for (id,_,_) in permanentResourceNames {
                let field=resourceField(id)
                check(field != nil && field?.stringValue=="" && field?.isEnabled==false,
                      "an offline or unobserved permanent resource was hidden/editable: \(id), connected=\(connected)")
            }
            model.numericControlsExpanded=false;host.layoutSubtreeIfNeeded();pump()
            let disabled=commands().filter { $0["command"] as? String == "disable_all" }.count
            model.performShortcut(HadesShortcutAction.disableAll.rawValue)
            wait("no-hero disable_all reply: request received, trainer idle (connected=\(connected))") {
                !model.busy && commands().filter { $0["command"] as? String == "disable_all" }.count==disabled+1
            }
            check(model.feedback?.text.key == (connected ? "host.backend.notice.completed" : "hades.disableAllPending"),
                "Disable All feedback did not distinguish native cleanup from detached desired reset")
            let noticeID = model.feedback!.id
            let feedbackRequests = commands().count
            wait("real Hades feedback adapter exposes acknowledged receipt") { feedbackDismiss()?.enabled == true }
            let retiredDismiss = feedbackDismiss()!
            feedbackVisibility.setVisible(false)
            wait("hidden Hades feedback adapter retires its controls") { feedbackDismiss() == nil }
            _ = retiredDismiss.press(); pump()
            check(model.feedback?.id == noticeID, "hidden Hades feedback callback consumed its retained notice")
            feedbackVisibility.setVisible(true)
            wait("returning Hades feedback keeps its receipt") { feedbackDismiss()?.enabled == true }
            check(model.feedback?.id == noticeID, "page selection generated another Hades feedback event")
            check(feedbackDismiss()!.press(), "real Hades feedback dismissal refused native AX input")
            wait("native Hades feedback dismissal") { model.feedback == nil }
            check(commands().count == feedbackRequests && model.connected == connected,
                  "Hades feedback presentation replayed a command or changed connection truth")
            let afterDisable=commands().count
            let issuesBeforeOneShot=model.currentIssues
            // Without a hero every one-shot is refused as in Hades II: no
            // request, a transient warning and no retained issue. The Generate
            // rows share that gate with their shortcuts.
            for action in [HadesShortcutAction.generateFishing,.generateChaosGate,.spawnOlympian,.spawnPickup,.spawnSpecial] {
                model.dismissFeedback(model.feedback?.id ?? UUID())
                model.performShortcut(action.rawValue);pump()
                check(model.feedback?.text.key=="hades.shortcut.unavailable" && model.feedback?.tone == .warning,
                      "a refused \(action.rawValue) shortcut lacked Hades II's warning notice (connected=\(connected))")
            }
            check(commands().count==afterDisable && model.currentIssues==issuesBeforeOneShot,
                  "a one-shot shortcut escaped live-owner gating")
            host.layoutSubtreeIfNeeded()
            check(nativeAccessibilityControls(host).filter { $0.role=="AXButton"
                    && $0.label==HadesPresentation.text("hades.generate",language:.en) }.allSatisfy { !$0.enabled },
                  "a Generate action stayed available without a hero (connected=\(connected))")
        }
        try setConnection(true,heroReady:true)
        model.refreshFromHost();wait("restored hero status reply: trainer mutation authority") { !model.busy && model.canMutate }
        try setFixtureError("host.timeWarp.error.verifyFailed",code:"time_warp_verify_failed")
        model.refreshFromHost();wait("known Time Warp verification failure: trainer idle") { !model.busy && model.backendStatus.errorCode=="time_warp_verify_failed" }
        check(model.connected && model.canMutate,"a known verification failure discarded a trusted runtime")
        recordPhase("recovery: current issues details")
        check(model.feedback?.tone == .warning && model.feedback?.text.key=="host.timeWarp.error.verifyFailed",
              "a known runtime failure lacked its warning notice")
        check(model.currentIssues.map(\.id)==["backend"] && model.currentIssues[0].text.key=="host.timeWarp.error.verifyFailed",
              "a known runtime failure was not projected as a current issue")
        let failureNotice=model.feedback!.id
        let sidebarHost=NSHostingView(rootView:ManagementPageFixture(
            content:HadesGameModule.makeSidebarActions(model:model).frame(width:220),visibility:feedbackVisibility)
            .environmentObject(localization))
        let sidebarWindow=NSWindow(contentRect:NSRect(x:0,y:200,width:240,height:420),
            styleMask:[.titled],backing:.buffered,defer:false)
        sidebarWindow.isReleasedWhenClosed=false
        sidebarWindow.contentView=sidebarHost
        sidebarWindow.makeKeyAndOrderFront(nil)
        let issuesTitle=localization.localized("host.feedback.currentIssues")
        let closeTitle=localization.localized("host.feedback.closeDetails")
        func noticeDetails() -> NativeAccessibilityControl? {
            nativeAccessibilityControls(feedbackHost).first { $0.identifier == "host.feedback.details" && $0.role == "AXButton" }
        }
        // The details popover is its own native window beside the fixtures.
        func detailsControls() -> [NativeAccessibilityControl] {
            NSApp.windows.filter { $0.isVisible && $0 !== window && $0 !== feedbackWindow && $0 !== sidebarWindow }
                .flatMap { nativeAccessibilityControls($0) }
        }
        func closeDetails() -> NativeAccessibilityControl? {
            detailsControls().first { $0.role=="AXButton" && $0.label==closeTitle }
        }
        wait("warning notice offers details for its retained issue") { noticeDetails()?.enabled == true }
        check(noticeDetails()!.press(),"Hades notice Details refused native AX input")
        wait("notice Details opens the current issues") {
            model.feedbackDetailsPresented && model.feedbackDetailsNoticeID==failureNotice && closeDetails()?.enabled==true
        }
        check(closeDetails()!.press(),"Hades current issues refused native Close")
        wait("native Close retires only the details") { !model.feedbackDetailsPresented && closeDetails()==nil }
        check(model.feedback?.id==failureNotice && !model.currentIssues.isEmpty,
              "closing details erased the originating notice or issue")
        var speedState=try JSONSerialization.jsonObject(with:Data(contentsOf:stateURL)) as! [String:Any]
        var speedFeatures=speedState["features"] as! [String:Any]
        var speedProjection=(speedFeatures["gameSpeed"] as? [String:Any]) ?? ["desired":1.0]
        speedProjection["errorPresentation"]="host.timeWarp.error.setFailed"
        speedProjection["errorArguments"]=["7"]
        speedFeatures["gameSpeed"]=speedProjection;speedState["features"]=speedFeatures
        speedState["fixtureError"]=nil
        try JSONSerialization.data(withJSONObject:speedState).write(to:stateURL,options:.atomic)
        model.refreshFromHost()
        wait("speed failure becomes a titled current issue") {
            !model.busy && model.backendStatus.error.isEmpty && model.currentIssues.map(\.id)==["runtime.gameSpeed"]
        }
        let speedIssue=model.currentIssues[0]
        check(speedIssue.title?.key=="hades.gameSpeed" && speedIssue.text.arguments==["7"],
              "speed failure lost its Hades title or Host arguments")
        pressNativeButton(named:issuesTitle,in:sidebarHost)
        wait("sidebar entry opens titled speed details") {
            model.feedbackDetailsPresented && closeDetails()?.enabled==true
                && detailsControls().contains { $0.text==HadesPresentation.text("hades.gameSpeed",language:.en) }
                && detailsControls().contains { $0.text==localization.string(speedIssue.text) }
        }
        speedProjection.removeValue(forKey:"errorPresentation");speedProjection.removeValue(forKey:"errorArguments")
        speedFeatures["gameSpeed"]=speedProjection;speedState["features"]=speedFeatures
        try JSONSerialization.data(withJSONObject:speedState).write(to:stateURL,options:.atomic)
        model.refreshFromHost()
        wait("resolved issues retire their details and sidebar entry") {
            sidebarHost.layoutSubtreeIfNeeded()
            return !model.busy && model.currentIssues.isEmpty && !model.feedbackDetailsPresented
                && closeDetails()==nil && accessibilityButton(named:issuesTitle,in:sidebarHost)==nil
        }
        sidebarWindow.contentView=nil;sidebarWindow.close()
        feedbackWindow.contentView = nil; feedbackWindow.close()
        // The independent interlock journey below owns each unsafe status
        // reply, explicit reconnect and malformed-observation assertion.
        // This UI/AX journey retains its own controls and issue-detail gates.
        stopBackend()
        window.close()
        print("hades_frontend_native_drafts_and_target_ownership_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix='mgt-hades-frontend-') as directory:
    folder = Path(directory)
    (folder / 'main.swift').write_text(HARNESS + PROFILE_JOURNEY + DIAGNOSTICS_JOURNEY + MANAGEMENT_JOURNEY + SLIDER_JOURNEY + VISUAL_HIERARCHY_JOURNEY + ROOM_PICKER_ALIGNMENT_JOURNEY + DISCLOSURE_JOURNEY + SEARCH_JOURNEY + NATIVE_PICKER)
    for language in ('en', 'zh-CN'):
        destination = folder / f'{language}.lproj'
        destination.mkdir()
        shutil.copy2(ROOT / 'Resources/Localization' / f'{language}.lproj' / 'Host.strings',
                     destination / 'Host.strings')
    worker_source = WORKER.replace('HOST_VERSION', str(HOST_PROTOCOL_VERSION)).replace(
        'MODULE_VERSION', str(json.loads((ROOT / 'Backend/games/hades/module.json').read_text())['protocolVersion']))
    initial_state = {'connected': True, 'pid': 42, 'heroReady': True,
        'health': 50, 'maxHealth': 100, 'money': 25, 'rerolls': 3, 'target': {'heroId': 'run:hero:1'},
        'healthLocked': False, 'healthLock': None,
        'moneyLocked': False, 'moneyLock': None, 'rerollsLocked': False, 'rerollsLock': None,
        'features': {'invincibility': True, 'damageMultiplier': 2}, 'resources': {'Gems': 12}, 'traits': [],
        'world': {'roomId': 'run:room:1', 'doors': [], 'canFish': True, 'canChaos': True, 'objects': []}}
    data = json.loads((ROOT / 'Backend/games/hades/catalog.json').read_text())
    selected = next(row for row in data['entries'] if row['id'] == 'AmmoBoltTrait')
    picker_entries = [next(row for row in data['entries'] if row['id'] == name)
                      for name in ('ArtemisWeaponTrait', 'ArtemisSecondaryTrait')]
    catalog = {'catalog': [selected, *picker_entries], 'resourceCatalog': data['resources'],
        'traitNames': data['traitNames'], 'worldRewards': list(json.loads(
            (ROOT / 'Backend/games/hades/world_catalog.json').read_text())['rewards'].values()),
        'worldTerms': json.loads((ROOT / 'Backend/games/hades/world_catalog.json').read_text())['terms']}
    generated = folder / 'ActiveGame.generated.swift'
    subprocess.run([sys.executable, str(ROOT / 'Tools/generate_game_binding.py'), 'hades', str(generated)], check=True, cwd=ROOT)
    sources = sorted((ROOT / 'Sources/Core').rglob('*.swift')) + sorted((ROOT / 'Sources/Hades').rglob('*.swift')) + [
        ROOT / 'tests/fixtures/swift/InMemoryDefaults.swift', ROOT / 'tests/fixtures/swift/NativeAccessibility.swift',
        generated, folder / 'main.swift']
    binary = folder / 'frontend'
    subprocess.run([shutil.which('swiftc'), '-parse-as-library', *map(str, sources), '-o', str(binary)], check=True, cwd=ROOT)

    # Compile once and give Save editing, runtime recovery and management their
    # own workers: a separate recovery process stops unrelated editor work from
    # consuming the editor's watchdog. Each launch takes its outer watchdog from
    # tests/macos_fixture_policy.py; this loop owns only the journey identity and
    # its completion marker.
    JOURNEY_IDS = {
        'frontend': 'hades.save_editor',
        'recovery': 'hades.recovery',
        'interlock': 'hades.interlock',
        'management': 'hades.management',
        'slider': 'hades.slider',
        'hierarchy': 'hades.hierarchy',
        'disclosure': 'hades.disclosure',
        'search': 'hades.search',
    }
    # Empty means the normal full regression. For isolated native layout
    # acceptance, select only the journey that owns the changed interface.
    selected_journeys = {value.strip() for value in os.environ.get(
        'MGT_HADES_FRONTEND_JOURNEYS', '').split(',') if value.strip()}
    for journey, completion_marker in (
        ('frontend', 'hades_save_editor_native_control_journeys_ok'),
        ('recovery', 'hades_frontend_native_drafts_and_target_ownership_ok'),
        ('interlock', 'hades_runtime_interlock_journey_ok'),
        ('management', 'hades_management_native_workflows_ok'),
        ('slider', 'hades_slider_module_journey_ok'),
        ('hierarchy', 'hades_visual_hierarchy_ok'),
        ('disclosure', 'hades_disclosure_module_journey_ok'),
        ('search', 'hades_workbench_search_native_ok'),
    ):
        if selected_journeys and journey not in selected_journeys:
            continue
        case_folder = folder / 'journeys' / journey
        case_folder.mkdir(parents=True)
        (case_folder / 'worker.py').write_text(worker_source)
        case_state = json.loads(json.dumps(initial_state))
        if journey == 'slider':
            case_state['features']['gameSpeed'] = {'desired': 1.0, 'actual': 1.0, 'active': True}
        (case_folder / 'state.json').write_text(json.dumps(case_state))
        (case_folder / 'catalog.json').write_text(json.dumps(catalog))
        home = case_folder / 'home'
        home.mkdir()
        env = {**os.environ, 'HOME': str(home), 'CFFIXED_USER_HOME': str(home)}
        print('hades_frontend_launch:' + journey, flush=True)
        try:
            proc = launch_fixture([str(binary), str(case_folder), sys.executable, journey],
                                  journey=JOURNEY_IDS[journey],
                                  phase_file=case_folder / 'native-phase.txt',
                                  diagnostics=(case_folder / 'commands.jsonl',
                                               case_folder / 'replies.jsonl',
                                               case_folder / 'trainer.log'),
                                  capture_output=True, text=True, env=env)
        except FixtureWatchdogExpired:
            # The watchdog already reported the last semantic phase, the owned
            # journals and bounded output; a stall is not a failed assertion.
            raise SystemExit(1)
        if proc.returncode:
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit(proc.returncode)
        if completion_marker not in proc.stdout.splitlines():
            print(proc.stdout)
            print(proc.stderr)
            raise SystemExit(f'{journey} fixture exited without its completion marker')
        if journey == 'disclosure':
            # The settle report is produced by the real AppKit run, so this
            # checks the behaviour rather than the harness source text.
            summary = [line for line in proc.stdout.splitlines()
                       if line.startswith('disclosure_retirement_boundary_summary')]
            boundaries = [line for line in proc.stdout.splitlines()
                          if line.startswith('disclosure_wait name=retirement:')]
            if not summary or 'boundaries=6' not in summary[0]:
                print(proc.stdout)
                raise SystemExit('disclosure journey did not report all six boundaries')
            if len(boundaries) != 6 or not all('satisfied=true' in line for line in boundaries):
                print(proc.stdout)
                raise SystemExit('a disclosure boundary did not settle: ' + repr(boundaries))
            print(summary[0])
        print(proc.stdout.strip())
