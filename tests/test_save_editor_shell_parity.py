"""Both game Save Editors compose through the same Core-owned shell primitives."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
core = (ROOT / "Sources/Core/UI/Components/TrainerSaveEditorShell.swift").read_text()
hades = (ROOT / "Sources/Hades/HadesSaveEditorView.swift").read_text()
hades2 = (ROOT / "Sources/Hades2/Views/Hades2SaveEditorView.swift").read_text()

for component in (
    "TrainerSaveEditorWindowHeader",
    "TrainerSaveEditorDocumentBar",
    "TrainerSaveEditorWorkbenchBar",
    "TrainerSaveEditorWorkspace",
):
    assert f"struct {component}" in core, component
    assert f"{component}(" in hades, ("Hades I", component)
    assert f"{component}(" in hades2, ("Hades II", component)

for token in ("Hades", "Hades2", "CurrentRun", "luabins", "Arcana", "Mirror"):
    assert token not in core, token

# Core owns the shared chrome/geometry; modules only provide labels, options and
# game-specific result/review content.
for phrase in (
    ".frame(width: 980)",
    ".frame(minHeight: 700, idealHeight: 850, maxHeight: .infinity)",
    ".trainerSurface(.canvas)",
    ".trainerDismissTextEditingOnClickAway()",
    "theme.rowHorizontalPadding",
    "theme.inlineRowVerticalPadding",
    "TrainerSearchField(",
    ".trainerPicker(.form",
    ".animation(TrainerMotion.animation(.disclosure",
    ".allowsHitTesting(hasReview && !busy)",
    ".accessibilityHidden(!hasReview)",
):
    assert phrase in core, phrase

for source in (hades, hades2):
    assert ".frame(width: 980)" not in source
    assert ".trainerSurface(.canvas)" not in source
    assert ".trainerDismissTextEditingOnClickAway()" not in source

# Hades I follows Hades II source-selection semantics: changing source selects
# a document directly, with pending changes routed through confirmation.
assert ".onChange(of: model.selectedSourceID)" in hades
assert "if model.review.count > 0 { confirmingRead = true }" in hades
assert "else { model.openSelection() }" in hades
assert 'Button(text("hades.saveEditor.read"))' not in hades

print("save_editor_shell_parity_ok")
