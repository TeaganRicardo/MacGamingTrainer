MGT_PLATFORM = "macos"

from macos_fixture_policy import launch_fixture
from fixture_budgets.core_save import JOURNEY_BUDGETS
from swift_test_compiler import compile_swift_test
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
from core.save_resolution import ResolvedSaveFile, DefaultSaveProvider, SaveProviderContext

p = argparse.ArgumentParser(); p.add_argument('--game', required=True); args = p.parse_args()
folder = pathlib.Path(__file__).parent.resolve()
saves = folder / 'saves'; saves.mkdir()
(saves / 'Profile1.sav').write_bytes(b'original temporary fixture')
replacement = folder / 'replacement.sav'; replacement.write_bytes(b'edited temporary fixture')

running = [False]


class Provider(DefaultSaveProvider):
    def describe_snapshot(self, files, created_at):
        return {
            'defaultName': '自动快照',
            'nameDetails': ['默认详情'],
            'localizedPresentation': {
                'en': {'name': 'Auto Snapshot', 'details': ['Localized detail']},
            },
        }


class FixtureAdapter(GameAdapter):
    def dispatch(self, command, params, request_id):
        if command == 'fixture.interrupted_restore':
            claim = self.save_service.store.ensure_storage_root() / '.staged-restore-applying-invalid.json'
            claim.write_text('{interrupted', encoding='utf-8')
        elif command == 'fixture.set_running':
            running[0] = bool(params.get('running', False))
        elif command == 'fixture.seed_recovery':
            recovery_dir = self.save_service.store.ensure_storage_root() / 'transactions' / '.rollback-fixture'
            recovery_dir.mkdir(parents=True, exist_ok=True)
            (recovery_dir / 'save.bak').write_bytes(b'recovery')
        else:
            assert command == 'fixture.observe_policy'
            self.save_service.configure_retention(9, 8 * 1024 * 1024)
        return {}
    def close(self):
        pass

spec = SaveManagementSpec((SaveRootSpec('main', str(saves), ('*.sav',)),), None,
                          True, 'stoppedOnly', True)
adapter = FixtureAdapter(GameAdapterContext(args.game, 'Fixture', 1, folder, {}, save_management=spec))
data_root = pathlib.Path.home() / 'Library/Application Support/MacGamingTrainer'
router = JsonlRequestRouter(adapter, save_data_root=data_root, target_running_probe=lambda: running[0])
router.save_service.provider = Provider(SaveProviderContext(folder))
router.save_service.replace_files((ResolvedSaveFile('main', 'Profile1.sav', replacement),))
for raw in sys.stdin:
    request = json.loads(raw)
    with (folder / 'commands.jsonl').open('a') as log:
        log.write(json.dumps(request) + '\n')
    reply = router.handle_encoded(request)
    if request['command'] in ('core.save.set_retention', 'core.save.protect', 'core.save.rename'):
        time.sleep(0.35 if request['command'] == 'core.save.rename' else 0.25)  # Prove UI waits / renders optimistic rename before reply.
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
func hostRect(_ control: NativeAccessibilityControl, in host: NSView, window: NSWindow) -> NSRect {
    host.convert(window.convertFromScreen(control.frame), from: nil)
}

final class HostSaveStubModel: ObservableObject, TrainerHostModel {
    let connected = false
    let statusTitle = TrainerTextToken(key: "host.disconnected")
    let connectionDetailText = TrainerTextToken(key: "host.gameLibrary")
    let hostActionsEnabled = false
    func connectFromHost(reason: TrainerHostConnectReason) {}
    func disconnectFromHost() {}
    func refreshFromHost() {}
    func backendPayloadTarget(_ payload: [String: Any]) -> TrainerBackendPayloadTarget { .independent }
    func prepareForTermination(completion: @escaping () -> Void) { completion() }
}

private struct ManagementProbeView: View {
    @Environment(\.trainerManagementActions) private var managementActions
    let onCapture: (TrainerManagementActions) -> Void

    var body: some View {
        Color.clear
            .frame(width: 1, height: 1)
            .onAppear { onCapture(managementActions) }
    }
}

enum HostSaveProbeBridge {
    nonisolated(unsafe) static var captured: TrainerManagementActions?
}

struct HostUnsupportedSaveModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "host-no-save", displayName: "Host No Save",
        targetProcessName: "MGTNoSuchTarget", targetBundleIdentifier: "",
        expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 1,
        supportsSaveManagement: false
    )
    static let presentation = TrainerGamePresentation()
    static func makeModel(services: TrainerModuleServices) -> HostSaveStubModel { HostSaveStubModel() }
    static func makeContent(model: HostSaveStubModel) -> some View {
        ManagementProbeView { HostSaveProbeBridge.captured = $0 }
    }
    static func makeSidebarActions(model: HostSaveStubModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: HostSaveStubModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: HostSaveStubModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static let presentationKeyPrefix = "hostNoSaveFixture."
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
}

