"""Issue #653: shipped Hades I resources have domain glyph identities."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

icons = (ROOT / "Sources/Hades/HadesResourceIcon.swift").read_text()
for resource_id in (
    "MetaPoints", "Gems", "LockKeys", "GiftPoints",
    "SuperGems", "SuperGiftPoints", "SuperLockKeys",
):
    assert f'case "{resource_id}"' in icons, resource_id
assert "HadesResourceGlyphShape" in icons
assert "TrainerGlyph(identifier:" in icons
assert "TrainerSemanticIcon.Concept.item" in icons  # unknown/future fallback only

view = (ROOT / "Sources/Hades/HadesTrainerView.swift").read_text()
resources = view.split("private var resourcesSection:", 1)[1].split("private var managementSection:", 1)[0]
assert "glyph: HadesResourceIcon.glyph(for: resource.id)" in resources
assert "icon: TrainerSemanticIcon.Concept.item" not in resources

navigation = (ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift").read_text()
assert "HadesResourceIcon.systemName(for: resource.id)" in navigation
assert "HadesWorkbenchIcon.worldObject(for: id)" in navigation
assert "if resource != nil { return TrainerSemanticIcon.Concept.item }" not in navigation
assert "return section.icon" not in navigation.split("if worldNames != nil", 1)[1].split("if let feature", 1)[0]

row = (ROOT / "Sources/Core/UI/Primitives/TrainerRow.swift").read_text()
assert "let glyph: TrainerGlyph" in row
assert "init(title: String, glyph: TrainerGlyph" in row

print("hades_resource_glyph_contract_ok")
