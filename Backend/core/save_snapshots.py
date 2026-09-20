from pathlib import Path
import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import uuid

from .save_resolution import ResolvedSaveFile

_SCHEMA_VERSION = 1
_SNAPSHOT_ID_RE = re.compile(r'^snap-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$')
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


class SaveSnapshotError(RuntimeError):
    code = 'snapshot_invalid'


class _SaveSnapshotRace(SaveSnapshotError):
    pass


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise SaveSnapshotError('Snapshot manifest contains an unsafe path.')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or str(path) in ('', '.'):
        raise SaveSnapshotError('Snapshot manifest contains an unsafe path.')
    return path


def _validate_display_name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 96:
        raise ValueError('Snapshot name must contain 1-96 visible characters.')
    value = value.strip()
    if '/' in value or '\\' in value or any(ord(ch) < 32 for ch in value):
        raise ValueError('Snapshot name contains unsafe characters.')
    return value


class SaveSnapshotStore:
    def __init__(self, game_id, data_root):
        self.game_id = game_id
        self.root = Path(data_root) / game_id / 'saves'
        self.snapshots = self.root / 'snapshots'

    def _ensure_parent(self):
        self.snapshots.mkdir(parents=True, exist_ok=True)

    def _new_id(self):
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        return 'snap-{}-{}'.format(stamp, uuid.uuid4().hex[:8])

    def _path_for_id(self, snapshot_id, require_exists=True):
        if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.fullmatch(snapshot_id):
            raise ValueError('Snapshot ID is invalid.')
        self._ensure_parent()
        path = self.snapshots / snapshot_id
        if path.resolve(strict=False).parent != self.snapshots.resolve(strict=False):
            raise SaveSnapshotError('Snapshot path is unsafe.')
        if require_exists:
            if path.is_symlink() or not path.is_dir():
                raise SaveSnapshotError('Snapshot does not exist or is unsafe.')
        return path

    def snapshot_folder(self, snapshot_id):
        return str(self._path_for_id(snapshot_id).resolve())

    def _normalize_sources(self, files):
        unique = {}
        for row in files:
            if not isinstance(row, ResolvedSaveFile):
                raise SaveSnapshotError('Snapshot source set is invalid.')
            if row.source_path.is_symlink() or not row.source_path.is_file():
                raise SaveSnapshotError('Snapshot source is missing or unsafe.')
            relative = _safe_relative(row.relative_path).as_posix()
            key = (row.root_id, relative)
            unique[key] = ResolvedSaveFile(row.root_id, relative, row.source_path)
        if not unique:
            raise SaveSnapshotError('No real save files were found.')
        return [unique[key] for key in sorted(unique)]

    def create_snapshot(self, files, hot=False, display_name=None, resolver=None):
        if type(hot) is not bool:
            raise ValueError('Snapshot hot flag must be boolean.')
        if hot and not callable(resolver):
            raise ValueError('Hot snapshot requires a resolver for stability verification.')
        self._ensure_parent()
        snapshot_id = self._new_id()
        name = _validate_display_name(display_name) if display_name is not None else datetime.datetime.now().astimezone().strftime('%Y-%m-%d %H-%M-%S')
        current = self._normalize_sources(files)
        attempts = 4 if hot else 1
        last_race = None

        for attempt in range(attempts):
            stage = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=str(self.snapshots)))
            try:
                manifest_files = []
                copied_hashes = {}
                for row in current:
                    key = (row.root_id, row.relative_path)
                    before = _sha256(row.source_path)
                    destination = stage / 'files' / row.root_id / _safe_relative(row.relative_path)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(row.source_path, destination)
                    if _sha256(destination) != before:
                        raise _SaveSnapshotRace('Save changed while copying.')
                    if hot and _sha256(row.source_path) != before:
                        raise _SaveSnapshotRace('Save changed while copying.')
                    copied_hashes[key] = before
                    manifest_files.append({
                        'rootId': row.root_id,
                        'relativePath': row.relative_path,
                        'sha256': before,
                        'size': destination.stat().st_size,
                    })

                if hot:
                    after = self._normalize_sources(resolver())
                    if [(row.root_id, row.relative_path) for row in after] != [
                        (row.root_id, row.relative_path) for row in current
                    ]:
                        raise _SaveSnapshotRace('Save file set changed while snapshotting.')
                    for row in after:
                        if _sha256(row.source_path) != copied_hashes[(row.root_id, row.relative_path)]:
                            raise _SaveSnapshotRace('Save changed while verifying snapshot.')

                now = datetime.datetime.now().astimezone().isoformat()
                manifest = {
                    'schemaVersion': _SCHEMA_VERSION,
                    'snapshotId': snapshot_id,
                    'gameId': self.game_id,
                    'createdAt': now,
                    'displayName': name,
                    'hot': hot,
                    'files': manifest_files,
                }
                manifest_path = stage / 'manifest.json'
                with manifest_path.open('w', encoding='utf-8', newline='') as handle:
                    json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                    handle.write('\n')
                    handle.flush()
                    os.fsync(handle.fileno())

                final = self._path_for_id(snapshot_id, require_exists=False)
                os.replace(stage, final)
                stage = None
                return self._row(final, manifest, valid=True)
            except _SaveSnapshotRace as error:
                last_race = error
                if attempt + 1 >= attempts:
                    raise SaveSnapshotError('Save did not become stable during hot backup.') from error
                time.sleep(0.08 * (attempt + 1))
                current = self._normalize_sources(resolver())
            finally:
                if stage is not None:
                    shutil.rmtree(stage, ignore_errors=True)

        raise last_race or SaveSnapshotError('Snapshot creation failed.')

    def _read_manifest(self, root):
        manifest_path = root / 'manifest.json'
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise SaveSnapshotError('Snapshot manifest is missing or unsafe.')
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise SaveSnapshotError('Snapshot manifest cannot be read.') from error
        if not isinstance(manifest, dict):
            raise SaveSnapshotError('Snapshot manifest must be an object.')
        if manifest.get('schemaVersion') != _SCHEMA_VERSION:
            raise SaveSnapshotError('Snapshot schema version is unsupported.')
        if manifest.get('snapshotId') != root.name or manifest.get('gameId') != self.game_id:
            raise SaveSnapshotError('Snapshot identity does not match its location.')
        if not isinstance(manifest.get('createdAt'), str) or not manifest['createdAt']:
            raise SaveSnapshotError('Snapshot createdAt is invalid.')
        _validate_display_name(manifest.get('displayName'))
        if type(manifest.get('hot')) is not bool:
            raise SaveSnapshotError('Snapshot hot flag is invalid.')
        files = manifest.get('files')
        if not isinstance(files, list) or not files:
            raise SaveSnapshotError('Snapshot file manifest is empty or invalid.')

        expected = {}
        for item in files:
            if not isinstance(item, dict):
                raise SaveSnapshotError('Snapshot file manifest is invalid.')
            root_id = item.get('rootId')
            relative = item.get('relativePath')
            digest = item.get('sha256')
            size = item.get('size')
            if not isinstance(root_id, str) or not root_id:
                raise SaveSnapshotError('Snapshot root ID is invalid.')
            relative_path = _safe_relative(relative).as_posix()
            if not isinstance(digest, str) or not _SHA256_RE.fullmatch(digest):
                raise SaveSnapshotError('Snapshot SHA-256 is invalid.')
            if type(size) is not int or size < 0:
                raise SaveSnapshotError('Snapshot file size is invalid.')
            key = (root_id, relative_path)
            if key in expected:
                raise SaveSnapshotError('Snapshot file manifest contains duplicates.')
            expected[key] = (digest, size)

        files_root = root / 'files'
        if files_root.is_symlink() or not files_root.is_dir():
            raise SaveSnapshotError('Snapshot files directory is missing or unsafe.')
        actual = {}
        for item in files_root.rglob('*'):
            if item.is_symlink():
                raise SaveSnapshotError('Snapshot contains a symbolic link.')
            if not item.is_file():
                continue
            relative_to_files = item.relative_to(files_root)
            if len(relative_to_files.parts) < 2:
                raise SaveSnapshotError('Snapshot file is missing a root ID.')
            root_id = relative_to_files.parts[0]
            relative_path = Path(*relative_to_files.parts[1:]).as_posix()
            actual[(root_id, relative_path)] = item
        if set(actual) != set(expected):
            raise SaveSnapshotError('Snapshot file set does not match its manifest.')
        for key, (digest, size) in expected.items():
            path = actual[key]
            if path.stat().st_size != size or _sha256(path) != digest:
                raise SaveSnapshotError('Snapshot file failed integrity verification.')
        return manifest

    def load_verified_snapshot(self, snapshot_id):
        root = self._path_for_id(snapshot_id)
        return {'root': root, 'manifest': self._read_manifest(root)}

    def _row(self, root, manifest, valid, error=''):
        return {
            'id': root.name,
            'name': manifest.get('displayName', root.name) if isinstance(manifest, dict) else root.name,
            'createdAt': manifest.get('createdAt', '') if isinstance(manifest, dict) else '',
            'fileCount': len(manifest.get('files', [])) if isinstance(manifest, dict) and isinstance(manifest.get('files'), list) else 0,
            'hot': bool(manifest.get('hot', False)) if isinstance(manifest, dict) else False,
            'path': str(root.resolve()),
            'valid': valid,
            'error': error,
        }

    def list_snapshots(self):
        self._ensure_parent()
        rows = []
        for root in sorted(self.snapshots.glob('snap-*'), reverse=True):
            if root.is_symlink() or not root.is_dir():
                continue
            manifest = None
            manifest_path = root / 'manifest.json'
            if not manifest_path.is_symlink() and manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
                except (OSError, ValueError):
                    manifest = None
            try:
                verified = self._read_manifest(root)
                rows.append(self._row(root, verified, valid=True))
            except (SaveSnapshotError, ValueError, OSError) as error:
                rows.append(self._row(root, manifest, valid=False, error=str(error)))
        return rows

    def rename_snapshot(self, snapshot_id, display_name):
        name = _validate_display_name(display_name)
        verified = self.load_verified_snapshot(snapshot_id)
        root = verified['root']
        manifest = dict(verified['manifest'])
        manifest['displayName'] = name
        fd, temp_name = tempfile.mkstemp(prefix='.manifest-', suffix='.json', dir=str(root))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as handle:
                json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                handle.write('\n')
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, root / 'manifest.json')
        finally:
            try:
                Path(temp_name).unlink()
            except FileNotFoundError:
                pass
        return self._row(root, manifest, valid=True)

    def delete_snapshot(self, snapshot_id):
        root = self._path_for_id(snapshot_id)
        path = str(root.resolve())
        shutil.rmtree(root)
        if root.exists():
            raise SaveSnapshotError('Snapshot deletion failed.')
        return {'deleted': True, 'id': snapshot_id, 'path': path}