struct HostSupportedSaveModule: TrainerGameModule {
    static let descriptor = GameModuleDescriptor(
        id: "host-save", displayName: "Host Save",
        targetProcessName: "MGTNoSuchTarget", targetBundleIdentifier: "",
        expectedHostProtocolVersion: 6, expectedModuleProtocolVersion: 1,
        supportsSaveManagement: true
    )
    static let presentation = TrainerGamePresentation()
    static func makeModel(services: TrainerModuleServices) -> HostSaveStubModel { HostSaveStubModel() }
    static func makeContent(model: HostSaveStubModel) -> some View {
        ManagementProbeView { HostSaveProbeBridge.captured = $0 }
    }
    static func makeSidebarActions(model: HostSaveStubModel) -> EmptyView { EmptyView() }
    static func makeHeaderActions(model: HostSaveStubModel) -> EmptyView { EmptyView() }
    static func makeManagementCommands(model: HostSaveStubModel, localization: TrainerLocalizationStore) -> TrainerEmptyCommands {
        TrainerEmptyCommands()
    }
    static let presentationKeyPrefix = "hostSaveFixture."
    static func presentationText(key: String, arguments: [String], language: TrainerPresentationLanguage) -> String { key }
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
        let descriptor = GameModuleDescriptor(id: "fixture", displayName: "Fixture",
            targetProcessName: "", targetBundleIdentifier: "", expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 1, supportsSaveManagement: true)
        try session.start(descriptor: descriptor, backendScriptURL: URL(fileURLWithPath: args[2]),
                          applyPayload: { _ in }, resetGameState: {}, log: { _ in })
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
        check(hasText(host, localization.localized("host.save.pendingIndeterminate")),
              "indeterminate pending restore text missing")
        press(host, title: localization.localized("host.clearStatus"))
        wait("actual Clear status did not clear the unresolved claim") {
            !model.busy && model.pendingRestore == nil
        }
        check(requests("core.save.cancel_staged", log: log).count == 1,
              "recovery button did not send the explicit cancellation once")

        // History section, localized snapshot presentation, and header/footer button order.
        check(hasText(host, localization.localized("host.save.history")), "Backup History section title missing")
        check(hasText(host, "Auto Snapshot"), "English localized automatic snapshot name missing")
        check(hasText(host, "Localized detail"), "English localized snapshot detail missing")
        check(hasText(host, localization.localized("host.save.fileCount", arguments: ["1"])),
              "snapshot file count missing")

        let refreshBtn = namedNativeControl(host, role: "AXButton", name: localization.localized("host.refresh"))
        let createBackupBtn = namedNativeControl(host, role: "AXButton", name: localization.localized("host.save.createBackup"))
        let openFolderBtn = namedNativeControl(host, role: "AXButton", name: localization.localized("host.save.openFolder"))
        let doneBtn = namedNativeControl(host, role: "AXButton", name: localization.localized("host.done"))
        check(refreshBtn?.enabled == true && createBackupBtn?.enabled == true &&
              openFolderBtn?.enabled == true && doneBtn?.enabled == true,
              "Save Manager header/footer buttons missing or disabled")
        let refreshRect = hostRect(refreshBtn!, in: host, window: window)
        let createBackupRect = hostRect(createBackupBtn!, in: host, window: window)
        let doneRect = hostRect(doneBtn!, in: host, window: window)
        check(refreshRect.maxX <= createBackupRect.minX,
              "Refresh button was not ordered before Create Backup in header")
        check(doneRect.minY > createBackupRect.maxY,
              "Done button was not positioned in footer below header")

