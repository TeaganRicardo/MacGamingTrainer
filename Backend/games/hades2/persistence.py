"""Hades II persistence errors, schema compatibility and corrupt-file quarantine."""
import os
import time
import uuid
from pathlib import Path

from core.persistence import atomic_write_text as _atomic_write_text, fsync_directory


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
        fsync_directory(path.parent)
        return destination
    except OSError:
        return None


def atomic_write_text(path, text, *, encoding='utf-8'):
    """Keep Hades II's public failure classification at the game boundary."""
    try:
        _atomic_write_text(path, text, encoding=encoding)
    except Exception as error:
        if isinstance(error, PersistenceError):
            raise
        raise PersistenceError('无法安全写入本地配置。') from error
