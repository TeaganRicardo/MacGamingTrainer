from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

host_actions = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text(encoding="utf-8")
game_module = (ROOT / "Sources/Hades2/Hades2Module.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")
protocol = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text(encoding="utf-8")
en = (ROOT / "Resources/Localization/en.lproj/Host.strings").read_text(encoding="utf-8")
zh = (ROOT / "Resources/Localization/zh-CN.lproj/Host.strings").read_text(encoding="utf-8")

required = {
    "host.shortcutSettings",
    "host.viewRuntimeLog",
    "host.launchGame",
    "host.trainerMenu",
    "host.refreshStatus",
    "host.disableAll",
    "host.viewLog",
}
for key in required:
    token = f'"{key}"'
    assert token in en, f"English Host resource missing {key}"
    assert token in zh, f"Chinese Host resource missing {key}"

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
    assert literal not in host_actions, f"Host action copy bypasses localization seam: {literal}"

assert '@EnvironmentObject private var localization: TrainerLocalizationStore' in host_actions
assert 'CommandMenu(localization.localized("host.trainerMenu"))' in host_actions
assert 'Button(localization.localized("host.shortcutSettings"))' in host_actions
assert 'Label(localization.localized("host.shortcutSettings"), systemImage: "keyboard")' in host_actions

assert "makeManagementCommands(model: Model, localization: TrainerLocalizationStore)" in protocol
assert "makeManagementCommands(model: model, localization: localization)" in app
assert "Hades2ManagementCommands(model: model, localization: localization)" in game_module

print("hades2_host_action_localization_regression_ok")
