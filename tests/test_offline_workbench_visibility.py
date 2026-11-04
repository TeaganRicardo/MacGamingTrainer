"""Regression for permanent, cross-module feature visibility while disconnected.

Static actions are always rendered; runtime capabilities and live instance data
only control whether they may be used. Run in Linux contracts and macOS build.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def source(path):
    return (ROOT / path).read_text()


hades = source("Sources/Hades/HadesTrainerView.swift")
rooms = source("Sources/Hades/HadesRoomsPanel.swift")
hades2 = source("Sources/Hades2/Hades2View.swift")
hades_model = source("Sources/Hades/HadesModule.swift")
hades_adapter = source("Backend/games/hades/adapter.py")

for label, view in (("Hades", hades), ("Hades rooms", rooms), ("Hades II", hades2)):
    assert not re.search(r"\bif\s*!?\s*model\.connected\s*\{", view), label

# Durable Hades I desired state follows the Hades II detached-edit contract.
assert "var canEditIntent: Bool { backendAvailable && backendStatus.protocolCompatible }" in hades_model
set_feature = hades_adapter.split("if command == 'set_feature':", 1)[1].split("if command == 'disable_all':", 1)[0]
assert "raise AdapterError('not_connected'" not in set_feature
hades_speed = hades.split("private var gameSpeedPanel: some View {", 1)[1].split("private var boonRarityPanel:", 1)[0]
assert "enabled: model.canEditIntent" in hades_speed
assert "enabled: model.canEditIntent && pageVisible" in hades_speed
boon_policy = hades.split("private var boonRarityPanel: some View {", 1)[1].split("private var boonsSection:", 1)[0]
assert 'ForEach(["Common", "Rare", "Epic", "Heroic"]' in boon_policy
assert "model.boonRarityTarget" in boon_policy

# Both modules keep current-run management selectors visible without live data.
traits = hades.split("private struct HadesCurrentTraitsPanel:", 1)[1].split("private struct HadesCurrentTraitRow:", 1)[0]
assert 'Picker(text("hades.currentTraits")' in traits
assert 'Text(text("hades.emptyTraits")).tag("")' in traits
assert ".trainerPicker(.expanding, state: matches.isEmpty ? .unavailable : .interactive)" in traits
# Exact boon acquisition is a fixed feature whose source/items can be empty.
# Preserve its selectors and action until runtime data arrives.
catalog = hades.split("private struct HadesCatalogView:", 1)[1].split("private struct HadesCurrentTraitsPanel:", 1)[0]
assert 'Picker(text("hades.exactSource")' in catalog
assert 'Picker(text("hades.selectTrait")' in catalog
assert 'TrainerSecondaryActionButton(' in catalog and 'title: text("hades.acquire")' in catalog
assert ".trainerPicker(.expanding, state: model.canMutate && !sourceGroups.isEmpty ? .interactive : .unavailable)" in catalog
assert ".trainerPicker(.expanding, state: model.canMutate && !selectedEntries.isEmpty ? .interactive : .unavailable)" in catalog
assert "selected != nil && model.canMutate" in catalog
assert 'if selected == nil { Text(text("hades.emptyCatalog")).tag(rarity) }' in catalog
assert "if matches.isEmpty { TrainerEmptyState" not in catalog
assert "HadesChaosPairControls(model: model)" in catalog

assert not re.search(r"if\s+matches\.isEmpty\s*\{[\s\S]*?\}\s*else\s*\{\s*Picker\(", traits)

manager = hades2.split("private var currentRunTraitsPanel:", 1)[1].split("private func currentRunTraitContextualControls", 1)[0]
effects = hades2.split("private var currentRunEffectsPanel:", 1)[1].split("private func exactItemLabel", 1)[0]
assert 'Picker(text("hades2.traits.manager")' in manager
assert ".disabled(!model.connected)" not in manager
assert "currentRunTraitsPanel" in effects and "if model.connected {" not in effects
assert "hades2.traits.connectRequired" not in hades2
# The Hades II speed slider is a fixed feature even without runtime support.
speed_panel = hades2.split("private var gameSpeedPanel: some View {", 1)[1].split("private var presentedContent:", 1)[0]
assert 'TrainerDisclosure(isExpanded: model.featureSupport["gameSpeed"] == true)' not in speed_panel
assert 'TrainerMappedSlider(' in speed_panel
assert 'model.featureSupport["gameSpeed"] == true' in speed_panel
assert "enabled: model.canEditDesired && pageVisible" in speed_panel


# Missing room data must disable controls, not remove entire rows.
room_body = rooms.split("struct HadesRoomsPanel: View {", 1)[1].split(".onChange(of: doors, initial: true)", 1)[0]
assert "TrainerDisclosure(isExpanded: !(model.world?.objects.isEmpty ?? true))" not in room_body
for key in ("hades.chamberObject", "hades.exitDoor", "hades.doorReward",
            "hades.doorRoute", "hades.restoreDoor"):
    assert 'TrainerLabeledControlRow(title: text("' + key + '")' in room_body, key
assert "if let door {" not in room_body
assert "if door.canReward {" not in room_body
assert "if door.canRestore {" not in room_body
assert "if !door.routes.isEmpty {" not in room_body
assert ".trainerPicker(.rowAction, state: doors.isEmpty ? .unavailable : .interactive)" in room_body
assert "door?.canReward == true" in room_body
assert "door?.canRestore == true" in room_body
assert "door?.routes.isEmpty == false" in room_body
assert "model.canMutate" in room_body

for lang in ("en", "zh-CN"):
    entries = json.loads(source(f"Sources/Hades2/Presentation/Localization/hades2.{lang}.json"))["entries"]
    assert "hades2.traits.manager" in entries
    assert "hades2.traits.connectRequired" not in entries

print("offline_workbench_visibility_consistency_ok")
