"""Hades II save snapshot and restore service.

This module owns only trainer save backups/restores. Executable signing and
version preparation stay in preparation.py.
"""
from pathlib import Path
import datetime
import json
import logging
import os
import re
import shutil
import tempfile
import time

from . import preparation as _preparation
from .persistence import quarantine_corrupt_file

# Keep these indirections tiny and explicit so tests can inject a temporary save
# root without coupling the save service to executable preparation internals.
def _sha(path):
    return _preparation.sha(path)

def _write_json(path, value):
    return _preparation._write_json(path, value)

def _backup_dir(prefix):
    parent = _preparation.DATA / 'backups'
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')
    return Path(tempfile.mkdtemp(prefix=prefix + '-' + stamp, dir=parent))

def _require_stopped():
    return _preparation._require_stopped()

def backup_saves(run_count=None, allow_running=False, display_prefix=None):
    """Create a verified snapshot. Running-game backups retry until the tree is stable."""
    if run_count is not None and (type(run_count) is not int or isinstance(run_count, bool) or not 0 <= run_count <= 99_999_999):
        raise ValueError('Run Count 必须是非负整数。')
    if display_prefix is not None:
        if (not isinstance(display_prefix, str) or not display_prefix.strip()
                or len(display_prefix.strip()) > 48 or any(ord(ch) < 32 for ch in display_prefix)):
            raise ValueError('备份名称前缀无效。')
        display_prefix = display_prefix.strip()
    if not allow_running:
        _require_stopped()
    if _preparation.SAVES.is_symlink():
        raise RuntimeError('存档目录不能是符号链接。')
    if not _preparation.SAVES.is_dir():
        return {'backed_up': False, 'reason': '尚无本地存档', 'source': str(_preparation.SAVES)}

    attempts = 4 if allow_running else 1
    last_error = None
    for attempt in range(attempts):
        root = _backup_dir('saves')
        files = {}
        try:
            for source in sorted(_preparation.SAVES.rglob('*')):
                if source.is_symlink():
                    raise RuntimeError('存档目录包含符号链接；无法保证一致的备份。')
                relative = source.relative_to(_preparation.SAVES)
                target = root / relative
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif source.is_file():
                    before = _sha(source)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    # Verify both the copy and the source after copying.  This
                    # catches a game/cloud write that overlaps the snapshot.
                    if _sha(target) != before or _sha(source) != before:
                        raise RuntimeError('存档在备份期间改变；正在重试稳定快照。')
                    files[str(relative)] = before
            if not allow_running:
                _require_stopped()
            if {str(item.relative_to(_preparation.SAVES)) for item in _preparation.SAVES.rglob('*') if item.is_file()} != set(files):
                raise RuntimeError('存档文件集合在备份期间改变；正在重试稳定快照。')
            for relative, digest in files.items():
                if _sha(_preparation.SAVES / relative) != digest:
                    raise RuntimeError('存档在备份期间改变；正在重试稳定快照。')

            now = datetime.datetime.now().astimezone()
            run_label = str(run_count) if run_count is not None else '—'
            display_name = f'{now:%Y-%m-%d %H-%M-%S} · Run {run_label}'
            if display_prefix:
                display_name = f'{display_prefix} · {display_name}'
            _write_json(root / 'trainer-backup-manifest.json', {
                'source': str(_preparation.SAVES), 'files': files,
                'createdAt': now.isoformat(),
                'displayName': display_name,
                'runCount': run_count,
                'hotBackup': bool(allow_running),
            })
            return {'backed_up': True, 'backup': str(root), 'backupId': root.name,
                    'name': display_name, 'runCount': run_count,
                    'hotBackup': bool(allow_running), 'file_count': len(files)}
        except Exception as error:
            last_error = error
            shutil.rmtree(root, ignore_errors=True)
            retryable = allow_running and (isinstance(error, OSError) or (isinstance(error, RuntimeError) and '备份期间改变' in str(error)))
            if not retryable or attempt + 1 >= attempts:
                raise
            time.sleep(0.08 * (attempt + 1))
    raise last_error or RuntimeError('创建存档备份失败。')


_SAVE_MANIFEST = 'trainer-backup-manifest.json'


