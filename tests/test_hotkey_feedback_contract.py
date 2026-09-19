from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = ROOT / "Sources/Core/Input/TrainerHotkeyFeedback.swift"
model_path = ROOT / "Sources/Hades2/Hades2Model.swift"

assert core.exists(), "Core hotkey feedback primitive is missing"
text = core.read_text()
model = model_path.read_text()

assert "enum TrainerHotkeyFeedback" in text
for token in ("case enabled", "case deferred", "case disabled", "TrainerHotkeyFeedbackPlayer"):
    assert token in text, token
assert "Hades" not in text and "godMode" not in text and "boon" not in text
assert len({name for name in ("Glass", "Pop", "Tink") if name in text}) == 3

assert "performFeatureShortcut" in model
assert "TrainerHotkeyFeedbackPlayer.play" in model
assert "guard success" in model
assert "activeFeatures[key] == true" in model
assert "targetEnabled:" in model

# Future-result toggles have Hades semantics: enabling force flags waits for a
# later boon choice, while disabling is immediately off.
assert "performDeferredToggleShortcut" in model
assert "forceLegendary" in model and "forceDuo" in model

print("hotkey_feedback_contract_ok")