        // Overflow menu items + inline rename with optimistic pendingRenameNames.
        do {
            guard let popup = popups(host).first, let menu = popup.menu else {
                check(false, "missing backup overflow menu"); return
            }
            for itemTitle in [
                localization.localized("host.rename"),
                localization.localized("host.showInFinder"),
                localization.localized("host.delete"),
            ] {
                guard let item = menu.items.first(where: { $0.title == itemTitle }), item.isEnabled else {
                    check(false, "overflow menu missing enabled item: \(itemTitle)"); return
                }
            }
        }
        selectBackupAction(localization.localized("host.rename"))
        wait("inline rename editor did not mount") { fields(in: host).contains { $0.isEditable } }
        let renameField = fields(in: host).first { $0.isEditable }!
        edit(renameField, in: window, text: "Renamed Backup", submit: true)
        check(model.busy, "rename completed before optimistic display check")
        check(hasText(host, "Renamed Backup"),
              "optimistic rename name did not render while rename request was in flight")
        wait("rename did not finish") { !model.busy }
        let renameRequests = requests("core.save.rename", log: log)
        check(renameRequests.count == 1 && (renameRequests.last?["params"] as? [String: Any])?["name"] as? String == "Renamed Backup",
              "inline rename did not dispatch expected name")
        check(hasText(host, "Renamed Backup"), "renamed snapshot name missing after reply")
        check(hasText(host, localization.localized("host.save.notice.renamed")),
              "rename confirmation notice missing")

        // Bulk selection control and Delete Selected bar.
        press(host, title: localization.localized("host.selection.select"))
        wait("bulk selection bar did not render") {
            hasText(host, localization.localized("host.selectedCount", arguments: ["1"]))
        }
        check(namedNativeControl(host, role: "AXButton", name: localization.localized("host.deleteSelected"))?.enabled == true,
              "Delete Selected action missing or disabled")
        press(host, title: localization.localized("host.selection.deselect"))
        wait("bulk selection bar did not dismiss") {
            namedNativeControl(host, role: "AXButton", name: localization.localized("host.deleteSelected")) == nil
        }

        // Hot backup badge, Restore confirmation sheet, and non-indeterminate staged pending banner.
        var setRunningDone = false
        session.send("fixture.set_running", params: ["running": true], operation: "set running", announceSuccess: false,
                     completion: { setRunningDone = $0 })
        wait("fixture.set_running(true) did not complete") { setRunningDone }
        let backupBefore = requests("core.save.backup", log: log).count
        press(host, title: localization.localized("host.save.createBackup"))
        wait("Create Backup did not add hot snapshot") { !model.busy && model.snapshots.count == 2 }
        check(requests("core.save.backup", log: log).count == backupBefore + 1,
              "Create Backup button did not dispatch backup command")
        check(hasText(host, localization.localized("host.save.hotBackup")),
              "Live Backup pill badge missing on hot snapshot")

        press(host, title: localization.localized("host.restore"))
        wait("Restore confirmation sheet did not open") { window.attachedSheet != nil }
        let restoreSheet = window.attachedSheet!
        let restoreSheetContent = restoreSheet.contentView!
        wait("Preserve Current checkbox did not mount in restore confirmation sheet") {
            namedNativeControl(restoreSheetContent, role: "AXCheckBox",
                             name: localization.localized("host.save.preserveCurrent")) != nil
        }
        press(restoreSheetContent, title: localization.localized("host.restore"))
        wait("Restore confirmation did not stage restore") {
            window.attachedSheet == nil && !model.busy &&
                model.pendingRestore != nil && model.pendingRestore?.indeterminate == false
        }
        let restoreRequests = requests("core.save.restore", log: log)
        check(restoreRequests.count == 1 && (restoreRequests.last?["params"] as? [String: Any])?["preserveCurrent"] as? Bool == true,
              "Restore confirmation did not dispatch preserveCurrent=true")
        check(namedNativeControl(host, role: "AXButton", name: localization.localized("host.cancel"))?.enabled == true,
              "Cancel button missing on non-indeterminate staged restore")
        check(hasText(host, localization.localized("host.save.pendingWaiting", arguments: ["Auto Snapshot"])),
              "staged pending waiting notice with snapshot name missing")
        press(host, title: localization.localized("host.cancel"))
        wait("Cancel did not clear staged restore") { !model.busy && model.pendingRestore == nil }
        var clearRunningDone = false
        session.send("fixture.set_running", params: ["running": false], operation: "clear running", announceSuccess: false,
                     completion: { clearRunningDone = $0 })
        wait("fixture.set_running(false) did not complete") { clearRunningDone }

        // Recovery paths warning banner + Save error banner.
        var seedRecoveryDone = false
        session.send("fixture.seed_recovery", operation: "seed recovery", announceSuccess: false,
                     completion: { seedRecoveryDone = $0 })
        wait("fixture.seed_recovery did not complete") { seedRecoveryDone }
        model.refresh()
        wait("recovery paths did not populate on refresh") { !model.busy && !model.recoveryPaths.isEmpty }
        check(hasText(host, localization.localized("host.save.recoveryCopiesWarning")),
              "recovery copies warning missing")
        check(hasText(host, model.recoveryPaths.joined(separator: "\n")),
              "recovery paths list missing")
        check(namedNativeControl(host, role: "AXButton", name: localization.localized("host.show"))?.enabled == true,
              "Show button missing or disabled for recovery copies")

