"""Atomic text replacement for module-owned preferences and profiles.

Callers own serialization, schema compatibility, quarantine and error presentation.
This primitive preserves the original exception when a write cannot be installed;
it does not implement Save transactions or recovery policy.
"""
import os
from pathlib import Path
import tempfile


def atomic_write_text(path, text, *, encoding='utf-8'):
    """Replace *path* with private, fsynced text staged in its own directory.

    A failed write/flush/file sync/replacement leaves the old destination intact.
    Directory sync is best-effort after replacement: a platform's inability to
    sync the directory must not report failure for an already installed document.
    """
    path = Path(path)
    temporary = None
    descriptor = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix='.' + path.name + '.', suffix='.tmp', dir=str(path.parent),
        )
        temporary = Path(name)
        with os.fdopen(descriptor, 'w', encoding=encoding, newline='') as stream:
            descriptor = None  # The stream now owns the descriptor.
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        temporary = None
        fsync_directory(path.parent)
    finally:
        # Cleanup also runs for interruption and fdopen failure. A cleanup error
        # must not replace the error that prevented installing the document.
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def fsync_directory(directory):
    """Attempt directory durability without rejecting a completed replacement."""
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
