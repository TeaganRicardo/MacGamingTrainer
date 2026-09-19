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
assert "static func toggle" not in text, "Core must not infer game-specific deferred semantics"
assert len({name for name in ("Glass", "Pop", "Tink") if name in text}) == 3

assert "performFeatureShortcut" in model
assert "TrainerHotkeyFeedbackPlayer.play" in model
assert "guard success" in model
assert "activeFeatures[key] == true" in model
assert "dormantFeatures[key] == true" in model
assert "featureHotkeyFeedback" in model
shortcut_block = model[model.index("private func performFeatureShortcut"):model.index("private func performDeferredToggleShortcut")]
assert ".toggle(targetEnabled:" not in shortcut_block, "active=false alone must not be reported as deferred"
assert "if let feedback" in shortcut_block

# Future-result toggles have Hades semantics: enabling force flags waits for a
# later boon choice, while disabling is immediately off.
assert "performDeferredToggleShortcut" in model
assert "forceLegendary" in model and "forceDuo" in model

print("hotkey_feedback_contract_ok")
