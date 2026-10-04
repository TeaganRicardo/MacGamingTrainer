from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

host_actions = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text(encoding="utf-8")
management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
hades_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
game_module = (ROOT / "Sources/Hades2/Hades2Module.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")
protocol = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text(encoding="utf-8")
global_hotkeys = (ROOT / "Sources/Core/Input/GlobalHotkeys.swift").read_text(encoding="utf-8")
backend_client = (ROOT / "Sources/Core/Runtime/BackendClient.swift").read_text(encoding="utf-8")
reference = (ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")
en = (ROOT / "Resources/Localization/en.lproj/Host.strings").read_text(encoding="utf-8")
zh = (ROOT / "Resources/Localization/zh-CN.lproj/Host.strings").read_text(encoding="utf-8")

required = {
    "host.trainerMenu",
    "host.shortcutSettings",
    "host.viewRuntimeLog",
    "host.viewLog",
    "host.saveManagement",
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
}
for key in required:
    token = f'"{key}"'
    assert token in en, f"English Host resource missing {key}"
    assert token in zh, f"Chinese Host resource missing {key}"

# Shell placement is Host-owned even when a module supplies the action callback.
for literal in (
    'Label("快捷键设置"',
    'Label("查看运行日志"',
    'Label("启动游戏"',
    'CommandMenu("修改器")',
    'Button("刷新状态")',
    'Button("全部关闭")',
    'Button("快捷键设置")',
    'Button("查看日志")',
):
    assert literal not in host_actions, f"Host shell action copy bypasses localization seam: {literal}"

assert not re.search(r"[\u3400-\u9fff]", host_actions), (
    "shell-placement actions must not own one-language copy"
)

for token in (
    '@EnvironmentObject private var localization: TrainerLocalizationStore',
    'Label(localization.localized("host.launchGame"), systemImage: "play.fill")',
    'CommandMenu(localization.localized("host.trainerMenu"))',
    'Button(localization.localized("host.refreshStatus"))',
    'Button(localization.localized("host.disableAll"))',
    'Button(localization.localized("host.shortcutSettings"))',
    'Button(localization.localized("host.viewLog"))',
):
    assert token in host_actions, token

sidebar_actions = host_actions[
    host_actions.index("struct Hades2SidebarActions"):
    host_actions.index("struct Hades2HeaderActions")
]
assert "EmptyView()" in sidebar_actions
assert "shortcutSettingsPresented" not in sidebar_actions
assert "openLog()" not in sidebar_actions
assert "host.viewRuntimeLog" not in sidebar_actions

# Commands are outside the View environment tree, so the existing Host store is
# injected explicitly through the game-module seam rather than recreated.
assert "makeManagementCommands(model: Model, localization: TrainerLocalizationStore)" in protocol
assert "makeManagementCommands(model: model, localization: localization)" in app
assert "Hades2ManagementCommands(model: model, localization: localization)" in game_module
assert "@ObservedObject private var localization: TrainerLocalizationStore" in host_actions

# Generic shortcut capture/registration chrome is Host-owned; Hades action names
# remain module-owned for B03.
for literal in (
    'TrainerSheetScaffold(title: "快捷键设置"',
    'Text("点击任一快捷键后直接按下新的组合键。',
    '"按下新快捷键…"',
    'model.shortcutError = "无法识别该按键',
):
    assert literal not in management, f"shared shortcut copy bypasses Host localization: {literal}"
for token in (
    'localization.localized("host.shortcutSettings")',
    'localization.localized("host.hotkeys.help")',
    'localization.localized("host.hotkeys.pressNew")',
    'Text(shortcutIssueText(issue))',
    'localization.localized("host.done")',
    'Label(localization.localized("host.shortcutSettings"), systemImage: "keyboard")',
    'Label(localization.localized("host.viewLog"), systemImage: "doc.text.magnifyingglass")',
    'Label(localization.localized("host.saveManagement"), systemImage: "externaldrive")',
):
    assert token in management, token

for token in (
    'Button(localization.localized("host.refresh"))',
    'Label(localization.localized("host.delete"), systemImage: "trash")',
):
    assert token in management, token

assert "TrainerHotkeyRegistrationFailure" in global_hotkeys
assert "case listenerInitialization(status: Int32)" in global_hotkeys
assert "case registrationConflicts([TrainerHotkeyRegistrationConflict])" in global_hotkeys
assert "presentationKey" not in global_hotkeys
assert "let title: String" not in global_hotkeys, "Core hotkey binding must not carry module presentation"
assert "host.hotkeys." not in model, "Hades shortcut state must remain typed, not store Host localization keys"
assert "@Published var shortcutIssue: Hades2ShortcutIssue?" in model
assert not re.search(r"[\u3400-\u9fff]", global_hotkeys), (
    "Core hotkey registration must not emit one-language presentation"
)

# Core transport failures keep stable error identity + diagnostics, while their
# presentation identity is language-neutral and resolved later by Host.
literal_presentations = re.findall(r'presentation:\s*"([^"]+)"', backend_client)
assert literal_presentations, "expected Core transport presentation identities"
assert all(value.startswith("host.") for value in literal_presentations), literal_presentations

# Shared actions must also localize their busy/status operation titles.
for token in (
    'title: "host.refreshStatus"',
    'title: "host.disconnectGame"',
    'title: "host.connectGame"',
    'title: "host.launchGame"',
    'title: "host.disableAll"',
):
    assert token in model, token
assert 'localization.localized("host.disableAll")' in hades_view
assert 'localization.localized("host.viewLog")' in management

# The cross-game fixture proves the exact same seam, including in-flight
# operations rather than only static labels.
for token in (
    'operation: connected ? "host.disconnectGame" : "host.connectGame"',
    'operation: "host.refreshStatus"',
    'operation: value ? "host.feature.enable" : "host.feature.disable"',
    'localization: TrainerLocalizationStore',
):
    assert token in reference, token

print("hades2_host_action_localization_regression_ok")

# A Host-owned key resolved through the Hades view helper must not be looked up
# in the Hades tables. `host.disableAll` keeps its Host key and Host resource on
# purpose, and before the fallback existed it rendered as a literal
# `[host.disableAll]` in the shortcut sheet — a regression against main.
#
# The fallback now lives once, in `Hades2GameModule.resolveText`, so this asserts
# the *rule* at the seam every call site routes through rather than the shape of
# one view's private helper. Pinning the inline `hasPrefix` guard here is what
# let the other three helpers in `Hades2ManagementViews.swift` keep the bug.
module_text = game_module
resolver = module_text[module_text.index("static func resolveText"):]
resolver = resolver[:resolver.index("\n    static func makeModel")]
assert 'guard key.hasPrefix(Hades2Presentation.Key.prefix) else {' in resolver, (
    "the module resolver has no Host-key fallback")
assert "localization.string(key, arguments: arguments)" in resolver, (
    "a Host key is not resolved through the Host table")
# A Hades key must still resolve through the module tables, not the Host one.
assert "Hades2Presentation.shared.string(" in resolver

# Backend and runtime-issue tokens may be Host- or Hades-owned. The shared
# token resolver in the main view must therefore route through the same
# owner-aware module seam; calling Hades2Presentation directly would drop Host
# arguments or render the raw Host key.
resolved_helper = re.search(
    r"private func resolved\(_ token: TrainerTextToken\) -> String \{(.*?)\n    \}",
    hades_view,
    re.S,
)
assert resolved_helper, "main Hades view lost its presentation-token resolver"
assert "Hades2GameModule.resolveText" in resolved_helper.group(1), (
    "presentation tokens bypass owner-aware Host/module resolution"
)
assert "Hades2Presentation.shared" not in resolved_helper.group(1), (
    "Host presentation tokens are still being forced through the Hades catalogue"
)

# Every single-key `text()` helper must route through that one resolver, so the
# fallback cannot be present in one view and missing from another. The
# `arguments:` overload is a different thing — it resolves an already-owned
# Hades token, which by construction is never a Host key.
for source in (hades_view, management):
    for helper in re.findall(
        r"private func text\(_ key: String\) -> String \{(.*?)\n    \}",
        source,
        re.S,
    ):
        assert "Hades2GameModule.resolveText" in helper, (
            "a Hades text() helper bypasses resolveText, so it has no Host fallback")
        assert 'hasPrefix("hades2.")' not in helper, (
            "a duplicated inline fallback can drift from the shared resolver")

# And the fallback must be real: the Host table actually owns that key.
for language, expected in (("zh-CN", "全部关闭"), ("en", "Disable All")):
    host_strings = (ROOT / f"Resources/Localization/{language}.lproj/Host.strings").read_text(encoding="utf-8")
    assert f'"host.disableAll" = "{expected}"' in host_strings, (
        f"{language} Host table no longer supplies the Disable All wording")
