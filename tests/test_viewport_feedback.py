import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

if sys.platform != "darwin":
    raise SystemExit("macOS-only viewport feedback model/view behavior")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = shutil.which("python3")
if not SWIFTC or not PYTHON:
    raise SystemExit("swiftc/python3 required")

worker = r'''
import argparse, json, pathlib, sys, time
p = argparse.ArgumentParser()
p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
count = 0
status_count = 0
for raw in sys.stdin:
    req = json.loads(raw)
    payload = {'connected': True, 'status': 'ready', 'scene': 'run'}
    reply = {'type': 'result', 'id': req['id'], 'protocolVersion': 6,
             'moduleProtocolVersion': 12, 'gameID': args.game, 'ok': True}
    if req['command'] == 'open_sell_traits':
        outcomes = ['accepted', 'opened', 'completed', 'completed', 'failed', 'outcome_unknown']
        outcome = outcomes[count]
        count += 1
        payload['lastAction'] = {'requestId': req['id'], 'command': req['command'],
                                 'outcome': outcome, 'duplicate': False}
        if outcome in ('failed', 'outcome_unknown'):
            reply['ok'] = False
            reply['error'] = {'code': outcome, 'presentation': 'hades2.error.exactNotEligible'}
            if outcome == 'outcome_unknown':
                payload['status'] = 'restart_required'
    elif req['command'] == 'status':
        status_count += 1
        if status_count == 1:
            reply['ok'] = False
            reply['error'] = {'code': 'unrelated_failure', 'presentation': 'hades2.error.exactNotEligible'}
    reply['result' if reply['ok'] else 'state'] = payload
    print(json.dumps(reply), flush=True)
    if req['command'] == 'open_sell_traits' and 'protocol_fault' in pathlib.Path(__file__).name:
        time.sleep(0.05)
        print('{malformed-json', flush=True)
'''

