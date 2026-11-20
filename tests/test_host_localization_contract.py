import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from test_inventory import load_macos_only_tests

hades_management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
hades_management_actions = (ROOT / "Sources/Hades2/Services/Hades2ManagementActions.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")

for language in ("zh-CN", "en"):
    source = ROOT / f"Resources/Localization/{language}.lproj/Host.strings"
    assert source.is_file(), f"missing source localization table: {source}"
    assert '"host.saveManagement"' in source.read_text(encoding="utf-8"), (
        f"{language} Host table must retain Save Management wording"
    )

# The module forwards the Host capability into the common action catalogue
# (Core localization, packaging, and management buttons are verified in
# test_host_localization_behavior.py, test_build_signing_scope.py, and test_core_host_lifecycle_macos.py).
assert "openSaveManagement: managementActions.openSaveManagement" in hades_management
assert "TrainerManagementGroups(groups: catalog.groups)" in hades_management
save_management = hades_management_actions.split("saveManagement: openSaveManagement.map { open in", 1)[1].split("additionalMaintenance:", 1)[0]
assert ".init(.saveManagement, localization: localization, enabled: canUseBackend, action: open)" in save_management
assert "TrainerLanguageCommands(localization: localization)" in app, "language selector must be user reachable in app menu"
assert "test_host_localization_behavior.py" in load_macos_only_tests(ROOT), (
    "compiled localization behavior must run in Build 2 macOS"
)

print("host_localization_package_contract_ok")
