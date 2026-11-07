"""Metadata policy for Trainer-owned save copies."""
import errno
import os
from pathlib import Path
import shutil
import stat

_LOCKING_FLAGS = sum(getattr(stat, name, 0) for name in (
    'UF_IMMUTABLE', 'SF_IMMUTABLE', 'UF_APPEND', 'SF_APPEND', 'UF_NOUNLINK', 'SF_NOUNLINK',
))


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
    if hasattr(os, 'fchflags'):
        os.fchflags(destination_fd, metadata.st_flags & ~_LOCKING_FLAGS)


def copy_owned_save_file(source, destination):
    with Path(source).open('rb') as original, Path(destination).open('xb') as copied:
        shutil.copyfileobj(original, copied)
        copied.flush()
        copy_save_metadata(original.fileno(), copied.fileno())


def remove_owned_save_tree(path):
    # Only callers with a contained private staging/rollback directory use this.
    # Old copies may already carry flags copied by earlier Trainer builds.
    if hasattr(os, 'chflags'):
        for directory, directories, files in os.walk(path, followlinks=False):
            for candidate in (Path(directory), *(Path(directory) / name for name in directories + files)):
                if not candidate.is_symlink():
                    flags = candidate.stat().st_flags
                    if flags & _LOCKING_FLAGS:
                        os.chflags(candidate, flags & ~_LOCKING_FLAGS)
    shutil.rmtree(path)
