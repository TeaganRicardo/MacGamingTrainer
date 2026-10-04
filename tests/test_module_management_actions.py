from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

module_contract = (ROOT / "Sources/Core/Host/TrainerGameModule.swift").read_text(encoding="utf-8")
host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")
hades_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
host_actions = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text(encoding="utf-8")
management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
hades = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "Sources/Hades2").rglob("*.swift"))
fixture = (ROOT / "ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift").read_text(encoding="utf-8")

# Core owns the only Save manager and exposes one neutral optional presentation
# capability to selected module content. No Save service/model crosses into Hades.
assert "struct TrainerManagementActions" in module_contract
assert "let openSaveManagement: (() -> Void)?" in module_contract
assert "trainerManagementActions" in module_contract
assert "@StateObject private var saveManager: TrainerSaveManagerModel" in host
assert "TrainerSaveManagerView(model: saveManager)" in host
assert "Module.descriptor.supportsSaveManagement" in host
assert ".environment(\\.trainerManagementActions, managementActions)" in host

for forbidden in ("TrainerSaveManagerModel(", "TrainerSaveManagerView("):
    assert forbidden not in hades
    assert forbidden not in fixture

# The Host sidebar no longer injects Save Management. Hades also contributes no
# shortcut/log copies there, so every moved utility has exactly one game-area entry.
host_sidebar = host[host.index("TrainerSidebar("):host.index("} content: {")]
assert "host.saveManagement" not in host_sidebar
assert "saveManagerPresented = true" not in host_sidebar

hades_sidebar = host_actions[
    host_actions.index("struct Hades2SidebarActions"):
    host_actions.index("struct Hades2HeaderActions")
]
assert "EmptyView()" in hades_sidebar
assert "shortcutSettingsPresented" not in hades_sidebar
assert "openLog()" not in hades_sidebar
assert "host.viewRuntimeLog" not in hades_sidebar

game_management = hades_view[
    hades_view.index("private var management"):
    hades_view.index("private func featureRow")
]
assert "Hades2ManagementUtilities(model: model)" in game_management
assert "model.openLog()" not in game_management

for token in (
    "struct Hades2ManagementUtilities",
    "@Environment(\\.trainerManagementActions) private var managementActions",
    'Label(localization.localized("host.shortcutSettings"), systemImage: "keyboard")',
    'Label(localization.localized("host.viewLog"), systemImage: "doc.text.magnifyingglass")',
    'Label(localization.localized("host.saveManagement"), systemImage: "externaldrive")',
    "managementActions.openSaveManagement",
    ".disabled(!model.backendAvailable)",
):
    assert token in management, token

# A module with no Save support needs no Hades-specific stub and receives the
# environment default instead of a duplicated Core transaction owner.
assert "trainerManagementActions" not in fixture
assert "TrainerSaveManagerModel(" not in fixture
assert "TrainerSaveManagerView(" not in fixture

print("module_management_actions_ok")
