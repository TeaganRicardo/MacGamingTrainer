import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

types = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text(encoding="utf-8")
api = (ROOT / "Sources/Hades2/Hades2API.swift").read_text(encoding="utf-8")
state = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
runtime = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
en = json.loads((ROOT / "Sources/Hades2/Presentation/Localization/hades2.en.json").read_text(encoding="utf-8"))["entries"]
zh = json.loads((ROOT / "Sources/Hades2/Presentation/Localization/hades2.zh-CN.json").read_text(encoding="utf-8"))["entries"]
terms = json.loads((ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json").read_text(encoding="utf-8"))

sources = [
    "Arachne", "Artemis", "Narcissus", "Echo", "Nemesis", "Hades",
    "Medea", "Heracles", "Circe", "Icarus", "Dionysus", "Athena", "Charon",
]
assert "struct Hades2OccurrenceTarget: Identifiable, Equatable" in types
assert 'case setNextOccurrence(String?)' in api
assert 'return .setNextOccurrenceDesired' in api
assert 'return ["target": target ?? NSNull()]' in api
assert "let nextOccurrenceTarget: Hades2FieldPatch<String>" in state
assert "let occurrenceTargets: [Hades2OccurrenceTarget]?" in state
assert '@Published var nextOccurrenceTarget: String?' in model
assert '@Published var occurrenceTargets: [Hades2OccurrenceTarget] = []' in model
assert "func setNextOccurrence(_ target: String?, completion: ((Bool) -> Void)? = nil) -> Bool" in model

assert 'occurrenceTargets = occurrenceList' in runtime
assert 'kind = definition.kind' in runtime and 'sourceId = definition.sourceId' in runtime
assert r'occurrenceTargetIDs: model.occurrenceTargets.map(\.id)' in view
assert 'ForEach(characters)' in view and 'ForEach(shops)' in view
assert 'hades2.occurrence.title' in view and 'hades2.spawn.characterRewards' in view

# Presentation is catalog-driven. The View must not learn resident route or
# stable wire identities; those remain module/runtime data.
for forbidden in (
    "npc:Arachne", "npc:Nemesis", "shop:Charon",
    "F_Story01", "F_Shop01", "Story_Echo_01", "NemesisCombatF",
):
    assert forbidden not in view, forbidden

for source in sources:
    key = f"hades2.occurrence.target.{source}"
    expected = f"{{term:officialSourceNames.{source}}}"
    assert en[key] == expected
    assert zh[key] == expected
    row = terms["officialSourceNames"][source]
    assert row["id"] and row["value"] and row["englishValue"]

assert terms["officialSourceNames"]["Nemesis"]["id"] == "NPC_Nemesis_01"
assert terms["officialSourceNames"]["Heracles"]["id"] == "NPC_Heracles_01"
assert terms["officialSourceNames"]["Charon"]["id"] == "NPC_Charon_01"
assert en["hades2.occurrence.title"] == "Next Eligible Encounter"
assert zh["hades2.occurrence.title"] == "下一次合资格遭遇"
assert en["hades2.occurrence.pending"] == "Pending"
assert zh["hades2.occurrence.pending"] == "待触发"

print("hades2_occurrence_frontend_ok")


resource_controls = (ROOT / "Sources/Core/UI/Components/TrainerResourceControls.swift").read_text()
assert 'TrainerSection(title: text("hades2.gathering.title")' not in gathering
assert 'TrainerSection(title: text("hades2.chaosGate.title")' not in chaos_gate
assert "tint: hasOverride ? theme.accent : theme.inactive" in occurrence_setting
assert "TrainerIconLabel(title: title, icon: icon, tint: state.indicatorColor, emphasized: state.isOn)" in resource_controls