def _save_backup_path(backup_id):
    if (not isinstance(backup_id, str) or not re.fullmatch(r'saves-[A-Za-z0-9_-]+', backup_id)
            or len(backup_id) > 160):
        raise ValueError('存档备份 ID 无效；不允许路径或路径穿越。')
    parent = _preparation.DATA / 'backups'
    root = parent / backup_id
    if root.is_symlink() or not root.is_dir() or root.resolve().parent != parent.resolve():
        raise RuntimeError('存档备份不存在或路径不安全。')
    return root


def _snapshot_files(root, files):
    """Validate manifest paths before reading any file, then verify its exact tree."""
    if not isinstance(files, dict) or not files:
        raise RuntimeError('存档备份清单缺少文件校验表。')
    for relative, digest in files.items():
        if (not isinstance(relative, str) or not relative or '\\' in relative
                or relative.startswith('/') or any(part in ('', '.', '..') for part in relative.split('/'))
                or relative == _SAVE_MANIFEST):
            raise RuntimeError('存档备份清单包含不安全路径。')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise RuntimeError('存档备份清单包含无效 SHA-256。')
    actual = set()
    for item in root.rglob('*'):
        if item.is_symlink():
            raise RuntimeError('存档备份包含符号链接。')
        if item.is_file() and str(item.relative_to(root)) != _SAVE_MANIFEST:
            actual.add(str(item.relative_to(root)))
    if actual != set(files):
        raise RuntimeError('存档备份文件缺失或包含清单外文件。')
    for relative, digest in files.items():
        if _sha(root / relative) != digest:
            raise RuntimeError('存档备份损坏：' + relative)
    return files


def _save_manifest(root):
    manifest_path = root / _SAVE_MANIFEST
    if manifest_path.is_symlink():
        raise RuntimeError('存档清单不能是符号链接。')
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError) as error:
        raise RuntimeError('无法读取存档备份清单。') from error
    if not isinstance(manifest, dict):
        raise RuntimeError('存档备份清单必须是对象。')
    # The initial local backup used a direct path-to-hash mapping.
    if 'files' not in manifest and manifest and all(
            isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
            for value in manifest.values()):
        manifest = {'files': manifest, 'format': 'legacy-hash-map'}
    _snapshot_files(root, manifest.get('files'))
    return manifest


def list_save_backups():
    """Read-only inventory; corrupt backups remain visible with a specific error."""
    rows = []
    parent = _preparation.DATA / 'backups'
    parent.mkdir(parents=True, exist_ok=True)
    for root in sorted(parent.glob('saves-*'), reverse=True):
        row = {'id': root.name, 'name': root.name, 'createdAt': '', 'fileCount': 0,
               'runCount': None, 'hotBackup': False, 'path': str(root), 'valid': False}
        try:
            root = _save_backup_path(root.name)
            row['path'] = str(root)
            row['createdAt'] = datetime.datetime.fromtimestamp(root.stat().st_mtime, datetime.timezone.utc).isoformat()
            manifest = _save_manifest(root)
            created = manifest.get('createdAt')
            name = manifest.get('displayName')
            run_count = manifest.get('runCount')
            row.update(createdAt=created if isinstance(created, str) else row['createdAt'],
                       name=name if isinstance(name, str) and name.strip() else row['createdAt'],
                       runCount=run_count if type(run_count) is int and not isinstance(run_count, bool) else None,
                       hotBackup=bool(manifest.get('hotBackup', False)),
                       fileCount=len(manifest['files']), valid=True)
        except (RuntimeError, ValueError, OSError) as error:
            row['error'] = str(error)
        rows.append(row)
    return rows


def rename_save_backup(backup_id, display_name):
    if (not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 96
            or '/' in display_name or '\\' in display_name or any(ord(ch) < 32 for ch in display_name)):
        raise ValueError('备份名称必须为 1–96 个可见字符，且不能包含路径分隔符。')
    root = _save_backup_path(backup_id)
    manifest = _save_manifest(root)
    manifest['displayName'] = display_name.strip()
    _write_json(root / _SAVE_MANIFEST, manifest)
    return {'renamed': True, 'backupId': backup_id, 'name': manifest['displayName'], 'path': str(root)}


