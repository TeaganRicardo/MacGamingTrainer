from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
backend = ROOT / "Backend/games/hades2"
sources = ROOT / "Sources/Hades2"
host = (ROOT / "Sources/Core/Host/TrainerHost.swift").read_text(encoding="utf-8")

assert not (backend / "save_service.py").exists(), "Hades save service must be removed"

router = (backend / "command_router.py").read_text(encoding="utf-8")
preparation = (backend / "preparation.py").read_text(encoding="utf-8")
api = (sources / "Hades2API.swift").read_text(encoding="utf-8")
model = (sources / "Hades2Model.swift").read_text(encoding="utf-8")
state = (sources / "Hades2BackendState.swift").read_text(encoding="utf-8")
types = (sources / "Hades2Types.swift").read_text(encoding="utf-8")
actions = (sources / "Views/Hades2HostActions.swift").read_text(encoding="utf-8")
management = (sources / "Views/Hades2ManagementViews.swift").read_text(encoding="utf-8")

for token in (
    "save_service",
    "list_backups",
    "rename_backup",
    "delete_backup",
    "open_backup_folder",
    "restore_backup",
    "cancel_staged_restore",
    "stage_restore",
    "staged_restore",
    "backup_saves",
    "restore_saves",
):
    assert token not in router, token
    assert token not in preparation, token

for token in (
    "SaveBackup",
    "saveManagerPresented",
    "saveManagerBusy",
    "pendingRestoreID",
    "pendingRestoreTimer",
    "refreshBackups",
    "createBackup",
    "renameBackup",
    "restoreBackup",
    "deleteBackup",
    "openBackupFolder",
    "cancelStagedRestore",
):
    assert token not in model + state + types + actions + management + api, token

assert "Hades2SaveManagerView" not in management
assert 'Label("存档管理"' not in actions
assert "saveManager.applyStagedIfPossible()" in host
assert "if !running" in host
assert "Timer.scheduledTimer" not in host

print("core_save_hades_decoupling_round20_ok")
