from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

source = (ROOT / "Sources/Core/Host/TrainerLocalization.swift").read_text(encoding="utf-8")

assert 'case zhCN = "zh-CN"' in source
assert 'case en = "en"' in source
assert 'UserDefaults' in source
assert 'defaultLanguage' in source

print("host_localization_runtime_contract_ok")