        model.restore(id: "snap-20261107-000000-00000000", preserveCurrent: true)
        wait("missing snapshot restore did not surface error") {
            !model.busy && model.error == "host.save.error.notFound"
        }
        check(hasText(host, localization.presentation("host.save.error.notFound")),
              "error banner did not render localized Save error")

        model.delete(ids: Set(model.snapshots.map(\.id)))
        wait("batch delete notice did not render") {
            !model.busy && model.notice == "host.save.notice.deletedMany"
        }
        check(hasText(host, localization.presentation("host.save.notice.deletedMany", arguments: ["2"])),
              "notice banner did not render formatted noticeArguments")

        window.close()

        // TrainerHostView + TrainerHostSidebarCard Save Management wiring.
        let fixtureHome = log.deletingLastPathComponent()
        HostSaveProbeBridge.captured = nil
        let unsupportedContext = TrainerGameContext<HostUnsupportedSaveModule>(session: session,
            logSink: TrainerLogSink(gameID: HostUnsupportedSaveModule.descriptor.id, homeDirectory: fixtureHome))
        let unsupportedWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 820, height: 780),
            styleMask: [.titled], backing: .buffered, defer: false
        )
        unsupportedWindow.isReleasedWhenClosed = false
        let unsupportedHost = NSHostingView(
            rootView: TrainerHostView(context: unsupportedContext)
                .environmentObject(localization)
                .trainerTheme(.standard)
        )
        unsupportedWindow.contentView = unsupportedHost
        unsupportedWindow.orderFront(nil)
        wait("unsupported TrainerHostView did not mount management environment") {
            HostSaveProbeBridge.captured != nil
        }
        check(HostSaveProbeBridge.captured?.openSaveManagement == nil,
              "supportsSaveManagement=false exposed openSaveManagement")
        unsupportedWindow.close()

        HostSaveProbeBridge.captured = nil
        let supportedContext = TrainerGameContext<HostSupportedSaveModule>(session: session,
            logSink: TrainerLogSink(gameID: HostSupportedSaveModule.descriptor.id, homeDirectory: fixtureHome))
        let hostWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 820, height: 780),
            styleMask: [.titled], backing: .buffered, defer: false
        )
        hostWindow.isReleasedWhenClosed = false
        let supportedHost = NSHostingView(
            rootView: TrainerHostView(context: supportedContext)
                .environmentObject(localization)
                .trainerTheme(.standard)
        )
        hostWindow.contentView = supportedHost
        hostWindow.orderFront(nil)

        let sidebarWindow = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 280, height: 400),
            styleMask: [.titled], backing: .buffered, defer: false
        )
        sidebarWindow.isReleasedWhenClosed = false
        let sidebarHost = NSHostingView(
            rootView: TrainerHostSidebarCard(context: supportedContext, selected: true, onSelect: {})
                .environmentObject(localization)
                .trainerTheme(.standard)
        )
        sidebarWindow.contentView = sidebarHost
        sidebarWindow.orderFront(nil)
        pump()
        sidebarHost.layoutSubtreeIfNeeded()
        let saveMgmtTitle = localization.localized("host.saveManagement")
        check(!hasText(sidebarHost, saveMgmtTitle) &&
              namedNativeControl(sidebarHost, role: "AXButton", name: saveMgmtTitle) == nil,
              "Host sidebar unexpectedly presented Save Management")

        wait("supported TrainerHostView did not mount management environment") {
            HostSaveProbeBridge.captured?.openSaveManagement != nil
        }
        let listsBeforeOpen = requests("core.save.list", log: log).count
        HostSaveProbeBridge.captured?.openSaveManagement?()
        wait("Save Management tool window did not open and refresh") {
            requests("core.save.list", log: log).count == listsBeforeOpen + 1 &&
                !supportedContext.saveManager.busy &&
                NSApp.windows.contains(where: {
                    $0.title == saveMgmtTitle &&
                        $0.contentView.map { hasText($0, localization.localized("host.save.history")) } == true
                })
        }
        supportedContext.toolWindows.closeAll()
        pump()
        sidebarWindow.close()
        hostWindow.close()
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
    compile_swift_test(
        harness_sources=[
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
            harness,
        ],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    (directory / "home").mkdir()
    environment = dict(os.environ, HOME=str(directory / "home"))
    launch_fixture([str(binary), sys.executable, str(worker)], cwd=ROOT, env=environment, check=True, journey='native.core_save_retention_controls', budgets=JOURNEY_BUDGETS)
