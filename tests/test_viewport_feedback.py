import ctypes
import json
import math
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


def run_with_restored_pointer(command, **kwargs):
    """Restore the runner's cursor even if the native child traps or times out."""
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

    graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    graphics.CGEventCreate.argtypes = [ctypes.c_void_p]
    graphics.CGEventCreate.restype = ctypes.c_void_p
    graphics.CGEventGetLocation.argtypes = [ctypes.c_void_p]
    graphics.CGEventGetLocation.restype = Point
    graphics.CGWarpMouseCursorPosition.argtypes = [Point]
    graphics.CGWarpMouseCursorPosition.restype = ctypes.c_int32
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    foundation.CFRelease.restype = None

    def position():
        event = graphics.CGEventCreate(None)
        if not event:
            raise RuntimeError("could not capture the native pointer position")
        try:
            point = graphics.CGEventGetLocation(event)
            if not math.isfinite(point.x) or not math.isfinite(point.y):
                raise RuntimeError("native pointer coordinates are not finite")
            return point
        finally:
            foundation.CFRelease(event)

    original = position()
    try:
        return subprocess.run(command, **kwargs)
    finally:
        # subprocess.run kills and reaps a timed-out child before unwinding.
        # A Swift defer cannot restore the cursor after fatalError/SIGTRAP.
        child_failed = sys.exc_info()[0] is not None
        try:
            result = graphics.CGWarpMouseCursorPosition(original)
            if result != 0:
                raise RuntimeError(f"cursor restoration failed with CGError {result}")
            restored = position()
            if abs(restored.x - original.x) > 1 or abs(restored.y - original.y) > 1:
                raise RuntimeError("cursor restoration did not reach the saved position")
        except Exception as error:
            print(f"FEEDBACK_POINTER_RESTORE_FAILURE {error}", file=sys.stderr, flush=True)
            if not child_failed:
                raise