harness = r'''
import AppKit
import Combine
import Foundation
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fatalError(message) }
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func wait(_ timeout: TimeInterval = 4, message: String = "synthetic backend did not reach expected state", _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition(), Date() < deadline { pump(0.02) }
    check(condition(), message)
}

func findScroll(_ view: NSView) -> NSScrollView? {
    if let scroll = view as? NSScrollView { return scroll }
    for child in view.subviews {
        if let scroll = findScroll(child) { return scroll }
    }
    return nil
}

struct EditorProbe: NSViewRepresentable {
    let field: NSTextField
    func makeNSView(context: Context) -> NSTextField { field }
    func updateNSView(_ nsView: NSTextField, context: Context) {}
}

@main
struct Main {
    @MainActor
    static func main() throws {
        let python = URL(fileURLWithPath: CommandLine.arguments[1])
        let worker = URL(fileURLWithPath: CommandLine.arguments[2])
        let temporary = worker.deletingLastPathComponent()
        let process = BackendProcess(
            executableURL: python,
            argumentsPrefix: ["-u"],
            forceKillDelay: 0.10
        )
        let session = TrainerBackendSession(client: BackendClient(process: process))
        let model = Hades2TrainerModel(
            session: session,
            logSink: TrainerLogSink(url: temporary.appendingPathComponent("trainer.log")),
            backendScriptURL: worker,
            runLogDirectoryURL: temporary.appendingPathComponent("game-log")
        )
        wait { model.backendAvailable && !model.busy && model.feedbackNotice != nil }
        model.dismissFeedback(model.feedbackNotice!.id)

        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let editor = NSTextField(string: "draft remains focused")
        let host = NSHostingView(rootView: TrainerShell {
            Color.clear.frame(width: 160)
        } content: {
            VStack {
                EditorProbe(field: editor).frame(height: 24)
                Hades2GameModule.makeContent(model: model)
                Color.clear.frame(height: 1800)
            }
        } feedback: {
            Hades2GameModule.makeFeedback(model: model)
        }.environmentObject(localization))
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1200, height: 900),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.contentView = host
        host.frame = NSRect(x: 0, y: 0, width: 1200, height: 900)
        host.layoutSubtreeIfNeeded()
        wait { editor.window === window && editor.bounds.width > 0 && editor.bounds.height > 0
            && editor.visibleRect.intersects(editor.bounds) }
        guard let scroll = findScroll(host) else { fatalError("real shell has no scroll viewport") }
        check(window.makeFirstResponder(editor), "could not establish editor focus")
        let focused = window.firstResponder
        var previousViewport = NSRect.zero
        var stableFrames = 0
        wait {
            host.layoutSubtreeIfNeeded()
            let frame = host.convert(scroll.contentView.bounds, from: scroll.contentView)
            stableFrames = frame == previousViewport ? stableFrames + 1 : 0
            previousViewport = frame
            return stableFrames >= 3
        }
        let viewport = host.convert(scroll.contentView.bounds, from: scroll.contentView)
        let editorCenter = NSPoint(x: editor.bounds.midX, y: editor.bounds.midY)
        check(viewport.contains(host.convert(editorCenter, from: editor)),
              "click fixture editor was outside the scroll viewport")
        guard let parent = host.superview else { fatalError("hosting view has no parent coordinate space") }
        // NSView.hitTest takes its superview's coordinates. The hosting view
        // is flipped, while the window frame is not.
        let editorPoint = parent.convert(editorCenter, from: editor)
        let originalHit = host.hitTest(editorPoint)
        check(originalHit === editor || originalHit?.isDescendant(of: editor) == true,
              "click fixture did not reach the underlying editor: point=\(editorPoint) editor=\(editor.frame) visible=\(editor.visibleRect) host=\(host.bounds) scroll=\(scroll.frame) hit=\(String(describing: originalHit)) ancestry=\(String(describing: originalHit?.superview))")
        FileHandle.standardOutput.write(Data("viewport_feedback_click_target=\(String(describing: originalHit))\n".utf8))
        var feedbackEvents: [UUID] = []
        let observation = model.$feedbackNotice.compactMap { $0 }.sink { feedbackEvents.append($0.id) }

        func nextNotice(_ expectedKey: String) -> TrainerFeedbackNotice {
            let previousID = model.feedbackNotice?.id
            let eventCount = feedbackEvents.count
            model.openSellTraits()
            wait { !model.busy && model.feedbackNotice?.id != previousID && model.feedbackNotice != nil }
            let notice = model.feedbackNotice!
            check(notice.text.key == expectedKey, "receipt meaning changed: \(notice.text.key)")
            check(feedbackEvents.count == eventCount + 1, "one reply produced duplicate feedback events")
            host.layoutSubtreeIfNeeded()
            pump(0.05)
            check(host.convert(scroll.contentView.bounds, from: scroll.contentView) == viewport,
                  "showing feedback moved or obscured the editor viewport: baseline=\(viewport) actual=\(host.convert(scroll.contentView.bounds, from: scroll.contentView))")
            check(window.firstResponder === focused, "feedback stole keyboard focus")
            return notice
        }

        let accepted = nextNotice("hades2.receipt.accepted")
        check(host.hitTest(editorPoint) === originalHit, "feedback intercepted unrelated editor clicks")
        let chinese = localization.string(accepted.text)
        localization.language = .en
        check(localization.string(accepted.text) != chinese, "visible receipt did not re-resolve language")
        check(model.feedbackNotice?.id == accepted.id, "language change duplicated the event")
        model.refreshFromHost()
        wait { !model.busy && model.feedbackNotice?.id != accepted.id }
        check(model.feedbackNotice?.text.key == "hades2.error.exactNotEligible",
              "receipt suppression hid a later unrelated backend failure")
        let opened = nextNotice("hades2.receipt.opened")
        model.dismissFeedback(accepted.id)
        check(model.feedbackNotice?.id == opened.id, "stale dismissal removed newer receipt")
        let completed = nextNotice("hades2.receipt.completed")
        let repeated = nextNotice("hades2.receipt.completed")
        check(repeated.id != completed.id, "identical completion text reused notice identity")

        // The slot remains outside the viewport at each scroll position.
        for offset in [0.0, 500.0, 1200.0] {
            scroll.contentView.scroll(to: NSPoint(x: 0, y: offset))
            scroll.reflectScrolledClipView(scroll.contentView)
            host.layoutSubtreeIfNeeded()
            check(host.convert(scroll.contentView.bounds, from: scroll.contentView) == viewport,
                  "feedback slot scrolled with game content")
        }

        let failed = nextNotice("hades2.receipt.failed")
        model.dismissFeedback(failed.id)
        check(model.feedbackNotice == nil && !model.errorText.key.isEmpty,
              "dismissing overlay erased retained failure")
        _ = nextNotice("hades2.receipt.outcomeUnknown")
        wait(6) { model.feedbackNotice == nil }
        check(!model.errorText.key.isEmpty && model.status == "restart_required",
              "automatic fade erased outcome-unknown recovery state")
        pump(0.1)
        check(model.feedbackNotice == nil, "expired feedback reappeared during an incidental render")

        model.refreshFromHost()
        wait { !model.busy && model.feedbackNotice != nil }
        let routine = model.feedbackNotice!
        check(routine.text.key == "host.backend.notice.completed", "routine success did not use the existing token")
        model.refreshFromHost()
        wait { !model.busy && model.feedbackNotice?.id != routine.id }
        check(model.feedbackNotice != nil, "identical routine feedback was not a new event")

        let defaultHost = NSHostingView(rootView: TrainerShell {
            Color.clear.frame(width: 160)
        } content: { Color.clear.frame(height: 1800) })
        defaultHost.frame = host.frame
        defaultHost.layoutSubtreeIfNeeded()
        guard let defaultScroll = findScroll(defaultHost) else { fatalError("default shell has no viewport") }
        check(defaultScroll.frame.height > scroll.frame.height + 60,
              "default empty feedback slot reserved a blank footer")

        // A transport failure arriving after an accepted reply belongs to a
        // different event; receipt suppression must end with that reply.
        let faultWorker = temporary.appendingPathComponent("protocol_fault_worker.py")
        try FileManager.default.copyItem(at: worker, to: faultWorker)
        let faultSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10
        )))
        let faultModel = Hades2TrainerModel(
            session: faultSession,
            logSink: TrainerLogSink(url: temporary.appendingPathComponent("fault.log")),
            backendScriptURL: faultWorker,
            runLogDirectoryURL: temporary.appendingPathComponent("fault-game-log")
        )
        var faultEvents: [String] = []
        let faultObservation = faultModel.$feedbackNotice.compactMap { $0 }.sink { faultEvents.append($0.text.key) }
        wait { faultModel.backendAvailable && !faultModel.busy }
        faultModel.openSellTraits()
        wait(message: "receipt suppression hid asynchronous backend recovery") {
            faultEvents.contains("host.backend.notice.recovering")
        }
        check(faultEvents.filter { $0 == "hades2.receipt.accepted" }.count == 1,
              "accepted receipt was duplicated before asynchronous recovery")
        wait(message: "recovered worker did not project fresh status") {
            faultEvents.contains("host.backend.notice.recovered")
        }
        faultSession.stop(suppressTerminationError: true)
        faultObservation.cancel()
        session.stop(suppressTerminationError: true)
        observation.cancel()
        print("viewport_feedback_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-viewport-feedback-") as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "viewport_feedback"
    stub = td / "worker.py"
    home = td / "home"
    home.mkdir()
    main.write_text(textwrap.dedent(harness))
    stub.write_text(textwrap.dedent(worker))
    generated = td / "ActiveGame.generated.swift"
    subprocess.run([PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)], check=True)
    sources = sorted((ROOT / "Sources/Core").rglob("*.swift")) + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
    subprocess.run([SWIFTC, "-parse-as-library", "-whole-module-optimization", *map(str, sources),
                    str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
                    str(generated), str(main), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home))
    subprocess.run([str(binary), PYTHON, str(stub)], check=True, cwd=ROOT, env=env, timeout=30)
