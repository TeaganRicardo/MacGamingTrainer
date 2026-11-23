"""Hades II persistence errors, schema compatibility and corrupt-file quarantine."""
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
    'os',
    'quarantine_corrupt_file',
]


def atomic_write_text(path, text, *, encoding='utf-8'):
    """Keep Hades II's public failure classification at the game boundary."""
    try:
        _atomic_write_text(Path(path), text, encoding=encoding)
    except Exception as error:
        if isinstance(error, PersistenceError):
            raise
        raise PersistenceError('无法安全写入本地配置。') from error
