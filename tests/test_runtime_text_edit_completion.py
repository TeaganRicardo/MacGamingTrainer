import json
"""Real Hades SwiftUI text editing uses a temporary backend, never the game/save tree."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from native_picker_harness import NATIVE_PICKER

if sys.platform != "darwin":
    raise SystemExit("macOS-only runtime text-edit behavior")
ROOT = Path(__file__).resolve().parents[1]
PYTHON = shutil.which("python3")
SWIFTC = shutil.which("swiftc")
WORKER = r"""
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game'); args=p.parse_args()
log=pathlib.Path(__file__).with_suffix('.commands.jsonl')
with pathlib.Path(__file__).with_suffix('.startups').open('a') as startup:
 startup.write('started\n')
state={'connected':True, 'status':'ready', 'scene':'run',
       'capabilities':{'setResource':True,'setHealth':True,'setMana':True,'setArmor':True,
                       'setRerolls':True,'setSpellCharge':True,'setStats':True,'setElements':True},
       'featureSupport':{'gameSpeed':True},
       'money':123,'health':99,'maxHealth':120,'mana':44,'maxMana':60,'armor':7,'spellCharge':12,'rerolls':3,
       'damageMultiplier':2,'moneyMultiplier':3,'resourceMultiplier':4,'gameSpeed':1,
       'gatheringProbabilities':{'mining':25},'chaosGateProbability':50,
       'gatheringTargets':{'mining':{'available':True,'scopeToken':'fixture-mining'}},
       'resources':[{'id':'MetaCurrency','name':'Ashes','englishName':'Ashes','count':17,'locked':False}],
       'elements':[{'id':'Fire','name':'Fire','count':18,'locked':False}],
       'stats':{'dodge':{'value':19,'locked':True},'crit':{'value':20,'locked':False},'grasp':{'value':21,'locked':True}}}
for raw in sys.stdin:
 req=json.loads(raw)
 with log.open('a') as out: out.write(json.dumps(req)+'\n')
 command=req['command']; params=req['params']
 if command=='status': time.sleep(.20)
 if command=='set_resource':
  if params['amount']==888:
   print(json.dumps({'type':'result','id':req['id'],'protocolVersion':6,'moduleProtocolVersion':__MGT_MODULE_PROTOCOL__,'gameID':args.game,'ok':False,
                     'error':{'code':'fixture_rejected','presentation':'hades2.error.exactNotEligible'}}),flush=True)
   continue
  if params['resource']=='Money': state['money']=params['amount']
  else: state['resources'][0]['count']=params['amount']
 if command=='set_vital': state[{'health':{'current':'health','max':'maxHealth'},'mana':{'current':'mana','max':'maxMana'},'armor':{'current':'armor'}}[params['vital']][params['field']]]=params['value']
 if command=='set_counter': state[params['counter']]=params['value']
 if command=='set_rerolls': state['rerolls']=params['amount']
 if command=='set_element': state['elements'][0]['count']=params['amount']
 if command=='set_stat':
  previous=state['stats'].get(params['stat'], {})
  state['stats'][params['stat']]={'value':params.get('value',previous.get('value')),'locked':params['locked']}
 if command=='set_desired': state[params['feature']]=params['value']
 if command=='set_boon_rarity_desired': state['boonRarity']=params
 if command=='set_gathering_desired':
  time.sleep(.20)
  state['gatheringProbabilities'][params['family']]=params['probability']
 if command=='generate_gathering':
  assert params=={'family':'mining','scopeToken':'fixture-mining'}
  state['gatheringTargets']['mining']={'available':False,'reason':'hades2.gathering.unavailable.existing'}
 if command=='set_chaos_gate_desired': state['chaosGateProbability']=params['probability']
 if command=='load_profile': state['money']=200
 if command=='disconnect': state['connected']=False
 result={'sources':[],'targets':[],'defaultSource':None} if command=='save_editor_inventory' else state
 print(json.dumps({'type':'result','id':req['id'],'protocolVersion':6,'moduleProtocolVersion':__MGT_MODULE_PROTOCOL__,'gameID':args.game,'ok':True,'result':result}),flush=True)
