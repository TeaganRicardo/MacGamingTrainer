"""Native macOS end-to-end tests for Core Generic Save Editor and TrainerStructuredSaveEditorClient."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from fixture_budgets.core_save import JOURNEY_BUDGETS
from macos_fixture_policy import launch_fixture
from swift_test_compiler import compile_swift_test

MGT_PLATFORM = "macos"

if sys.platform != "darwin":
    raise SystemExit("macOS-only Core Generic Save Editor test")

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
PYTHON = sys.executable
if not SWIFTC:
    raise SystemExit("swiftc required")

WORKER = r'''
import json
import os
from pathlib import Path
import sys
import time

REPO_ROOT = Path(os.environ["MGT_REPO_ROOT"])
sys.path.insert(0, str(REPO_ROOT / "Backend"))

import core.protocol as protocol_mod
import core.server as server_mod
from core.adapter import GameAdapter, GameAdapterContext
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_editor import (
    CatalogSaveWorkspace,
    SaveDomainSpec,
    SaveEditorSpec,
    SaveFieldCatalog,
    SaveFieldChoice,
    SaveFieldSpec,
    discover_mapping_fields,
)
from core.save_restore import SaveRestoreTransaction
from core.structured_save_edit import StructuredSaveEligibility

FIXTURE_DIR = Path(os.environ["MGT_CORE_SAVE_FIXTURE_DIR"])
SAVES_DIR = FIXTURE_DIR / "saves"
DATA_DIR = FIXTURE_DIR / "data"
COMMAND_LOG = FIXTURE_DIR / "commands.jsonl"
GATE_FILE = FIXTURE_DIR / "hold-stage"
ROLLBACK_FAIL_FLAG = FIXTURE_DIR / "fail-rollback"
DELAYED_OPEN_FLAG = FIXTURE_DIR / "delay-first-open"
DELAYED_OPEN_DONE = FIXTURE_DIR / "delayed-open-released"
ABANDON_RELEASED_FILE = FIXTURE_DIR / "abandoned-open-id"


class _SampleJsonCodec:
    def decode(self, payload: bytes) -> dict:
        doc = json.loads(payload.decode("utf-8"))
        if not isinstance(doc, dict) or doc.get("formatVersion") != 1:
            raise ValueError("Unsupported sample save format.")
        return doc

    def encode(self, document: dict) -> bytes:
        if not isinstance(document, dict) or document.get("formatVersion") != 1:
            raise TypeError("Sample save document must carry formatVersion=1.")
        return json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")

    def load(self, path: Path) -> dict:
        return self.decode(path.read_bytes())


def _sample_spec() -> SaveEditorSpec[dict]:
    catalog = SaveFieldCatalog(
        domains=(
            SaveDomainSpec("general", {"en": "General", "zh-CN": "常规"}, icon="gearshape"),
            SaveDomainSpec("inventory", {"en": "Inventory", "zh-CN": "物品栏"}, icon="bag"),
            SaveDomainSpec("advanced", {"en": "Advanced", "zh-CN": "高级"}, icon="wrench"),
        ),
        fields=(
            SaveFieldSpec(
                id="player.heroName",
                domain="general",
                path=("player", "heroName"),
                names={"en": "Hero Name", "zh-CN": "角色名称"},
                group_id="profile",
                group_names={"en": "Profile", "zh-CN": "档案"},
                owner_id="owner.player",
                owner_names={"en": "Player", "zh-CN": "角色"},
                value_type="string",
            ),
            SaveFieldSpec(
                id="player.hardcore",
                domain="general",
                path=("player", "hardcore"),
                names={"en": "Hardcore Mode", "zh-CN": "硬核模式"},
                group_id="profile",
                group_names={"en": "Profile", "zh-CN": "档案"},
                owner_id="owner.player",
                owner_names={"en": "Player", "zh-CN": "角色"},
                value_type="boolean",
            ),
            SaveFieldSpec(
                id="player.difficulty",
                domain="general",
                path=("player", "difficulty"),
                names={"en": "Difficulty", "zh-CN": "难度"},
                group_id="rules",
                group_names={"en": "Rules", "zh-CN": "规则"},
                owner_id="owner.rules",
                owner_names={"en": "Game Rules", "zh-CN": "游戏规则"},
                value_type="enum",
                choices=(
                    SaveFieldChoice("normal", {"en": "Normal", "zh-CN": "普通"}),
                    SaveFieldChoice("hard", {"en": "Hard", "zh-CN": "困难"}),
                ),
            ),
            SaveFieldSpec(
                id="inventory.gold",
                domain="inventory",
                path=("inventory", "gold"),
                names={"en": "Gold", "zh-CN": "金币"},
                group_id="currency",
                group_names={"en": "Currency", "zh-CN": "货币"},
                owner_id="owner.inventory",
                owner_names={"en": "Stash", "zh-CN": "仓库"},
                value_type="integer",
                min_value=0,
                max_value=999,
            ),
            SaveFieldSpec(
                id="inventory.speed",
                domain="inventory",
                path=("inventory", "speed"),
                names={"en": "Speed Multiplier", "zh-CN": "速度倍率"},
                group_id="currency",
                group_names={"en": "Currency", "zh-CN": "货币"},
                owner_id="owner.inventory",
                owner_names={"en": "Stash", "zh-CN": "仓库"},
                value_type="number",
                min_value=0.5,
                max_value=5.0,
            ),
            SaveFieldSpec(
                id="formatVersion",
                domain="advanced",
                path=("formatVersion",),
                names={"en": "Format Version", "zh-CN": "格式版本"},
                group_id="meta",
                group_names={"en": "Metadata", "zh-CN": "元数据"},
                owner_id="owner.meta",
                owner_names={"en": "Metadata", "zh-CN": "元数据"},
                value_type="integer",
                editable=False,
            ),
        ),
        discover_unknown=discover_mapping_fields,
    )
    eligibility = StructuredSaveEligibility(
        editor_files=lambda files: [
            {"rootId": row.root_id, "relativePath": row.relative_path, "label": row.relative_path}
            for row in files
            if row.relative_path.endswith(".json")
        ],
        is_source=lambda relative_path: relative_path.startswith("Slot") and relative_path.endswith(".json"),
        default_source=lambda files: (
            {"rootId": files[0].root_id, "relativePath": "Slot1.json"}
            if any(row.relative_path == "Slot1.json" for row in files)
            else None
        ),
    )
    return SaveEditorSpec(codec=_SampleJsonCodec(), eligibility=eligibility, catalog=catalog)


class SampleJsonGameAdapter(GameAdapter):
    def __init__(self, context: GameAdapterContext) -> None:
        super().__init__(context)
        self.save_workspaces = CatalogSaveWorkspace.registry(
            lambda: self.save_service,
            _sample_spec(),
            max_open=8,
        )

    def dispatch(self, command: str, params: dict, request_id: str):
        with COMMAND_LOG.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"command": command, "params": params}, sort_keys=True) + "\n")
        if command.startswith("save_editor_"):
            if command == "save_editor_stage" and GATE_FILE.exists():
                deadline = time.monotonic() + 5.0
                while GATE_FILE.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
            if command == "save_editor_apply" and ROLLBACK_FAIL_FLAG.exists():
                real_replace = SaveRestoreTransaction._replace_file
                calls = []

                def _fail_ack_and_rollback(tx_self, source, destination, digest, **options):
                    calls.append(destination)
                    if len(calls) == 1:
                        real_replace(tx_self, source, destination, digest, **options)
                        raise OSError("synthetic lost ack")
                    raise OSError("synthetic rollback failure")

                orig = SaveRestoreTransaction._replace_file
                SaveRestoreTransaction._replace_file = _fail_ack_and_rollback
                try:
                    return self.dispatch_save_editor(command, params)
                finally:
                    SaveRestoreTransaction._replace_file = orig
            return self.dispatch_save_editor(command, params)
        if command == "status":
            return {"connected": False}
        raise ValueError("Unsupported sample command.")

    def close(self) -> None:
        if self.save_workspaces is not None:
            self.save_workspaces.clear()


def _create_adapter(game_id: str) -> GameAdapter:
    assert game_id == "sample_json"
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(SAVES_DIR), ("Slot*.json",)),),
        provider=None,
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    ctx = GameAdapterContext(
        game_id="sample_json",
        display_name="Sample JSON Game",
        module_protocol_version=1,
        module_dir=FIXTURE_DIR / "module",
        public_metadata={"protocolVersion": 1},
        save_management=spec,
        home=Path.home(),
    )
    return SampleJsonGameAdapter(ctx)


_RealRouter = protocol_mod.JsonlRequestRouter


class _TestRouter(_RealRouter):
    def __init__(self, adapter):
        super().__init__(adapter, save_data_root=DATA_DIR, target_running_probe=lambda: False)


server_mod.create_adapter = _create_adapter
server_mod.JsonlRequestRouter = _TestRouter
server_mod.main(["--game", "sample_json"])
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

@MainActor
func pump(_ seconds: TimeInterval = 0.03) {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if let event = NSApp.nextEvent(
            matching: .any,
            until: min(deadline, Date().addingTimeInterval(0.01)),
            inMode: .default,
            dequeue: true
        ) {
            NSApp.sendEvent(event)
        }
        NSApp.updateWindows()
    }
}

@MainActor
func wait(_ message: String, timeout: TimeInterval = 6.0, _ condition: () -> Bool) {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        pump(0.015)
        if condition() { return }
    }
    fail("Timeout: \(message)")
}

func readCommands(at url: URL) -> [[String: Any]] {
    guard let raw = try? String(contentsOf: url, encoding: .utf8) else { return [] }
    return raw.split(separator: "\n").compactMap {
        try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any]
    }
}

@MainActor
@main struct CoreGenericSaveEditorMacOSMain {
    static func main() throws {
        let args = CommandLine.arguments
        guard args.count == 4 else { fail("expected python, worker, and fixture dir") }
        let pythonURL = URL(fileURLWithPath: args[1])
        let workerURL = URL(fileURLWithPath: args[2])
        let fixtureDir = URL(fileURLWithPath: args[3])
        let commandLog = fixtureDir.appendingPathComponent("commands.jsonl")
        let savesDir = fixtureDir.appendingPathComponent("saves")
        let rollbackFlag = fixtureDir.appendingPathComponent("fail-rollback")
        let stageGate = fixtureDir.appendingPathComponent("hold-stage")

        let app = NSApplication.shared
        app.setActivationPolicy(.prohibited)
        app.finishLaunching()
        enableNativeAccessibility()

        let defaults = InMemoryDefaults()
        defaults.set(TrainerPresentationLanguage.en.rawValue, forKey: TrainerLocalizationStore.userDefaultsKey)
        let localization = TrainerLocalizationStore(defaults: defaults)

        let descriptor = GameModuleDescriptor(
            id: "sample_json",
            displayName: "Sample JSON Game",
            targetProcessName: "SampleJson",
            targetBundleIdentifier: "",
            expectedHostProtocolVersion: 6,
            expectedModuleProtocolVersion: 1,
            supportsSaveManagement: true
        )

        func makeSession() throws -> TrainerBackendSession {
            let process = BackendProcess(executableURL: pythonURL, argumentsPrefix: ["-u"], forceKillDelay: 0.1)
            let session = TrainerBackendSession(client: BackendClient(process: process))
            try session.start(
                descriptor: descriptor,
                backendScriptURL: workerURL,
                applyPayload: { _ in },
                resetGameState: {},
                log: { _ in }
            )
            return session
        }

        // Part 1: Full generic Core Save Editor UI & end-to-end backend round-trip.
        let session = try makeSession()
        let model = TrainerSaveEditorModel(session: session)
        model.pageSize = 1
        let windows = TrainerToolWindowStore()
        let window = windows.open(id: "core-generic-save-editor", title: "Save Editor", localization: localization, theme: .standard) {
            TrainerToolWindowContent(canClose: { !model.busy }, onClose: model.close) {
                TrainerSaveEditorView(model: model)
            }
        }
        wait("initial inventory & open & query completed") {
            model.workspaceID != nil && !model.busy && !model.queryLoading && !model.rows.isEmpty
        }
        let root = window.contentView!
        root.layoutSubtreeIfNeeded(); pump()

        // Owner-complete paging: limit=1 returns whole owner.player (2 rows), total=3, nextOffset=2.
        check(model.rows.map(\.id) == ["player.heroName", "player.hardcore"],
              "expected owner-complete first page: \(model.rows.map(\.id))")
        check(model.total == 3 && model.nextOffset == 2 && model.canNextPage && !model.canPreviousPage,
              "unexpected pagination metrics")

        // Bilingual toggle updates domain titles & field labels without mutating target.
        let targetBeforeLang = readCommands(at: commandLog).filter { $0["command"] as? String == "save_editor_target" }.count
        localization.language = .zhCN
        wait("Chinese language updated domain & row labels") {
            model.domains.first?.title == "常规" && model.rows.first?.name == "角色名称"
        }
        check(readCommands(at: commandLog).filter { $0["command"] as? String == "save_editor_target" }.count == targetBeforeLang,
              "language switch unexpectedly called save_editor_target")
        localization.language = .en
        wait("English language restored") {
            model.domains.first?.title == "General" && model.rows.first?.name == "Hero Name"
        }

        // Owner-complete Next & Previous page via Accessibility buttons.
        let nextTitle = localization.localized("host.saveEditor.next")
        let prevTitle = localization.localized("host.saveEditor.previous")
        guard let nextBtn = namedNativeControl(root, role: "AXButton", name: nextTitle),
              nextBtn.enabled, nextBtn.press() else { fail("next page button missing/disabled") }
        wait("second page loaded player.difficulty") {
            !model.queryLoading && model.offset == 2 && model.rows.map(\.id) == ["player.difficulty"]
        }
        check(model.canPreviousPage && !model.canNextPage, "unexpected second-page flags")
        guard let prevBtn = namedNativeControl(root, role: "AXButton", name: prevTitle),
              prevBtn.enabled, prevBtn.press() else { fail("previous page button missing/disabled") }
        wait("previous page returned to offset 0") {
            !model.queryLoading && model.offset == 0 && model.rows.count == 2
        }

        // Toggle boolean AXCheckBox ("Hardcore Mode").
        guard let hardcoreToggle = namedNativeControl(root, role: "AXCheckBox", name: "Hardcore Mode"),
              hardcoreToggle.press() else { fail("Hardcore Mode switch missing") }
        wait("Hardcore Mode staged") { !model.busy && model.review.count == 1 }

        // Restore standard page size before switching to Inventory & Advanced categories.
        model.pageSize = TrainerSaveEditorModel.pageSize

        // Select Inventory category, test bounds rejection, then valid integer commitText.
        model.selectDomain("inventory")
        wait("inventory domain loaded") {
            !model.queryLoading && model.selectedDomainID == "inventory" && model.rows.contains { $0.id == "inventory.gold" }
        }
        let goldRow = model.rows.first { $0.id == "inventory.gold" }!
        let rejectedOut = model.commitText(goldRow, text: "1500", workspace: model.workspaceID)
        check(rejectedOut == "1500" && model.hasFailedDraft(goldRow) && model.failures["inventory.gold"] != nil,
              "out-of-bounds integer was not rejected")
        _ = model.commitText(goldRow, text: "650", workspace: model.workspaceID)
        wait("Gold staged cleanly") {
            !model.busy && model.review.count == 2 && !model.hasFailedDraft(goldRow)
        }

        // Select Advanced category: verify unknown discovered field has unknown-impact warning and is editable!
        model.selectDomain("advanced")
        wait("advanced domain loaded") {
            !model.queryLoading && model.rows.contains { $0.id == "discovered:customStats/luckyCharm" }
        }
        root.layoutSubtreeIfNeeded(); pump()
        let luckyRow = model.rows.first { $0.id == "discovered:customStats/luckyCharm" }!
        check(luckyRow.editable && (luckyRow.warning?.lowercased().contains("unknown") == true),
              "unknown discovered field missing editable flag or warning")
        check(nativeAccessibilityControls(root).contains {
            $0.role == "AXStaticText" && ($0.text?.lowercased().contains("unknown") == true)
        }, "unknown-impact warning not visible in SwiftUI hierarchy")
        guard let charmToggle = namedNativeControl(root, role: "AXCheckBox", name: "luckyCharm"),
              charmToggle.press() else { fail("unknown boolean field switch missing") }
        wait("unknown field staged") { !model.busy && model.review.count == 3 }

        // Verify overflow unset button on discovered:ephemeral.
        check(nativeAccessibilityControls(root).contains {
            ($0.help == localization.localized("host.more") || $0.label == localization.localized("host.more"))
                && ($0.role == "AXMenuButton" || $0.role == "AXPopUpButton")
        }, "overflow unset menu missing")
        let ephemeralRow = model.rows.first { $0.id == "discovered:ephemeral" }!
        model.stage(ephemeralRow.id, operation: "unset", workspace: model.workspaceID, baseline: ephemeralRow.baselineGeneration)
        wait("ephemeral unset staged") { !model.busy && model.review.count == 4 }

        // Remove one staged action via review drawer trash button (saveEditor.remove.<id>).
        root.layoutSubtreeIfNeeded(); pump()
        guard let removeBtn = nativeAccessibilityControls(root).first(where: {
            $0.identifier == "saveEditor.remove.player.hardcore" && $0.label == localization.localized("host.saveEditor.remove")
        }), removeBtn.enabled, removeBtn.press() else { fail("review remove button missing") }
        wait("unstage via review drawer") { !model.busy && model.review.count == 3 }

        // Switch physical write target to Slot2.json and Apply.
        let initialBaseline = model.baselineGeneration!
        model.selectTarget("main/Slot2.json", baseline: initialBaseline)
        wait("target switched to Slot2.json") { !model.busy && model.selectedTargetID == "main/Slot2.json" }
        guard let applyBtn = namedNativeControl(root, role: "AXButton", name: localization.localized("host.saveEditor.apply")),
              applyBtn.enabled, applyBtn.press() else { fail("Apply button missing or disabled") }
        wait("Apply completed") { !model.busy && model.receipt != nil }
        root.layoutSubtreeIfNeeded(); pump()
        check(model.receipt?.verified == true && model.receipt?.target.id == "main/Slot2.json", "unexpected Apply receipt")
        check(model.baselineGeneration != initialBaseline && model.review.count == 0, "baseline did not rotate")
        check(namedNativeControl(root, role: "AXStaticText", name: localization.localized("host.saveEditor.applied")) != nil,
              "applied receipt banner missing")

        // Verify Slot2.json on disk & Slot1.json untouched.
        let slot1Disk = try JSONSerialization.jsonObject(with: Data(contentsOf: savesDir.appendingPathComponent("Slot1.json"))) as! [String: Any]
        let slot2Disk = try JSONSerialization.jsonObject(with: Data(contentsOf: savesDir.appendingPathComponent("Slot2.json"))) as! [String: Any]
        check((slot1Disk["inventory"] as? [String: Any])?["gold"] as? Int == 50, "Slot1 unexpectedly modified")
        check((slot2Disk["inventory"] as? [String: Any])?["gold"] as? Int == 650, "Gold edit missing on disk")
        check((slot2Disk["customStats"] as? [String: Any])?["luckyCharm"] as? Bool == false, "unknown edit missing on disk")
        check(slot2Disk["ephemeral"] == nil, "unset field still present on disk")
        check(((slot2Disk["opaqueNested"] as? [String: Any])?["keep"] as? [Any])?.count == 3, "untouched sibling structure lost")

        // Re-open Slot2.json from disk and verify persisted values read back accurately.
        model.selectedSourceID = "main/Slot2.json"
        wait("reopened Slot2.json from disk") {
            !model.busy && !model.queryLoading && model.source?.relativePath == "Slot2.json"
        }
        model.selectDomain("inventory")
        wait("reopened inventory domain loaded Gold=650") {
            !model.queryLoading && model.rows.first(where: { $0.id == "inventory.gold" })?.displayValue == "650"
        }
        model.selectDomain("advanced")
        wait("reopened advanced domain loaded luckyCharm=false") {
            !model.queryLoading && model.rows.first(where: { $0.id == "discovered:customStats/luckyCharm" })?.displayValue == "false"
        }
        check(!model.rows.contains { $0.id == "discovered:ephemeral" }, "unset field unexpectedly reappeared on re-read")

        // Part 2: Client safety invariants on the live workspace (per-entry vs workspace lock, rollback_failed lock, lifecycle expiry).
        // Per-entry lock allows sibling edit eligibility; workspace lock blocks all.
        model.selectDomain("general")
        wait("general domain reloaded") { !model.queryLoading && model.rows.contains { $0.id == "player.heroName" } }
        let gen2 = model.baselineGeneration!
        FileManager.default.createFile(atPath: stageGate.path, contents: Data())
        model.stage("player.heroName", operation: "set", value: "Melinoe", workspace: model.workspaceID, baseline: gen2)
        wait("per-entry lock held") { model.busy }
        check(model.client.canEditEntry("player.hardcore", baseline: gen2), "entry lock blocked sibling field")
        check(!model.client.canEditEntry("player.heroName", baseline: gen2), "entry lock allowed same field")
        check(model.hasWorkspaceLock == false, "stage erroneously acquired full workspace lock")
        try? FileManager.default.removeItem(at: stageGate)
        wait("held stage completed") { !model.busy && model.review.count == 1 }

        // Simulated rollback failure triggers recoveryPath banner & locks replay.
        FileManager.default.createFile(atPath: rollbackFlag.path, contents: Data())
        let applyBeforeFail = readCommands(at: commandLog).filter { $0["command"] as? String == "save_editor_apply" }.count
        model.apply(baseline: model.baselineGeneration)
        wait("rollback failure surfaced") { !model.busy && model.recoveryPath != nil }
        try? FileManager.default.removeItem(at: rollbackFlag)
        root.layoutSubtreeIfNeeded(); pump()
        check(!model.canEditRows && !model.canApply && model.recoveryUnresolved,
              "recovery failure did not lock edits/Apply")
        check(namedNativeControl(root, role: "AXStaticText", name: localization.localized("host.saveEditor.recovery")) != nil,
              "recovery banner missing in SwiftUI hierarchy")
        model.apply(baseline: model.baselineGeneration)
        pump(0.05)
        check(readCommands(at: commandLog).filter { $0["command"] as? String == "save_editor_apply" }.count == applyBeforeFail + 1,
              "unresolved recovery state replayed Apply")

        // Backend restart expires workspace cleanly.
        let wsBeforeRestart = model.workspaceID!
        session.restart()
        wait("lifecycle expiry surfaced workspaceExpired") {
            model.failures["workspace"]?.key == "host.save.error.workspaceExpired"
        }
        check(wsBeforeRestart == model.workspaceID && !model.canEditRows, "expired workspace remained editable")

        // Close window cleanly.
        model.close()
        session.stop(); pump()

        // Part 3: Dedicated TrainerStructuredSaveEditorClient abandoned superseded open + window close verification.
        let closeSession = try makeSession()
        let dedicatedClient = TrainerStructuredSaveEditorClient(session: closeSession)
        var acceptedFirst = false
        var acceptedSecond = false
        // Issue two back-to-back open calls: first is immediately superseded by second beginNewDocumentRead().
        dedicatedClient.send(
            "save_editor_open",
            params: ["source": ["rootId": "main", "relativePath": "Slot1.json"], "language": "en"],
            operation: "host.saveEditor.title",
            timeout: 35.0,
            bindsWorkspace: false,
            lock: .workspace,
            isOpenCommand: true,
            onReply: { reply in
                acceptedFirst = reply.success
            }
        )
        dedicatedClient.send(
            "save_editor_open",
            params: ["source": ["rootId": "main", "relativePath": "Slot1.json"], "language": "en"],
            operation: "host.saveEditor.title",
            timeout: 35.0,
            bindsWorkspace: false,
            lock: .workspace,
            isOpenCommand: true,
            onReply: { reply in
                if reply.success,
                   let ws = reply.result?["workspaceId"] as? String,
                   let gen = reply.result?["baselineGeneration"] as? String {
                    dedicatedClient.bind(workspaceID: ws, baselineGeneration: gen)
                    acceptedSecond = true
                }
            }
        )
        let closeCountBefore = readCommands(at: commandLog).filter { $0["command"] as? String == "save_editor_close" }.count
        wait("second open succeeded and abandoned first open was closed") {
            acceptedSecond && !dedicatedClient.busy && readCommands(at: commandLog).filter {
                $0["command"] as? String == "save_editor_close"
            }.count >= closeCountBefore + 1
        }
        check(!acceptedFirst, "superseded first save_editor_open reply was accepted")
        let finalWS = dedicatedClient.workspaceID!
        dedicatedClient.retireAndClose()
        wait("retireAndClose sent save_editor_close for active workspace") {
            readCommands(at: commandLog).contains {
                ($0["command"] as? String == "save_editor_close")
                    && (($0["params"] as? [String: Any])?["workspaceId"] as? String == finalWS)
            }
        }
        window.performClose(nil); pump()
        closeSession.stop(); pump()
        print("core_generic_save_editor_macos_ok")
    }
}
'''

with tempfile.TemporaryDirectory(prefix="mgt-core-save-editor-macos-") as temporary:
    base = Path(temporary)
    (base / ".fixture-owned").touch()
    home = base / "home"
    home.mkdir()
    saves = base / "saves"
    saves.mkdir()
    slot1 = {
        "formatVersion": 1,
        "player": {"heroName": "Astra", "hardcore": False, "difficulty": "normal"},
        "inventory": {"gold": 50, "speed": 1.25},
        "customStats": {"luckyCharm": True},
        "ephemeral": "remove-me",
        "opaqueNested": {"keep": [1, 2, {"tag": "preserved"}]},
    }
    slot2 = {
        "formatVersion": 1,
        "player": {"heroName": "OldHero", "hardcore": True, "difficulty": "hard"},
        "inventory": {"gold": 5, "speed": 1.0},
    }
    (saves / "Slot1.json").write_text(json.dumps(slot1, sort_keys=True), encoding="utf-8")
    (saves / "Slot2.json").write_text(json.dumps(slot2, sort_keys=True), encoding="utf-8")

    worker_path = base / "worker.py"
    worker_path.write_text(WORKER, encoding="utf-8")
    harness_path = base / "main.swift"
    harness_path.write_text(HARNESS, encoding="utf-8")
    binary = base / "core-generic-save-editor-macos"
    compile_swift_test(
        games=(),
        harness_sources=[
            ROOT / "tests/fixtures/swift/InMemoryDefaults.swift",
            ROOT / "tests/fixtures/swift/NativeAccessibility.swift",
            harness_path,
        ],
        output=binary,
        swiftc=SWIFTC,
        cwd=ROOT,
    )
    env = dict(
        os.environ,
        HOME=str(home),
        CFFIXED_USER_HOME=str(home),
        TMPDIR=str(base),
        MGT_REPO_ROOT=str(ROOT),
        MGT_CORE_SAVE_FIXTURE_DIR=str(base),
    )
    run = launch_fixture(
        [str(binary), PYTHON, str(worker_path), str(base)],
        journey="native.core_generic_save_editor",
        budgets=JOURNEY_BUDGETS,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if run.returncode != 0 or "core_generic_save_editor_macos_ok" not in run.stdout:
        print(run.stdout)
        print(run.stderr)
        raise SystemExit(run.returncode or 1)
    print("core_generic_save_editor_macos_ok")
