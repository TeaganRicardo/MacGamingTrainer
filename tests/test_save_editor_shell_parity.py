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
    assert ".trainerSaveEditorWindow()" in source
    assert ".frame(width: 980)" not in source
    assert ".trainerSurface(.canvas)" not in source

# Hades I follows Hades II source-selection semantics: changing source selects
# a document directly, with pending changes routed through confirmation.
assert ".onChange(of: model.selectedSourceID)" in hades
assert "if model.review.count > 0 { confirmingRead = true }" in hades
assert "else { model.openSelection() }" in hades
assert 'Button(text("hades.saveEditor.read"))' not in hades

# Batch 3 (#751): cross-game Save Editor control, scaffold, paging, feedback, and spacing parity.
advanced_sheet = (ROOT / "Sources/Hades2/Views/Hades2SaveAdvancedValueView.swift").read_text()
grouping = (ROOT / "Sources/Hades2/Views/Hades2SaveEditorEntityGrouping.swift").read_text()

assert "struct TrainerSaveEditorPagingBar" in core
for source in (hades, hades2):
    assert "TrainerSaveEditorPagingBar(" in source
    assert "TrainerLoadingIndicator()" in source
    assert "TrainerInlineNotice(color: theme.warning" in source
    assert "TrainerSemanticIcon.Concept.refresh" in source
    assert "model.query(offset: model.offset)" in source
    assert "TrainerSemanticIcon.Feedback.toastSuccess" in source
    assert ".foregroundStyle(theme.success)" in source
    assert "TrainerListCard {" in source
    assert "TrainerSemanticIcon.Action.remove" in source
    assert '"saveEditor.remove."' in source
    assert "ProgressView()" not in source

assert "DisclosureGroup(" not in hades2
assert "TrainerDisclosureButton(" in hades2 and "TrainerDisclosure(" in hades2
assert ".foregroundStyle(theme.accent)" not in hades2[hades2.index("private func applyReceipt"):]

assert ".toggleStyle(.switch)" not in hades
assert ".controlSize(.small)" not in hades
assert "Menu {" not in hades
assert "TrainerToggleControl(" in hades
assert "TrainerCheckboxControl(" in hades
assert "TrainerOverflowMenu(" in hades
assert "TrainerSection(title: text(model.domain.titleKey), icon: model.domain.sectionIcon)" in hades
assert ".trainerPicker(.rowValue, state: model.canEdit(row) ? .interactive : .unavailable)" in hades
assert "cornerRadius: 6" not in hades
assert "theme.compactCornerRadius" in hades
assert ".padding(.vertical, 15)" not in core

for modal_name, modal_source in (("HadesSaveTypedEditor", hades), ("Hades2SaveAdvancedValueView", advanced_sheet)):
    assert "TrainerSheetScaffold(" in modal_source, modal_name
    assert "TrainerPrimaryActionButton(" in modal_source, modal_name
    assert ".keyboardShortcut(.defaultAction)" in modal_source, modal_name
    assert ".trainerSheetDoneGestures(" in modal_source, modal_name
    assert ".interactiveDismissDisabled(" in modal_source, modal_name
assert "TrainerLoadingIndicator()" in advanced_sheet
assert "ProgressView()" not in advanced_sheet
assert "action: cancelSheet" in hades
assert "onCancel: finishSheet" in hades
assert "private func finishSheet()" in hades

assert "TrainerSemanticIcon.Section.inventory" in grouping
assert "TrainerSemanticIcon.Tool.saveHistory" in grouping
assert "TrainerSemanticIcon.Feedback.success" in grouping
assert "TrainerSemanticIcon.Tool.profiles" in grouping

print("save_editor_shell_parity_ok")
