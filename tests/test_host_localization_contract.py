from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
localization = (ROOT / "Sources/Core/Host/TrainerLocalization.swift").read_text(encoding="utf-8")
sidebar = (ROOT / "Sources/Core/UI/TrainerSidebar.swift").read_text(encoding="utf-8")
host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")
hades_management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")
hades_management_actions = (ROOT / "Sources/Hades2/Services/Hades2ManagementActions.swift").read_text(encoding="utf-8")
shared_management = (ROOT / "Sources/Core/UI/Components/TrainerManagementGroups.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")
build = (ROOT / "build.sh").read_text(encoding="utf-8")

for language in ("zh-CN", "en"):
    source = ROOT / f"Resources/Localization/{language}.lproj/Host.strings"
    assert source.is_file(), f"missing source localization table: {source}"
    assert '"host.saveManagement"' in source.read_text(encoding="utf-8"), (
        f"{language} Host table must retain Save Management wording"
    )
assert 'source="${LOCALIZATION_ROOT}/${language}.lproj/Host.strings"' in build
assert 'cp "$source" "${destination}/Host.strings"' in build
assert 'packaged.read_bytes() != source.read_bytes()' in build, "build must verify packaged tables match sources"

assert "Bundle.standard" in localization and "url(forResource: language.rawValue, withExtension: \"lproj\")" in localization, "lookup must load the selected table from Bundle.standard"
assert "host.gameLibrary" not in sidebar, "sidebar must use shared localization lookup"
# The module forwards the Host capability into the common action catalogue;
# Core localizes that action's key and renders the resulting title unchanged.
assert "openSaveManagement: managementActions.openSaveManagement" in hades_management
assert "TrainerManagementGroups(groups: catalog.groups)" in hades_management
save_management = hades_management_actions.split("saveManagement: openSaveManagement.map { open in", 1)[1].split("additionalMaintenance:", 1)[0]
assert ".init(.saveManagement, localization: localization, enabled: canUseBackend, action: open)" in save_management
assert 'case .saveManagement: "host.saveManagement"' in shared_management
assert "title: localization.localized(common.titleKey)" in shared_management
assert "[saveEditor, saveManagement].compactMap { $0 }" in shared_management
assert "TrainerSecondaryActionButton(title: action.title, systemImage: action.icon," in shared_management
status_controls = (ROOT / "Sources/Core/UI/Components/TrainerStatusControls.swift").read_text(encoding="utf-8")
assert 'localization.localized(primaryActionTitleKey)' in status_controls
assert 'return "host.connectGame"' in status_controls and 'return "host.disconnectGame"' in status_controls
assert "TrainerLanguageCommands(localization: localization)" in app, "language selector must be user reachable in app menu"
macos_only = (ROOT / "Tools/macos_only_tests.txt").read_text(encoding="utf-8").splitlines()
assert "test_host_localization_behavior.py" in macos_only, "compiled localization behavior must run in Build 2 macOS"
assert "test_host_localization_runtime.py" not in macos_only, "source-only contract must run on Linux"

print("host_localization_package_contract_ok")
