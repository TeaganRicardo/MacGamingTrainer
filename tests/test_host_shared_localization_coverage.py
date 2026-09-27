from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

ZH = ROOT / "Resources/Localization/zh-CN.lproj/Host.strings"
EN = ROOT / "Resources/Localization/en.lproj/Host.strings"


def parse_strings(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        match = re.fullmatch(r'"([^"]+)"\s*=\s*"(.*)";', line)
        assert match, f"invalid Host.strings row: {path}:{raw}"
        key, value = match.groups()
        assert key not in rows, f"duplicate localization key: {key}"
        rows[key] = value
    return rows


zh = parse_strings(ZH)
en = parse_strings(EN)
assert zh.keys() == en.keys(), (
    f"Host localization key drift: zh-only={sorted(zh.keys() - en.keys())}, "
    f"en-only={sorted(en.keys() - zh.keys())}"
)

required_keys = {
    "host.language.zhCN",
    "host.language.en",
    "host.refreshStatusHelp",
    "host.restartBackend",
    "host.accessibility.on",
    "host.accessibility.off",
    "host.selection.select",
    "host.selection.deselect",
    "host.selection.selected",
    "host.selection.notSelected",
    "host.more",
    "host.value",
    "host.amount",
    "host.lock",
    "host.locked",
    "host.resource.searchPlaceholder",
    "host.resource.noMatches",
    "host.backend.operation.recover",
    "host.backend.error.startFailed",
    "host.backend.error.terminated",
    "host.backend.error.recoveryFailed",
    "host.backend.error.unavailable",
    "host.backend.error.queueFull",
    "host.backend.error.sendFailed",
    "host.backend.error.protocolMismatch",
    "host.backend.error.operationFailed",
    "host.backend.error.timeout",
    "host.backend.error.protocolError",
    "host.backend.notice.recovering",
    "host.backend.notice.restarted",
    "host.backend.notice.recovered",
    "host.backend.notice.completed",
    "host.trainerMenu",
    "host.shortcutSettings",
    "host.viewRuntimeLog",
    "host.viewLog",
    "host.launchGame",
    "host.refreshStatus",
    "host.disableAll",
    "host.hotkeys.help",
    "host.hotkeys.pressNew",
    "host.hotkeys.unrecognized",
    "host.hotkeys.listenerFailed",
    "host.hotkeys.registrationFailed",
    "host.hotkeys.conflict",
    "host.feature.enable",
    "host.feature.disable",
    "host.save.openFolder",
    "host.refresh",
    "host.save.createBackup",
    "host.clearStatus",
    "host.cancel",
    "host.save.recoveryCopiesWarning",
    "host.show",
    "host.save.history",
    "host.save.empty",
    "host.done",
    "host.deletePermanently",
    "host.save.deleteSelectedMessage",
    "host.save.deleteOneMessage",
    "host.selectedCount",
    "host.deleteSelected",
    "host.save.bulkSelectionHelp",
    "host.save.namePlaceholder",
    "host.save.doubleClickRename",
    "host.save.hotBackup",
    "host.save.fileCount",
    "host.save.invalidBackup",
    "host.restore",
    "host.rename",
    "host.showInFinder",
    "host.delete",
    "host.save.deleteSelectedTitle",
    "host.save.deleteTitle",
    "host.save.pendingIndeterminate",
    "host.save.pendingWaiting",
    "host.save.restoreTitle",
    "host.save.restoreOptions",
    "host.save.restoreExplanation",
    "host.save.preserveCurrent",
    "host.save.operation.refresh",
    "host.save.operation.create",
    "host.save.operation.rename",
    "host.save.operation.openFolder",
    "host.save.operation.show",
    "host.save.operation.restore",
    "host.save.operation.cancelPending",
    "host.save.operation.applyPending",
    "host.save.operation.delete",
    "host.save.notice.created",
    "host.save.notice.renamed",
    "host.save.notice.restoreSubmitted",
    "host.save.notice.pendingCancelled",
    "host.save.notice.pendingApplied",
    "host.save.notice.deletedOne",
    "host.save.notice.deletedMany",
    "host.save.error.invalidFolder",
    "host.save.error.backendUnavailable",
    "host.save.error.incomplete",
    "host.save.error.failed",
    "host.save.error.rollbackFailed",
    "host.save.error.busy",
    "host.save.error.notFound",
    "host.save.error.unsupported",
    "host.save.error.stagedUnavailable",
    "host.save.error.stagedIndeterminate",
    "host.save.error.unsafe",
    "host.save.error.invalidSnapshot",
    "host.save.error.restoreFailed",
}
missing = required_keys - zh.keys()
assert not missing, f"shared Host presentation keys missing: {sorted(missing)}"

# Core/shared resources must stay game-agnostic. Hades-native terms belong to
# the module terminology registry and B03, not Host.strings.
host_resource_text = ZH.read_text(encoding="utf-8") + "\n" + EN.read_text(encoding="utf-8")
for forbidden in ("祝福", "巫咒", "卡戎", "Boon", "Hex", "Olympian", "Charon"):
    assert forbidden not in host_resource_text, f"Hades-native terminology leaked into Host resources: {forbidden}"

localization = (ROOT / "Sources/Core/Host/TrainerLocalization.swift").read_text(encoding="utf-8")
assert "func presentation(" in localization, "shared presentation values need one Host resolver"
assert 'value.hasPrefix("host.")' in localization, "only Host-owned key tokens may be resolved through Host.strings"
assert 'localization.localized("host.language.zhCN")' in localization
assert 'localization.localized("host.language.en")' in localization

message_banner = (ROOT / "Sources/Core/UI/Primitives/TrainerMessageBanner.swift").read_text(encoding="utf-8")
assert "localization.presentation(text)" in message_banner, (
    "shared Host status/error key tokens must resolve at the presentation boundary"
)

status_controls = (ROOT / "Sources/Core/UI/Components/TrainerStatusControls.swift").read_text(encoding="utf-8")
for token in (
    "localization.presentation(operationText)",
    "localization.presentation(statusText)",
    'localization.localized("host.refreshStatusHelp")',
    'localization.localized("host.restartBackend")',
):
    assert token in status_controls, token

reference = (ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")
assert 'connected ? "host.connected" : "host.disconnected"' in reference
assert "hostConnectionStatus" in reference, "reference fixture must exercise the shared status localization seam"

# These files own shared product presentation. They may still contain stable
# identifiers, symbols, diagnostics, or product branding, but the known
# user-visible Chinese literals below must not remain hard-coded.
shared_files = {
    "Sources/Core/UI/Components/TrainerFeatureControls.swift": ("开启", "关闭"),
    "Sources/Core/UI/Components/TrainerListControls.swift": ("取消选择", "选择", "已选择", "未选择", "更多"),
    "Sources/Core/UI/Components/TrainerResourceControls.swift": ("搜索名称或资源 ID", "没有匹配项目", "数量", "已锁定", "锁定"),
    "Sources/Core/UI/Components/TrainerStatControls.swift": ("数值",),
    "Sources/Core/UI/Primitives/TrainerField.swift": ("数值",),
    "Sources/Core/UI/Components/TrainerStatusControls.swift": ("按需读取状态，不进行持续调试轮询", "重启后端"),
    "Sources/Core/Save/TrainerSaveManagerView.swift": (
        "存档管理", "打开存档目录", "刷新", "创建备份", "清除状态", "检测到上次恢复中断后保留的恢复副本",
        "备份历史", "暂无存档备份", "永久删除", "删除所选", "选择以进行批量管理", "存档名称", "双击重命名",
        "热备份", "个文件", "备份校验失败", "在 Finder 中显示", "删除所选存档", "恢复选项",
        "恢复前保留当前存档",
    ),
}
for relative, literals in shared_files.items():
    source = (ROOT / relative).read_text(encoding="utf-8")
    for literal in literals:
        assert literal not in source, f"{relative} still hard-codes shared presentation: {literal}"

save_model = (ROOT / "Sources/Core/Save/TrainerSaveManagerModel.swift").read_text(encoding="utf-8")
for literal in (
    "刷新存档", "创建存档备份", "重命名存档", "恢复存档", "取消等待恢复", "应用等待恢复",
    "已创建存档备份", "已重命名存档", "恢复请求已提交", "已取消等待恢复", "已应用等待恢复",
    "后端未运行", "存档操作未完成", "存档操作失败", "恢复副本保留在",
):
    assert literal not in save_model, f"Save model still stores localized presentation directly: {literal}"
for code in (
    "save_busy", "save_not_found", "save_unsupported", "staged_unavailable", "staged_indeterminate",
    "save_unsafe", "snapshot_invalid", "restore_failed", "rollback_failed",
):
    assert code in save_model, f"Save presentation must map stable error code {code}"

session = (ROOT / "Sources/Core/Runtime/TrainerBackendSession.swift").read_text(encoding="utf-8")
for key in (
    "host.backend.operation.recover",
    "host.backend.error.startFailed",
    "host.backend.error.terminated",
    "host.backend.error.recoveryFailed",
    "host.backend.notice.recovering",
    "host.backend.notice.restarted",
    "host.backend.notice.recovered",
    "host.backend.notice.completed",
):
    assert key in session, key

assert '\\(reply.operation)完成' not in session, "generic completion notice must not hard-code one language"

print("host_shared_localization_coverage_ok")
