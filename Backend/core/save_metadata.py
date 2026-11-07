"""Metadata policy for Trainer-owned save copies."""
import errno
import ctypes
import os
from pathlib import Path
import shutil
import stat

_LOCKING_FLAGS = sum(getattr(stat, name, 0) for name in (
    'UF_IMMUTABLE', 'SF_IMMUTABLE', 'UF_APPEND', 'SF_APPEND', 'UF_NOUNLINK', 'SF_NOUNLINK',
))
if hasattr(os, 'chflags'):
    _fchflags = ctypes.CDLL(None, use_errno=True).fchflags
    _fchflags.argtypes = (ctypes.c_int, ctypes.c_uint)
    _fchflags.restype = ctypes.c_int


def _set_flags(descriptor, flags):
    if _fchflags(descriptor, flags) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def copy_save_metadata(source_fd, destination_fd):
    metadata = os.fstat(source_fd)
    os.fchmod(destination_fd, stat.S_IMODE(metadata.st_mode))
    os.utime(destination_fd, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    if hasattr(os, 'listxattr'):
        ignored = {errno.ENOTSUP, errno.ENODATA, errno.EINVAL, errno.EPERM}
        try:
            for name in os.listxattr(source_fd):
                os.setxattr(destination_fd, name, os.getxattr(source_fd, name))
        except OSError as error:
            if error.errno not in ignored:
                raise
    if hasattr(os, 'chflags'):
        _set_flags(destination_fd, metadata.st_flags & ~_LOCKING_FLAGS)


def copy_owned_save_file(source, destination):
    with Path(source).open('rb') as original, Path(destination).open('xb') as copied:
        shutil.copyfileobj(original, copied)
        copied.flush()
        copy_save_metadata(original.fileno(), copied.fileno())


def _clear_owned_locking_flags(descriptor):
    metadata = os.fstat(descriptor)
    if metadata.st_flags & _LOCKING_FLAGS:
        _set_flags(descriptor, metadata.st_flags & ~_LOCKING_FLAGS)
    if not stat.S_ISDIR(metadata.st_mode):
        return
    for name in os.listdir(descriptor):
        item = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if not (stat.S_ISDIR(item.st_mode) or stat.S_ISREG(item.st_mode)):
            continue
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        if stat.S_ISDIR(item.st_mode):
            flags |= os.O_DIRECTORY
        child = os.open(name, flags, dir_fd=descriptor)
        try:
            _clear_owned_locking_flags(child)
        finally:
            os.close(child)


def remove_owned_save_tree(path):
    # Old private copies can carry source flags. Bind every flag change to a
    # non-symlink descriptor so a replaced staging name cannot unlock a target.
    if hasattr(os, 'chflags'):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            _clear_owned_locking_flags(descriptor)
        finally:
            os.close(descriptor)
    shutil.rmtree(path)
