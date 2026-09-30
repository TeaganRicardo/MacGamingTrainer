from pathlib import Path
import ast
import json
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
    "host.backend.error.invalidRequest",
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

# Core/shared resources must stay game-agnostic. Hades-native terms,
# compatibility aliases, and Hades internal vocabulary belong to the module,
# not shared Host localization. Derive the values from the authoritative
# terminology registry instead of sampling a hand-maintained token list.
TERMINOLOGY_REGISTRY = ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
REGISTRY = json.loads(TERMINOLOGY_REGISTRY.read_text(encoding="utf-8"))
HADES_NATIVE_TERM_GROUPS = (
    "officialTerms",
    "nativeChoiceTitles",
    "officialSourceNames",
)
HADES_FORBIDDEN_HOST_GROUPS = HADES_NATIVE_TERM_GROUPS + (
    "compatibilityAliases",
    "internalTerms",
)


def registry_values(groups: tuple[str, ...]) -> set[str]:
    values: set[str] = set()
    for group in groups:
        for entry in REGISTRY[group].values():
            for field in ("value", "englishValue"):
                value = entry.get(field)
                if isinstance(value, str) and value:
                    values.add(value)
    return values


HADES_FORBIDDEN_HOST_TERMS = registry_values(HADES_FORBIDDEN_HOST_GROUPS)
REGISTRY_COMPATIBILITY_ALIASES = registry_values(("compatibilityAliases",))


def governed_term_occurs(term: str, text: str) -> bool:
    """Match governed English terms lexically; CJK terms remain exact substrings."""
    if re.search(r"[A-Za-z0-9]", term):
        pattern = rf"(?<![A-Za-z0-9_]){re.escape(term)}(?![A-Za-z0-9_])"
        return re.search(pattern, text) is not None
    return term in text


def find_hades_vocabulary_leaks(resources: dict[str, str]) -> dict[str, list[str]]:
    leaks: dict[str, list[str]] = {}
    for resource, text in resources.items():
        found = sorted(
            term for term in HADES_FORBIDDEN_HOST_TERMS
            if governed_term_occurs(term, text)
        )
        if found:
            leaks[resource] = found
    return leaks


def shell_string_literals(source: str) -> list[str]:
    """Extract shell single/double-quoted strings while ignoring real comments."""
    literals: list[str] = []
    index = 0
    at_word_start = True
    control = set(";|&()<>" )
    while index < len(source):
        char = source[index]
        if char.isspace():
            at_word_start = True
            index += 1
            continue
        if char == "#" and at_word_start:
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline + 1
            at_word_start = True
            continue
        if char in control:
            at_word_start = True
            index += 1
            continue
        if char == "\\":
            index += 2
            at_word_start = False
            continue
        if char not in {"'", '"'}:
            at_word_start = False
            index += 1
            continue

        quote = char
        index += 1
        value: list[str] = []
        while index < len(source):
            char = source[index]
            if char == quote:
                literals.append("".join(value))
                index += 1
                break
            if quote == '"' and char == "\\" and index + 1 < len(source):
                value.append(source[index + 1])
                index += 2
                continue
            value.append(char)
            index += 1
        at_word_start = False
    return literals


