"""Exercise automatic-backup policy/protection through real native controls.

The synthetic app talks to the real Core JSONL router and Save service, using
only a temporary save tree. This proves controls and transaction observations,
not a rendered-layout or real-game acceptance result.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if sys.platform != "darwin":
    raise SystemExit("macOS-only native Save retention controls")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

WORKER = r'''
import argparse, json, pathlib, sys, time
sys.path.insert(0, BACKEND_PATH)
from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.protocol import JsonlRequestRouter
from core.save_resolution import ResolvedSaveFile

p = argparse.ArgumentParser(); p.add_argument('--game', required=True); args = p.parse_args()
folder = pathlib.Path(__file__).parent.resolve()
saves = folder / 'saves'; saves.mkdir()
(saves / 'Profile1.sav').write_bytes(b'original temporary fixture')
replacement = folder / 'replacement.sav'; replacement.write_bytes(b'edited temporary fixture')

class FixtureAdapter(GameAdapter):
    def dispatch(self, command, params, request_id):
        if command == 'fixture.interrupted_restore':
            claim = self.save_service.store.ensure_storage_root() / '.staged-restore-applying-invalid.json'
            claim.write_text('{interrupted', encoding='utf-8')
        else:
            assert command == 'fixture.observe_policy'
            self.save_service.configure_retention(9, 8 * 1024 * 1024)
        return {}
    def close(self):
        pass

spec = SaveManagementSpec((SaveRootSpec('main', str(saves), ('*.sav',)),), None,
                          True, 'stoppedOnly', True)
adapter = FixtureAdapter(GameAdapterContext(args.game, 'Fixture', 1, folder, {}, save_management=spec))
router = JsonlRequestRouter(adapter, save_data_root=folder / 'data', target_running_probe=lambda: False)
router.save_service.replace_files((ResolvedSaveFile('main', 'Profile1.sav', replacement),))
for raw in sys.stdin:
    request = json.loads(raw)
    with (folder / 'commands.jsonl').open('a') as log:
        log.write(json.dumps(request) + '\n')
    reply = router.handle_encoded(request)
    if request['command'] in ('core.save.set_retention', 'core.save.protect'):
        time.sleep(0.25)  # Prove the sheet waits for the actual acknowledgement.
    print(reply, flush=True)
'''

HARNESS = r'''
import AppKit
import SwiftUI

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fputs(message + "\n", stderr); exit(1) }
}
func pump(_ seconds: TimeInterval = 0.08) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}
func wait(_ description: String, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(8)
    while !condition() && Date() < deadline { pump(0.01) }
    check(condition(), description)
}
func fields(in view: NSView) -> [NSTextField] {
    if let field = view as? NSTextField { return [field] }
    return view.subviews.flatMap(fields)
}
func edit(_ field: NSTextField, in window: NSWindow, text: String, submit: Bool) {
    check(window.makeFirstResponder(field), "could not focus \(field.placeholderString ?? "field")")
    guard let editor = field.currentEditor() as? NSTextView else { check(false, "missing actual field editor"); return }
    editor.selectAll(nil)
    editor.insertText(text, replacementRange: editor.selectedRange())
    if submit { editor.doCommand(by: #selector(NSResponder.insertNewline(_:))) }
    pump()
}
func requests(_ command: String, log: URL) -> [[String: Any]] {
    let data = (try? String(contentsOf: log, encoding: .utf8)) ?? ""
    return data.split(separator: "\n").compactMap {
        (try? JSONSerialization.jsonObject(with: Data($0.utf8))) as? [String: Any]
    }.filter { $0["command"] as? String == command }
}
func press(_ root: Any, title: String) {
    guard let control = namedNativeControl(root, role: "AXButton", name: title) else {
        print(nativeAccessibilityControls(root).map { "\($0.role ?? "?") | \($0.label ?? "") | \($0.text ?? "")" }.joined(separator: "\n"))
        check(false, "missing actual button \(title)"); return
    }
    check(control.enabled && control.press(), "actual button did not press: \(title)")
    pump()
}
func hasText(_ root: Any, _ text: String) -> Bool {
    nativeAccessibilityControls(root).contains { $0.role == "AXStaticText" && $0.text == text }
}

@main
struct Main {
    @MainActor
    static func main() throws {
        let args = CommandLine.arguments
        check(args.count == 3, "expected python and worker")
        _ = NSApplication.shared
        enableNativeAccessibility()
        let session = TrainerBackendSession(client: BackendClient(process: BackendProcess(
            executableURL: URL(fileURLWithPath: args[1]), argumentsPrefix: ["-u"], forceKillDelay: 0.1)))
        let descriptor = GameModuleDescriptor(id: "fixture", displayName: "Fixture", backendGameID: "fixture",
            targetProcessName: "", targetBundleIdentifier: "", expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 1, supportsSaveManagement: true)
        try session.start(descriptor: descriptor, backendScriptURL: URL(fileURLWithPath: args[2]),
                          applyPayload: { _ in }, resetGameState: {}, log: { _ in }, onStatusChange: { _ in })
        defer { session.stop(suppressTerminationError: true) }
        let model = TrainerSaveManagerModel(session: session)
        model.refresh()
        wait("initial real Save state did not arrive") { !model.busy && model.snapshots.count == 1 }
        check(model.error.isEmpty && model.storageUsage?.automaticCount == 1, "fixture backup was not automatic")
        let log = URL(fileURLWithPath: args[2]).deletingLastPathComponent().appendingPathComponent("commands.jsonl")
        let localization = TrainerLocalizationStore(defaults: InMemoryDefaults())
        localization.language = .en
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 830, height: 1000),
                              styleMask: [.titled], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        let host = NSHostingView(rootView: TrainerSaveManagerView(model: model)
            .environmentObject(localization).trainerTheme(.standard))
        window.contentView = host
        window.orderFront(nil)
        pump()
        host.layoutSubtreeIfNeeded()
        press(host, title: localization.localized("host.save.retention.title"))
        wait("Automatic Backups did not open its native sheet") { window.attachedSheet != nil }
        let sheet = window.attachedSheet!
        let sheetContent = sheet.contentView!
        wait("retention sheet did not mount both native number fields") { fields(in: sheetContent).filter { $0.isEditable }.count == 2 }
        let count = fields(in: sheetContent).first { $0.placeholderString == localization.localized("host.save.retention.count") }!
        let bytes = fields(in: sheetContent).first { $0.placeholderString == localization.localized("host.save.retention.bytes") }!
        check(count.stringValue == "20" && bytes.stringValue == "256", "initial policy did not render")
        edit(count, in: sheet, text: "0", submit: true)
        let saveTitle = localization.localized("host.save.retention.save")
        check(namedNativeControl(sheetContent, role: "AXButton", name: saveTitle)?.enabled == false,
              "invalid count left the actual Save Policy button enabled")
        check(requests("core.save.set_retention", log: log).isEmpty, "Return unexpectedly saved invalid policy")
        edit(count, in: sheet, text: "3", submit: true)
        check(count.currentEditor() == nil && count.stringValue == "3", "Return did not commit the native count field")
        edit(bytes, in: sheet, text: "2", submit: false)
        sheet.makeFirstResponder(nil)
        pump()
        check(bytes.currentEditor() == nil && bytes.stringValue == "2", "blur did not commit native byte budget")
        check(requests("core.save.set_retention", log: log).isEmpty, "editing policy dispatched before Save")

        // A real backend observation changes both values while one input owns a draft.
        edit(count, in: sheet, text: "4", submit: false)
        var observationDone = false
        session.send("fixture.observe_policy", operation: "fixture observation", announceSuccess: false,
                     completion: { observationDone = $0 })
        wait("background policy observation did not finish") { observationDone }
        model.refresh()
        wait("Save state refresh did not finish") { !model.busy && model.retention?.maxCount == 9 }
        pump()
        check((count.currentEditor() as? NSTextView)?.string == "4" && count.stringValue == "4",
              "background observation replaced the focused native draft")
        check(bytes.stringValue == "8", "unfocused native value did not refresh from observation")
        check(requests("core.save.set_retention", log: log).isEmpty, "background observation committed the draft")
        press(sheetContent, title: saveTitle)
        check(model.busy && window.attachedSheet != nil, "Save sheet closed before the backend acknowledgement")
        wait("Save acknowledgement did not close the sheet") { !model.busy && window.attachedSheet == nil }
        check(model.retention?.maxCount == 4 && model.retention?.maxBytes == 8 * 1024 * 1024,
              "actual Save button did not commit focused draft and refreshed byte budget")
        let commits = requests("core.save.set_retention", log: log)
        let params = commits.last?["params"] as? [String: Any]
        check(commits.count == 1 && params?["maxCount"] as? Int == 4 && params?["maxBytes"] as? Int == 8 * 1024 * 1024,
              "native Save dispatched unexpected policy values")
        wait("acknowledged policy feedback was not presented") {
            hasText(host, localization.localized("host.save.notice.retentionSaved"))
        }

        // Exercise the actual popup and NSMenuItem target/action. The timer
        // selects its item inside AppKit's native tracking run loop.
        func popups(_ view: NSView) -> [NSPopUpButton] {
            if let popup = view as? NSPopUpButton { return [popup] }
            return view.subviews.flatMap(popups)
        }
        func selectBackupAction(_ title: String) {
            check(nativeAccessibilityControls(host).contains {
                $0.role == "AXMenuButton" && $0.help == localization.localized("host.more") && $0.enabled
            }, "missing enabled actual backup overflow control")
            guard let popup = popups(host).first, let menu = popup.menu else {
                check(false, "missing actual backup overflow popup"); return
            }
            var selected = false
            let choose: @MainActor () -> Void = {
                guard let index = menu.items.firstIndex(where: { $0.title == title }) else {
                    check(false, "missing actual menu item \(title)"); return
                }
                check(menu.items[index].isEnabled, "actual menu item was disabled: \(title)")
                menu.performActionForItem(at: index)
                selected = true
                menu.cancelTrackingWithoutAnimation()
            }
            let timer = Timer(timeInterval: 0.15, repeats: false) { _ in
                MainActor.assumeIsolated { choose() }
            }
            RunLoop.main.add(timer, forMode: .common)
            RunLoop.main.add(timer, forMode: .eventTracking)
            popup.performClick(nil)
            wait("actual menu item was not selected: \(title)") { selected }
        }
        selectBackupAction(localization.localized("host.save.keepBackup"))
        wait("protection acknowledgement did not refresh") { !model.busy && model.snapshots.first?.protected == true }
        check(model.storageUsage?.automaticCount == 0 && model.storageUsage?.protectedCount == 1,
              "protection did not refresh automatic/protected usage")
        check(requests("core.save.protect", log: log).count == 1,
              "actual protection menu did not dispatch once")
        wait("protection feedback was not presented") {
            hasText(host, localization.localized("host.save.notice.protectionSaved"))
        }
        let usage = model.storageUsage!
        let usageText = localization.localized("host.save.usage.automatic", arguments: ["0",
            ByteCountFormatter.string(fromByteCount: 0, countStyle: .binary), "1",
            ByteCountFormatter.string(fromByteCount: Int64(usage.protectedBytes), countStyle: .binary)])
        check(hasText(host, usageText), "actual automatic/protected usage text did not refresh")
        selectBackupAction(localization.localized("host.save.allowAutomaticCleanup"))
        wait("return-to-cleanup acknowledgement did not refresh") {
            !model.busy && model.snapshots.first?.protected == false
        }
        check(model.storageUsage?.automaticCount == 1 && model.storageUsage?.protectedCount == 0,
              "allowing cleanup did not restore automatic pool usage")
        let protectionRequests = requests("core.save.protect", log: log)
        let protectionParams = protectionRequests.compactMap { $0["params"] as? [String: Any] }
        check(protectionParams.count == 2 && protectionParams[0]["protected"] as? Bool == true &&
              protectionParams[1]["protected"] as? Bool == false,
              "native protection actions did not dispatch their explicit intent")

        var interrupted = false
        session.send("fixture.interrupted_restore", operation: "fixture interruption", announceSuccess: false,
                     completion: { interrupted = $0 })
        wait("interrupted restore fixture did not complete") { interrupted }
        model.refresh()
        wait("malformed restore claim hid the complete inventory") {
            !model.busy && model.pendingRestore?.indeterminate == true && !model.snapshots.isEmpty
        }
        check(model.pendingRestore?.snapshotID == nil && model.error.isEmpty,
              "unavailable restore intent was required to display recovery state")
        press(host, title: localization.localized("host.clearStatus"))
        wait("actual Clear status did not clear the unresolved claim") {
            !model.busy && model.pendingRestore == nil
        }
        check(requests("core.save.cancel_staged", log: log).count == 1,
              "recovery button did not send the explicit cancellation once")
        window.close()
        print("core_save_retention_controls_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-retention-controls-") as temporary:
    directory = Path(temporary)
    worker = directory / "worker.py"
    worker.write_text("BACKEND_PATH = " + repr(str(ROOT / "Backend")) + "\n" + WORKER)
    harness = directory / "main.swift"
    harness.write_text(HARNESS)
    binary = directory / "retention_controls"
    for language in ("en", "zh-CN"):
        localized = directory / f"{language}.lproj"
        localized.mkdir()
        shutil.copy2(ROOT / f"Resources/Localization/{language}.lproj/Host.strings", localized / "Host.strings")
    subprocess.run([SWIFTC, "-parse-as-library", *map(str, sorted((ROOT / "Sources/Core").rglob("*.swift"))),
                    str(ROOT / "tests/fixtures/swift/InMemoryDefaults.swift"),
                    str(ROOT / "tests/fixtures/swift/NativeAccessibility.swift"), str(harness), "-o", str(binary)],
                   cwd=ROOT, check=True)
    (directory / "home").mkdir()
    environment = dict(os.environ, HOME=str(directory / "home"))
    subprocess.run([str(binary), sys.executable, str(worker)], cwd=ROOT, env=environment, check=True, timeout=45)
