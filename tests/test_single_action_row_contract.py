"""Issue #653: single-action workbench blocks use Core row geometry."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
panel = view.split("private var currentRunEffectsPanel: some View {", 1)[1].split("private func exactItemLabel", 1)[0]

assert "currentRunTraitsPanel.trainerPanel()" in panel
assert "TrainerLabeledControlRow(" in panel
assert 'title: text("hades2.spawn.purgingPool")' in panel
assert ".trainerGroupedRows()" in panel
assert "Divider()" not in panel
assert "TrainerIconLabel(" not in panel

print("single_action_row_contract_ok")
