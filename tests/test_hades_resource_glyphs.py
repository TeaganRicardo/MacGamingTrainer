"""Issue #653: shipped Hades I resources have stable domain glyph identities."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

icons = (ROOT / "Sources/Hades/HadesResourceIcon.swift").read_text()
expected_kinds = {
    "MetaPoints": "darkness",
    "Gems": "gemstones",
    "LockKeys": "chthonicKey",
    "GiftPoints": "nectar",
    "SuperGems": "diamond",
    "SuperGiftPoints": "ambrosia",
    "SuperLockKeys": "titanBlood",
}
for resource_id, kind in expected_kinds.items():
    assert f'case "{resource_id}": .{kind}' in icons, (resource_id, kind)

assert "HadesResourceGlyphShape" in icons
assert "TrainerSemanticIcon.Concept.item" in icons  # unknown/future fallback only
for kind in expected_kinds.values():
    assert f"case .{kind}:" in icons, kind
assert len(set(expected_kinds.values())) == len(expected_kinds)

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

print("hades_resource_glyph_identity_ok")
