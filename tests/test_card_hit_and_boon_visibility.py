"""Regression: entire inactive module card is a hit target and Hades II Boon Management stays discoverable."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
sidebar = (ROOT / "Sources/Core/UI/TrainerSidebar.swift").read_text()
hades = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
native = (ROOT / "tests/visual_hierarchy_harness.py").read_text()

card = sidebar.split("struct TrainerSidebarCard<", 1)[1].split("struct TrainerSidebar<", 1)[0]
assert ".frame(maxWidth: .infinity, alignment: .leading)" in card
assert ".focusEffectDisabled()" in card
assert ".allowsHitTesting(selected)" in card
assert ".trainerSurface(selected ? .raised : .panel" in card
surface = card.split(".trainerSurface(selected ? .raised : .panel", 1)[1]
assert ".overlay {" in surface
assert "if !selected {" in surface
assert ".contentShape(Rectangle())" in surface
assert ".onTapGesture(perform: onSelect)" in surface
assert ".accessibilityHidden(true)" in surface
assert "collapsed module-card background rejected pointer selection" in native

effects = hades.split("private var currentRunEffectsPanel: some View {", 1)[1].split("private func exactItemLabel", 1)[0]
assert "currentRunTraitsPanel" in effects
assert "if model.connected {" not in effects
assert effects.index("currentRunTraitsPanel") < effects.index("hades2.spawn.purgingPool")
assert 'if !model.connected {' in effects
assert 'text("hades2.traits.connectRequired")' in effects
manager = hades.split("private var currentRunTraitsPanel: some View {", 1)[1].split("private func currentRunTraitContextualControls", 1)[0]
assert ".disabled(!model.connected)" in manager
assert 'Label(text("hades2.traits.manager")' in manager
assert ".trainerPickerWidth(.expanding)" in manager
assert "currentRunTraitCommonControls(managedCurrentRunTrait)" in manager
assert "model.canMutateTraits" in hades
for language, prefix in (("en", "Connect to the game"), ("zh-CN", "连接游戏")):
    path = ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json"
    entries = json.loads(path.read_text())["entries"]
    assert entries["hades2.traits.connectRequired"].startswith(prefix)
    assert entries["hades2.traits.manager"]

print("card_hit_and_boon_manager_visibility_ok")
