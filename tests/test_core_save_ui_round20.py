"""Core Save Manager UI pins kept pending pointer, alert, Finder-reveal and error-arg journeys."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
view = (ROOT / "Sources/Core/Save/TrainerSaveManagerView.swift").read_text(encoding="utf-8")

# Kept pending a pointer double-click rename journey.
assert ".onTapGesture(count: 2)" in view
# Kept pending a modal .alert confirmation journey; bulk selection is exercised natively.
assert "deleteIDs = selectedIDs" in view
assert "model.delete(ids: ids)" in view
# Kept pending a Finder-reveal mock; buttons and menu items are asserted enabled natively.
assert "model.reveal(id: snapshot.id)" in view
assert "model.revealRecoveryCopies()" in view
# Kept pending a rendered rollback-failed journey passing errorArguments to the view.
assert "localization.presentation(model.error, arguments: model.errorArguments)" in view

print("core_save_ui_round20_ok")
