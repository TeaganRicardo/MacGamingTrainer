"""Core Save structural boundaries and Finder-reveal keep; behavior runs on macOS."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
save_dir = ROOT / "Sources/Core/Save"
save_sources = "\n".join(p.read_text(encoding="utf-8") for p in sorted(save_dir.glob("*.swift")))
model_text = (save_dir / "TrainerSaveManagerModel.swift").read_text(encoding="utf-8")

# Structural boundary: Core Save sources name no game.
assert "Hades" not in save_sources
# Lint (event-driven): Core Save uses no polling timers.
assert "Timer.scheduledTimer" not in save_sources
# Kept pending Finder-reveal mock: model.reveal/revealRecoveryCopies call Finder directly.
assert "NSWorkspace.shared.activateFileViewerSelecting" in model_text

print("core_save_swift_model_round20_ok")
