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
assert "activeFeatures[key.rawValue] == true" in model
assert "dormantFeatures[key.rawValue] == true" in model
assert "featureHotkeyFeedback" in model
shortcut_block = model[model.index("private func performFeatureShortcut"):model.index("private func performBoonForceShortcutFeedback")]
assert ".toggle(targetEnabled:" not in shortcut_block, "active=false alone must not be reported as deferred"
assert "if let feedback" in shortcut_block

# Force Legendary / Duo are immediately active when the boon-rarity runtime
# hook is already active. They are deferred only while that parent runtime is
# dormant/unavailable; disabling is immediately off.
assert "performBoonForceShortcutFeedback" in model
force_helper = model[model.index("private func performBoonForceShortcutFeedback"):model.index("private func performShortcut")]
assert "activeFeatures[Hades2FeatureKey.boonRarityEnabled.rawValue] == true" in force_helper
assert ".enabled" in force_helper and ".deferred" in force_helper and ".disabled" in force_helper
assert "forceLegendary" in model and "forceDuo" in model


global_hotkeys = (ROOT / "Sources/Core/Input/GlobalHotkeys.swift").read_text()
assert "handlerInstallStatus" in global_hotkeys
assert "guard handlerInstallStatus == noErr, handler != nil else" in global_hotkeys
assert "快捷键监听初始化失败" in global_hotkeys

print("hotkey_feedback_contract_ok")
