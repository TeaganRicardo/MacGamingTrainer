"""Native tool-window reuse and close ownership with isolated content."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != "darwin":
    raise SystemExit("macOS-only native tool-window test")
ROOT = Path(__file__).resolve().parents[1]
SWIFT = shutil.which("swiftc")
assert SWIFT

HARNESS = r'''
import AppKit
import SwiftUI

@MainActor final class DocumentDraft: ObservableObject {
    @Published var text = "first draft"
    let source = UUID()
}

struct DraftView: View {
    @ObservedObject var draft: DocumentDraft
    var body: some View {
        TextField("Document draft", text: $draft.text)
            .frame(width: 400).padding(25)
    }
}

@MainActor func pump(_ duration: TimeInterval = 0.06) {
    let deadline = Date().addingTimeInterval(duration)
    while Date() < deadline {
        if let event = NSApp.nextEvent(matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default, dequeue: true) { NSApp.sendEvent(event) }
        NSApp.updateWindows()
    }
}

@MainActor func wait(_ message: String, onFailure: () -> Void = {}, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(4)
    repeat {
        if condition() { return }
        pump(0.02)
    } while Date() < deadline
    onFailure()
    fatalError(message)
}

@MainActor final class WindowLifecycleTrace {
    private var events: [[String: Any]] = []
    private var observers: [NSObjectProtocol] = []
    private let began = ProcessInfo.processInfo.systemUptime

    init(window: NSWindow) {
        for name in [NSWindow.willMiniaturizeNotification, NSWindow.didMiniaturizeNotification,
                     NSWindow.didDeminiaturizeNotification, NSWindow.didBecomeKeyNotification,
                     NSWindow.didResignKeyNotification] {
            observers.append(NotificationCenter.default.addObserver(forName: name, object: window, queue: .main) {
                [weak self, weak window] notification in
                let phase = notification.name.rawValue
                MainActor.assumeIsolated {
                    if let window { self?.record(phase, window: window) }
                }
            })
        }
    }

    func record(_ phase: String, window: NSWindow) {
        guard events.count < 24 else { return }
        events.append(["phase": phase, "elapsed": ProcessInfo.processInfo.systemUptime - began,
                       "miniaturized": window.isMiniaturized, "visible": window.isVisible,
                       "key": window.isKeyWindow, "active": NSApp.isActive])
    }

    func dump(_ phase: String, window: NSWindow, field: NSTextField, editor: NSTextView,
              originalContent: NSView?, draft: DocumentDraft, source: UUID, factories: Int) {
        let currentEditor = field.currentEditor()
        let snapshot: [String: Any] = [
            "phase": phase, "miniaturized": window.isMiniaturized, "visible": window.isVisible,
            "key": window.isKeyWindow, "main": window.isMainWindow,
            "active": NSApp.isActive, "running": NSApp.isRunning,
            "appKeyWindow": NSApp.keyWindow?.windowNumber ?? -1,
            "window": window.windowNumber, "canBecomeKey": window.canBecomeKey,
            "sameContent": window.contentView === originalContent,
            "sameResponder": window.firstResponder === editor,
            "currentEditorIsOriginal": currentEditor === editor,
            "currentEditorIdentity": currentEditor.map { String(describing: ObjectIdentifier($0)) } ?? "<none>",
            "responder": String(describing: window.firstResponder),
            "editorText": currentEditor?.string ?? "<none>", "draft": draft.text,
            "sameSource": draft.source == source, "factories": factories,
            "events": events]
        let data = try! JSONSerialization.data(withJSONObject: snapshot, options: [.sortedKeys])
        FileHandle.standardError.write(Data("tool_window_restore_failure=".utf8) + data + Data("\n".utf8))
    }

    func stop() {
        observers.forEach { NotificationCenter.default.removeObserver($0) }
        observers.removeAll()
    }
}

func fields(_ view: NSView) -> [NSTextField] {
    (view as? NSTextField).map { [$0] } ?? view.subviews.flatMap(fields)
}

@main
struct Main {
    @MainActor static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        app.finishLaunching()
        Timer.scheduledTimer(withTimeInterval: 0.01, repeats: false) { _ in
            MainActor.assumeIsolated {
                exercise()
                app.stop(nil)
                app.postEvent(NSEvent.otherEvent(with: .applicationDefined, location: .zero,
                    modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                    windowNumber: 0, context: nil, subtype: 0, data1: 0, data2: 0)!, atStart: false)
            }
        }
        app.run()
    }

    @MainActor static func exercise() {
        precondition(NSApp.isRunning, "tool-window fixture did not enter the AppKit application loop")
        let host = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 240),
                            styleMask: [.titled, .closable], backing: .buffered, defer: false)
        host.isReleasedWhenClosed = false
        host.title = "Tool-window fixture Host"
        host.center()
        defer { host.close() }
        @MainActor func activateHost(before operation: String) {
            // In the product, the user opens a tool from the active Host.
            // Keep that independent native window present while a tool is minimized.
            host.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            wait("fixture Host did not become active/key before " + operation, onFailure: {
                FileHandle.standardError.write(Data(("tool_window_fixture_activation_failure "
                    + "operation=\(operation) running=\(NSApp.isRunning) active=\(NSApp.isActive) "
                    + "visible=\(host.isVisible) key=\(host.isKeyWindow)\n").utf8))
            }) {
                NSApp.isRunning && NSApp.isActive && host.isVisible && host.isKeyWindow
            }
        }
        activateHost(before: "initial open")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        let store = TrainerToolWindowStore()
        let draft = DocumentDraft()
        let source = draft.source
        var factories = 0
        var closed: [String] = []
        var allowFirstClose = false
        let first = store.open(id: "first", title: "First", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(canClose: { allowFirstClose }, onClose: { closed.append("first") }) {
                DraftView(draft: draft)
            }
        }
        pump(0.2)
        wait("initial tool did not become the active key window") {
            NSApp.isActive && first.isVisible && first.isKeyWindow
        }
        let originalContent = first.contentView
        let field = fields(originalContent!).first { $0.isEditable }!
        precondition(first.makeFirstResponder(field), "tool draft refused native focus")
        let editor = field.currentEditor() as! NSTextView
        editor.selectAll(nil)
        editor.insertText("retained document draft", replacementRange: editor.selectedRange())
        wait("native tool typing did not update its owner") { draft.text == "retained document draft" }
        let reused = store.open(id: "first", title: "First", localization: localization, theme: .standard) {
            fatalError("Reopening an existing entry recreated its document")
        }
        precondition(first === reused && first.contentView === originalContent)
        precondition(first.firstResponder === editor && draft.source == source
                     && field.stringValue == "retained document draft",
                     "raising an existing tool replaced its focused draft or document source")
        let trace = WindowLifecycleTrace(window: first)
        defer { trace.stop() }
        @MainActor func restorationFailure(_ phase: String) {
            trace.dump(phase, window: first, field: field, editor: editor, originalContent: originalContent,
                       draft: draft, source: source, factories: factories)
        }
        trace.record("before miniaturize", window: first)
        first.miniaturize(nil)
        wait("native tool did not minimize", onFailure: { restorationFailure("minimize") }) { first.isMiniaturized }
        // Restore through an active Host action. The Store must itself make
        // the retained tool key; the fixture never raises it after open returns.
        activateHost(before: "minimized tool reopen")
        precondition(first.isMiniaturized, "Host activation restored the tool before Store.open")
        trace.record("before reopen", window: first)
        let restored = store.open(id: "first", title: "Restored", localization: localization, theme: .standard) {
            fatalError("Restoring a minimized tool reread its document")
        }
        trace.record("reopen returned", window: first)
        wait("reopening a minimized tool did not restore its native window", onFailure: { restorationFailure("reopen") }) {
            !first.isMiniaturized && first.isVisible && first.isKeyWindow
        }
        precondition(restored === first && first.contentView === originalContent
                     && first.firstResponder === editor && draft.text == "retained document draft"
                     && draft.source == source && factories == 1,
                     "native window restoration discarded its source, focus or draft")
        let second = store.open(id: "second", title: "Second", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(onClose: { closed.append("second") }) {
                Text("second draft").frame(width: 400, height: 250)
            }
        }
        precondition(first !== second && factories == 2)
        precondition(first.sheetParent == nil && second.sheetParent == nil)
        precondition(first.isVisible && second.isVisible)
        precondition(!store.canCloseAll, "a pending tool allowed application termination")
        store.setInteractionEnabled(false)
        pump()
        precondition(!field.isEnabled && draft.text == "retained document draft" && closed.isEmpty,
                     "termination gating changed a draft, allowed editing or closed its owner")
        store.setInteractionEnabled(true)
        pump()
        precondition(field.isEnabled && first.contentView === originalContent,
                     "cancelled termination did not restore the same tool")
        first.performClose(nil)
        precondition(first.isVisible && closed.isEmpty, "busy tools must retain their native window")
        allowFirstClose = true
        precondition(store.canCloseAll, "completed tools did not release termination guard")
        first.performClose(nil)
        precondition(closed == ["first"] && second.isVisible, "closing one tool closed another tool")
        let reopened = store.open(id: "first", title: "Fresh", localization: localization, theme: .standard) {
            factories += 1
            return TrainerToolWindowContent(onClose: { closed.append("fresh") }) {
                Text("fresh document").frame(width: 450, height: 300)
            }
        }
        precondition(reopened !== first && factories == 3, "a closed entry retained its prior document")
        second.performClose(nil)
        reopened.performClose(nil)
        precondition(closed == ["first", "second", "fresh"])
        print("trainer_tool_windows_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-tool-windows-") as directory:
    root = Path(directory)
    main = root / "main.swift"
    main.write_text(HARNESS)
    binary = root / "windows"
    sources = ["Sources/Core/Runtime/TrainerJSON.swift", "Sources/Core/Runtime/BackendProcess.swift", "Sources/Core/Runtime/BackendClient.swift",
               "Sources/Core/Host/TrainerLocalization.swift", "Sources/Core/UI/TrainerTheme.swift",
               "Sources/Core/UI/TrainerToolWindows.swift", "tests/fixtures/swift/InMemoryDefaults.swift"]
    subprocess.run([SWIFT, "-parse-as-library", *[str(ROOT / path) for path in sources],
                    str(main), "-o", str(binary)], check=True)
    env = dict(os.environ, HOME=str(root / "home"))
    (root / "home").mkdir()
    result = subprocess.run([str(binary)], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "trainer_tool_windows_ok" in result.stdout
    print(result.stdout.strip())