def source_string_literals(path: Path) -> list[str]:
    """Return player-copy candidates without treating identifiers/comments as copy."""
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        tree = ast.parse(source, filename=str(path))
        return [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
    if path.suffix == ".sh" or path.name == "build.sh":
        return shell_string_literals(source)
    # Swift shared surfaces use double-quoted string literals.
    return re.findall(r'"((?:\\.|[^"\\])*)"', source)


assert shell_string_literals("${#ARRAY[@]}; echo 'Boon build failed' # 'ignored comment'") == [
    "Boon build failed"
], (
    "shell vocabulary scan must include single-quoted strings, preserve ${#...} "
    "parameter syntax, and ignore real comments"
)
assert governed_term_occurs("Life", "Life refresh failed")
assert not governed_term_occurs("Life", "Lifecycle refresh failed"), (
    "English native terms must not match substrings inside ordinary identifiers/words"
)


shared_resource_root = ROOT / "Resources/Localization"
shared_resource_texts = {
    str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
    for path in sorted(shared_resource_root.rglob("*"))
    if path.is_file()
}
assert shared_resource_texts, "shared localization resources are missing"

# Regression/control pair for #197. The old seven-token snapshot missed both
# values below (M6); a neutral canary in the same resources must remain clean.
assert REGISTRY["compatibilityAliases"]["rerollShort"]["value"] == "重骰"
assert REGISTRY["officialSourceNames"]["Chaos"]["value"] == "卡俄斯"
alias_probe = {
    resource: text + "\n重骰\n卡俄斯"
    for resource, text in shared_resource_texts.items()
}
alias_probe_leaks = find_hades_vocabulary_leaks(alias_probe)
for resource in shared_resource_texts:
    assert {"重骰", "卡俄斯"} <= set(alias_probe_leaks.get(resource, [])), (
        f"registry-derived Host gate missed #197 alias/native mutation in {resource}"
    )

neutral_probe = {
    resource: text + "\nNeutralHostCanary"
    for resource, text in shared_resource_texts.items()
}
assert not find_hades_vocabulary_leaks(neutral_probe), (
    "Host terminology gate rejected a neutral control; the check is not term-specific"
)

actual_leaks = find_hades_vocabulary_leaks(shared_resource_texts)
assert not actual_leaks, f"Hades terminology leaked into shared Host resources: {actual_leaks}"

# ENGINEERING_INVARIANTS.md mirrors the compatibility aliases for readers, but
# the registry remains authoritative. Keep the prose mirror exact so a newly
# added alias cannot be omitted from governance documentation again.
invariants = (ROOT / "ENGINEERING_INVARIANTS.md").read_text(encoding="utf-8")
alias_line = next(
    (line for line in invariants.splitlines() if line.startswith("- **Compatibility Aliases:**")),
    None,
)
assert alias_line is not None, "ENGINEERING_INVARIANTS.md is missing the Compatibility Aliases line"
documented_aliases = set(re.findall(r"`([^`]+)`", alias_line))
assert documented_aliases == REGISTRY_COMPATIBILITY_ALIASES, (
    "ENGINEERING_INVARIANTS.md compatibility aliases drifted from registry: "
    f"doc-only={sorted(documented_aliases - REGISTRY_COMPATIBILITY_ALIASES)}, "
    f"registry-only={sorted(REGISTRY_COMPATIBILITY_ALIASES - documented_aliases)}"
)

localization = (ROOT / "Sources/Core/Host/TrainerLocalization.swift").read_text(encoding="utf-8")
assert "func presentation(" in localization, "shared presentation values need one Host resolver"
assert 'value.hasPrefix("host.")' in localization, "only Host-owned key tokens may be resolved through Host.strings"
assert 'localization.localized("host.language.zhCN")' in localization
assert 'localization.localized("host.language.en")' in localization

# Core owns the token shape but never a module's vocabulary: a module supplies
# its own namespace plus resolver, and Core stores only that closure. The token
# lives in the Runtime layer, beside the wire identity it travels with.
backend_client = (ROOT / "Sources/Core/Runtime/BackendClient.swift").read_text(encoding="utf-8")
assert "struct TrainerTextToken" in backend_client, "modules need one language-neutral token type"
assert "func registerModulePresentation(" in localization, "modules must be able to contribute their own keys"
assert "func removeModulePresentation(" in localization, "a module namespace must be removable"

# Enforce game-agnostic shared ownership from production sources instead of a
# hand-picked Hades word list. The module manifest owns structural identity;
# the terminology registry owns native/alias/internal vocabulary.
HADES_MANIFEST = json.loads((ROOT / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))
adapter_identity = HADES_MANIFEST["backend"]["adapter"]
adapter_module, _, adapter_type = adapter_identity.partition(":")
frontend = HADES_MANIFEST["frontend"]
target = HADES_MANIFEST["targetApplication"]
HADES_MODULE_IDENTITIES = {
    HADES_MANIFEST["id"],
    HADES_MANIFEST["displayName"],
    str(HADES_MANIFEST["steamAppId"]),
    Path(frontend["sourceDirectory"]).name,
    frontend["moduleType"],
    adapter_module,
    adapter_type,
    target["processName"],
    target["bundleIdentifier"],
}
assert all(HADES_MODULE_IDENTITIES), "Hades module identity metadata is incomplete"

shared_code_paths = [
    ROOT / "Sources/App.swift",
    ROOT / "build.sh",
    ROOT / "Tools/module_support.py",
    ROOT / "Tools/generate_game_binding.py",
    ROOT / "Tools/validate_game_module.py",
]
shared_code_paths += sorted((ROOT / "Sources/Core").rglob("*.swift"))
shared_code_paths += sorted((ROOT / "Backend/core").rglob("*.py"))
shared_code_texts = {
    str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
    for path in shared_code_paths
}

identity_leaks = {
    path: sorted(token for token in HADES_MODULE_IDENTITIES if token in source)
    for path, source in shared_code_texts.items()
}
identity_leaks = {path: tokens for path, tokens in identity_leaks.items() if tokens}
assert not identity_leaks, f"Hades module identity leaked into shared ownership: {identity_leaks}"

shared_literal_texts = {
    path: "\n".join(source_string_literals(ROOT / path))
    for path in shared_code_texts
}
vocabulary_leaks = find_hades_vocabulary_leaks(shared_literal_texts)
assert not vocabulary_leaks, (
    f"Hades terminology registry vocabulary leaked into shared ownership: {vocabulary_leaks}"
)

message_banner = (ROOT / "Sources/Core/UI/Primitives/TrainerMessageBanner.swift").read_text(encoding="utf-8")
assert "localization.presentation(text)" in message_banner, (
    "shared Host status/error key tokens must resolve at the presentation boundary"
)

status_controls = (ROOT / "Sources/Core/UI/Components/TrainerStatusControls.swift").read_text(encoding="utf-8")
for token in (
    "localization.string(operationToken)",
    "localization.string(statusToken)",
    "localization.string(detailToken)",
    'localization.localized("host.refreshStatusHelp")',
    'localization.localized("host.restartBackend")',
):
    assert token in status_controls, token

reference = (ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")
assert 'connected ? "host.connected" : "host.disconnected"' in reference
assert "hostConnectionStatus" in reference, "reference fixture must exercise the shared status localization seam"
assert "TrainerTextToken" in reference, "a second module must use the shared language-neutral token type"
fixture_identity_leaks = sorted(token for token in HADES_MODULE_IDENTITIES if token in reference)
assert not fixture_identity_leaks, f"reference fixture leaked Hades module identity: {fixture_identity_leaks}"
reference_path = ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift"
fixture_vocabulary_leaks = find_hades_vocabulary_leaks({
    "reference fixture": "\n".join(source_string_literals(reference_path))
})
assert not fixture_vocabulary_leaks, f"reference fixture leaked Hades vocabulary: {fixture_vocabulary_leaks}"

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


# Core-owned AdapterError presentation must cross the Host localization seam.
# Keep this generic: a future Core error subclass must inherit the enforcing
# HostPresentationError seam rather than introducing another raw presentation
# convention beside Time Warp.
core_dir = ROOT / "Backend/core"
for source_path in sorted(core_dir.glob("*.py")):
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            direct_adapter_bases = [
                base.id for base in node.bases
                if isinstance(base, ast.Name) and base.id == "AdapterError"
            ]
            if direct_adapter_bases:
                assert node.name == "HostPresentationError", (
                    f"{source_path} defines Core AdapterError subclass {node.name} "
                    "outside the Host presentation seam"
                )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "AdapterError", (
                f"{source_path} constructs AdapterError directly; Core player-facing "
                "failures must use HostPresentationError"
            )

# Core protocol/server failures have their own generic keyed funnel. Raw
# parser/server sentences may remain as diagnostics, but must never be assigned
# to canonical presentation or passed directly as an error_reply presentation.
protocol_source = (ROOT / "Backend/core/protocol.py").read_text(encoding="utf-8")
server_source = (ROOT / "Backend/core/server.py").read_text(encoding="utf-8")
assert "def core_error_reply(" in protocol_source
assert "presentation = str(error)" not in protocol_source
assert "presentation = '操作失败，请查看日志。'" not in protocol_source
assert "router.error_reply(" not in server_source, (
    "Core server framing bypasses the Host-owned core_error_reply presentation seam"
)
for raw in ("请求 ID 无效。", "同一请求 ID 的内容发生变化。", "请求包含不可序列化的 JSON 值。"):
    assert raw not in protocol_source, f"Core protocol still exposes raw localized presentation: {raw}"

time_warp_source = (ROOT / "Backend/core/process_time_warp.py").read_text(encoding="utf-8")
time_warp_keys = set(re.findall(r'"(host\.timeWarp\.error\.[^"]+)"', time_warp_source))
assert time_warp_keys, "Time Warp exposes no Host presentation keys"
for key in time_warp_keys:
    assert key in zh and key in en, f"Time Warp Host key is not bilingual: {key}"
    assert zh[key].strip() and en[key].strip(), f"Time Warp Host key is empty: {key}"

print("host_shared_localization_coverage_ok")
