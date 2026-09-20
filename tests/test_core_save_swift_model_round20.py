from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
types = ROOT / "Sources/Core/Save/TrainerSaveTypes.swift"
model = ROOT / "Sources/Core/Save/TrainerSaveManagerModel.swift"
client = ROOT / "Sources/Core/Runtime/BackendClient.swift"

assert types.is_file(), "generic save types missing"
assert model.is_file(), "generic save manager model missing"
assert client.is_file(), "generic backend client missing"

types_text = types.read_text(encoding="utf-8")
model_text = model.read_text(encoding="utf-8")
client_text = client.read_text(encoding="utf-8")
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
assert 'let indeterminate: Bool' in types_text
assert 'self.indeterminate = row["indeterminate"] as? Bool ?? false' in types_text
assert 'func applyStagedIfPossible()' in model_text
apply_block = model_text[model_text.index('    func applyStagedIfPossible()'):model_text.index('    private func deleteNext', model_text.index('    func applyStagedIfPossible()'))]
assert 'successNotice: nil' in apply_block
assert 'reply:' in model_text, "Core payload must use request-specific reply callback"

# rollback_failed is the one Core error that carries a user-actionable path.
assert "let recoveryPath: String?" in client_text
assert 'recoveryPath: detail?["recoveryPath"] as? String' in client_text
assert 'reply.errorCode == "rollback_failed"' in model_text
assert "reply.recoveryPath" in model_text
assert "恢复副本保留在：" in model_text

print("core_save_swift_model_round20_ok")
