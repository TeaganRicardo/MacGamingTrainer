from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sheet = (ROOT / "Sources/Core/UI/Components/TrainerSheetScaffold.swift").read_text(encoding="utf-8")
list_controls = (ROOT / "Sources/Core/UI/Components/TrainerListControls.swift").read_text(encoding="utf-8")
save_view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")

# All Trainer sheets must paint the same root background as the main TrainerShell.
assert "theme.background.ignoresSafeArea()" in sheet

# Overflow chrome is shared Core UI and renders only the bare ellipsis.
assert "struct TrainerOverflowMenu" in list_controls
assert 'Image(systemName: "ellipsis")' in list_controls
assert ".menuIndicator(.hidden)" in list_controls
assert "TrainerOverflowMenu" in save_view
assert 'ellipsis.circle' not in save_view
assert ".menuStyle(" not in save_view

# Save actions use the app's normal macOS control size; no one-off tiny buttons.
assert ".controlSize(.small)" not in save_view

# Game Save Editor sheets and inline controls follow the same Core primitives.
hades_save_view = (ROOT / "Sources/Hades/HadesSaveEditorView.swift").read_text(encoding="utf-8")
hades2_advanced_view = (ROOT / "Sources/Hades2/Views/Hades2SaveAdvancedValueView.swift").read_text(encoding="utf-8")
for source in (hades_save_view, hades2_advanced_view):
    assert "TrainerSheetScaffold(" in source
    assert "TrainerInlineNotice(" in source
    assert ".keyboardShortcut(.defaultAction)" in source
    assert ".trainerSheetEscapeDismiss(" in source
assert "struct TrainerSheetEscapeMonitor" in sheet
assert "TrainerOverflowMenu(" in hades_save_view
assert "TrainerCheckboxControl(" in hades_save_view
assert "TrainerToggleControl(" in hades_save_view
assert ".controlSize(.small)" not in hades_save_view
assert ".menuStyle(" not in hades_save_view
assert "TrainerLoadingIndicator()" in hades2_advanced_view
assert "ProgressView()" not in hades2_advanced_view

print("core_save_modal_style_round22_ok")
