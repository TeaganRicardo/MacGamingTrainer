from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

localization = (ROOT / 'Sources/Core/Host/TrainerLocalization.swift').read_text()
app = (ROOT / 'Sources/App.swift').read_text()
build = (ROOT / 'build.sh').read_text()

assert 'case zhCN = "zh-CN"' in localization
assert 'case en = "en"' in localization
assert 'UserDefaults' in localization
assert 'TrainerLocalizationStore' in app
assert 'LOCALIZATION_ROOT' in build or (ROOT / 'Resources/Localization').exists()
for language in ('zh-CN', 'en'):
    assert (ROOT / f'Resources/Localization/{language}.lproj/Host.strings').exists()

print('host_localization_contract_ok')
