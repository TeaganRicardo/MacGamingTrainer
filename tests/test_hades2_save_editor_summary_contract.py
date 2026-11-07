"""The Save Editor basket summary reports requested actions and linked effects."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "Sources/Hades2/Views/Hades2SaveEditorView.swift").read_text(encoding="utf-8")

match = re.search(
    r'Text\(text\("hades2\.saveEditor\.basket\.summary", arguments: \[(.*?)\]\)\)',
    VIEW,
    re.S,
)
assert match, "Save Editor basket summary is missing"
arguments = re.findall(r"String\(model\.(pendingCount|pendingEffectCount)\)", match.group(1))
assert arguments == ["pendingCount", "pendingEffectCount"], arguments
assert "pendingPhysicalChangeCount" not in match.group(1)

for locale, expected in (
    ("hades2.en.json", "{0} requested · {1} linked effects"),
    ("hades2.zh-CN.json", "{0} 项修改 · {1} 项关联影响"),
):
    payload = json.loads((ROOT / "Sources/Hades2/Presentation/Localization" / locale).read_text(encoding="utf-8"))
    summary = payload["entries"]["hades2.saveEditor.basket.summary"]
    assert summary == expected, (locale, summary)
    assert "{2}" not in summary

print("hades2_save_editor_summary_contract_ok")
