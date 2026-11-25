"""Hades II persistence errors, schema compatibility and corrupt-file quarantine."""
import hashlib
import json
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

    def __init__(
        self,
        message: str,
        *,
        presentation: str = 'hades2.error.localWriteFailed',
        arguments=(),
    ):
        super().__init__(
            self.code,
            presentation,
            diagnostic=message,
            arguments=arguments,
            message=message,
        )


class UnsupportedSchemaVersionError(PersistenceError):
    code = 'unsupported_schema'

    def __init__(self, kind, found, supported):
        if found > supported:
            presentation = 'hades2.error.preferenceNewerFormat'
            message = '{} 使用了更新的数据格式（schemaVersion={}，当前支持 {}），本次读取已拒绝且原文件保持不变。'.format(
                kind, found, supported
            )
        else:
            presentation = 'hades2.error.preferenceOlderFormat'
            message = '{} 使用了已不再支持的旧数据格式（schemaVersion={}，当前支持 {}），本次读取已拒绝且原文件保持不变。'.format(
                kind, found, supported
            )
        super().__init__(
            message,
            presentation=presentation,
            arguments=(str(kind), str(found), str(supported)),
        )
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


def _migrate_desired_state(source, destination):
    from .preferences import DESIRED_STATE_SCHEMA_VERSION

    relative_destination = 'hades2/' + destination.name
    pending = destination.parent / ('.legacy-' + destination.name)
    marker = {'schemaVersion': DESIRED_STATE_SCHEMA_VERSION + 1, 'relocatedTo': relative_destination}
    if source.is_symlink() or destination.is_symlink() or pending.is_symlink():
        raise OSError('Desired-state migration paths must not be symbolic links.')
    text = source.read_bytes().decode('utf-8') if source.is_file() else None
    try:
        raw = json.loads(text) if text is not None else None
    except json.JSONDecodeError:
        raw = None
    if isinstance(raw, dict) and set(raw) == {'schemaVersion', 'relocatedTo'} and (
        type(raw['schemaVersion']) is int and raw['relocatedTo'] == relative_destination
    ):
        if not destination.is_file():
            if not pending.is_file():
                raise OSError('Relocated desired-state is missing; original transition marker was preserved.')
            os.replace(pending, destination)
        return

    if destination.is_file():
        # Earlier releases may already have split the two histories. Keep the
        # namespaced state and retain the old root bytes before retiring its path.
        if text is not None:
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            archive = destination.parent / 'legacy-desired-state' / (digest + '.json')
            if not archive.exists():
                _atomic_write_text(archive, text)
    elif text is not None:
        # Publish the old-reader refusal only after the original data is durable.
        # A failed final rename resumes from this copy on the next startup.
        _atomic_write_text(pending, text)
    else:
        return
    _atomic_write_text(source, json.dumps(marker, sort_keys=True) + '\n')
    if not destination.is_file():
        os.replace(pending, destination)


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
            _migrate_desired_state(legacy_file, target_file)
            for corrupt in sorted(legacy_root.glob(f'{filename}.corrupt-*')):
                dest_corrupt = target_dir / corrupt.name
                if not (dest_corrupt.exists() or dest_corrupt.is_symlink()):
                    _move(corrupt, dest_corrupt)
        except (OSError, UnicodeError) as error:
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
