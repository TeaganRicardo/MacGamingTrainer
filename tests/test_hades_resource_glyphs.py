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

# #706 keeps all seven native permanent resources directly visible, each
# with its own Core number control, the native resource icon and no fake lock.
view = (ROOT / "Sources/Hades/HadesTrainerView.swift").read_text()
resources = view.split("private var resourcesSection:", 1)[1].split("private var managementSection:", 1)[0]
fallbacks = view.split("private static let permanentResourceFallbacks:", 1)[1].split(
    "private var resourcesSection:", 1
)[0]
assert all(f'.init(id: "{resource_id}"' in fallbacks for resource_id in expected_symbols)
assert "ForEach(permanentResources)" in resources
assert "TrainerLabeledControlRow(" in resources
assert "TrainerNumberField(" in resources
assert "HadesResourceIcon.systemName(for: resource.id)" in resources
assert 'draft(.resource(resource.id))' in resources
assert "model.resources[resource.id] != nil" in resources
assert "enabled: model.canMutate" in resources
assert "model.resourceCatalog" in fallbacks
assert "TrainerResourceEditor(" not in resources
assert "TrainerLockButton(" not in resources
assert "HadesValueRow" not in view

navigation = (ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift").read_text()
assert "HadesResourceIcon.systemName(for: resource.id)" in navigation
assert "HadesWorkbenchIcon.worldObject(for: id)" in navigation
assert "if resource != nil { return TrainerSemanticIcon.Concept.item }" not in navigation
assert "return section.icon" not in navigation.split("if worldNames != nil", 1)[1].split("if let feature", 1)[0]

print("hades_resource_glyph_identity_ok")
