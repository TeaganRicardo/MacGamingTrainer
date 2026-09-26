from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
localization = (ROOT / "Sources/Core/Host/TrainerLocalization.swift").read_text(encoding="utf-8")
sidebar = (ROOT / "Sources/Core/UI/TrainerSidebar.swift").read_text(encoding="utf-8")
host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")
app = (ROOT / "Sources/App.swift").read_text(encoding="utf-8")
build = (ROOT / "build.sh").read_text(encoding="utf-8")

for language in ("zh-CN", "en"):
    source = ROOT / f"Resources/Localization/{language}.lproj/Host.strings"
    assert source.is_file(), f"missing source localization table: {source}"
assert 'source="${LOCALIZATION_ROOT}/${language}.lproj/Host.strings"' in build
assert 'cp "$source" "${destination}/Host.strings"' in build
assert 'packaged.read_bytes() != source.read_bytes()' in build, "build must verify packaged tables match sources"

assert "Bundle.standard" in localization and "url(forResource: language.rawValue, withExtension: \"lproj\")" in localization, "lookup must load the selected table from Bundle.standard"
assert 'localization.localized("host.gameLibrary")' in sidebar, "sidebar must use shared localization lookup"
assert 'localization.localized("host.saveManagement")' in host, "Host actions must use shared localization lookup"
status_controls = (ROOT / "Sources/Core/UI/Components/TrainerStatusControls.swift").read_text(encoding="utf-8")
assert 'localization.localized("host.connectGame")' in status_controls and 'localization.localized("host.disconnectGame")' in status_controls
assert "TrainerLanguageCommands(localization: localization)" in app, "language selector must be user reachable in app menu"
macos_only = (ROOT / "Tools/macos_only_tests.txt").read_text(encoding="utf-8").splitlines()
assert "test_host_localization_behavior.py" in macos_only, "compiled localization behavior must run in Build 2 macOS"
assert "test_host_localization_runtime.py" not in macos_only, "source-only contract must run on Linux"

print("host_localization_package_contract_ok")
