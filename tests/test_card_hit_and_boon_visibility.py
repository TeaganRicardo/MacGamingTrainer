"""Regression: Hades II Boon Management stays discoverable."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
hades = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()

effects = hades.split("private var currentRunEffectsPanel: some View {", 1)[1].split("private func exactItemLabel", 1)[0]
assert "currentRunTraitsPanel" in effects
assert "if model.connected {" not in effects
assert effects.index("currentRunTraitsPanel") < effects.index("hades2.spawn.purgingPool")
assert 'if !model.connected {' not in effects
assert 'text("hades2.traits.connectRequired")' not in effects
manager = hades.split("private var currentRunTraitsPanel: some View {", 1)[1].split("private func currentRunTraitContextualControls", 1)[0]
assert ".disabled(!model.connected)" not in manager
assert 'TrainerIconLabel(\n                    title: text("hades2.traits.manager")' in manager
assert ".trainerPicker(.expanding, state:" in manager
assert "currentRunTraitCommonControls(managedCurrentRunTrait)" in manager
assert "model.canMutateTraits" in hades
for language, prefix in (("en", "Connect to the game"), ("zh-CN", "连接游戏")):
    path = ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json"
    entries = json.loads(path.read_text())["entries"]
    assert "hades2.traits.connectRequired" not in entries
    assert entries["hades2.traits.manager"]

print("card_hit_and_boon_manager_visibility_ok")
