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

print("core_save_modal_style_round22_ok")
