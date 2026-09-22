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


class SaveSnapshotBusyError(SaveSnapshotError):
    code = 'save_busy'


class SaveNotFoundError(SaveSnapshotError):
    code = 'save_not_found'


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


def _validate_name_details(value):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or len(value) > 4:
        raise ValueError('Snapshot nameDetails must contain at most four strings.')
    details = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > 64:
            raise ValueError('Snapshot nameDetails entries must contain 1-64 visible characters.')
        clean = item.strip()
        if any(ord(ch) < 32 for ch in clean):
            raise ValueError('Snapshot nameDetails contain unsafe characters.')
        details.append(clean)
    return details


def _local_timestamp():
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


class SaveSnapshotStore:
    def __init__(self, game_id, data_root):
        self.game_id = game_id
        self.data_root = Path(data_root)
        self.game_root = self.data_root / game_id
        self.root = self.game_root / 'saves'
        self.snapshots = self.root / 'snapshots'

    def ensure_storage_root(self):
        expected_parent = self.data_root.resolve(strict=False)
        if self.game_root.is_symlink() or self.root.is_symlink():
            raise SaveSnapshotError('Save management storage path cannot be a symbolic link.')
        if self.game_root.resolve(strict=False).parent != expected_parent:
            raise SaveSnapshotError('Save management storage escaped its data root.')
        self.root.mkdir(parents=True, exist_ok=True)
        if self.game_root.is_symlink() or self.root.is_symlink() or not self.root.is_dir():
            raise SaveSnapshotError('Save management storage path is unsafe.')
        if self.game_root.resolve(strict=False).parent != self.data_root.resolve(strict=False):
            raise SaveSnapshotError('Save management storage escaped its data root.')
        return self.root

    def _ensure_parent(self):
        self.ensure_storage_root()
        if self.snapshots.is_symlink():
            raise SaveSnapshotError('Snapshot storage path cannot be a symbolic link.')
        self.snapshots.mkdir(parents=True, exist_ok=True)
        if self.snapshots.is_symlink() or not self.snapshots.is_dir():
            raise SaveSnapshotError('Snapshot storage path is unsafe.')

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
            raise SaveNotFoundError('No real save files were found.')
        return [unique[key] for key in sorted(unique)]

    def create_snapshot(self, resolver, hot=False, display_name=None, name_details=None, created_at=None, describe=None):
        if not callable(resolver):
            raise ValueError('Snapshot creation requires a resolver callback.')
        if type(hot) is not bool:
            raise ValueError('Snapshot hot flag must be boolean.')
        self._ensure_parent()
        snapshot_id = self._new_id()
        created_at = created_at or _local_timestamp()
        if not isinstance(created_at, str) or not created_at or '+' in created_at or created_at.endswith('Z'):
            raise ValueError('Snapshot createdAt must be a local timestamp without timezone.')
        explicit_name = _validate_display_name(display_name) if display_name is not None else None
        explicit_details = _validate_name_details(name_details) if name_details is not None else None
        attempts = 4 if hot else 1

        for attempt in range(attempts):
            current = self._normalize_sources(resolver())
            described_name, described_details = (None, [])
            if describe is not None:
                if not callable(describe):
                    raise ValueError('Snapshot describe callback must be callable.')
                description = describe(tuple(current), created_at)
                if not isinstance(description, (tuple, list)) or len(description) != 2:
                    raise ValueError('Snapshot describe callback must return (name, details).')
                described_name, described_details = description
            name = explicit_name
            if name is None:
                name = _validate_display_name(described_name) if described_name is not None else created_at.replace('T', ' ').replace(':', '-')
            details = explicit_details if explicit_details is not None else _validate_name_details(described_details)
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
                    if _sha256(destination) != before or _sha256(row.source_path) != before:
                        raise _SaveSnapshotRace('Save changed while copying.')
                    copied_hashes[key] = before
                    manifest_files.append({
                        'rootId': row.root_id,
                        'relativePath': row.relative_path,
                        'sha256': before,
                        'size': destination.stat().st_size,
                    })

                after = self._normalize_sources(resolver())
                if [(row.root_id, row.relative_path) for row in after] != [
                    (row.root_id, row.relative_path) for row in current
                ]:
                    raise _SaveSnapshotRace('Save file set changed while snapshotting.')
                for row in after:
                    if _sha256(row.source_path) != copied_hashes[(row.root_id, row.relative_path)]:
                        raise _SaveSnapshotRace('Save changed while verifying snapshot.')

                manifest = {
                    'schemaVersion': _SCHEMA_VERSION,
                    'snapshotId': snapshot_id,
                    'gameId': self.game_id,
                    'createdAt': created_at,
                    'displayName': name,
                    'nameDetails': details,
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
                if not hot or attempt + 1 >= attempts:
                    message = 'Save changed during snapshot creation.' if not hot else 'Save did not become stable during hot backup.'
                    raise SaveSnapshotBusyError(message) from error
                time.sleep(0.08 * (attempt + 1))
            finally:
                if stage is not None:
                    shutil.rmtree(stage, ignore_errors=True)

        raise SaveSnapshotError('Snapshot creation failed.')

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
        manifest['nameDetails'] = _validate_name_details(manifest.get('nameDetails', []))
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
            if item.name == '.DS_Store':
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
        root = self._path_for_id(snapshot_id).resolve()
        return {'root': root, 'manifest': self._read_manifest(root)}

    def _row(self, root, manifest, valid, error=''):
        name = root.name
        created_at = ''
        file_count = 0
        name_details = []
        hot = False

        if isinstance(manifest, dict):
            candidate_name = manifest.get('displayName')
            try:
                name = _validate_display_name(candidate_name)
            except ValueError:
                pass

            candidate_created_at = manifest.get('createdAt')
            if isinstance(candidate_created_at, str):
                created_at = candidate_created_at

            files = manifest.get('files')
            if isinstance(files, list):
                file_count = len(files)

            candidate_hot = manifest.get('hot')
            if type(candidate_hot) is bool:
                hot = candidate_hot

            if valid:
                name_details = _validate_name_details(manifest.get('nameDetails', []))

        return {
            'id': root.name,
            'name': name,
            'createdAt': created_at,
            'fileCount': file_count,
            'nameDetails': name_details,
            'hot': hot,
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
