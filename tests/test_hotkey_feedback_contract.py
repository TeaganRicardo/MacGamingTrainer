from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = ROOT / "Sources/Core/Input/TrainerHotkeyFeedback.swift"
model_path = ROOT / "Sources/Hades2/Hades2Model.swift"

assert core.exists(), "Core hotkey feedback primitive is missing"
text = core.read_text()
model = model_path.read_text()

# Kept (no render/audio hook): distinct NSSound names for enabled/deferred/disabled cannot be observed without an audio hook.
assert len({name for name in ("Glass", "Pop", "Tink") if name in text}) == 3

assert "performFeatureShortcut" in model
assert "TrainerHotkeyFeedbackPlayer.play" in model
assert "guard success" in model
assert "activeFeatures[key.rawValue] == true" in model
assert "dormantFeatures[key.rawValue] == true" in model
assert "featureHotkeyFeedback" in model
shortcut_block = model[model.index("private func performFeatureShortcut"):model.index("private func performBoonForceShortcutFeedback")]
assert ".toggle(targetEnabled:" not in shortcut_block, "active=false alone must not be reported as deferred"
assert "let feedback = self.featureHotkeyFeedback" in shortcut_block
assert "TrainerHotkeyFeedbackPlayer.play(feedback)" in shortcut_block

# Force Legendary / Duo are immediately active when the boon-rarity runtime
# hook is already active. They are deferred only while that parent runtime is
# dormant/unavailable; disabling is immediately off.
assert "performBoonForceShortcutFeedback" in model
force_helper = model[model.index("private func performBoonForceShortcutFeedback"):model.index("func performShortcut")]
assert "activeFeatures[Hades2FeatureKey.boonRarityEnabled.rawValue] == true" in force_helper
assert ".enabled" in force_helper and ".deferred" in force_helper and ".disabled" in force_helper
assert "forceLegendary" in model and "forceDuo" in model


global_hotkeys = (ROOT / "Sources/Core/Input/GlobalHotkeys.swift").read_text()
# Kept (no fault-injection hook): Carbon InstallEventHandler failure cannot be injected without a seam.
assert "guard registry.handlerInstallStatus == noErr else" in global_hotkeys

print("hotkey_feedback_contract_ok")
