"""Real Hades SwiftUI text editing uses a temporary backend, never the game/save tree."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only runtime text-edit behavior")
ROOT = Path(__file__).resolve().parents[1]
PYTHON = shutil.which("python3")
SWIFTC = shutil.which("swiftc")
WORKER = r"""
import argparse, json, pathlib, sys, time
p=argparse.ArgumentParser(); p.add_argument('--game'); args=p.parse_args()
log=pathlib.Path(__file__).with_suffix('.commands.jsonl')
state={'connected':True, 'status':'ready', 'scene':'run',
       'capabilities':{'setResource':True,'setVitals':True,'setStats':True,'setElements':True},
       'featureSupport':{'gameSpeed':True},
       'money':123,'health':99,'maxHealth':120,'mana':44,'maxMana':60,'armor':7,'spellCharge':12,'rerolls':3,
       'damageMultiplier':2,'moneyMultiplier':3,'resourceMultiplier':4,'gameSpeed':1,
       'gatheringProbabilities':{'mining':25},'chaosGateProbability':50,
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
   print(json.dumps({'type':'result','id':req['id'],'protocolVersion':6,'moduleProtocolVersion':13,'gameID':args.game,'ok':False,
                     'error':{'code':'fixture_rejected','presentation':'hades2.error.exactNotEligible'}}),flush=True)
   continue
  if params['resource']=='Money': state['money']=params['amount']
  else: state['resources'][0]['count']=params['amount']
 if command=='set_vital': state[{'health':{'current':'health','max':'maxHealth'},'mana':{'current':'mana','max':'maxMana'},'armor':{'current':'armor'}}[params['vital']][params['field']]]=params['value']
 if command=='set_counter': state[params['counter']]=params['value']
 if command=='set_rerolls': state['rerolls']=params['amount']
 if command=='set_element': state['elements'][0]['count']=params['amount']
 if command=='set_stat': state['stats'][params['stat']]={'value':params['value'],'locked':params['locked']}
 if command=='set_desired': state[params['feature']]=params['value']
 if command=='set_boon_rarity_desired': state['boonRarity']=params
 if command=='set_gathering_desired': state['gatheringProbabilities'][params['family']]=params['probability']
 if command=='set_chaos_gate_desired': state['chaosGateProbability']=params['probability']
 if command=='load_profile': state['money']=200
 if command=='disconnect': state['connected']=False
 print(json.dumps({'type':'result','id':req['id'],'protocolVersion':6,'moduleProtocolVersion':13,'gameID':args.game,'ok':True,'result':state}),flush=True)
"""
HARNESS = r"""
import AppKit
import SwiftUI
import Foundation
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
 guard let editor=field.currentEditor() as? NSTextView else { fatalError("field editor missing") }
 editor.selectAll(nil); editor.insertText(draft, replacementRange: editor.selectedRange())
 return editor
}
func click(at point: NSPoint, in window: NSWindow) -> NSEvent {
 NSEvent.mouseEvent(with:.leftMouseDown, location:point, modifierFlags:[], timestamp:0,
                   windowNumber:window.windowNumber, context:nil, eventNumber:1, clickCount:1, pressure:1)!
}
@main struct Main {
 @MainActor static func main() throws {
  _ = NSApplication.shared
  let python=URL(fileURLWithPath:CommandLine.arguments[1])
  let worker=URL(fileURLWithPath:CommandLine.arguments[2]); let temporary=worker.deletingLastPathComponent()
  let log=worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
  let session=TrainerBackendSession(client:BackendClient(process:BackendProcess(executableURL:python,argumentsPrefix:["-u"])))
  let model=Hades2TrainerModel(session:session,logSink:TrainerLogSink(url:temporary.appendingPathComponent("log")),backendScriptURL:worker,runLogDirectoryURL:temporary.appendingPathComponent("no-game-log"))
  wait { model.canSetResource && !model.busy }
  let localization=TrainerLocalizationStore(defaults:InMemoryDefaults())
  let host=NSHostingView(rootView:TrainerShell { EmptyView() } content: {
   Hades2TrainerView(model:model)
  }.environmentObject(localization))
  let window=NSWindow(contentRect:NSRect(x:0,y:0,width:1400,height:2600),styleMask:[.titled],backing:.buffered,defer:false)
  window.contentView=host; host.layoutSubtreeIfNeeded(); pump(0.5)
  guard var money=fields(host).first(where:{$0.isEditable && $0.stringValue == "123"}) else { fatalError("money text field not found: \(fields(host).map(\.stringValue))") }
  check(window.makeFirstResponder(money), "could not focus money field"); pump()
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
  guard let untyped=money.currentEditor() as? NSTextView else { fatalError("focused field editor missing") }
  model.money=777; pump()
  check(untyped.string=="123" && mutations().isEmpty, "refresh overwrote a focused editor before the first keystroke")
  window.makeFirstResponder(nil); pump()
  check(money.stringValue=="777" && mutations().isEmpty, "unchanged completion did not restore the latest observation")
  model.money=123; pump()
  check(window.makeFirstResponder(money), "could not refocus after unchanged completion")
  guard let editor=money.currentEditor() as? NSTextView else { fatalError("field editor missing") }
  for draft in ["4", "40", "400"] {
   editor.selectAll(nil); editor.insertText(draft, replacementRange:editor.selectedRange()); pump(0.45)
   check(mutations().isEmpty, "typing submitted a runtime mutation before completion")
  }
  check(window.makeFirstResponder(nil), "could not leave editing")
  waitForCommand("set_resource", count:1)
  check(mutations().count==1, "blur did not submit one changed value")
  let params=mutations()[0]["params"] as? [String:Any]
  check(params?["amount"] as? Int == 400, "blur submitted a partial draft")
  check(model.money==400, "completed edit remained deferred")
  _ = edit(money, to:"123", in:window)
  window.makeFirstResponder(nil); waitForCommand("set_resource",count:2)
  check(model.money==123, "latest completed intent lost the return to the initial value")
  _ = edit(money, to:"401", in:window)
  check(window.makeFirstResponder(nil), "could not finish quick edit")
  waitForCommand("set_resource", count:3)
  check((mutations()[2]["params"] as? [String:Any])?["amount"] as? Int == 401,
        "quick focus/edit/blur lost the draft")

  // A marked composition remains a draft across a real model refresh. Return
  // then completes the final text, and a following blur cannot submit it again.
  check(window.makeFirstResponder(money), "could not focus for composition"); pump()
  let composing=money.currentEditor() as! NSTextView
  composing.selectAll(nil)
  composing.setMarkedText("4.", selectedRange:NSRange(location:2,length:0), replacementRange:composing.selectedRange())
  check(composing.hasMarkedText(), "native marked-text fixture did not start")
  model.money=777; pump(0.45)
  check(composing.string=="4." && mutations().count==3, "refresh or composition submitted/overwrote the draft")
  composing.insertText("402", replacementRange:NSRange(location:0,length:composing.string.utf16.count))
  composing.doCommand(by: #selector(NSResponder.insertNewline(_:)))
  waitForCommand("set_resource", count:4)
  check(money.currentEditor()==nil && model.money==402, "Return did not finish: editor=\(String(describing: money.currentEditor())) money=\(String(describing: model.money)) draft=\(money.stringValue) responder=\(String(describing: window.firstResponder))")
  window.makeFirstResponder(nil); pump(0.45)
  check(mutations().count==4, "Return followed by blur submitted twice")

  for invalid in ["", "-", ".", "abc", "3.5", "9999999", "nan", "inf"] {
   _ = edit(money, to:invalid, in:window); window.makeFirstResponder(nil); pump(0.45)
   check(mutations().count==4 && money.stringValue=="402", "invalid draft was applied or not restored: '\(invalid)' draft=\(money.stringValue) mutations=\(mutations().count) feedback=\(String(describing:model.feedbackNotice))")
   check(model.feedbackNotice?.text.key=="hades2.input.invalid", "invalid draft lost validation feedback")
  }
  _ = edit(money, to:"000402", in:window); window.makeFirstResponder(nil); pump(0.45)
  check(mutations().count==4 && money.stringValue=="402", "normalization submitted an unchanged number")

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
  pump(0.45)
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

  guard let damage=fields(host).first(where:{$0.isEditable && $0.stringValue=="2" && $0.bounds.width < 80}) else { fatalError("damage multiplier field missing") }
  let damageEditor=edit(damage,to:"5.25",in:window); pump(0.45)
  check(damage.currentEditor() != nil && commands("set_desired").isEmpty, "multiplier typing dismissed focus or applied early")
  model.damageMultiplier=9; pump()
  check(damageEditor.string=="5.25", "background desired refresh overwrote the multiplier draft")
  window.makeFirstResponder(nil); waitForCommand("set_desired",count:1)
  check(model.damageMultiplier==5.25 && (commands("set_desired").last?["params"] as? [String:Any])?["feature"] as? String=="damageMultiplier", "multiplier blur misrouted its draft")

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
  complete(.boonRarity,"101.5",command:"set_boon_rarity_desired")
  complete(.gathering(.mining),"35.5",command:"set_gathering_desired")
  complete(.chaosGate,"65.5",command:"set_chaos_gate_desired")
  let oneShots=commands().filter { ["spawn_reward","generate_gathering","restore","save_editor_apply"].contains($0["command"] as? String ?? "") }
  check(oneShots.isEmpty, "numeric completion executed an explicit action")

  model.toggleConnectionFromHost(); wait { !model.connected && !model.busy }
  let resourceCount=commands("set_resource").count
  check(model.completeTextEdit(.resource("Money"),text:"999",generation:model.editGeneration)=="200", "disconnected direct edit did not restore current state")
  pump(0.45); check(commands("set_resource").count==resourceCount, "disconnected runtime edit was submitted")
  let desiredCount=commands("set_desired").count
  _ = model.completeTextEdit(.multiplier("damageMultiplier"),text:"8",generation:model.editGeneration)
  waitForCommand("set_desired",count:desiredCount+1)
  check(!model.connected && model.damageMultiplier==8, "detached desired configuration was incorrectly rejected")

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
  session.stop(); pump(); window.close()
  print("runtime_text_edit_completion_ok")
 }
}
"""
with tempfile.TemporaryDirectory(prefix="mgt-text-edit-") as temporary:
    td = Path(temporary)
    worker = td / "worker.py"; worker.write_text(WORKER)
    main = td / "main.swift"; main.write_text(HARNESS)
    generated = td / "ActiveGame.generated.swift"
    subprocess.run([PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)], check=True)
    sources = sorted((ROOT / "Sources/Core").rglob("*.swift")) + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
    binary = td / "text_edit"
    subprocess.run([SWIFTC, "-parse-as-library", *map(str,sources), str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"), str(generated), str(main), "-o", str(binary)], check=True)
    home = td / "home"; home.mkdir()
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home))
    subprocess.run([str(binary), PYTHON, str(worker)], env=env, check=True, timeout=45)
