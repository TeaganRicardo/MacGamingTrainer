from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

hades_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
trainer_host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")
trainer_context = (ROOT / "Sources/Core/Host/TrainerGameContext.swift").read_text(encoding="utf-8")
hades2_module = (ROOT / "Sources/Hades2/Hades2Module.swift").read_text(encoding="utf-8")
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

# Host owns sidebar sections + issues entry; modules supply declarative sections
# instead of copying sidebar/header/menu views.
assert not (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").exists()
assert "TrainerHostSidebarIssuesEntry(" in trainer_host
assert "shortcutSettingsPresented" not in trainer_host
assert "openSaveManagement" in trainer_context

game_management = hades_view[
    hades_view.index("private var management"):
    hades_view.index("private func featureRow")
]
assert "Hades2ManagementUtilities()" in game_management
assert "model.openLog()" not in game_management

for token in (
    "struct Hades2ManagementUtilities",
    "@Environment(\\.trainerManagementGroups) private var managementGroups",
    "TrainerManagementGroups(groups: managementGroups)",
):
    assert token in management, token

assert "Hades2ManagementCatalog.make(" in hades2_module
assert "canStartBackendAction() && !model.connected && model.pid == nil" in action_adapter
assert "openSaveManagement" not in action_adapter
generator = (ROOT / "Tools/generate_game_binding.py").read_text(encoding="utf-8")
assert "if !application.terminationRequested && application.selectedGameID ==" in generator
assert "context.managementGroups(localization: localization)" in generator
assert "TrainerManagementCommandMenu(title: localization.localized(\"host.trainerMenu\"), groups: groups)" in generator

# A module with no Save support needs no Hades-specific stub and still receives
# Host sidebar sections and Core-resolved defaults without fabricating Save tools.
assert "trainerManagementActions" not in fixture
assert "TrainerSaveManagerModel(" not in fixture
assert "TrainerSaveManagerView(" not in fixture
assert "func workbenchSections(" in fixture

print("module_management_actions_ok")
