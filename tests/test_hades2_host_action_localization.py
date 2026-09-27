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

for token in (
    '@EnvironmentObject private var localization: TrainerLocalizationStore',
    'Label(localization.localized("host.shortcutSettings"), systemImage: "keyboard")',
    'Label(localization.localized("host.viewRuntimeLog"), systemImage: "doc.text")',
    'Label(localization.localized("host.launchGame"), systemImage: "play.fill")',
    'CommandMenu(localization.localized("host.trainerMenu"))',
    'Button(localization.localized("host.refreshStatus"))',
    'Button(localization.localized("host.disableAll"))',
    'Button(localization.localized("host.shortcutSettings"))',
    'Button(localization.localized("host.viewLog"))',
):
    assert token in host_actions, token

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
    'localization.presentation(model.shortcutError, arguments: model.shortcutErrorArguments)',
    'localization.localized("host.done")',
):
    assert token in management, token

assert "TrainerHotkeyRegistrationFailure" in global_hotkeys
assert 'presentationKey: "host.hotkeys.listenerFailed"' in global_hotkeys
assert 'presentationKey: "host.hotkeys.registrationFailed"' in global_hotkeys
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
assert 'localization.localized("host.viewLog")' in hades_view

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
