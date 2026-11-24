"""Hades II persistence errors, schema compatibility and corrupt-file quarantine."""
import logging
from pathlib import Path

from core.errors import PresentableError
from core.persistence import (
    atomic_write_text as _atomic_write_text,
    os,
    quarantine_corrupt_file,
)


class PersistenceError(PresentableError, RuntimeError):
    code = 'persistence_failed'

    def __init__(self, message: str):
        super().__init__(self.code, None, diagnostic=message, message=message)


class UnsupportedSchemaVersionError(PersistenceError):
    code = 'unsupported_schema'

    def __init__(self, kind, found, supported):
        if found > supported:
            message = '{} 使用了更新的数据格式（schemaVersion={}，当前支持 {}），本次读取已拒绝且原文件保持不变。'.format(
                kind, found, supported
            )
        else:
            message = '{} 使用了已不再支持的旧数据格式（schemaVersion={}，当前支持 {}），本次读取已拒绝且原文件保持不变。'.format(
                kind, found, supported
            )
        super().__init__(message)
        self.kind = kind
        self.found = found
        self.supported = supported


__all__ = [
    'PersistenceError',
    'UnsupportedSchemaVersionError',
    'atomic_write_text',
    'migrate_legacy_root_data_dir',
    'os',
    'quarantine_corrupt_file',
]

_LEGACY_ROOT_FILES = ('desired-state.json',)
_LEGACY_ROOT_DIRS = ('profiles', 'backups', 'diagnostics')


def migrate_legacy_root_data_dir(data_dir):
    """Migrate pre-WP4.2 flat root Hades II files and directories into `MacGamingTrainer/hades2/`."""
    target_dir = Path(data_dir)
    if target_dir.name != 'hades2' or target_dir.is_symlink():
        return []
    legacy_root = target_dir.parent
    if not legacy_root.is_dir() or legacy_root.is_symlink():
        return []
    failures = []

    def _move(src: Path, dst: Path) -> None:
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dst)
        except OSError as error:
            failures.append(f'{src.name}: {error}')

    for filename in _LEGACY_ROOT_FILES:
        legacy_file = legacy_root / filename
        target_file = target_dir / filename
        try:
            if (legacy_file.is_file() or legacy_file.is_symlink()) and not (
                target_file.exists() or target_file.is_symlink()
            ):
                _move(legacy_file, target_file)
            for corrupt in sorted(legacy_root.glob(f'{filename}.corrupt-*')):
                dest_corrupt = target_dir / corrupt.name
                if not (dest_corrupt.exists() or dest_corrupt.is_symlink()):
                    _move(corrupt, dest_corrupt)
        except OSError as error:
            failures.append(f'{filename}: {error}')

    for dirname in _LEGACY_ROOT_DIRS:
        legacy_sub = legacy_root / dirname
        target_sub = target_dir / dirname
        try:
            if not legacy_sub.is_dir() or legacy_sub.is_symlink():
                continue
            if not (target_sub.exists() or target_sub.is_symlink()):
                _move(legacy_sub, target_sub)
            elif target_sub.is_dir() and not target_sub.is_symlink():
                for entry in sorted(legacy_sub.iterdir()):
                    dest = target_sub / entry.name
                    if not (dest.exists() or dest.is_symlink()):
                        _move(entry, dest)
                try:
                    if not any(legacy_sub.iterdir()):
                        legacy_sub.rmdir()
                except OSError:
                    pass
        except OSError as error:
            failures.append(f'{dirname}: {error}')

    if failures:
        logging.warning(
            'Could not migrate legacy Hades II data into %s; left files in place: %s',
            target_dir,
            '; '.join(failures),
        )
    return failures


def atomic_write_text(path, text, *, encoding='utf-8'):
    """Keep Hades II's public failure classification at the game boundary."""
    try:
        _atomic_write_text(Path(path), text, encoding=encoding)
    except Exception as error:
        if isinstance(error, PersistenceError):
            raise
        raise PersistenceError('无法安全写入本地配置。') from error