worker = r'''
import argparse, json, pathlib, sys, time
p = argparse.ArgumentParser()
p.add_argument('--game', required=True)
args, _ = p.parse_known_args()
count = 0
status_count = 0
for raw in sys.stdin:
    req = json.loads(raw)
    with pathlib.Path(__file__).with_suffix('.commands.jsonl').open('a') as log:
        log.write(json.dumps(req) + '\n')
    payload = {'connected': True, 'status': 'ready', 'scene': 'run',
               'capabilities': {'sellTraits': True}}
    issues_path = pathlib.Path(__file__).with_name('issues.json')
    if issues_path.exists():
        payload.update(json.loads(issues_path.read_text()))
    reply = {'type': 'result', 'id': req['id'], 'protocolVersion': 6,
             'moduleProtocolVersion': __MGT_MODULE_PROTOCOL__, 'gameID': args.game, 'ok': True}
    if req['command'] == 'open_sell_traits':
        outcomes = ['accepted', 'opened', 'completed', 'completed', 'failed', 'outcome_unknown']
        ack_loss = 'ack_loss_' in pathlib.Path(__file__).name
        outcome = ('accepted' if 'accepted' in pathlib.Path(__file__).name else 'completed') if ack_loss else outcomes[count]
        count += 1
        payload['lastAction'] = {'requestId': req['id'], 'command': req['command'],
                                 'outcome': outcome, 'duplicate': False}
        if outcome in ('failed', 'outcome_unknown'):
            reply['ok'] = False
            reply['error'] = {'code': outcome, 'presentation': 'hades2.error.exactNotEligible'}
            if outcome == 'outcome_unknown':
                payload['status'] = 'restart_required'
        if ack_loss:
            reply['ok'] = False
            reply['error'] = {'code': 'restart_required',
                              'presentation': 'hades2.error.commandResultConnectionLost'}
            payload.update(connected=False, status='restart_required', capabilities={'sellTraits': False})
    elif req['command'] == 'status':
        status_count += 1
        if status_count == 1 and not issues_path.exists():
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
import CoreGraphics
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

@MainActor
final class FeedbackPageVisibility {
    let pageVisibility = TrainerGamePageVisibility()
    var visible: Bool { pageVisibility.isVisible }
    func setVisible(_ visible: Bool) { pageVisibility.setVisible(visible) }
}

@MainActor
final class FeedbackInteractionWindow: NSWindow {
    struct PointerDelivery {
        let type: NSEvent.EventType
        let windowNumber: Int
        let location: NSPoint
        let timestamp: TimeInterval
    }
    private(set) var pointerDeliveries: [PointerDelivery] = []

    override func sendEvent(_ event: NSEvent) {
        switch event.type {
        case .mouseMoved, .mouseEntered, .mouseExited:
            // Observe dispatch without manufacturing tracking events, changing
            // the pointer, or intercepting the native hover implementation.
            if pointerDeliveries.count == 16 { pointerDeliveries.removeFirst() }
            pointerDeliveries.append(PointerDelivery(type: event.type,
                windowNumber: event.windowNumber, location: event.locationInWindow,
                timestamp: event.timestamp))
        default:
            break
        }
        super.sendEvent(event)
    }
}

struct FeedbackInteractionPage: View {
    @ObservedObject var model: Hades2TrainerModel
    let visibility: FeedbackPageVisibility
    let editor: NSTextField

    var body: some View {
        TrainerShell {
            Hades2GameModule.makeSidebarActions(model: model).frame(width: 220)
        } content: {
            VStack {
                EditorProbe(field: editor).frame(height: 24)
                Color.clear.frame(height: 1100)
            }
        } feedback: {
            Hades2GameModule.makeFeedback(model: model)
        }
        .environment(\.trainerGamePageVisibility, visibility.pageVisibility)
    }
}

@MainActor
func feedbackInputPump(_ duration: TimeInterval) {
    // Dispatch AppKit activation, tracking and focus events as well as timers.
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
func exerciseFeedbackInput(model: Hades2TrainerModel, worker: URL) throws {
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.finishLaunching()
    app.activate(ignoringOtherApps: true)
    enableNativeAccessibility()
    let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
    localization.language = .en
    localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
        Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
    }
    check(localization.localized("host.feedback.closeDetails") != "host.feedback.closeDetails",
          "feedback interaction fixture did not load shipped Host translations")
    let visibility = FeedbackPageVisibility()
    let editor = NSTextField(string: "unsubmitted feedback interaction draft")
    let host = NSHostingView(rootView: FeedbackInteractionPage(model: model, visibility: visibility, editor: editor)
        .environmentObject(localization))
    let window = FeedbackInteractionWindow(contentRect: NSRect(x: 100, y: 100, width: 1000, height: 600),
                                          styleMask: [.titled], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.acceptsMouseMovedEvents = true
    window.contentView = host
    window.makeKeyAndOrderFront(nil)
    app.activate(ignoringOtherApps: true)
    defer { window.contentView = nil; window.close() }

    func waitInput(_ description: String, _ condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(3)
        repeat {
            host.layoutSubtreeIfNeeded()
            if condition() { return }
            feedbackInputPump(0.02)
        } while Date() < deadline
        check(condition(), "native feedback interaction timed out: " + description)
    }
    func control(_ name: String) -> NativeAccessibilityControl? {
        nativeAccessibilityControls(host).first {
            $0.identifier == "host.feedback." + name && $0.role == "AXButton"
        }
    }
    func requestCount() -> Int {
        let log = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
        return ((try? String(contentsOf: log, encoding: .utf8)) ?? "").split(separator: "\n").count
    }
    func movePointer(to point: NSPoint) {
        // The CI trace proved sendEvent reached this window while the physical
        // cursor stayed elsewhere. Move that cursor, then retain the original
        // AppKit event route; warp alone is never evidence of hover delivery.
        guard let primary = NSScreen.screens.first else {
            fatalError("native pointer input has no primary screen")
        }
        let screenPoint = window.convertPoint(toScreen: point)
        let targetOwner = NSWindow.windowNumber(at: screenPoint, belowWindowWithWindowNumber: 0)
        check(app.isActive && window.isKeyWindow && window.isVisible
                && window.occlusionState.contains(.visible) && targetOwner == window.windowNumber
                && NSScreen.screens.contains(where: { $0.visibleFrame.contains(screenPoint) }),
              "native pointer target is not in the fixture's active visible front window")
        // AppKit uses the primary screen's lower-left origin; Quartz uses its
        // upper-left origin. Both are display points, not backing pixels.
        let quartzPoint = CGPoint(x: screenPoint.x, y: primary.frame.maxY - screenPoint.y)
        let warp = CGWarpMouseCursorPosition(quartzPoint)
        check(warp == .success, "native cursor warp failed: \(warp.rawValue)")
        let event = NSEvent.mouseEvent(with: .mouseMoved, location: point, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 0, clickCount: 0, pressure: 0)!
        app.sendEvent(event)
        feedbackInputPump(0.1)
        let cursor = NSEvent.mouseLocation
        let outsideEventStream = window.mouseLocationOutsideOfEventStream
        let delivered = window.pointerDeliveries.contains {
            $0.type == .mouseMoved && $0.windowNumber == window.windowNumber
                && $0.timestamp == event.timestamp && $0.location == point
        }
        let positioned = abs(cursor.x - screenPoint.x) <= 1 && abs(cursor.y - screenPoint.y) <= 1
            && abs(outsideEventStream.x - point.x) <= 1 && abs(outsideEventStream.y - point.y) <= 1
        let inputArrived = delivered && positioned
        if !inputArrived {
            let context: [String: Any] = [
                "originalInputPredicatePassed": false, "delivered": delivered, "positioned": positioned,
                "targetInWindow": NSStringFromPoint(point), "targetOnScreen": NSStringFromPoint(screenPoint),
                "cursorOnScreen": NSStringFromPoint(cursor),
                "cursorOutsideEventStream": NSStringFromPoint(outsideEventStream),
                "active": app.isActive, "key": window.isKeyWindow, "window": window.windowNumber,
            ]
            let payload = (try? JSONSerialization.data(withJSONObject: context, options: [.sortedKeys]))
                ?? Data(String(describing: context).utf8)
            FileHandle.standardError.write(Data("FEEDBACK_POINTER_INPUT_FAILURE ".utf8) + payload + Data("\n".utf8))
        }
        check(inputArrived, "native pointer position and original window event did not agree")
    }
    func focus(_ target: NativeAccessibilityControl) {
        let selector = NSSelectorFromString("setAccessibilityFocused:")
        check(target.object.responds(to: selector), "feedback action has no documented AX focus setter")
        typealias Setter = @convention(c) (AnyObject, Selector, Bool) -> Void
        unsafeBitCast(target.object.method(for: selector), to: Setter.self)(target.object, selector, true)
    }
    func isFocused(_ target: NativeAccessibilityControl) -> Bool {
        let selector = NSSelectorFromString("isAccessibilityFocused")
        guard target.object.responds(to: selector) else { return false }
        typealias Getter = @convention(c) (AnyObject, Selector) -> Bool
        return unsafeBitCast(target.object.method(for: selector), to: Getter.self)(target.object, selector)
    }
    func reportHoverFailure(_ notice: TrainerFeedbackNotice, targetInWindow: NSRect,
                            targetOnScreen: NSRect, elapsed: TimeInterval,
                            expectedResponder: NSResponder?, requestsBefore: Int) {
        // The original short-circuit predicate has already failed. Read all
        // geometry, AX and visibility context only after freezing that result.
        // Never read an active text control's stringValue: it can validate edits.
        let currentNotice = model.feedbackNotice?.id
        let currentResponder = window.firstResponder
        let detailsPresented = model.feedbackDetailsPresented
        let detailsNotice = model.feedbackDetailsNoticeID
        let visible = visibility.visible
        let cursor = NSEvent.mouseLocation
        let deliveries = window.pointerDeliveries
        let dismiss = control("dismiss")
        let details = control("details")
        let point = NSPoint(x: targetInWindow.midX, y: targetInWindow.midY)
        var tracking: [[String: Any]] = []
        func inspectTracking(_ view: NSView) {
            guard tracking.count < 32 else { return }
            let localPoint = view.convert(point, from: nil)
            for area in view.trackingAreas where tracking.count < 32 {
                let bounds = area.options.contains(.inVisibleRect) ? view.visibleRect : area.rect
                guard bounds.contains(localPoint) else { continue }
                tracking.append([
                    "view": String(describing: type(of: view)),
                    "owner": area.owner.map { String(describing: type(of: $0)) } ?? "nil",
                    "boundsInWindow": NSStringFromRect(view.convert(bounds, to: nil)),
                    "hidden": view.isHiddenOrHasHiddenAncestor, "options": area.options.rawValue,
                ])
            }
            for child in view.subviews { inspectTracking(child) }
        }
        inspectTracking(host)
        func identity(_ responder: NSResponder?) -> String {
            responder.map { String(describing: ObjectIdentifier($0)) } ?? "nil"
        }
        let context: [String: Any] = [
            "originalPredicatePassed": false,
            "expectedNotice": notice.id.uuidString, "currentNotice": currentNotice?.uuidString ?? "nil",
            "elapsed": elapsed, "ordinaryDuration": TrainerFeedbackTiming.ordinaryDuration,
            "fadeDuration": TrainerFeedbackTiming.fadeDuration,
            "pageVisible": visible, "detailsPresented": detailsPresented,
            "detailsNotice": detailsNotice?.uuidString ?? "nil",
            "dismissExists": dismiss != nil, "dismissEnabled": dismiss?.enabled ?? false,
            "dismissFocused": dismiss.map { isFocused($0) } ?? false,
            "detailsFocused": details.map { isFocused($0) } ?? false,
            "expectedResponder": identity(expectedResponder), "currentResponder": identity(currentResponder),
            "responderPreserved": currentResponder === expectedResponder,
            "active": app.isActive, "running": app.isRunning,
            "window": window.windowNumber, "key": window.isKeyWindow,
            "visible": window.isVisible, "occlusionState": window.occlusionState.rawValue,
            "windowFrame": NSStringFromRect(window.frame),
            "hostVisibleInWindow": NSStringFromRect(host.convert(host.visibleRect, to: nil)),
            "targetInWindow": NSStringFromRect(targetInWindow),
            "targetOnScreenAtInput": NSStringFromRect(targetOnScreen),
            "targetInHostVisibleRect": host.visibleRect.contains(host.convert(targetInWindow, from: nil)),
            "cursorOnScreen": NSStringFromPoint(cursor), "cursorInOriginalTarget": targetOnScreen.contains(cursor),
            "cursorOutsideEventStream": NSStringFromPoint(window.mouseLocationOutsideOfEventStream),
            "screens": NSScreen.screens.map { NSStringFromRect($0.visibleFrame) },
            "requestsBefore": requestsBefore, "requestsAfter": requestCount(),
            "pointerDeliveries": deliveries.map {
                ["type": $0.type.rawValue, "window": $0.windowNumber,
                 "point": NSStringFromPoint($0.location), "timestamp": $0.timestamp] as [String: Any]
            },
            "trackingAtOriginalTargetAfterFailure": tracking,
            "visibleWindows": Array(app.windows.filter(\.isVisible).prefix(12)).map {
                ["number": $0.windowNumber, "type": String(describing: type(of: $0)),
                 "frame": NSStringFromRect($0.frame), "key": $0.isKeyWindow,
                 "sheet": $0.sheetParent != nil] as [String: Any]
            },
        ]
        let payload = (try? JSONSerialization.data(withJSONObject: context, options: [.sortedKeys]))
            ?? Data(String(describing: context).utf8)
        FileHandle.standardError.write(Data("FEEDBACK_HOVER_FAILURE ".utf8) + payload + Data("\n".utf8))
    }
    func next(_ key: String) -> TrainerFeedbackNotice {
        let previous = model.feedbackNotice?.id
        let before = requestCount()
        model.openSellTraits()
        waitInput("real module receipt " + key) {
            !model.busy && model.feedbackNotice != nil && model.feedbackNotice?.id != previous
                && control("dismiss")?.enabled == true
        }
        let notice = model.feedbackNotice!
        check(notice.text.key == key, "native interaction changed the module receipt meaning")
        check(requestCount() == before + 1, "fixture operation did not dispatch exactly once")
        return notice
    }

    waitInput("active native window and initial feedback") {
        app.keyWindow === window && control("dismiss")?.enabled == true && editor.window === window
    }
    check(window.makeFirstResponder(editor), "feedback editor refused native focus")
    let focusedEditor = window.firstResponder
    let initialRequests = requestCount()
    check(control("dismiss")!.press(), "initial feedback refused native dismissal")
    waitInput("initial native dismissal") { model.feedbackNotice == nil }
    check(requestCount() == initialRequests, "feedback dismissal sent a backend request")

    let hoverNotice = next("hades2.receipt.accepted")
    check(hoverNotice.tone != .warning, "hover fixture requires the ordinary readable interval")
    let hoverRequests = requestCount()
    let dismissScreenBounds = control("dismiss")!.frame
    let dismissBounds = window.convertFromScreen(dismissScreenBounds)
    check(dismissBounds.width > 0 && dismissBounds.height > 0, "feedback hover target has no native bounds")
    let hoverStarted = ProcessInfo.processInfo.systemUptime
    movePointer(to: NSPoint(x: dismissBounds.midX, y: dismissBounds.midY))
    check(dismissScreenBounds.contains(NSEvent.mouseLocation), "native pointer missed the actual feedback control")
    feedbackInputPump(TrainerFeedbackTiming.ordinaryDuration + TrainerFeedbackTiming.fadeDuration + 0.2)
    let hoverRetained = model.feedbackNotice?.id == hoverNotice.id && control("dismiss")?.enabled == true
    if !hoverRetained {
        reportHoverFailure(hoverNotice, targetInWindow: dismissBounds, targetOnScreen: dismissScreenBounds,
            elapsed: ProcessInfo.processInfo.systemUptime - hoverStarted,
            expectedResponder: focusedEditor, requestsBefore: hoverRequests)
    }
    check(hoverRetained, "native pointer hover failed to pause the feedback lifetime")
    check(dismissScreenBounds.contains(NSEvent.mouseLocation), "native pointer left the feedback control during hover")
    check(window.firstResponder === focusedEditor && !model.feedbackDetailsPresented,
          "hover pause was confounded by stolen focus or open details")
    check(requestCount() == hoverRequests, "hover or feedback timing dispatched a backend request")
    movePointer(to: editor.convert(NSPoint(x: editor.bounds.midX, y: editor.bounds.midY), to: nil))
    check(control("dismiss")!.press(), "hovered notice refused native dismissal")
    waitInput("dismissal after hover") { model.feedbackNotice == nil }
    // Retire pointer presentation before the separate keyboard episode, so
    // focus pausing cannot accidentally pass because hover remained active.
    visibility.setVisible(false)
    feedbackInputPump(0.1)
    visibility.setVisible(true)
    feedbackInputPump(0.1)

    let focusedNotice = next("hades2.receipt.opened")
    let focusedRequests = requestCount()
    let dismiss = control("dismiss")!
    focus(dismiss)
    waitInput("feedback button receives native keyboard focus") { isFocused(dismiss) }
    feedbackInputPump(TrainerFeedbackTiming.ordinaryDuration + TrainerFeedbackTiming.fadeDuration + 0.2)
    check(model.feedbackNotice?.id == focusedNotice.id && isFocused(dismiss) && !model.feedbackDetailsPresented,
          "native feedback button focus failed to pause its lifetime")
    for type in [NSEvent.EventType.keyDown, .keyUp] {
        let event = NSEvent.keyEvent(with: type, location: .zero, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, characters: "\u{1b}", charactersIgnoringModifiers: "\u{1b}",
            isARepeat: false, keyCode: 53)!
        app.sendEvent(event)
    }
    waitInput("native Escape dismisses the focused notice") { model.feedbackNotice == nil && control("dismiss") == nil }
    check(requestCount() == focusedRequests && editor.stringValue == "unsubmitted feedback interaction draft",
          "focus or Escape changed a draft or sent a backend request")

    _ = next("hades2.receipt.completed")
    _ = next("hades2.receipt.completed")
    let failure = next("hades2.receipt.failed")
    waitInput("real module exposes retained failure details") { control("details")?.enabled == true }
    let detailRequests = requestCount()
    let staleDetails = control("details")!
    let staleDismiss = control("dismiss")!
    visibility.setVisible(false)
    waitInput("hidden page retires both native feedback actions") {
        control("details") == nil && control("dismiss") == nil
    }
    _ = staleDetails.press()
    _ = staleDismiss.press()
    feedbackInputPump(0.1)
    check(!model.feedbackDetailsPresented && model.feedbackNotice?.id == failure.id,
          "a hidden page's retained native callback opened details or dismissed its notice")
    check(requestCount() == detailRequests && !model.currentIssues.isEmpty,
          "hidden feedback callbacks changed backend traffic or retained failure state")
    visibility.setVisible(true)
    waitInput("returning page restores its own feedback") {
        model.feedbackNotice?.id == failure.id && control("details")?.enabled == true
    }
    check(control("details")!.press(), "real module Details refused native AX input")
    waitInput("real module opens its own failure details") {
        model.feedbackDetailsPresented && model.feedbackDetailsNoticeID == failure.id
    }
    func closeDetails() -> NativeAccessibilityControl? {
        app.windows.filter(\.isVisible).lazy.flatMap { nativeAccessibilityControls($0) }.first {
            $0.role == "AXButton" && $0.label == localization.localized("host.feedback.closeDetails")
        }
    }
    waitInput("actual module details popover has a native Close button") { closeDetails()?.enabled == true }
    check(closeDetails()!.press(), "actual module details refused native Close")
    waitInput("native Close retires only details presentation") { !model.feedbackDetailsPresented }
    check(model.feedbackNotice?.id == failure.id && !model.currentIssues.isEmpty,
          "closing native details erased the originating failure")
    check(control("dismiss")!.press(), "real failed notice refused native dismissal")
    waitInput("native dismissal leaves failure details available") { model.feedbackNotice == nil }
    check(!model.currentIssues.isEmpty && requestCount() == detailRequests,
          "native Details/Close/Dismiss changed failure authority or dispatched a backend request")
    print("hades2_feedback_native_hover_focus_escape_and_lifetime_ok")
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
        model.hostTargetLifetimeChanged(observation: TrainerTargetObservation(isRunning: false, launchGeneration: 0))
        wait { model.backendAvailable && !model.busy && model.feedbackNotice != nil }
        if CommandLine.arguments.count == 4 && CommandLine.arguments[3] == "interactions" {
            try exerciseFeedbackInput(model: model, worker: worker)
            session.stop(suppressTerminationError: true)
            return
        }
        model.dismissFeedback(model.feedbackNotice!.id)
        check(model.currentIssues.isEmpty, "routine success became a retained issue")
        model.showFeedbackDetails()
        check(!model.feedbackDetailsPresented, "details opened with no unresolved owner state")

        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.registerModulePresentation(prefix: Hades2GameModule.presentationKeyPrefix) {
            Hades2GameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        let editor = NSTextField(string: "draft remains focused")
        let host = NSHostingView(rootView: TrainerShell {
            VStack {
                Color.clear.frame(width: 160, height: 1)
                Spacer()
                Hades2SidebarActions(model: model)
            }.frame(width: 160)
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
        let defaultHost = NSHostingView(rootView: TrainerShell {
            Color.clear.frame(width: 160)
        } content: { Color.clear.frame(height: 1800) })
        defaultHost.frame = host.frame
        defaultHost.layoutSubtreeIfNeeded()
        guard let defaultScroll = findScroll(defaultHost) else { fatalError("default shell has no viewport") }
        check(defaultScroll.frame == scroll.frame,
              "idle Hades feedback reserves viewport space: default=\(defaultScroll.frame) Hades=\(scroll.frame)")
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
        // The noninteractive text/background portion of the card must also
        // leave the underlying viewport available for clicks.
        let noticeTextPoint = parent.convert(
            NSPoint(x: viewport.midX - 100, y: viewport.maxY - 36), from: host
        )
        let underlyingNoticeHit = host.hitTest(noticeTextPoint)
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
        check(host.hitTest(noticeTextPoint) === underlyingNoticeHit,
              "noninteractive feedback text/background intercepted the viewport")
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

        // The overlay remains attached to the viewport at each scroll position.
        for offset in [0.0, 500.0, 1200.0] {
            scroll.contentView.scroll(to: NSPoint(x: 0, y: offset))
            scroll.reflectScrolledClipView(scroll.contentView)
            host.layoutSubtreeIfNeeded()
            check(host.convert(scroll.contentView.bounds, from: scroll.contentView) == viewport,
                  "feedback overlay scrolled with game content")
        }

        let failed = nextNotice("hades2.receipt.failed")
        model.dismissFeedback(failed.id)
        check(model.feedbackNotice == nil && !model.errorText.key.isEmpty,
              "dismissing overlay erased retained failure")
        check(!model.currentIssues.isEmpty, "collapsed failure lost its details entry")
        model.showFeedbackDetails(for: failed.id)
        check(!model.feedbackDetailsPresented, "stale notice opened details after collapse")
        let unknown = nextNotice("hades2.receipt.outcomeUnknown")
        check(model.currentIssues.contains { $0.id == "recovery" },
              "outcome-unknown omitted the retained restart requirement")
        // The receipt, runtime error and retained terminal recovery must give
        // the same safe next step in both languages, including after a live
        // language change. A reconnect alone cannot restore unknown trust.
        let originalLanguage = localization.language
        let uncertainMessages = [unknown.text] + [
            "hades2.error.outcomeUnknownEmpty", "hades2.error.outcomeUnknownGeneric",
            "hades2.error.outcomeUnknownRuntime", "hades2.error.outcomeUnknownTransport",
            "hades2.error.outcomeUnknownUnreadable", "hades2.error.restartRequired",
        ].map { TrainerTextToken(key: $0, arguments: ["fixture diagnostic"]) }
        for language in [TrainerPresentationLanguage.zhCN, .en] {
            localization.language = language
            let required = language == .en
                ? ["may have executed", "Do not repeat", "Inspect the game state", "restart Hades II", "before reconnecting"]
                : ["可能已执行", "请勿重复", "检查游戏状态", "重新启动 Hades II", "后再连接"]
            for token in uncertainMessages {
                let rendered = localization.string(token)
                check(required.allSatisfy { rendered.contains($0) },
                      "unknown-action feedback conflicts with restart recovery in \(language): \(rendered)")
            }
            check(localization.string(model.statusTitle).contains(language == .en ? "Restarted" : "重启"),
                  "terminal session status lost restart meaning")
            check(model.currentIssues.contains { $0.id == "operation" && $0.text == unknown.text },
                  "retained details lost the uncertain action receipt")
            check(!localization.string(completed.text).contains(language == .en ? "restart" : "重启")
                    && !localization.string(failed.text).contains(language == .en ? "restart" : "重启"),
                  "completed or ordinary failed receipts acquired terminal recovery instructions")
        }
        localization.language = originalLanguage
        pump(6)
        model.showFeedbackDetails(for: unknown.id)
        pump(3)
        check(model.feedbackNotice?.id == unknown.id && model.feedbackDetailsPresented,
              "details interaction did not pause the eight-second error summary")
        model.closeFeedbackDetails()
        wait(4, message: "error summary did not resume after closing details") { model.feedbackNotice == nil }
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

        check(defaultScroll.frame == scroll.frame,
              "visible Hades feedback changed the viewport geometry")

        // Current issues are a projection of owner state, not a notification
        // history. Structured Host arguments and feature identities survive;
        // resolved states remove the entry and close its details.
        let issues = temporary.appendingPathComponent("issues.json")
        try JSONSerialization.data(withJSONObject: [
            "warnings": ["host.backend.error.unavailable"],
            "featureErrors": ["invincibility": "runtime refusal"],
            "featureErrorPresentations": [
                "gameSpeed": ["presentation": "host.timeWarp.error.setFailed", "arguments": [-7]],
            ],
        ]).write(to: issues)
        // Explicit worker restart is the existing owner transition that clears
        // the earlier retained outcome-unknown error. An unrelated successful
        // read must not be treated as resolving that one-shot operation.
        model.restartBackendFromHost()
        wait { model.backendAvailable && !model.busy }
        model.refreshFromHost()
        wait(message: "structured runtime issues did not reach the current-issues projection") {
            !model.busy && model.currentIssues.contains { $0.id == "runtime.gameSpeed" }
        }
        let speedIssue = model.currentIssues.first { $0.id == "runtime.gameSpeed" }
        check(speedIssue?.text.arguments == ["-7"], "details flattened Host error arguments")
        check(speedIssue?.title != nil, "known runtime feature lost its readable title")
        check(model.currentIssues.contains { $0.id == "warning" }, "details omitted current warnings")
        model.showFeedbackDetails()
        try JSONSerialization.data(withJSONObject: [
            "warnings": [String](), "featureErrors": [String: String](),
            "featureErrorPresentations": [String: Any](),
        ]).write(to: issues)
        model.refreshFromHost()
        wait(message: "resolved current issues did not clear details: \(model.currentIssues)") {
            !model.busy && model.currentIssues.isEmpty && !model.feedbackDetailsPresented
        }
        model.status = "incompatible"
        check(model.currentIssues.map(\.id) == ["compatibility"],
              "details omitted the current incompatible target")
        model.status = "ready"
        check(model.currentIssues.isEmpty, "resolved compatibility remained as issue history")

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
        faultModel.hostTargetLifetimeChanged(observation: TrainerTargetObservation(isRunning: false, launchGeneration: 0))
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

        // A known completed/accepted action and failed command acceptance
        // arrive in one reply. Keep the receipt visible in recovery details,
        // while the immediate notice explains why no further action is safe.
        for outcome in ["completed", "accepted"] {
            let ackWorker = temporary.appendingPathComponent("ack_loss_\(outcome)_worker.py")
            try FileManager.default.copyItem(at: worker, to: ackWorker)
            let ackSession = TrainerBackendSession(client: BackendClient(process: BackendProcess(
                executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.10
            )))
            let ackModel = Hades2TrainerModel(
                session: ackSession,
                logSink: TrainerLogSink(url: temporary.appendingPathComponent("ack-\(outcome).log")),
                backendScriptURL: ackWorker,
                runLogDirectoryURL: temporary.appendingPathComponent("ack-\(outcome)-game-log")
            )
            ackModel.hostTargetLifetimeChanged(observation: TrainerTargetObservation(isRunning: false, launchGeneration: 0))
            wait { ackModel.backendAvailable && !ackModel.busy }
            ackModel.openSellTraits()
            wait(message: "known receipt hid the terminal command-connection recovery notice") {
                !ackModel.busy && ackModel.feedbackNotice?.text.key == "hades2.error.commandResultConnectionLost"
            }
            check(ackModel.noticeText.key == "hades2.receipt.\(outcome)",
                  "ACK failure relabeled or erased a known action outcome")
            check(ackModel.feedbackNotice?.tone == .warning && !ackModel.connected
                    && ackModel.status == "restart_required" && !ackModel.canOpenSellTraits,
                  "ACK failure kept mutation controls or omitted terminal connection state")
            check(ackModel.currentIssues.contains { $0.id == "result" && $0.text == ackModel.noticeText },
                  "recovery details omitted the known operation receipt")
            check(ackModel.currentIssues.contains { $0.id == "recovery" },
                  "recovery details omitted the game restart requirement")
            check(ackModel.currentIssues.contains { $0.text.key == "hades2.error.commandResultConnectionLost" },
                  "recovery details replaced acceptance failure with action failure")
            let feedback = ackModel.feedbackNotice!
            let rendered = localization.string(feedback.text)
            check(rendered.contains("result was received") && rendered.contains("Restart the game and the trainer")
                    && rendered.contains("do not repeat"),
                  "ACK recovery guidance implied a retry or an unknown action: \(rendered)")
            ackModel.showFeedbackDetails(for: feedback.id)
            check(ackModel.feedbackDetailsPresented, "ACK recovery details were not reachable")
            ackModel.dismissFeedback(feedback.id)
            check(ackModel.currentIssues.contains { $0.id == "result" }
                    && ackModel.status == "restart_required",
                  "dismissing ACK feedback erased the result or recovery evidence")
            ackSession.stop(suppressTerminationError: true)
        }
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
    for language in ("en", "zh-CN"):
        destination = td / f"{language}.lproj"
        destination.mkdir()
        shutil.copy2(ROOT / "Resources/Localization" / f"{language}.lproj/Host.strings",
                     destination / "Host.strings")
    main.write_text(textwrap.dedent(harness))
    stub.write_text(textwrap.dedent(worker.replace("__MGT_MODULE_PROTOCOL__", str(json.loads((ROOT / "Backend/games/hades2/module.json").read_text())["protocolVersion"]))))
    generated = td / "ActiveGame.generated.swift"
    subprocess.run([PYTHON, str(ROOT / "Tools/generate_game_binding.py"), "hades2", str(generated)], check=True)
    sources = sorted((ROOT / "Sources/Core").rglob("*.swift")) + sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
    subprocess.run([SWIFTC, "-parse-as-library", "-whole-module-optimization", *map(str, sources),
                    str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
                    str(ROOT / "tests/fixtures/swift/NativeAccessibility.swift"),
                    str(generated), str(main), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home))
    subprocess.run([str(binary), PYTHON, str(stub)], check=True, cwd=ROOT, env=env, timeout=45)
    interaction_directory = td / "interactions"
    interaction_directory.mkdir()
    interaction_worker = interaction_directory / "worker.py"
    shutil.copy2(stub, interaction_worker)
    run_with_restored_pointer([str(binary), PYTHON, str(interaction_worker), "interactions"],
                              check=True, cwd=ROOT, env=env, timeout=30)
