"""Native AppKit UI checks for Hades I Save Editor and typed modal sheet parity (#751)."""

MGT_PLATFORM = "macos"

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fixture_budgets.hades import JOURNEY_BUDGETS
from macos_fixture_policy import launch_fixture
from swift_test_compiler import compile_swift_test

if sys.platform != "darwin":
    raise SystemExit("macOS-only Hades I Save Editor frontend test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = sys.executable
if not SWIFTC:
    raise SystemExit("swiftc required")

WORKER = r'''
import json, pathlib, sys

log_path = pathlib.Path(__file__).with_suffix(".commands.jsonl")
state = {
    "baseline": "gen-1",
    "query_count": 0,
    "apply_count": 0,
    "staged": [],
    "fail_query": False,
}

def make_rows(offset, parent_id=None, domain="resources"):
    baseline = state["baseline"]
    if parent_id == "row:container":
        return [{
            "baselineGeneration": baseline,
            "content": None,
            "id": "row:child",
            "name": "Child Flag",
            "englishName": "Child Flag",
            "group": "Nested",
            "groupId": "nested",
            "owner": "Profile",
            "ownerId": "profile",
            "valueType": "boolean",
            "displayValue": "true",
            "typedValue": {"luaType": "boolean", "value": True},
            "editable": True,
            "operations": ["set"],
            "hasChildren": False,
            "warning": None,
            "choices": None,
        }]
    return [
        {
            "baselineGeneration": baseline,
            "content": None,
            "id": "row:bool",
            "name": "Boolean Switch",
            "englishName": "Boolean Switch",
            "group": "General",
            "groupId": "general",
            "owner": "Profile",
            "ownerId": "profile",
            "valueType": "boolean",
            "displayValue": "false",
            "typedValue": {"luaType": "boolean", "value": False},
            "editable": True,
            "operations": ["set", "unset"],
            "hasChildren": False,
            "warning": None,
            "choices": None,
        },
        {
            "baselineGeneration": baseline,
            "content": None,
            "id": "row:container",
            "name": "Container Row",
            "englishName": "Container Row",
            "group": "General",
            "groupId": "general",
            "owner": "Profile",
            "ownerId": "profile",
            "valueType": "table",
            "displayValue": "{ 1 entry }",
            "typedValue": {"luaType": "table", "arraySize": 0, "hashSize": 1, "entries": []},
            "editable": True,
            "operations": ["set", "append", "unset"],
            "hasChildren": True,
            "warning": "Table warning",
            "choices": None,
        },
    ]

def review_payload():
    actions = []
    for entry_id, op, val in state["staged"]:
        name = "Boolean Switch" if entry_id == "row:bool" else "Container Row"
        actions.append({
            "id": entry_id,
            "name": name,
            "before": "false" if entry_id == "row:bool" else "{}",
            "after": "true" if op == "set" and val == {"luaType": "boolean", "value": True} else "updated",
            "operation": op,
            "valueType": "boolean" if entry_id == "row:bool" else "table",
            "typedValue": val,
            "typedKey": None,
            "effects": [],
        })
    return {
        "baselineGeneration": state["baseline"],
        "actions": actions,
        "count": len(actions),
        "effectCount": 0,
    }

for raw in sys.stdin:
    req = json.loads(raw)
    cmd = req["command"]
    params = req.get("params", {})
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(req, sort_keys=True) + "\n")
    ok = True
    result = {}
    failure = None
    if cmd == "catalog":
        result = {}
    elif cmd == "save_editor_inventory":
        file1 = {"rootId": "main", "relativePath": "Profile1.sav", "profile": "Profile 1", "variant": "main"}
        result = {
            "sources": [file1],
            "targets": [file1],
            "defaultSource": {"rootId": "main", "relativePath": "Profile1.sav"},
        }
    elif cmd == "save_editor_open":
        result = {
            "workspaceId": "ws-1",
            "baselineGeneration": state["baseline"],
            "source": {"kind": "currentFile", "snapshotId": None, "rootId": "main", "relativePath": "Profile1.sav"},
            "sourceSHA256": "abc123",
            "target": {"rootId": "main", "relativePath": "Profile1.sav"},
            "domains": ["resources", "advanced"],
            "review": review_payload(),
        }
    elif cmd == "save_editor_query":
        state["query_count"] += 1
        if params.get("query") == "fail-query":
            ok = False
            failure = {
                "code": "query_failed",
                "presentation": "hades.saveEditor.invalidResponse",
                "arguments": [],
                "recoveryPath": "/tmp/mgt-fixture-recovery",
            }
        else:
            offset = int(params.get("offset", 0))
            parent_id = params.get("parentId")
            rows = make_rows(offset, parent_id=parent_id, domain=params.get("domain", "resources"))
            crumbs = [{"id": "row:container", "name": "Container Row"}] if parent_id == "row:container" else []
            result = {
                "baselineGeneration": state["baseline"],
                "rows": rows,
                "total": 85 if not parent_id else 1,
                "offset": offset,
                "limit": 40,
                "breadcrumbs": crumbs,
                "parentId": parent_id,
            }
    elif cmd == "save_editor_stage":
        entry_id = params["entryId"]
        op = params["operation"]
        val = params.get("value")
        state["staged"] = [item for item in state["staged"] if item[0] != entry_id]
        state["staged"].append((entry_id, op, val))
        result = review_payload()
    elif cmd == "save_editor_unstage":
        entry_id = params["entryId"]
        state["staged"] = [item for item in state["staged"] if item[0] != entry_id]
        result = review_payload()
    elif cmd == "save_editor_cancel":
        state["staged"] = []
        result = review_payload()
    elif cmd == "save_editor_detail":
        rows = make_rows(0)
        match = next((r for r in rows if r["id"] == params["entryId"]), rows[0])
        result = {"row": match}
    elif cmd == "save_editor_apply":
        state["apply_count"] += 1
        state["baseline"] = f"gen-{state['apply_count'] + 1}"
        state["staged"] = []
        result = {
            "baselineGeneration": state["baseline"],
            "applied": True,
            "verified": True,
            "installedSHA256": "def456",
            "hot": False,
            "runtimeReloaded": False,
            "previousSnapshotId": "snap-1",
            "target": {"rootId": "main", "relativePath": "Profile1.sav"},
            "maintenanceWarning": None,
            "namingWarning": None,
        }
    elif cmd == "save_editor_close":
        result = {"closed": True}
    reply = {
        "type": "result",
        "id": req["id"],
        "protocolVersion": 6,
        "moduleProtocolVersion": MODULE_VERSION,
        "gameID": "hades",
        "ok": ok,
        "result": result,
    }
    if not ok and failure:
        reply["error"] = failure
    print(json.dumps(reply), flush=True)
'''

HARNESS = r'''
import AppKit
import Foundation
import SwiftUI

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() { fail(message) }
}

func pump(_ seconds: TimeInterval = 0.05) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

func wait(_ message: String, timeout: TimeInterval = 5, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while !condition() && Date() < deadline { pump(0.02) }
    check(condition(), message)
}

func commands(at url: URL) -> [[String: Any]] {
    guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return raw.split(separator: "\n").compactMap {
        try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
    }
}

@MainActor
@main struct HadesSaveEditorFrontendMain {
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 3 else { fail("expected python + worker") }
        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        enableNativeAccessibility()

        let defaults = InMemoryDefaults()
        defaults.set(TrainerPresentationLanguage.en.rawValue, forKey: TrainerLocalizationStore.userDefaultsKey)
        let localization = TrainerLocalizationStore(defaults: defaults)
        localization.registerModulePresentation(prefix: HadesGameModule.presentationKeyPrefix) {
            HadesGameModule.presentationText(key: $0, arguments: $1, language: $2)
        }
        func text(_ key: String) -> String {
            HadesGameModule.resolveText(key: key, localization: localization)
        }

        let python = URL(fileURLWithPath: args[1])
        let worker = URL(fileURLWithPath: args[2])
        let commandLog = worker.deletingPathExtension().appendingPathExtension("commands.jsonl")
        let process = BackendProcess(executableURL: python, argumentsPrefix: ["-u"], forceKillDelay: 0.1)
        let session = TrainerBackendSession(client: BackendClient(process: process))
        try session.start(
            descriptor: HadesGameModule.descriptor,
            backendScriptURL: worker,
            applyPayload: { _ in },
            resetGameState: {},
            log: { _ in }
        )

        let editor = HadesSaveEditorModel(session: session)
        let windows = TrainerToolWindowStore()
        let window = windows.open(id: "hades-save-ui-parity", title: "Hades Save UI Parity", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { !editor.busy }, onClose: editor.close) {
                HadesSaveEditorView(model: editor)
            }
        }
        wait("initial save editor rows loaded (failures=\(editor.failures), ws=\(String(describing: editor.workspaceID)), rows=\(editor.rows.count))") {
            editor.workspaceID != nil && !editor.busy && !editor.queryLoading && !editor.rows.isEmpty
        }
        let root = window.contentView!
        root.layoutSubtreeIfNeeded(); pump()

        // 1. Header subtitle, section header, paging bar, workbench refresh, toggle, overflow menu.
        check(namedNativeControl(root, role: "AXStaticText", name: "Profile1.sav") != nil,
              "window header subtitle did not surface active source")
        check(namedNativeControl(root, role: "AXStaticText", name: text("hades.saveEditor.domain.resources")) != nil,
              "TrainerSection domain header missing")

        let prevTitle = text("hades.saveEditor.previous")
        let nextTitle = text("hades.saveEditor.next")
        guard let prevBtn = namedNativeControl(root, role: "AXButton", name: prevTitle),
              let nextBtn = namedNativeControl(root, role: "AXButton", name: nextTitle),
              !prevBtn.enabled, nextBtn.enabled, nextBtn.help == nextTitle, prevBtn.help == prevTitle,
              nextBtn.press() else {
            fail("unified TrainerSaveEditorPagingBar buttons missing or misconfigured")
        }
        wait("paging next moved to offset 40") { !editor.queryLoading && editor.offset == 40 }
        check(editor.canPreviousPage, "previous eligibility missing after next-page reply")
        let beforeBusyPage = commands(at: commandLog).filter { $0["command"] as? String == "save_editor_query" }.count
        editor.query(offset: editor.offset)
        check(editor.queryLoading && !editor.canNextPage && !editor.canPreviousPage,
              "pagination should be locked by active query")
        editor.nextPage()
        editor.previousPage()
        wait("explicit refresh query completed without queued page navigation") {
            !editor.queryLoading && commands(at: commandLog).filter {
                $0["command"] as? String == "save_editor_query"
            }.count == beforeBusyPage + 1
        }
        check(editor.offset == 40 && editor.canPreviousPage,
              "rejected navigation mutated the visible page or history")
        guard let prevAgain = namedNativeControl(root, role: "AXButton", name: prevTitle),
              prevAgain.enabled, prevAgain.press() else {
            fail("previous page button did not re-enable on offset 40")
        }
        wait("paging previous returned to offset 0") { !editor.queryLoading && editor.offset == 0 }

        // A new search must invalidate old page navigation before the debounce fires.
        // Navigating in that window must not cancel the search or carry its old offset.
        guard let nextForSearch = namedNativeControl(root, role: "AXButton", name: nextTitle),
              nextForSearch.enabled, nextForSearch.press() else {
            fail("could not enter second page before search debounce test")
        }
        wait("second page reopened") { !editor.queryLoading && editor.offset == 40 }
        let beforeSearchQueries = commands(at: commandLog).filter {
            $0["command"] as? String == "save_editor_query"
        }.count
        editor.search = "filtered"
        check(!editor.canPreviousPage && !editor.canNextPage,
              "new search allowed navigation with stale page context")
        editor.nextPage()
        editor.previousPage()
        wait("search debounce reset offset without an intervening page request") {
            let queries = commands(at: commandLog).filter { $0["command"] as? String == "save_editor_query" }
            guard queries.count == beforeSearchQueries + 1,
                  let params = queries.last?["params"] as? [String: Any] else { return false }
            return !editor.queryLoading && editor.offset == 0
                && params["query"] as? String == "filtered"
                && params["offset"] as? Int == 0
        }
        check(!editor.canPreviousPage && editor.canNextPage,
              "successful new search retained stale Back history")
        editor.search = ""
        wait("cleared search returned to first page") {
            let queries = commands(at: commandLog).filter { $0["command"] as? String == "save_editor_query" }
            guard queries.count == beforeSearchQueries + 2,
                  let params = queries.last?["params"] as? [String: Any] else { return false }
            return !editor.queryLoading && editor.offset == 0
                && params["query"] as? String == ""
                && params["offset"] as? Int == 0
        }

        let beforeRefresh = commands(at: commandLog).filter { $0["command"] as? String == "save_editor_query" }.count
        guard let refreshRowsBtn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.refreshRows")),
              refreshRowsBtn.enabled, refreshRowsBtn.press() else {
            fail("workbench refresh button missing or disabled")
        }
        wait("workbench refresh triggered save_editor_query") {
            commands(at: commandLog).filter { $0["command"] as? String == "save_editor_query" }.count == beforeRefresh + 1 && !editor.queryLoading
        }

        // Toggle via Core TrainerToggleControl switch (regular size, AXCheckBox).
        guard let switchCtrl = namedNativeControl(root, role: "AXCheckBox", name: "Boolean Switch"),
              switchCtrl.press() else {
            fail("TrainerToggleControl AXCheckBox missing in HadesSaveEditorField")
        }
        wait("boolean switch staged into review") { !editor.busy && editor.review.count == 1 }

        // Overflow menu (TrainerOverflowMenu -> host.more) present on unsettable row.
        check(nativeAccessibilityControls(root).contains {
            ($0.help == localization.localized("host.more") || $0.label == localization.localized("host.more"))
                && ($0.role == "AXMenuButton" || $0.role == "AXPopUpButton")
        }, "TrainerOverflowMenu affordance missing on row with unset operation")

        // Browse child & return via borderless breadcrumb button.
        guard let browseBtn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.browse") + " Container Row"),
              browseBtn.enabled, browseBtn.press() else {
            fail("browse child button missing")
        }
        wait("entered Container Row child view") { !editor.queryLoading && editor.parentID == "row:container" }
        root.layoutSubtreeIfNeeded(); pump()
        guard let domainCrumb = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.domain.resources")),
              domainCrumb.enabled, domainCrumb.press() else {
            fail("root breadcrumb button missing")
        }
        wait("breadcrumb returned to root domain") { !editor.queryLoading && editor.parentID == nil }

        // 2. Review drawer: Revise -> native sheet + Cancel, and Edit Typed Value -> Esc dismissal edge cases.
        guard let reviseBtn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.revise")),
              reviseBtn.enabled, reviseBtn.press() else {
            fail("Revise button missing in Changes drawer")
        }
        wait("Revise native sheet opened") { window.attachedSheet != nil }
        let reviseContent = window.attachedSheet!.contentView!
        reviseContent.layoutSubtreeIfNeeded(); pump()
        guard let reviseCancelBtn = namedNativeControl(reviseContent, role: "AXButton", name: text("host.cancel")),
              reviseCancelBtn.enabled, reviseCancelBtn.press() else {
            fail("Revise sheet Cancel button missing")
        }
        wait("Revise sheet dismissed") { window.attachedSheet == nil }

        // The same Done path handles Return and a click on the blocked sheet parent.
        guard let reviseReturn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.revise")),
              reviseReturn.enabled, reviseReturn.press() else { fail("Revise not available for Return path") }
        wait("Revise sheet reopened for Return") { window.attachedSheet != nil }
        let keySheetWindow = window.attachedSheet!
        let returnEvent = NSEvent.keyEvent(
            with: .keyDown, location: .zero, modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: keySheetWindow.windowNumber,
            context: nil, characters: "\r", charactersIgnoringModifiers: "\r",
            isARepeat: false, keyCode: 36
        )!
        app.sendEvent(returnEvent)
        wait("Return used Revise Done and closed the sheet") { window.attachedSheet == nil }

        guard let reviseOutside = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.revise")),
              reviseOutside.enabled, reviseOutside.press() else { fail("Revise not available for outside-click path") }
        wait("Revise sheet reopened for outside click") { window.attachedSheet != nil }
        let outsideEvent = NSEvent.mouseEvent(
            with: .leftMouseDown, location: CGPoint(x: 12, y: 12), modifierFlags: [],
            timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: window.windowNumber,
            context: nil, eventNumber: 1, clickCount: 1, pressure: 1
        )!
        app.sendEvent(outsideEvent)
        wait("parent-window click used Revise Done and closed sheet") { window.attachedSheet == nil }

        guard let editTypedBtn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.editTyped")),
              editTypedBtn.enabled, editTypedBtn.press() else {
            fail("Edit Typed Value button missing on complex container row")
        }
        wait("HadesSaveTypedEditor sheet opened") { window.attachedSheet != nil }
        let sheetWindow = window.attachedSheet!
        let sheet = sheetWindow.contentView!
        sheet.layoutSubtreeIfNeeded(); pump()
        check(namedNativeControl(sheet, role: "AXCheckBox", name: text("hades.saveEditor.append")) != nil,
              "TrainerCheckboxControl append option missing in HadesSaveTypedEditor")
        func textViews(in view: NSView) -> [NSTextView] {
            (view as? NSTextView).map { [$0] } ?? view.subviews.flatMap(textViews)
        }
        func sendEsc(to targetWindow: NSWindow) {
            let esc = NSEvent.keyEvent(
                with: .keyDown, location: .zero, modifierFlags: [],
                timestamp: ProcessInfo.processInfo.systemUptime, windowNumber: targetWindow.windowNumber,
                context: nil, characters: "\u{1b}", charactersIgnoringModifiers: "\u{1b}",
                isARepeat: false, keyCode: 53
            )!
            app.sendEvent(esc)
            pump()
        }
        guard let jsonEditor = textViews(in: sheet).first(where: { $0.isEditable && !$0.isFieldEditor }) else {
            fail("HadesSaveJSONEditor missing NSTextView")
        }
        check(sheetWindow.makeFirstResponder(jsonEditor), "failed to focus HadesSaveJSONEditor")
        jsonEditor.selectAll(nil)
        jsonEditor.insertText("invalid json draft", replacementRange: jsonEditor.selectedRange())
        pump()
        guard let doneBtn = namedNativeControl(sheet, role: "AXButton", name: text("host.done")),
              doneBtn.enabled, doneBtn.press() else {
            fail("HadesSaveTypedEditor Done button missing")
        }
        wait("invalid JSON stayed open with failed draft") { window.attachedSheet === sheetWindow && !editor.canApply }
        check(sheetWindow.makeFirstResponder(jsonEditor), "failed to refocus HadesSaveJSONEditor after error")
        sendEsc(to: sheetWindow)
        check(window.attachedSheet === sheetWindow && !editor.canApply,
              "Esc must use Done semantics: invalid JSON stays editable until corrected or explicitly cancelled")
        guard let invalidCancel = namedNativeControl(sheet, role: "AXButton", name: text("host.cancel")),
              invalidCancel.enabled, invalidCancel.press() else {
            fail("explicit Cancel missing after rejected Done")
        }
        wait("explicit Cancel discarded invalid draft and restored Apply") {
            window.attachedSheet == nil && editor.failures["row:container"] == nil && editor.canApply
        }

        // Reopen typed editor: Esc is Done and must commit valid edits without leaked activeEdits.
        guard let editTypedAgain = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.editTyped")),
              editTypedAgain.enabled, editTypedAgain.press() else {
            fail("Edit Typed Value button missing on reopen")
        }
        wait("HadesSaveTypedEditor reopened") { window.attachedSheet != nil }
        let reopenedSheetWindow = window.attachedSheet!
        let reopenedSheet = reopenedSheetWindow.contentView!
        reopenedSheet.layoutSubtreeIfNeeded(); pump()
        let reopenedJSON = textViews(in: reopenedSheet).first { $0.isEditable && !$0.isFieldEditor }!
        check(reopenedSheetWindow.makeFirstResponder(reopenedJSON), "failed to focus reopened HadesSaveJSONEditor")
        reopenedJSON.selectAll(nil)
        reopenedJSON.insertText("{\"luaType\":\"nil\"}", replacementRange: reopenedJSON.selectedRange())
        pump()
        check(!editor.canApply, "active edit did not guard Apply while typing")
        sendEsc(to: reopenedSheetWindow)
        wait("Esc Done committed valid typed edit without leaking activeEdits") {
            window.attachedSheet == nil && editor.canApply &&
                editor.review.actions.contains(where: { $0.id == "row:container" })
        }

        // Recovery failure while typed sheet is open: explicit Cancel is still safe.
        guard let recoveryTypedBtn = namedNativeControl(root, role: "AXButton", name: text("hades.saveEditor.editTyped")),
              recoveryTypedBtn.enabled, recoveryTypedBtn.press() else {
            fail("Edit Typed Value button missing before recovery check")
        }
        wait("recovery check sheet opened") { window.attachedSheet != nil }
        let recoverySheet = window.attachedSheet!.contentView!
        recoverySheet.layoutSubtreeIfNeeded(); pump()
        editor.search = "fail-query"
        editor.query()
        wait("recovery failure observed while sheet open") { !editor.queryLoading && editor.recoveryPath != nil && !editor.canEditRows }
        guard let cancelBtn = namedNativeControl(recoverySheet, role: "AXButton", name: text("host.cancel")),
              cancelBtn.enabled, cancelBtn.press() else {
            fail("HadesSaveTypedEditor Cancel button missing or disabled during recovery failure")
        }
        wait("HadesSaveTypedEditor Cancel dismissed when canEditRows became false") { window.attachedSheet == nil }
        stateCheck: do {
            editor.openSelection()
            wait("reopened clean save document after recovery test") { !editor.busy && !editor.queryLoading && editor.canEditRows }
        }
        // Done is now an actual staged typed edit; restore the empty review state
        // before checking the independent basket-remove path below.
        editor.cancel(baseline: editor.baselineGeneration)
        wait("explicit discard cleared the previously accepted typed edit") {
            !editor.busy && editor.review.count == 0
        }
        guard let switchAgainForRemove = namedNativeControl(root, role: "AXCheckBox", name: "Boolean Switch"),
              switchAgainForRemove.press() else { fail("switch missing before trash remove") }
        wait("restaged switch before trash check") { !editor.busy && editor.review.count == 1 }

        guard let removeBtn = nativeAccessibilityControls(root).first(where: {
            $0.identifier == "saveEditor.remove.row:bool" && $0.label == text("hades.remove")
        }), removeBtn.enabled, removeBtn.press() else {
            fail("saveEditor.remove.<id> trash button missing or unlabeled in Changes drawer")
        }
        wait("trash button unstaged row:bool") { !editor.busy && editor.review.count == 0 }

        // Re-stage & Apply -> verified receipt + error notice coverage.
        guard let switchAgain = namedNativeControl(root, role: "AXCheckBox", name: "Boolean Switch"),
              switchAgain.press() else { fail("switch missing before Apply") }
        wait("second stage ready") { !editor.busy && editor.canApply }
        guard let applyBtn = namedNativeControl(root, role: "AXButton", name: text("hades.apply")),
              applyBtn.enabled, applyBtn.press() else { fail("Apply button missing") }
        wait("Apply completed receipt") { !editor.busy && editor.receipt != nil }
        root.layoutSubtreeIfNeeded(); pump()
        check(namedNativeControl(root, role: "AXStaticText", name: text("hades.saveEditor.applied")) != nil,
              "verified receipt headline missing")

        editor.search = "fail-query"
        editor.query()
        wait("query failure surfaced") { !editor.queryLoading && !editor.failures.isEmpty }
        check(!editor.canNextPage && !editor.canPreviousPage,
              "failed search must not enable stale paging")
        let beforeRejectedPaging = commands(at: commandLog).filter {
            $0["command"] as? String == "save_editor_query"
        }.count
        editor.nextPage()
        editor.previousPage()
        check(commands(at: commandLog).filter {
            $0["command"] as? String == "save_editor_query"
        }.count == beforeRejectedPaging, "failed search allowed a stale page request")

        window.performClose(nil); pump()
        session.stop(); pump()
        print("hades_save_editor_frontend_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-hades-save-ui-") as temporary:
    base = Path(temporary)
    (base / ".fixture-owned").touch()
    home = base / "home"
    home.mkdir()
    module_version = json.loads((ROOT / "Backend/games/hades/module.json").read_text())["protocolVersion"]
    worker_path = base / "worker.py"
    worker_path.write_text(f"MODULE_VERSION = {module_version}\n" + WORKER, encoding="utf-8")
    harness_path = base / "main.swift"
    harness_path.write_text(HARNESS, encoding="utf-8")
    binary = base / "hades-save-editor-frontend"
    compile_swift_test(
        games=("hades",),
        harness_sources=[ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
                         ROOT / "tests/fixtures/swift/NativeAccessibility.swift", harness_path],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    env = dict(os.environ, HOME=str(home), CFFIXED_USER_HOME=str(home))
    run = launch_fixture(
        [str(binary), PYTHON, str(worker_path)],
        journey="hades.save_editor_frontend",
        budgets=JOURNEY_BUDGETS,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if run.returncode != 0 or "hades_save_editor_frontend_ok" not in run.stdout:
        print(run.stdout)
        print(run.stderr)
        raise SystemExit(run.returncode or 1)
    print("hades_save_editor_frontend_ok")
