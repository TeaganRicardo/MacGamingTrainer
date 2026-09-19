from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
api = (ROOT / 'Sources/Hades2/Hades2API.swift').read_text()
model = (ROOT / 'Sources/Hades2/Hades2Model.swift').read_text()
view = (ROOT / 'Sources/Hades2/Views/Hades2ManagementViews.swift').read_text()
router = (ROOT / 'Backend/games/hades2/command_router.py').read_text()

assert 'case restoreBackup(String, backupCurrent: Bool)' in api
assert 'case .restoreBackup(let id, let backupCurrent):' in api
assert '["backupId": id, "backupCurrent": backupCurrent]' in api

assert 'func restoreBackup(_ backupID: String, backupCurrent: Bool)' in model
assert '.restoreBackup(backupID, backupCurrent: backupCurrent)' in model

assert 'Button("备份当前并恢复")' in view
assert 'Button("直接恢复"' in view
assert 'model.restoreBackup(selectedBackup, backupCurrent: true)' in view
assert 'model.restoreBackup(selectedBackup, backupCurrent: false)' in view
assert '不会创建“恢复前自动备份”' in view

assert "backup_current=params.get('backupCurrent',True)" in router.replace(' ', '')
assert "type(backup_current)isnotbool" in router.replace(' ', '')
assert 'stage_restore(backup_id,run_count=run_count,backup_current=backup_current)' in router.replace(' ', '')
assert 'restore_saves(backup_id,run_count=run_count,backup_current=backup_current)' in router.replace(' ', '')

print('restore_options_contract_ok')
