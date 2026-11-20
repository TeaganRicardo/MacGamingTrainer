from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sheet = (ROOT / "Sources/Core/UI/Components/TrainerSheetScaffold.swift").read_text(encoding="utf-8")
save_view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")

# Kept pending a rendered sheet-background pixel check: all Trainer sheets share theme.background.
assert "theme.background.ignoresSafeArea()" in sheet

# Lints: Save actions use normal control size and shared overflow/primary button components.
assert ".controlSize(.small)" not in save_view
assert ".menuStyle(" not in save_view
assert ".buttonStyle(.borderedProminent)" not in save_view

# Game Save Editor sheets and inline controls follow the same Core primitives.
hades_save_view = (ROOT / "Sources/Hades/HadesSaveEditorView.swift").read_text(encoding="utf-8")
hades2_advanced_view = (ROOT / "Sources/Hades2/Views/Hades2SaveAdvancedValueView.swift").read_text(encoding="utf-8")
for source in (hades_save_view, hades2_advanced_view):
    assert "TrainerSheetScaffold(" in source
    assert "TrainerInlineNotice(" in source
    assert ".keyboardShortcut(.defaultAction)" in source
    assert ".trainerSheetDoneGestures(" in source
assert "TrainerOverflowMenu(" in hades_save_view
assert "TrainerCheckboxControl(" in hades_save_view
assert "TrainerToggleControl(" in hades_save_view
assert ".controlSize(.small)" not in hades_save_view
assert ".menuStyle(" not in hades_save_view
assert "TrainerLoadingIndicator()" in hades2_advanced_view
assert "ProgressView()" not in hades2_advanced_view

print("core_save_modal_style_round22_ok")