def delete_save_backup(backup_id):
    """Delete one trainer-created save snapshot after strict path validation."""
    root = _save_backup_path(backup_id)
    path = str(root.resolve())
    # Deliberately do not require a valid manifest: a corrupt backup must still
    # be removable from the UI. _save_backup_path already constrains deletion to
    # a direct saves-* child of the trainer backup directory and rejects links.
    shutil.rmtree(root)
    if root.exists():
        raise RuntimeError('删除存档备份失败。')
    return {'deleted': True, 'backupId': backup_id, 'path': path}


def save_backup_folder(backup_id=None):
    parent = _preparation.DATA / 'backups'
    parent.mkdir(parents=True, exist_ok=True)
    if backup_id is None:
        return str(parent.resolve())
    return str(_save_backup_path(backup_id).resolve())


def _staged_restore_path():
    return _preparation.DATA / 'staged-restore.json'


def staged_restore():
    path = _staged_restore_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('暂存恢复记录无效。')
        backup_id = data.get('backupId')
        if not isinstance(backup_id, str) or not backup_id:
            raise ValueError('暂存恢复记录无效。')
        run_count = data.get('runCount')
        if run_count is not None and (type(run_count) is not int or not 0 <= run_count <= 99_999_999):
            raise ValueError('暂存恢复记录 Run Count 无效。')
        staged_at = data.get('stagedAt', '')
        if not isinstance(staged_at, str) or len(staged_at) > 128:
            raise ValueError('暂存恢复记录时间无效。')
        backup_current = data.get('backupCurrent', True)
        if type(backup_current) is not bool:
            raise ValueError('暂存恢复备份选项无效。')
        root = _save_backup_path(backup_id)
        _save_manifest(root)
        return {'backupId': backup_id, 'runCount': run_count, 'stagedAt': staged_at,
                'backupCurrent': backup_current}
    except Exception as error:
        quarantined = quarantine_corrupt_file(path)
        logging.warning('Invalid staged restore marker quarantined=%s: %s', quarantined, error)
        if quarantined is None and path.exists():
            raise RuntimeError('暂存恢复记录损坏且无法安全隔离；请检查文件权限。') from error
        return None


def stage_restore(backup_id, run_count=None, backup_current=True):
    root = _save_backup_path(backup_id)
    _save_manifest(root)
    if run_count is not None and (type(run_count) is not int or not 0 <= run_count <= 99_999_999):
        raise ValueError('Run Count 无效。')
    if type(backup_current) is not bool:
        raise ValueError('恢复备份选项无效。')
    now = datetime.datetime.now().astimezone().isoformat()
    _write_json(_staged_restore_path(), {
        'backupId': backup_id, 'runCount': run_count, 'stagedAt': now,
        'backupCurrent': backup_current,
    })
    return {'staged': True, 'status': 'staged_until_exit', 'backupId': backup_id,
            'stagedAt': now, 'backupCurrent': backup_current}


def cancel_staged_restore():
    path = _staged_restore_path()
    existed = path.exists()
    path.unlink(missing_ok=True)
    return {'cancelled': existed}


def apply_staged_restore():
    pending = staged_restore()
    if pending is None:
        return None
    info = restore_saves(
        pending['backupId'],
        run_count=pending.get('runCount'),
        backup_current=pending.get('backupCurrent', True),
    )
    _staged_restore_path().unlink(missing_ok=True)
    return {'stagedApplied': True, 'backupId': pending['backupId'], 'restore': info}


def _install_snapshot_in_place(source_root, files):
    """Atomically replace snapshot files without ever renaming the save root."""
    save_root = _preparation.SAVES
    save_root.mkdir(parents=True, exist_ok=True)
    for relative, digest in files.items():
        destination = save_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.trainer-save-file-', dir=destination.parent)
        os.close(fd)
        temporary = Path(temporary)
        try:
            shutil.copy2(source_root / relative, temporary)
            if _sha(temporary) != digest:
                raise RuntimeError('暂存存档文件校验失败：' + relative)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
    for item in sorted(save_root.rglob('*'), key=lambda value: len(value.parts), reverse=True):
        relative = str(item.relative_to(save_root))
        if item.is_symlink():
            raise RuntimeError('存档目录包含符号链接；拒绝继续恢复。')
        if item.is_file() and relative not in files:
            item.unlink()
        elif item.is_dir():
            try:
                item.rmdir()
            except OSError:
                pass
    _snapshot_files(save_root, files)


