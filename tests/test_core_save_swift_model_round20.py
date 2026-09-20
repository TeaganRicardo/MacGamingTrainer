from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
types = ROOT / "Sources/Core/Save/TrainerSaveTypes.swift"
model = ROOT / "Sources/Core/Save/TrainerSaveManagerModel.swift"

assert types.is_file(), "generic save types missing"
assert model.is_file(), "generic save manager model missing"

types_text = types.read_text(encoding="utf-8")
model_text = model.read_text(encoding="utf-8")
combined = types_text + "\n" + model_text

for token in (
    "struct TrainerSaveSnapshot",
    "struct TrainerPendingRestore",
    "final class TrainerSaveManagerModel",
    "@Published private(set) var snapshots",
    "@Published private(set) var pendingRestore",
    "func refresh()",
    "func backup(",
    "func rename(",
    "func delete(ids:",
    "func reveal(",
    "func restore(",
    "func cancelStaged()",
    "func applyStagedIfPossible()",
    '"core.save.list"',
    '"core.save.backup"',
    '"core.save.rename"',
    '"core.save.delete"',
    '"core.save.open_folder"',
    '"core.save.restore"',
    '"core.save.cancel_staged"',
    '"core.save.apply_staged"',
):
    assert token in combined, token

assert "Hades" not in combined
assert "Timer.scheduledTimer" not in combined
assert "SaveBackup" not in combined
assert 'nameDetails' in types_text
assert 'hot' in types_text
assert 'valid' in types_text
assert 'reply:' in model_text, "Core payload must use request-specific reply callback"

print("core_save_swift_model_round20_ok")
