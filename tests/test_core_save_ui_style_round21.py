from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
save_view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")
list_controls = (ROOT / "Sources/Core/UI/Components/TrainerListControls.swift").read_text(encoding="utf-8")

assert "struct TrainerSelectionControl" in list_controls
assert "TrainerSelectionControl(" in save_view
assert "TrainerListCard" not in save_view
assert "TrainerRow" in save_view
assert ".trainerGroupedRows()" in save_view
assert 'TrainerSection(title: "备份历史"' in save_view

# Snapshot name is the visual primary text; timestamp/details remain muted
# secondary information.
assert "Text(snapshot.name)" in save_view
assert ".font(.headline.weight(.semibold))" in save_view
assert 'TrainerPillBadge(text: "热备份"' in save_view
assert ".font(.caption)" in save_view
assert ".foregroundStyle(.secondary)" in save_view

# Save-specific view composes Core UI chrome instead of owning its own checkbox
# rendering.
assert 'Image(systemName: selectedIDs.contains(snapshot.id) ? "checkmark.square.fill" : "square")' not in save_view

print("core_save_ui_style_round21_ok")