def _temporary_current_snapshot():
    save_root = _preparation.SAVES
    if not save_root.is_dir():
        return None, None
    rollback = Path(tempfile.mkdtemp(prefix='.trainer-save-rollback-', dir=save_root.parent))
    files = {}
    try:
        for source in sorted(save_root.rglob('*')):
            if source.is_symlink():
                raise RuntimeError('存档目录包含符号链接；无法保证恢复回滚。')
            if not source.is_file():
                continue
            relative = source.relative_to(save_root)
            before = _sha(source)
            destination = rollback / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if _sha(destination) != before or _sha(source) != before:
                raise RuntimeError('存档在准备恢复期间改变；请等待同步完成后重试。')
            files[str(relative)] = before
        actual = {str(item.relative_to(save_root)) for item in save_root.rglob('*') if item.is_file()}
        if actual != set(files):
            raise RuntimeError('存档文件集合在准备恢复期间改变；请重试。')
        return rollback, files
    except Exception:
        shutil.rmtree(rollback, ignore_errors=True)
        raise


def restore_saves(backup_id, run_count=None, backup_current=True):
    """Restore a selected verified snapshot without ever renaming the save root."""
    _require_stopped()
    if type(backup_current) is not bool:
        raise ValueError('恢复备份选项无效。')
    if _preparation.SAVES.is_symlink():
        raise RuntimeError('存档目录不能是符号链接。')
    root = _save_backup_path(backup_id)
    manifest = _save_manifest(root)
    previous = {'backed_up': False, 'backupId': None, 'backup': None}
    rollback_root = None
    previous_files = None
    if backup_current:
        previous = backup_saves(run_count=run_count, display_prefix="恢复前自动备份")
        if previous['backed_up']:
            rollback_root = Path(previous['backup'])
            previous_files = _save_manifest(rollback_root)['files']
    else:
        rollback_root, previous_files = _temporary_current_snapshot()
    _preparation.SAVES.parent.mkdir(parents=True, exist_ok=True)
    cleanup_temporary_rollback = not backup_current
    try:
        _require_stopped()
        if previous_files is not None and _preparation.SAVES.exists():
            if previous_files:
                _snapshot_files(_preparation.SAVES, previous_files)
            elif any(item.is_file() for item in _preparation.SAVES.rglob('*')):
                raise RuntimeError('存档文件集合在恢复期间改变；请重试。')
        elif previous_files is None and (_preparation.SAVES.exists() or _preparation.SAVES.is_symlink()):
            raise RuntimeError('存档目录在恢复期间出现；请等待同步完成后重试。')
        try:
            _install_snapshot_in_place(root, manifest['files'])
        except Exception as error:
            if previous_files is not None and rollback_root is not None:
                try:
                    if previous_files:
                        _install_snapshot_in_place(rollback_root, previous_files)
                    else:
                        for item in sorted(_preparation.SAVES.rglob('*'), key=lambda value: len(value.parts), reverse=True):
                            if item.is_file() or item.is_symlink():
                                item.unlink()
                            elif item.is_dir():
                                try: item.rmdir()
                                except OSError: pass
                except Exception as rollback_error:
                    cleanup_temporary_rollback = False
                    preserved = str(rollback_root)
                    raise RuntimeError(f'恢复失败且回滚未完成；原存档保留在 {preserved}：{rollback_error}') from error
                suffix = f'；安全备份 ID：{previous.get("backupId")}' if previous.get('backupId') else ''
                raise RuntimeError(f'恢复失败；原存档已回滚{suffix}：{error}') from error
            raise RuntimeError(f'恢复失败；此前无本地存档：{error}') from error
    finally:
        if cleanup_temporary_rollback and rollback_root is not None:
            shutil.rmtree(rollback_root, ignore_errors=True)
    logging.info(
        'Save restore completed backupId=%s backupCurrent=%s targetFiles=%d previousFiles=%s',
        backup_id, backup_current, len(manifest['files']),
        len(previous_files) if previous_files is not None else None,
    )
    return {'restored': True, 'backupId': backup_id,
            'previousBackupId': previous.get('backupId'), 'fileCount': len(manifest['files'])}
