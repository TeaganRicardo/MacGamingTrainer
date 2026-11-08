"""Shipped Hades I resources keep stable discovery icons; editing uses the Core editor (#653, #706)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

icons = (ROOT / "Sources/Hades/HadesResourceIcon.swift").read_text()
expected_symbols = {
    "MetaPoints": "drop.fill",
    "Gems": "diamond.fill",
    "LockKeys": "key.fill",
    "GiftPoints": "waterbottle.fill",
    "SuperGems": "seal.fill",
    "SuperGiftPoints": "wineglass.fill",
    "SuperLockKeys": "drop.circle.fill",
}
for resource_id, symbol in expected_symbols.items():
    assert f'case "{resource_id}": "{symbol}"' in icons, (resource_id, symbol)
assert len(set(expected_symbols.values())) == len(expected_symbols)
assert "default: TrainerSemanticIcon.Concept.item" in icons  # unknown/future fallback only

# Resource rows were replaced by Hades II's shared resource editor: one picker
# fed by the game-owned catalog, with no per-row glyph or fabricated lock.
view = (ROOT / "Sources/Hades/HadesTrainerView.swift").read_text()
resources = view.split("private var resourcesSection:", 1)[1].split("private var managementSection:", 1)[0]
assert "TrainerResourceEditor(" in resources
assert "lock: nil" in resources
assert "model.resourceCatalog" in resources
assert "HadesValueRow" not in view

navigation = (ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift").read_text()
assert "HadesResourceIcon.systemName(for: resource.id)" in navigation
assert "HadesWorkbenchIcon.worldObject(for: id)" in navigation
assert "if resource != nil { return TrainerSemanticIcon.Concept.item }" not in navigation
assert "return section.icon" not in navigation.split("if worldNames != nil", 1)[1].split("if let feature", 1)[0]

print("hades_resource_glyph_identity_ok")