"""
HARNESS = r"""
import AppKit
import SwiftUI
import Foundation
enum RuntimeTextTrace {
 static var updateDepth=0
 static var currentPhase=""
 static var active: Bool { currentPhase == "editing:money:quick-blur" }
 static func write(_ message: String) {
  guard active else { return }
  FileHandle.standardError.write(Data("text_edit_trace:\(ProcessInfo.processInfo.systemUptime):\(currentPhase):\(message)\n".utf8))
 }
 static func native(_ event: String) {
  guard active else { return }
  write("\(event) updateDepth=\(updateDepth)")
  write(Thread.callStackSymbols.prefix(24).joined(separator:"\n"))
 }
 static func window(_ event: String, field: NSView) {
  guard active else { return }
  let window = field.window
  let identity = window.map { String(describing: ObjectIdentifier($0)) } ?? "nil"
  write("\(event) field=\(ObjectIdentifier(field)) window=\(identity) visible=\(window?.isVisible ?? false) key=\(window?.isKeyWindow ?? false)")
 }
}
func phase(_ name: String) {
 RuntimeTextTrace.currentPhase=name
 FileHandle.standardError.write(Data("runtime_text_edit_completion:\(name)\n".utf8))
}
func check(_ test: @autoclosure () -> Bool, _ message: String) { if !test() { fatalError(message) } }
func pump(_ time: TimeInterval = 0.10) { RunLoop.current.run(until: Date().addingTimeInterval(time)) }
func wait(_ message: String = "fixture did not become ready", _ test: () -> Bool) {
 let deadline=Date().addingTimeInterval(5)
 while !test() && Date()<deadline { pump(0.02) }
 check(test(), message)
}
func fields(_ view: NSView) -> [NSTextField] {
 (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}
func edit(_ field: NSTextField, to draft: String, in window: NSWindow) -> NSTextView {
 if field.currentEditor() == nil { check(window.makeFirstResponder(field), "could not focus text field") }
 guard let editor=field.currentEditor() as? NSTextView else { fatalError("field editor missing: draft=\(draft) field=\(field.stringValue) editable=\(field.isEditable) firstResponder=\(String(describing:window.firstResponder)) mounted=\(field.window === window)") }
 editor.selectAll(nil); editor.insertText(draft, replacementRange: editor.selectedRange())
 return editor
}
func click(at point: NSPoint, in window: NSWindow) -> NSEvent {
 NSEvent.mouseEvent(with:.leftMouseDown, location:point, modifierFlags:[], timestamp:0,
                   windowNumber:window.windowNumber, context:nil, eventNumber:1, clickCount:1, pressure:1)!
}
func checkTeardownNotifications() {
 var text="observed"
 var focused: String?
 var changes=[Bool]()
 var commits=0
 var dismantling=false
 let binding=Binding(get:{text},set:{text=$0})
 let tracked=TrainerTextField.editingTracker(Binding(get:{focused},set:{focused=$0}),equals:"shared-key")
 let owner=TrainerTextField(title:"Lifecycle fixture",text:binding,onEditingChanged:{ active in
  check(!dismantling,"teardown synchronously re-entered its editing owner")
  tracked(active); changes.append(active)
 },onCommit:{ completed in commits += 1; return completed.text })
 let old=owner.makeCoordinator()
 let oldField=NSTextField(string:"abandoned")
 oldField.delegate=old
 old.begin()
 dismantling=true
 TrainerTextField.dismantleNSView(oldField,coordinator:old)
 dismantling=false
 check(old.edit==nil && oldField.delegate==nil && changes==[true] && commits==0,
       "teardown committed or synchronously notified its abandoned edit")
 // Repeated teardown must not queue a second end. A new coordinator can begin
 // the same logical field before the old asynchronous notification is drained.
 TrainerTextField.dismantleNSView(oldField,coordinator:old)
 let replacement=owner.makeCoordinator()
 let replacementField=NSTextField(string:"completed")
 replacementField.delegate=replacement
 replacement.begin()
 check(changes==[true,false,true] && focused=="shared-key",
       "a replacement began before its previous owner's end notification")
 pump()
 check(changes==[true,false,true] && focused=="shared-key" && commits==0,
       "a delayed old end cleared the replacement's same-key focus")
 replacement.controlTextDidEndEditing(Notification(name:NSControl.textDidEndEditingNotification,object:replacementField))
 check(changes==[true,false,true,false] && focused==nil && commits==1 && text=="completed",
       "normal native completion lost its synchronous end notification")
 let removed=owner.makeCoordinator()
 removed.begin()
 dismantling=true
 TrainerTextField.dismantleNSView(NSTextField(),coordinator:removed)
 dismantling=false
 check(focused=="shared-key","teardown ended editing before leaving SwiftUI's update")
 pump()
 check(focused==nil && changes==[true,false,true,false,true,false] && commits==1,
       "a removed editor retained focus or delivered its end more than once")
}
final class GenerateAction: NSObject {
 let model: Hades2TrainerModel
 var presses=0
 init(_ model: Hades2TrainerModel) { self.model=model }
 @objc(generateClicked:) func clicked(_ sender: Any?) { presses += 1; model.generateGathering(.mining) }
}
@MainActor final class PageVisibility: ObservableObject {
 @Published var visible = true
 var destinations: [String] = []
}
struct HeaderFixture: View {
 @ObservedObject var model: Hades2TrainerModel
 @ObservedObject var visibility: PageVisibility
 var body: some View {
  VStack {
   Hades2SidebarActions(model:model)
   Hades2HeaderActions(model:model)
  }.environment(\.trainerGamePageVisible,visibility.visible)
   .environment(\.trainerNavigateToSection) { visibility.destinations.append($0) }
 }
}
@main struct Main {
 @MainActor static func main() throws {
  let journey=CommandLine.arguments[3]
  phase("\(journey):start")
  _ = NSApplication.shared
  enableNativeAccessibility()
  let python=URL(fileURLWithPath:CommandLine.arguments[1])
  let worker=URL(fileURLWithPath:CommandLine.arguments[2]); let temporary=worker.deletingLastPathComponent()
  let log=worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
  let startups=worker.deletingPathExtension().appendingPathExtension("startups")
  func workerStartCount() -> Int {
   ((try? String(contentsOf:startups,encoding:.utf8)) ?? "").split(separator:"\n").count
  }
  let session=TrainerBackendSession(client:BackendClient(process:BackendProcess(executableURL:python,argumentsPrefix:["-u"])))
  let model=Hades2TrainerModel(session:session,logSink:TrainerLogSink(url:temporary.appendingPathComponent("log")),backendScriptURL:worker,runLogDirectoryURL:temporary.appendingPathComponent("no-game-log"))
  check(!session.isStarted && workerStartCount()==0,
        "direct-model initialization eagerly started Backend before Host observed the target")
  let initialObservation=TrainerTargetObservation(isRunning:false,launchGeneration:0)
  model.hostTargetLifetimeChanged(observation:initialObservation)
  wait { model.canSetResource && !model.busy }
  check(session.isStarted && workerStartCount()==1,
        "Host initial target observation did not start exactly one Backend worker")
  model.hostTargetLifetimeChanged(observation:initialObservation)
  pump(0.15)
  check(model.canSetResource && workerStartCount()==1,
        "duplicate initial observation restarted the Backend worker")
  let localization=TrainerLocalizationStore(defaults:InMemoryDefaults())
  if journey == "navigation" {
   let visibility=PageVisibility()
   let host=NSHostingView(rootView:HeaderFixture(model:model,visibility:visibility).environmentObject(localization))
   let window=NSWindow(contentRect:NSRect(x:0,y:0,width:700,height:700),styleMask:[.titled],backing:.buffered,defer:false)
   window.isReleasedWhenClosed=false
   window.contentView=host; window.makeKeyAndOrderFront(nil); host.layoutSubtreeIfNeeded(); pump()
   let beforeNavigation=(try? String(contentsOf:log,encoding:.utf8)) ?? ""
   func hasPopover() -> Bool {
    NSApp.windows.contains { $0.isVisible && $0.accessibilityRole() == .popover }
   }
   let searchLabel=Hades2GameModule.resolveText(key:"hades2.workbench.search",localization:localization)
   // SwiftUI owns the authored AX label; its backing NSTextField exposes the
   // placeholder used by the other search-field native journeys. Inspect both
   // surfaces rather than requiring SwiftUI's AX label on the AppKit editor.
   guard let searchField=fields(host).first(where:{$0.isEditable && $0.placeholderString==searchLabel}) else {
    fatalError("shared workbench search field missing")
   }
   wait("shared workbench search lost its localized accessibility name") {
    namedNativeControl(host,role:"AXTextField",name:searchLabel) != nil
   }
   check(window.makeFirstResponder(searchField),"workbench search could not receive keyboard focus")
   // Let SwiftUI observe the native focus transition before hiding the page.
   pump()
   wait("workbench search did not enter native editing") { searchField.currentEditor() != nil }
   visibility.visible=false
   wait("hiding the game retained search-field focus") { searchField.currentEditor() == nil }
   visibility.visible=true; pump()
   model.workbenchSearch="Invincibility"
   wait("search results did not open") { hasPopover() }
   visibility.visible=false
   wait("a hidden game retained its search popover") { !hasPopover() }
   check(model.workbenchSearch=="Invincibility", "hiding the page erased its search input")
   model.workbenchSearch="Gold"; pump()
   check(!hasPopover(), "a background search change reopened a hidden popover")
   visibility.visible=true; pump()
   check(!hasPopover() && model.workbenchSearch=="Gold", "returning to the page lost input or reopened stale results")
   model.workbenchSearch="Grasp"
   wait("numeric search results did not open") { hasPopover() }
   var graspResult:NativeAccessibilityControl?
   wait("numeric search destination missing from the shared result rows") {
    graspResult=NSApp.windows.filter { $0.isVisible && $0.accessibilityRole() == .popover }
     .flatMap { nativeAccessibilityControls($0) }
     .first { $0.identifier == "trainer.workbench.result.hades2.stat.grasp" && $0.role == "AXButton" }
    return graspResult != nil
   }
   check(graspResult!.press(),"shared search destination could not be selected")
   wait("search selection did not dismiss its popover") { !hasPopover() }
   check(visibility.destinations==[Hades2WorkbenchSection.values.id]
         && model.numericControlsExpanded && model.workbenchSearch.isEmpty,
         "shared search lost the module's numeric reveal, destination or query policy")
   model.workbenchSearch="Invincibility"
   wait("clear-action search results did not open") { hasPopover() }
   guard let clear=nativeAccessibilityControls(host).first(where:{$0.identifier=="trainer.search.clear"}) else {
    fatalError("workbench clear action missing")
   }
   check(clear.press(),"workbench clear action could not be pressed")
   wait("clearing search retained a query or popover") { model.workbenchSearch.isEmpty && !hasPopover() }
   check(visibility.destinations==[Hades2WorkbenchSection.values.id],
         "clear submitted a stale search result")
   check(((try? String(contentsOf:log,encoding:.utf8)) ?? "")==beforeNavigation,
         "workbench query, selection, clear or page switching issued a backend request")
   model.error="host.operationFailed"; pump(); model.showFeedbackDetails()
   wait("feedback details did not open") { model.feedbackDetailsPresented && hasPopover() }
   visibility.visible=false
   wait("a hidden game retained its feedback popover") { !model.feedbackDetailsPresented && !hasPopover() }
   check(!model.currentIssues.isEmpty, "hiding feedback erased the underlying issue")
   session.stop(); window.close(); phase("navigation:complete"); return
  }
  if journey == "controls" {
   checkTeardownNotifications()
   let backdrop=Color(nsColor: .magenta)
   let reference=ImageRenderer(content:TrainerRow { Color.clear.frame(height:40) }
    .trainerGroupedRows().frame(width:900).background(backdrop))
   let referenceImage=NSBitmapImageRep(cgImage:reference.cgImage!)
   let referenceCorner=referenceImage.colorAt(x:1,y:1)!.usingColorSpace(.deviceRGB)!
   for language in [TrainerPresentationLanguage.en, .zhCN] {
    localization.language=language
    for (content, expectedHeight) in [
     (AnyView(Hades2ChaosGatePanel(model:model)), CGFloat(64)),
     (AnyView(Hades2GatheringPanel(model:model)), CGFloat(324)),
     (AnyView(Hades2BoonRarityPanel(model:model)), CGFloat(129))
    ] {
     let root=content.environmentObject(localization)
      .frame(width:900).fixedSize(horizontal:false,vertical:true).background(Color(nsColor: .magenta))
     let rowHost=NSHostingView(rootView:root)
     let size=rowHost.fittingSize
     let rowWindow=NSWindow(contentRect:NSRect(origin:.zero,size:size),styleMask:[.titled],backing:.buffered,defer:false)
     rowWindow.isReleasedWhenClosed=false
     rowWindow.contentView=rowHost; rowHost.layoutSubtreeIfNeeded(); pump()
     check(abs(size.height - expectedHeight) < 1,
           "controls differ from the Host's 64-point row height: \(size), expected \(expectedHeight)")
     // ImageRenderer includes SwiftUI layer clipping, which AppKit's view-only
     // cacheDisplay omits for these layer-backed hosts.
     let renderer=ImageRenderer(content:root)
     let image=NSBitmapImageRep(cgImage:renderer.cgImage!)
     let corner=image.colorAt(x:1,y:1)!.usingColorSpace(.deviceRGB)!
     check(abs(corner.redComponent-referenceCorner.redComponent)
         + abs(corner.greenComponent-referenceCorner.greenComponent)
         + abs(corner.blueComponent-referenceCorner.blueComponent) < 0.03,
           "control panel corners differ from the Host: \(corner), expected \(referenceCorner)")
     if expectedHeight == 129 {
      check(model.boonRarityTarget == "Heroic", "minimum rarity did not default to Heroic")
      check(fields(rowHost).allSatisfy { !$0.isEditable }, "retired probability editor is still mounted")
      let title=Hades2GameModule.resolveText(key:"hades2.rarity.title",localization:localization)
      guard let toggle=namedNativeControl(rowHost,role:"AXCheckBox",name:title) else { fatalError("rarity switch missing") }
      check(toggle.press(), "rarity switch could not be activated")
      wait { model.boonRarityEnabled && !model.busy }
      let forceName=Hades2GameModule.resolveText(key:"hades2.rarity.legendary",localization:localization)
      guard let force=namedNativeControl(rowHost,role:"AXCheckBox",name:forceName) else { fatalError("force legendary missing") }
      check(force.press(), "force legendary could not be activated")
      wait { model.boonForceLegendary && !model.busy }
      check(model.boonRarityTarget == "Heroic", "force setting changed the minimum rarity")
      check(abs(toggle.frame.midY-force.frame.midY) > 32, "force controls did not remain below the minimum row")
      let duoName=Hades2GameModule.resolveText(key:"hades2.rarity.duo",localization:localization)
      guard let duo=namedNativeControl(rowHost,role:"AXCheckBox",name:duoName) else { fatalError("force duo missing") }
      check(duo.press(), "force duo could not be activated")
      wait { model.boonForceDuo && !model.busy }
      check(duo.press(), "force duo could not be disabled")
      wait { !model.boonForceDuo && !model.busy }
      check(force.press(), "force legendary could not be disabled")
      wait { !model.boonForceLegendary && !model.busy }
      check(toggle.press(), "rarity switch could not be disabled")
      wait { !model.boonRarityEnabled && !model.busy }
     }
     rowWindow.close()
    }
   }
   session.stop(); phase("controls:complete"); return
  }
  let toolWindows=TrainerToolWindowStore()
  var backupPresentations=0
  let host=NSHostingView(rootView:TrainerShell { EmptyView() } content: {
   Hades2TrainerView(model:model)
  }.environmentObject(localization)
    .environment(\.trainerToolWindows,toolWindows.actions(localization:localization,theme:.standard))
    .environment(\.trainerManagementActions,TrainerManagementActions(openSaveManagement:{backupPresentations += 1})))
  let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1400,height:2600),styleMask:[.titled],backing:.buffered,defer:false)
  window.contentView=host; host.layoutSubtreeIfNeeded(); pump(0.5)
  phase("\(journey):host-ready")
  check(!fields(host).contains(where:{$0.isEditable && $0.accessibilityLabel()=="—"}),
        "a numeric input still exposes its visual placeholder as its native accessibility name")
  let traitTargetName=Hades2GameModule.resolveText(key:"hades2.traits.targetLevel",localization:localization)
  check(fields(host).contains(where:{$0.isEditable && !$0.isEnabled && $0.accessibilityLabel()==traitTargetName}),
        "the unavailable trait target-level input lost its semantic native name")
  try? FileManager.default.removeItem(at:log)
  func commands(_ command: String? = nil) -> [[String:Any]] {
   let text=(try? String(contentsOf:log,encoding:.utf8)) ?? ""
   return text.split(separator:"\n").compactMap { try? JSONSerialization.jsonObject(with:Data($0.utf8)) as? [String:Any] }.filter { command == nil || ($0["command"] as? String)==command }
  }
  func mutations() -> [[String:Any]] { commands("set_resource") }
  func waitForCommand(_ command: String, count: Int) {
   wait("\(command) did not complete \(count) requests") { commands(command).count==count && !model.busy }
   pump()
  }
  if journey == "management" {
   phase("management:accessibility")
   for language in [TrainerPresentationLanguage.en, .zhCN] {
    localization.language=language; pump()
    for key in ["hades2.feature.moneyMultiplier", "hades2.feature.resourceMultiplier", "hades2.rarity.title"] {
     let name=Hades2GameModule.resolveText(key:key,localization:localization)
     check(nativeAccessibilityControls(host).contains { element in
      ["AXCheckBox", "AXSwitch"].contains(element.role ?? "") && element.label==name
     }, "a native feature switch lost its semantic name: \(name)")
    }
    let healthName=Hades2GameModule.resolveText(key:"hades2.vital.health",localization:localization)
    let lockName=localization.localized("host.lockValue",arguments:[healthName])
    check(namedNativeControl(host,role:"AXButton",name:lockName) != nil,
          "the native lock action lost its target name: \(lockName)")
   }
   func managementAction(_ key:String) -> NativeAccessibilityControl {
    let name=Hades2GameModule.resolveText(key:key,localization:localization)
    guard let action=namedNativeControl(host,role:"AXButton",name:name) else { fatalError("management action missing: \(name)") }
    return action
   }
   phase("management:navigation")
   // Management navigation uses its own capability. Opening an existing Save
   // document only focuses its window, even while a runtime request is busy.
   model.connected=true; model.pid=nil; pump()
   let saveTitle=Hades2GameModule.resolveText(key:"hades2.saveEditor.title",localization:localization)
   check(managementAction("hades2.saveEditor.title").press(),"Save entry did not open its native tool")
   wait { commands("save_editor_inventory").count==1 }
   guard let saveWindow=NSApp.windows.first(where:{$0.title==saveTitle}) else { fatalError("Save entry did not use the independent tool-window owner") }
   let saveRequests=commands("save_editor_inventory").count
   model.refreshFromHost(); wait { model.busy }
   check(managementAction("hades2.saveEditor.title").enabled,
         "an unrelated runtime request disabled the existing Save tool's focus entry")
   check(managementAction("hades2.saveEditor.title").press(),"busy Save focus action was rejected")
   check(managementAction("host.shortcutSettings").enabled && managementAction("host.viewLog").enabled,
         "runtime busy state disabled local settings or logs")
   check(managementAction("host.saveManagement").enabled && managementAction("host.saveManagement").press()
         && backupPresentations==1,"the Host-owned backup entry inherited a runtime mutation lock")
   wait { !model.busy }; pump()
   check(NSApp.windows.first(where:{$0.title==saveTitle}) === saveWindow
         && commands("save_editor_inventory").count==saveRequests,
         "reopening Save while runtime-busy recreated or re-read its document")
   saveWindow.performClose(nil); pump()
   model.connected=false; model.pid=nil; pump()
   check(!managementAction("host.disableAll").enabled,
         "Disable All remained available without a runtime connection")
   check(managementAction("hades2.manage.prepareSigning").enabled
         && managementAction("hades2.manage.restoreSigning").enabled,
         "stopped-game signature maintenance required an unrelated connection")
   check(managementAction("host.shortcutSettings").enabled && managementAction("host.viewLog").enabled,
         "disconnection disabled local settings or logs")
   model.pid=909; pump()
   check(!managementAction("hades2.manage.prepareSigning").enabled
         && !managementAction("hades2.manage.restoreSigning").enabled,
         "signature maintenance remained available for a known running game")
   model.exiting=true; pump()
   check(!managementAction("hades2.manage.profiles").enabled
         && !managementAction("hades2.saveEditor.title").enabled
         && !managementAction("host.shortcutSettings").enabled
         && managementAction("host.viewLog").enabled,
         "exit cleanup left management mutations available or hid diagnostic logs")
   model.exiting=false; model.pid=nil; model.connected=true; pump()
   phase("management:layout")
   // All common and optional native actions remain present exactly once and inside their
   // host at narrow and regular widths in both languages. This checks layout
   // bounds; rendered hierarchy and VoiceOver acceptance remain user-run.
   let managementKeys=["host.refreshStatus","hades2.saveEditor.title","host.saveManagement","host.disableAll",
                       "hades2.manage.profiles","host.shortcutSettings","host.viewLog",
                       "host.viewLogHistory","host.clearCompletedLogs","hades2.manage.diagnostics",
                       "hades2.manage.prepareSigning","hades2.manage.restoreSigning"]
   for width:CGFloat in [420,760] {
    for language in [TrainerPresentationLanguage.en,.zhCN] {
     localization.language=language; pump()
     let layoutHost=NSHostingView(rootView:Hades2ManagementUtilities(model:model,openSaveEditor:{})
       .environmentObject(localization)
       .environment(\.trainerManagementActions,TrainerManagementActions(openSaveManagement:{}))
       .frame(width:width))
     let layoutWindow=NSWindow(contentRect:NSRect(x:0,y:0,width:width,height:1000),styleMask:[.titled],backing:.buffered,defer:false)
     layoutWindow.contentView=layoutHost; layoutHost.layoutSubtreeIfNeeded(); pump()
     let bounds=layoutWindow.convertToScreen(layoutHost.convert(layoutHost.bounds,to:nil)).insetBy(dx:-1,dy:-1)
     for key in managementKeys {
      let label=Hades2GameModule.resolveText(key:key,localization:localization)
      let matches=nativeAccessibilityControls(layoutHost).filter{$0.role=="AXButton" && $0.label==label}
      check(matches.count==1,"a management action was missing or duplicated at width \(width): \(label)")
      check(matches[0].frame.width>0 && matches[0].frame.height>0 && bounds.contains(matches[0].frame),
            "a management action overflowed its native host at width \(width): \(label)")
     }
     layoutWindow.close()
    }
   }
   try? FileManager.default.removeItem(at:log)
   session.stop(); pump(); window.close()
   phase("management:complete")
   return
  }
  phase("editing:materials")
  // Actual selected-trait fields must lose their native editor when the menu
  // or an observation replaces that trait, without applying its old draft.
  func inputTrait(_ id: String, level: Int, uses: Double) -> CurrentRunTrait {
   CurrentRunTrait(generationID:"input-generation",runID:"input-run",instanceID:id,
    name:id,displayName:id,englishName:id,family:"temporary",sourceID:"fixture",sourceName:"Fixture",sourceEnglishName:"Fixture",
    level:level,rarity:"Common",availableRarities:["Common","Rare"],sameNameCount:1,remainingUses:uses,
    lifecycleState:"",linkedTrait:"",linkedDisplayName:"",linkedEnglishName:"",canAdvanceLifecycle:false,
    canSetRemainingUses:true,canExpire:true,levelCapability:.increaseOne,levelReason:"",rarityCapability:.setExact,
    rarityReason:"",removalCapability:.singleInstanceForce,removalReason:"",removalScopeAllMatching:false,deferredIssue:nil)
  }
  let firstTrait=inputTrait("Input First",level:2,uses:7)
  let secondTrait=inputTrait("Input Second",level:4,uses:9)
  model.capabilities["traitMutation"]=true
  model.currentRunTraits=[firstTrait,secondTrait];pump()
  let levelName=Hades2GameModule.resolveText(key:"hades2.traits.targetLevel",localization:localization)
  let usesName=Hades2GameModule.resolveText(key:"hades2.traits.remainingUses",localization:localization)
  let traitPickerName=Hades2GameModule.resolveText(key:"hades2.traits.manager",localization:localization)
  guard let oldLevel=fields(host).first(where:{$0.accessibilityLabel()==levelName && $0.isEnabled}),
        let picker=namedNativeControl(host,role:"AXPopUpButton",name:traitPickerName),
        picker.valueText?.contains("Input First")==true else {
   fatalError("native Hades II selected-trait inputs missing")
  }
  let beforeTraitSelection=commands().count
  _ = edit(oldLevel,to:"42",in:window)
  selectNativePicker(picker,in:window,moving:1,opening:.accessibility);pump()
  let selectedLevel=fields(host).first { $0.accessibilityLabel()==levelName && $0.isEnabled }
  check(namedNativeControl(host,role:"AXPopUpButton",name:traitPickerName)?.valueText?.contains("Input Second")==true
        && oldLevel.currentEditor()==nil && selectedLevel?.stringValue=="5" && commands().count==beforeTraitSelection,
        "native trait selection redirected a focused level draft")
  guard let oldUses=fields(host).first(where:{$0.accessibilityLabel()==usesName && $0.isEnabled}) else {
   fatalError("native remaining-use input missing")
  }
  _ = edit(oldUses,to:"77",in:window)
  model.currentRunTraits=[firstTrait];pump()
  let selectedUses=fields(host).first { $0.accessibilityLabel()==usesName && $0.isEnabled }
  check(oldUses.currentEditor()==nil && selectedUses?.stringValue=="7" && commands().count==beforeTraitSelection,
        "an observation-selected replacement inherited or submitted another trait's remaining-use draft")
  model.currentRunTraits=[];model.capabilities["traitMutation"]=false;pump()
  guard var money=fields(host).first(where:{$0.isEditable && $0.stringValue == "123"}) else { fatalError("money text field not found: \(fields(host).map(\.stringValue))") }
  check(window.makeFirstResponder(money), "could not focus money field"); pump()
  // Selected-material observations refresh idle controls without taking over
  // a native draft. Losing that owner abandons its draft before selecting the
  // next material; it must never submit the old amount to the replacement.
  func material(_ id: String, _ count: Double) -> MaterialResource {
   MaterialResource(id:id,name:id,englishName:id,count:count,locked:false,
                    sectionTitle:"",englishSectionTitle:"",sortOrder:0)
  }
  guard let amount=fields(host).first(where:{$0.isEditable && $0.stringValue=="17"})
  else { fatalError("selected material amount field missing") }
  window.makeFirstResponder(nil); pump()
  phase("editing:material:idle-observation")
  model.resources=[material("MetaCurrency",31)]; pump()
  check(amount.stringValue=="31" && mutations().isEmpty,
        "external selected-material observation left the unfocused amount stale: \(amount.stringValue)")
  check(window.makeFirstResponder(amount), "could not focus selected material")
  phase("editing:material:focused-observation")
  model.resources=[material("MetaCurrency",32)]; pump()
  check((amount.currentEditor() as? NSTextView)?.string=="31" && mutations().isEmpty,
        "observation replaced a focused material before typing")
  window.makeFirstResponder(nil); pump()
  check(amount.stringValue=="32" && mutations().isEmpty,
        "unchanged material blur did not restore the latest observation")
  let materialEditor=edit(amount,to:"41",in:window)
  phase("editing:material:draft-observation")
  model.resources=[material("MetaCurrency",33)]; pump()
  check(materialEditor.string=="41" && mutations().isEmpty,
        "external material change overwrote or submitted an in-progress draft")
  phase("editing:material:return")
  materialEditor.doCommand(by:#selector(NSResponder.insertNewline(_:)))
  waitForCommand("set_resource",count:1)
  check((mutations()[0]["params"] as? [String:Any])?["resource"] as? String=="MetaCurrency"
        && model.resources.first?.count==41,
        "material Return did not commit exactly once to the captured owner")
  _ = edit(amount,to:"51",in:window)
  phase("editing:material:replace-owner:before")
  model.resources=[material("PlantFNightshade",73)]
  phase("editing:material:replace-owner:assigned"); pump()
  phase("editing:material:replace-owner:after")
  guard let replacementAmount=fields(host).first(where:{$0.isEditable && $0.stringValue=="73"})
  else { fatalError("material owner replacement did not reset the displayed amount") }
  window.makeFirstResponder(nil); pump()
  check(amount.currentEditor()==nil && mutations().count==1,
        "material owner replacement submitted an abandoned draft")
  let replacementEditor=edit(replacementAmount,to:"81",in:window)
  phase("editing:material:replacement-observation")
  model.resources=[material("PlantFNightshade",74)]; pump()
  check(replacementEditor.string=="81" && replacementAmount.currentEditor() != nil && mutations().count==1,
        "the replacement material lost its focused draft to an old end notification")
  phase("editing:material:remove-owner:before")
  model.resources=[]
  phase("editing:material:remove-owner:assigned"); pump()
  phase("editing:material:remove-owner:after")
  window.makeFirstResponder(nil); pump()
  check(replacementAmount.currentEditor()==nil && mutations().count==1,
        "losing every material submitted an abandoned draft")
  phase("editing:material:restore-owner")
  model.refreshFromHost(); wait { !model.busy }; pump()
  check(fields(host).contains(where:{$0.isEditable && $0.stringValue=="41"}),
        "restored material owner did not restore its observed amount")
  phase("editing:material:complete")
  try? FileManager.default.removeItem(at:log)
  phase("editing:money:untyped-observation")
  check(window.makeFirstResponder(money), "could not restore money focus after material checks")
  guard let untyped=money.currentEditor() as? NSTextView else { fatalError("focused field editor missing") }
  model.money=777; pump()
  check(untyped.string=="123" && mutations().isEmpty, "refresh overwrote a focused editor before the first keystroke")
  window.makeFirstResponder(nil); pump()
  check(money.stringValue=="777" && mutations().isEmpty, "unchanged completion did not restore the latest observation")
  model.money=123; pump()
  check(window.makeFirstResponder(money), "could not refocus after unchanged completion")
  guard let editor=money.currentEditor() as? NSTextView else { fatalError("field editor missing") }
  phase("editing:money:typing")
  for draft in ["4", "40", "400"] {
   editor.selectAll(nil); editor.insertText(draft, replacementRange:editor.selectedRange()); pump(0.45)
   check(mutations().isEmpty, "typing submitted a runtime mutation before completion")
  }
  phase("editing:money:blur")
  check(window.makeFirstResponder(nil), "could not leave editing")
  waitForCommand("set_resource", count:1)
  check(mutations().count==1, "blur did not submit one changed value")
  let params=mutations()[0]["params"] as? [String:Any]
  check(params?["amount"] as? Int == 400, "blur submitted a partial draft")
  check(model.money==400, "completed edit remained deferred")
  phase("editing:money:second-blur")
  _ = edit(money, to:"123", in:window)
  window.makeFirstResponder(nil); waitForCommand("set_resource",count:2)
  check(model.money==123, "latest completed intent lost the return to the initial value")
  phase("editing:money:quick-blur")
  _ = edit(money, to:"401", in:window)
  check(window.makeFirstResponder(nil), "could not finish quick edit")
  waitForCommand("set_resource", count:3)
  check((mutations()[2]["params"] as? [String:Any])?["amount"] as? Int == 401,
        "quick focus/edit/blur lost the draft")

  // A marked composition remains a draft across a real model refresh. Return
  // then completes the final text, and a following blur cannot submit it again.
  phase("editing:composition:focus")
  check(window.makeFirstResponder(money), "could not focus for composition"); pump()
  let composing=money.currentEditor() as! NSTextView
  composing.selectAll(nil)
  phase("editing:composition:marked-text:before")
  composing.setMarkedText("4.", selectedRange:NSRange(location:2,length:0), replacementRange:composing.selectedRange())
  phase("editing:composition:marked-text:after")
  check(composing.hasMarkedText(), "native marked-text fixture did not start")
  phase("editing:composition:observation:before")
  model.money=777
  phase("editing:composition:observation:assigned"); pump(0.45)
  phase("editing:composition:observation:after")
  check(composing.string=="4." && mutations().count==3, "refresh or composition submitted/overwrote the draft")
  phase("editing:composition:insert-text:before")
  composing.insertText("402", replacementRange:NSRange(location:0,length:composing.string.utf16.count))
  phase("editing:composition:insert-text:after")
  phase("editing:composition:return:before")
  composing.doCommand(by: #selector(NSResponder.insertNewline(_:)))
  phase("editing:composition:return:after")
  waitForCommand("set_resource", count:4)
  check(money.currentEditor()==nil && model.money==402, "Return did not finish: editor=\(String(describing: money.currentEditor())) money=\(String(describing: model.money)) draft=\(money.stringValue) responder=\(String(describing: window.firstResponder))")
  phase("editing:composition:following-blur:before")
  window.makeFirstResponder(nil)
  phase("editing:composition:following-blur:resigned"); pump(0.45)
  phase("editing:composition:following-blur:after")
  check(mutations().count==4, "Return followed by blur submitted twice")

  phase("editing:validation")
  for invalid in ["", "-", ".", "abc", "3.5", "9999999", "nan", "inf"] {
   _ = edit(money, to:invalid, in:window); window.makeFirstResponder(nil); pump(0.45)
   check(mutations().count==4 && money.stringValue=="402", "invalid draft was applied or not restored: '\(invalid)' draft=\(money.stringValue) mutations=\(mutations().count) feedback=\(String(describing:model.feedbackNotice))")
   check(model.feedbackNotice?.text.key=="hades2.input.invalid", "invalid draft lost validation feedback")
   let native = money as! TrainerTextField.Field
   check(native.presentation == .invalid && native.validationMessage == Hades2GameModule.resolveText(key:"hades2.input.invalid",localization:localization)
         && native.accessibilityHelp() == native.validationMessage,
         "invalid numeric input lost its field-local visible/accessibility feedback")
  }
  _ = edit(money, to:"000402", in:window); window.makeFirstResponder(nil); pump(0.45)
  check(mutations().count==4 && money.stringValue=="402", "normalization submitted an unchanged number")
  check((money as! TrainerTextField.Field).validationMessage == nil, "a corrected value retained stale validation")
  let cancelledMoneyEditor = edit(money, to:"999", in:window)
  cancelledMoneyEditor.doCommand(by:#selector(NSResponder.cancelOperation(_:)))
  window.makeFirstResponder(nil); pump()
  check(mutations().count==4 && money.stringValue=="402" && money.currentEditor()==nil,
        "Escape submitted a runtime numeric draft or retained native focus")
  model.money=406; pump()
  check(money.stringValue=="406" && mutations().count==4, "an observation after Escape did not refresh the idle field")
  model.money=402; pump()

  // The shared click seam keeps native control events intact and ignores a
  // field's own content and other windows. Actual empty window space blurs.
  _ = edit(money, to:"403", in:window); pump()
  let inside=click(at:money.convert(NSPoint(x:money.bounds.midX,y:money.bounds.midY),to:nil),in:window)
  check(TrainerTextEditingDismissal.handle(inside,in:window) === inside && money.currentEditor() != nil,
        "click within the editor dismissed it or consumed the event")
  let other=NSWindow(contentRect:NSRect(x:0,y:0,width:100,height:100),styleMask:[.titled],backing:.buffered,defer:false)
  let otherEvent=click(at:NSPoint(x:50,y:50),in:other)
  check(TrainerTextEditingDismissal.handle(otherEvent,in:window) === otherEvent && money.currentEditor() != nil,
        "a different window dismissed the active editor")
  let blank=click(at:NSPoint(x:1,y:1),in:window)
  check(TrainerTextEditingDismissal.handle(blank,in:window) === blank && money.currentEditor()==nil,
        "blank-space click did not dismiss editing without consuming the event")
  waitForCommand("set_resource", count:5); other.close()

  guard let mana=fields(host).first(where:{$0.isEditable && $0.stringValue=="44"}) else { fatalError("mana field missing") }
  _ = edit(money,to:"404",in:window)
  _ = edit(mana,to:"45",in:window)
  waitForCommand("set_resource",count:6)
  window.makeFirstResponder(nil)
  waitForCommand("set_vital",count:1)
  check(model.money==404 && model.mana==45, "focus switch lost or misrouted one of the drafts")

  model.refreshFromHost(); check(model.busy, "busy fixture did not begin")
  _ = edit(money,to:"405",in:window); window.makeFirstResponder(nil)
  check(model.feedbackNotice?.text.key=="hades2.input.unavailable", "busy edit lost its feedback")
  check((money as! TrainerTextField.Field).validationMessage != nil,
        "an unavailable completion lost the field's recovery cue")
  wait { !model.busy }
  check(mutations().count==6 && money.stringValue=="404", "busy edit was deferred or not restored")

  _ = edit(money,to:"888",in:window); window.makeFirstResponder(nil)
  waitForCommand("set_resource",count:7)
  check(model.money==404 && money.stringValue=="888" && model.feedbackNotice?.tone == .warning,
        "backend rejection did not retain the attempted draft and error")
  pump(0.45); check(mutations().count==7, "a rejected mutation was replayed")
  _ = edit(money,to:"404",in:window); window.makeFirstResponder(nil); pump()

  // A profile barrier invalidates the callback captured at edit start.
  _ = edit(money,to:"555",in:window); pump()
  model.loadProfile("fixture-replacement")
  wait { model.money==200 && !model.busy }; window.makeFirstResponder(nil); pump(0.45)
  check(mutations().count==7 && money.currentEditor()==nil, "profile replacement submitted a stale edit")
  guard let replacement=fields(host).first(where:{$0.isEditable && $0.stringValue=="200"}) else { fatalError("profile replacement did not rebuild the numeric field") }
  money=replacement

  // Damage now lives in the collapsed numeric area. Exercise the same native
  // multiplier editing/completion contract through the visible Gold gain field;
  // the typed completion cases below still cover Damage's command identity.
  let multiplierName=Hades2GameModule.resolveText(key:"hades2.feature.moneyMultiplier",localization:localization)
  guard let gainMultiplier=fields(host).first(where:{$0.isEditable && $0.accessibilityLabel()==multiplierName}) else { fatalError("gold gain multiplier field missing") }
  let multiplierEditor=edit(gainMultiplier,to:"5.25",in:window); pump(0.45)
  check(gainMultiplier.currentEditor() != nil && commands("set_desired").isEmpty, "multiplier typing dismissed focus or applied early")
  model.moneyMultiplier=9; pump()
  check(multiplierEditor.string=="5.25", "background desired refresh overwrote the multiplier draft")
  window.makeFirstResponder(nil); waitForCommand("set_desired",count:1)
  check(model.moneyMultiplier==5.25 && (commands("set_desired").last?["params"] as? [String:Any])?["feature"] as? String=="moneyMultiplier", "multiplier blur misrouted its draft")

  phase("editing:command-families")
  // All Hades numeric families cross one validation/completion interface.
  let generation=model.editGeneration
  func complete(_ edit: Hades2RuntimeTextEdit, _ draft: String, command: String) {
   let before=commands(command).count
   _ = model.completeTextEdit(edit,text:draft,generation:generation)
   waitForCommand(command,count:before+1)
  }
  complete(.resource("MetaCurrency"),"23",command:"set_resource")
  complete(.rerolls,"24",command:"set_rerolls")
  complete(.counter("spellCharge"),"25.5",command:"set_counter")
  complete(.element("Fire"),"26",command:"set_element")
  complete(.stat("dodge"),"27.5",command:"set_stat")
  let statCount=commands("set_stat").count
  check(model.completeTextEdit(.stat("crit"),text:"28",generation:generation)=="28", "unlocked stat target was not kept")
  pump(0.45); check(commands("set_stat").count==statCount, "unlocked stat blur changed its explicit lock semantics")
  check(model.completeTextEdit(.stat("grasp"),text:"21.5",generation:generation)=="21", "integer stat silently truncated")
  for (feature,value) in [("damageMultiplier","5.5"),("moneyMultiplier","6.5"),("resourceMultiplier","7.5")] {
   complete(.multiplier(feature),value,command:"set_desired")
   check((commands("set_desired").last?["params"] as? [String:Any])?["feature"] as? String==feature, "multiplier completion misrouted its identity")
  }
  let speedCount=commands("set_desired").count
  check(model.completeTextEdit(.gameSpeed,text:"10.04",generation:generation)=="1.0", "speed was rounded into the valid range before validation")
  pump(0.45); check(commands("set_desired").count==speedCount, "invalid speed was submitted")
  complete(.gameSpeed,"2.36",command:"set_desired"); check(model.gameSpeed==2.4, "speed precision did not normalize once")
  complete(.gathering(.mining),"35.5",command:"set_gathering_desired")
  complete(.chaosGate,"65.5",command:"set_chaos_gate_desired")
  let oneShots=commands().filter { ["spawn_reward","generate_gathering","restore","save_editor_apply"].contains($0["command"] as? String ?? "") }
  check(oneShots.isEmpty, "numeric completion executed an explicit action")

  phase("editing:native-probability")
  // Native is an empty editable field, not a 100% draft. Editing survives a
  // status observation; focus/blur without input must never set a preference.
  let nativeLabel=Hades2GameModule.resolveText(key:"hades2.gathering.native",localization:localization)
  guard let nativeField=fields(host).first(where:{$0.isEditable && $0.placeholderString==nativeLabel && $0.stringValue.isEmpty})
  else { fatalError("Native gathering editor was not mounted as an empty field") }
  let nativeCount=commands("set_gathering_desired").count
  check(window.makeFirstResponder(nativeField), "Native probability field was not editable")
  pump()
  guard let nativeEditor=nativeField.currentEditor() as? NSTextView else { fatalError("Native editor failed to focus") }
  model.refreshFromHost(); wait { !model.busy }
  check(nativeEditor.string.isEmpty && nativeField.currentEditor() != nil,
        "background observation replaced focused Native editing state")
  window.makeFirstResponder(nil); pump()
  check(nativeField.stringValue.isEmpty && commands("set_gathering_desired").count==nativeCount,
        "unmodified Native focus/blur submitted an unintended 100% override")
  _ = edit(nativeField,to:"100",in:window); pump(0.45)
  check(commands("set_gathering_desired").count==nativeCount,
        "Native numeric override was applied during typing")
  window.makeFirstResponder(nil)
  waitForCommand("set_gathering_desired",count:nativeCount+1)
  check(model.gatheringProbabilities[.flora]==100,
        "Native to explicit 100% was not distinguished from Native")

  // Each completed control action retains its accepted place in the queue.
  // A later lock cannot replace an earlier lock across the intervening unlock.
  let beforeLocks=commands("set_stat").count
  model.refreshFromHost(); check(model.busy, "queue-order fixture did not begin")
  model.setStat("dodge",text:"33.3",locked:true)
  model.setStat("dodge",text:"33.3",locked:false)
  model.setStat("dodge",text:"44.4",locked:true)
  waitForCommand("set_stat",count:beforeLocks+3)
  let locks=commands("set_stat").suffix(3).compactMap { $0["params"] as? [String:Any] }
  check(locks.map { $0["locked"] as? Bool } == [true,false,true] && model.dodgeLocked && model.dodgeValue==44.4,
        "completed lock/unlock/lock actions changed order or lost the last accepted intent")

  phase("editing:queued-actions")
  // The click that completes a field still activates its originally available
  // control. The edit runs first; one explicit generation follows exactly once.
  guard let probability=fields(host).first(where:{$0.isEditable && $0.stringValue=="35.5"}) else { fatalError("mining probability field missing") }
  check(model.canGenerateGathering(.mining), "generation fixture was not available before editing")
  let beforeProbability=commands("set_gathering_desired").count
  _ = edit(probability,to:"36.5",in:window)
  let action=GenerateAction(model)
  let button=NSButton(title:"Generate",target:action,action:NSSelectorFromString("generateClicked:"))
  let buttonClick=click(at:NSPoint(x:1,y:1),in:window)
  check(TrainerTextEditingDismissal.handle(buttonClick,in:window) === buttonClick && probability.currentEditor()==nil,
        "control click was consumed or did not complete the probability")
  check(model.busy && model.canGenerateGathering(.mining), "completed edit disabled the control clicked to finish it")
  button.performClick(nil)
  check(!model.canGenerateGathering(.mining), "a queued explicit action did not close admission immediately")
  model.generateGathering(.mining)
  waitForCommand("generate_gathering",count:1)
  check(action.presses==1 && commands("set_gathering_desired").count==beforeProbability+1,
        "a control click lost its action or repeated the completion")
  let actionOrder=commands().suffix(2).compactMap { $0["command"] as? String }
  check(actionOrder==["set_gathering_desired","generate_gathering"] && model.gatheringProbabilities[.mining]==36.5,
        "explicit generation ran before the completed probability or was replayed")

  phase("editing:disconnect")
  model.toggleConnectionFromHost(); wait { !model.connected && !model.busy }
  let resourceCount=commands("set_resource").count
  check(model.completeTextEdit(.resource("Money"),text:"999",generation:model.editGeneration)=="200", "disconnected direct edit did not restore current state")
  pump(0.45); check(commands("set_resource").count==resourceCount, "disconnected runtime edit was submitted")
  let desiredCount=commands("set_desired").count
  _ = model.completeTextEdit(.multiplier("damageMultiplier"),text:"8",generation:model.editGeneration)
  waitForCommand("set_desired",count:desiredCount+1)
  check(!model.connected && model.damageMultiplier==8, "detached desired configuration was incorrectly rejected")

  phase("editing:backup-name")
  // Backup naming shares the same native edit owner, including the unchanged
  // completion that closes a transient editor and Escape cancellation.
  var name="backup"; var renamed=[String](); var cancelled=0
  let nameHost=NSHostingView(rootView:AnyView(TrainerInlineNameEditor(
   text:Binding(get:{name},set:{name=$0}), placeholder:"Backup name",
   onCommit:{renamed.append(name)}, onCancel:{cancelled += 1}).frame(width:180,height:24)))
  let nameWindow=NSWindow(contentRect:NSRect(x:0,y:0,width:240,height:60),styleMask:[.titled],backing:.buffered,defer:false)
  nameWindow.contentView=nameHost; nameHost.layoutSubtreeIfNeeded(); pump()
  guard let nameField=fields(nameHost).first(where:{$0.isEditable}) else { fatalError("backup name field missing") }
  check(nameField.currentEditor() != nil, "backup rename did not acquire initial focus")
  _ = edit(nameField,to:"renamed",in:nameWindow); pump()
  check(renamed.isEmpty, "backup naming committed during typing")
  let nameBlank=click(at:NSPoint(x:1,y:1),in:nameWindow)
  check(TrainerTextEditingDismissal.handle(nameBlank,in:nameWindow) === nameBlank, "backup click was consumed")
  check(renamed==["renamed"] && nameField.currentEditor()==nil, "backup blank click did not finish once")
  let unchanged=edit(nameField,to:"renamed",in:nameWindow)
  unchanged.doCommand(by:#selector(NSResponder.insertNewline(_:)))
  nameWindow.makeFirstResponder(nil); pump()
  check(renamed==["renamed","renamed"], "unchanged backup name did not finish or Enter submitted twice")
  let abandoned=edit(nameField,to:"cancelled",in:nameWindow)
  abandoned.doCommand(by:#selector(NSResponder.cancelOperation(_:)))
  check(cancelled==1 && name=="renamed" && renamed.count==2, "Escape committed the backup name or lost cancellation")
  _ = edit(nameField,to:"removed",in:nameWindow)
  nameHost.rootView=AnyView(EmptyView()); pump()
  check(renamed.count==2, "removing the backup editor committed an abandoned draft")
  nameWindow.close()
  try? FileManager.default.removeItem(at:log)
  session.stop(); pump(); window.close()
  phase("editing:complete")
 }
}
"""
with tempfile.TemporaryDirectory(prefix="mgt-text-edit-") as temporary:
    td = Path(temporary)
    main = td / "main.swift"; main.write_text(HARNESS + NATIVE_PICKER)
    generated = td / "ActiveGame.generated.swift"
    subprocess.run([PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)], check=True)
    sources = sorted((ROOT / "Sources/Core").rglob("*.swift")) + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
    # The first hosted cycle follows quick blur and precedes native automatic
    # focus inside a SwiftUI update. Trace only that bounded phase in fixture
    # copies, including idle fields and every native configuration assignment.
    traces = {
        ROOT / "Sources/Core/UI/Primitives/TrainerTextField.swift": [
            ("        override func becomeFirstResponder() -> Bool {\n            let acquired = super.becomeFirstResponder()", r'''
        override func becomeFirstResponder() -> Bool {
            RuntimeTextTrace.window("become:before", field: self)
            RuntimeTextTrace.native("become:before field=\(ObjectIdentifier(self))")
            let acquired = super.becomeFirstResponder()
            RuntimeTextTrace.window("become:after acquired=\(acquired)", field: self)'''),
            ("        func begin(validationMessage: String? = nil) {", r'''
        func begin(validationMessage: String? = nil) {
            RuntimeTextTrace.native("begin \(ObjectIdentifier(self)) \(parent.accessibilityLabel ?? parent.title) active=\(edit != nil)")'''),
            ("            for notify in notifications { notify() }", r'''
            for notify in notifications {
                RuntimeTextTrace.native("teardown-notification:before")
                notify()
                RuntimeTextTrace.write("teardown-notification:after")
            }'''),
            ("        func controlTextDidChange(_ notification: Notification) {", r'''
        func controlTextDidChange(_ notification: Notification) {
            RuntimeTextTrace.native("change \(ObjectIdentifier(self)) \(parent.accessibilityLabel ?? parent.title)")'''),
            ("        func controlTextDidEndEditing(_ notification: Notification) {", r'''
        func controlTextDidEndEditing(_ notification: Notification) {
            RuntimeTextTrace.native("end:enter \(ObjectIdentifier(self)) \(parent.accessibilityLabel ?? parent.title) active=\(edit != nil)")
            defer { RuntimeTextTrace.write("end:exit \(ObjectIdentifier(self))") }'''),
            ("            let normalized = completed.onCommit(completion)", r'''
            RuntimeTextTrace.write("commit:before \(ObjectIdentifier(self)) draft=\(draft)")
            let normalized = completed.onCommit(completion)
            RuntimeTextTrace.write("commit:after \(ObjectIdentifier(self)) normalized=\(normalized)")'''),
            ("        func control(_ control: NSControl, textView: NSTextView, doCommandBy command: Selector) -> Bool {", r'''
        func control(_ control: NSControl, textView: NSTextView, doCommandBy command: Selector) -> Bool {
            RuntimeTextTrace.native("command \(ObjectIdentifier(self)) \(command) marked=\(textView.hasMarkedText())")'''),
            ("        func cancel(_ field: NSTextField) {", r'''
        func cancel(_ field: NSTextField) {
            RuntimeTextTrace.native("cancel:enter \(ObjectIdentifier(self)) \(parent.accessibilityLabel ?? parent.title) active=\(edit != nil)")
            defer { RuntimeTextTrace.write("cancel:exit \(ObjectIdentifier(self))") }'''),
            ("    func updateNSView(_ field: NSTextField, context: Context) {", r'''
    func updateNSView(_ field: NSTextField, context: Context) {
        RuntimeTextTrace.updateDepth += 1
        let trace = RuntimeTextTrace.active
        if trace {
            RuntimeTextTrace.window("update:enter coordinator=\(ObjectIdentifier(context.coordinator)) \(accessibilityLabel ?? title) edit=\(context.coordinator.edit != nil)", field: field)
        }
        defer {
            if trace { RuntimeTextTrace.write("update:exit \(ObjectIdentifier(context.coordinator))") }
            RuntimeTextTrace.updateDepth -= 1
        }'''),
            ("        context.coordinator.parent = self", r'''
        if trace { RuntimeTextTrace.write("parent:before field=\(ObjectIdentifier(field))") }
        context.coordinator.parent = self
        if trace { RuntimeTextTrace.write("parent:after field=\(ObjectIdentifier(field))") }'''),
            ("        if context.coordinator.acceptsSourceObservation && field.stringValue != text {\n            field.stringValue = text\n            (field as? Field)?.refreshObservation()\n        }", r'''
        if context.coordinator.acceptsSourceObservation && field.stringValue != text {
            RuntimeTextTrace.write("stringValue:before field=\(ObjectIdentifier(field))")
            field.stringValue = text
            (field as? Field)?.refreshObservation()
            RuntimeTextTrace.write("stringValue:after field=\(ObjectIdentifier(field))")
        }'''),
            ("    private func configure(_ field: NSTextField) {", r'''
    private func configure(_ field: NSTextField) {
        RuntimeTextTrace.window("configure:enter", field: field)
        defer { RuntimeTextTrace.window("configure:exit", field: field) }'''),
            ("    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextField, context: Context) -> CGSize? {\n        CGSize(", r'''
    func sizeThatFits(_ proposal: ProposedViewSize, nsView: NSTextField, context: Context) -> CGSize? {
        let trace = RuntimeTextTrace.active
        if trace { RuntimeTextTrace.write("size:enter field=\(ObjectIdentifier(nsView)) coordinator=\(ObjectIdentifier(context.coordinator))") }
        defer { if trace { RuntimeTextTrace.write("size:exit field=\(ObjectIdentifier(nsView))") } }
        return CGSize('''),
            ("        { active in\n            if active { focus.wrappedValue = field }", r'''
        { active in
            RuntimeTextTrace.write("focus-notification:before \(String(describing:field)) active=\(active)")
            defer { RuntimeTextTrace.write("focus-notification:after \(String(describing:field)) active=\(active)") }
            if active { focus.wrappedValue = field }'''),
        ],
        ROOT / "Sources/Hades2/Hades2View.swift": [
            ("    private func syncConnectionSnapshot(_ snapshot: Hades2ViewConnectionSnapshot) {", r'''
    private func syncConnectionSnapshot(_ snapshot: Hades2ViewConnectionSnapshot) {
        RuntimeTextTrace.write("connection:enter money=\(String(describing:snapshot.money)) focus=\(String(describing:focusedField))")
        defer { RuntimeTextTrace.write("connection:exit") }'''),
            ("    private func applyCatalogChanges(from oldValue: Hades2ViewCatalogSnapshot, to newValue: Hades2ViewCatalogSnapshot) {", r'''
    private func applyCatalogChanges(from oldValue: Hades2ViewCatalogSnapshot, to newValue: Hades2ViewCatalogSnapshot) {
        RuntimeTextTrace.write("catalog:enter \(String(describing:oldValue)) -> \(String(describing:newValue))")
        defer { RuntimeTextTrace.write("catalog:exit") }'''),
        ],
    }
    configuration_assignments = [
        "field.placeholderString = title",
        "field.setAccessibilityLabel(accessibilityLabel ?? title)",
        "field.font = font",
        "field.alignment = alignment",
        "field.isEnabled = enabled",
        "field.isBezeled = style == .rounded",
        "field.bezelStyle = .roundedBezel",
        "field.drawsBackground = false",
        "field.textColor = .labelColor",
    ]
    for assignment in configuration_assignments:
        property_name = assignment.split(" = ")[0].removeprefix("field.").split("(")[0]
        traces[ROOT / "Sources/Core/UI/Primitives/TrainerTextField.swift"].append((
            "        " + assignment,
            '        RuntimeTextTrace.write("property:' + property_name + ':before field=\\(ObjectIdentifier(field))")\n'
            + "        " + assignment + "\n"
            + '        RuntimeTextTrace.write("property:' + property_name + ':after field=\\(ObjectIdentifier(field))")'
        ))
    for source, replacements in traces.items():
        text = source.read_text()
        for anchor, replacement in replacements:
            assert text.count(anchor) == 1, (source, anchor)
            text = text.replace(anchor, replacement)
        traced = td / source.name
        traced.write_text(text)
        sources[sources.index(source)] = traced
    binary = td / "text_edit"
    subprocess.run([SWIFTC, "-parse-as-library", *map(str,sources), str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"), str(ROOT / "tests/fixtures/swift/NativeAccessibility.swift"), str(generated), str(main), "-o", str(binary)], check=True)
    # Keep independent native journeys within their existing execution budget.
    for journey in os.environ.get("MGT_TEXT_EDIT_JOURNEYS", "editing,management,controls,navigation").split(","):
        fixture = td / journey; fixture.mkdir()
        worker = fixture / "worker.py"; worker.write_text(WORKER.replace("__MGT_MODULE_PROTOCOL__", str(json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["protocolVersion"])))
        home = fixture / "home"; home.mkdir()
        env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home))
        print(f"runtime_text_edit_completion_launch:{journey}", flush=True)
        try:
            result = subprocess.run([str(binary), PYTHON, str(worker), journey], env=env,
                                    capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired as error:
            for output, stream in ((error.stdout, sys.stdout), (error.stderr, sys.stderr)):
                if output is not None:
                    text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
                    print(text, end="", file=stream, flush=True)
            raise
        print(result.stdout, end="", flush=True)
        print(result.stderr, end="", file=sys.stderr, flush=True)
        result.check_returncode()
        assert not re.search(r"AttributeGraph: cycle detected through attribute [0-9]+", result.stderr), \
            f"{journey}: text editing re-entered the SwiftUI attribute graph"
    print("runtime_text_edit_completion_ok")
