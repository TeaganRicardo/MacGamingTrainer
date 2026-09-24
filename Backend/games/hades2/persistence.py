"""Small, game-local durable file helpers.

Hades II keeps historical user data outside the generic Core namespace.  The
helpers here deliberately stay game-local until another module proves the same
persistence contract is actually shared.
"""
import os
import tempfile
import time
import uuid
from pathlib import Path


class PersistenceError(RuntimeError):
    code = 'persistence_failed'


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


def quarantine_corrupt_file(path):
    """Move a corrupt user-data file aside without overwriting prior evidence.

    Quarantine is deliberately best-effort.  Callers use it only after they
    have already established that file contents are unusable; a rename failure
    must not turn a recoverable startup/profile-list path into a fatal error.
    """
    path = Path(path)
    if not path.is_file():
        return None
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    destination = path.with_name(
        '{}.corrupt-{}-{}'.format(path.name, stamp, uuid.uuid4().hex[:8])
    )
    try:
        os.replace(str(path), str(destination))
        _fsync_directory(path.parent)
        return destination
    except OSError:
        return None


def atomic_write_text(path, text, *, encoding='utf-8'):
    """Atomically replace *path* with fsynced text in the same directory.

    The temporary file is created beside the destination so os.replace() keeps
    its atomic same-filesystem guarantee.  File contents are fsynced before the
    rename.  A parent-directory fsync is attempted for rename durability, but
    filesystems/platforms that do not support directory fsync are tolerated.
    """
    path = Path(path)
    temp_path = None
    fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=str(path.parent))
        temp_path = Path(temp_name)
        with os.fdopen(fd, 'w', encoding=encoding, newline='') as handle:
            fd = None  # ownership transferred to the file object
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temp_path), str(path))
        temp_path = None
        _fsync_directory(path.parent)
    except Exception as error:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
        if isinstance(error, PersistenceError):
            raise
        raise PersistenceError('无法安全写入本地配置。') from error


def _fsync_directory(directory):
    # The destination has already been atomically replaced when this runs.
    # Directory fsync improves rename durability where supported, but it must
    # remain best-effort: surfacing a post-replace directory-sync failure would
    # tell callers the transaction failed even though the visible file already
    # contains the new state.
    try:
        directory_fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
    finally:
        os.close(directory_fd)
