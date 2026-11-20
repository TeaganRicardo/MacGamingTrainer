from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

hades_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
host_actions = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text(encoding="utf-8")
management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
action_adapter = (ROOT / "Sources/Hades2/Services/Hades2ManagementActions.swift").read_text(encoding="utf-8")
hades = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "Sources/Hades2").rglob("*.swift"))
fixture = (ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")

# Core owns the only Save manager and exposes one neutral optional presentation
# capability to selected module content (tested in test_core_save_retention_controls.py
# and test_core_host_lifecycle_macos.py). No Save service/model crosses into Hades or the fixture.
for forbidden in ("TrainerSaveManagerModel(", "TrainerSaveManagerView("):
    assert forbidden not in hades
    assert forbidden not in fixture

# Hades contributes no shortcut/log copies to the sidebar, so every moved utility
# has one game-area entry.
hades_sidebar = host_actions[
    host_actions.index("struct Hades2SidebarActions"):
    host_actions.index("struct Hades2HeaderActions")
]
assert "shortcutSettingsPresented" not in hades_sidebar
assert "openLog()" not in hades_sidebar
assert "host.viewRuntimeLog" not in hades_sidebar

game_management = hades_view[
    hades_view.index("private var management"):
    hades_view.index("private func featureRow")
]
assert "Hades2ManagementUtilities(" in game_management
assert "model.openLog()" not in game_management

for token in (
    "struct Hades2ManagementUtilities",
    "@Environment(\\.trainerManagementActions) private var managementActions",
    "TrainerManagementGroups(groups: catalog.groups)",
    "Hades2ManagementCatalog.make(model: model, localization: localization",
    "managementActions.openSaveManagement",
):
    assert token in management, token

assert "TrainerManagementCommandMenu(" in host_actions
assert "openSaveManagement.map" in action_adapter
assert "canStartBackendAction() && !model.connected && model.pid == nil" in action_adapter
generator = (ROOT / "Tools/generate_game_binding.py").read_text(encoding="utf-8")
assert "if !application.terminationRequested && application.selectedGameID ==" in generator
assert ".makeManagementCommands(model: context.model, localization: localization)" in generator

# A module with no Save support needs no Hades-specific stub and receives the
# environment default instead of a duplicated Core transaction owner.
assert "trainerManagementActions" not in fixture
assert "TrainerSaveManagerModel(" not in fixture
assert "TrainerSaveManagerView(" not in fixture

print("module_management_actions_ok")
