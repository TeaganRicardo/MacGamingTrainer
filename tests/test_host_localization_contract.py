import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from test_inventory import load_macos_only_tests

hades_management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
hades_management_actions = (ROOT / "Sources/Hades2/Services/Hades2ManagementActions.swift").read_text(encoding="utf-8")
host_context = (ROOT / "Sources/Core/Host/TrainerGameContext.swift").read_text(encoding="utf-8")
host_view = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")

for language in ("zh-CN", "en"):
    source = ROOT / f"Resources/Localization/{language}.lproj/Host.strings"
    assert source.is_file(), f"missing source localization table: {source}"
    assert '"host.saveManagement"' in source.read_text(encoding="utf-8"), (
        f"{language} Host table must retain Save Management wording"
    )

# The Host resolves optional Save Management and shared management groups centrally
# for both management page and App menu (behavior verified in
# test_host_localization_behavior.py, test_build_signing_scope.py, and test_core_host_lifecycle_macos.py).
assert "Module.descriptor.supportsSaveManagement" in host_context
assert "TrainerManagementAction(\n                .saveManagement," in host_context
assert ".environment(\\.trainerManagementGroups," in host_view
assert "@Environment(\\.trainerManagementGroups)" in hades_management
assert "TrainerManagementGroups(groups:" in hades_management
assert "openSaveManagement" not in hades_management_actions
assert "TrainerLanguageCommands(localization: localization)" in app, "language selector must be user reachable in app menu"
assert "test_host_localization_behavior.py" in load_macos_only_tests(ROOT), (
    "compiled localization behavior must run in Build 2 macOS"
)

print("host_localization_package_contract_ok")
