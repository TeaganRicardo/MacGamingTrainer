from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile

from core.adapter import AdapterError
from core.target_probe import BoundedCommandTimeoutError, bounded_run
from .operation_budgets import PROCESS_IDENTITY_TIMEOUT_SECONDS


def _identified_start(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value.isprintable() else None


def process_identity(pid):
    try:
        result = bounded_run(
            ['/bin/ps', '-p', str(pid), '-o', 'lstart='],
            PROCESS_IDENTITY_TIMEOUT_SECONDS,
            text=True,
            check=False,
        )
    except (OSError, BoundedCommandTimeoutError):
        return None
    return _identified_start(result.stdout) if result.returncode == 0 else None


class HadesRecoveryJournal:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def _locked(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # The journal is replaced/unlinked; its lock must keep one stable
            # inode across both old and replacement backend clients.
            with self.path.with_name(self.path.name + '.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
        except OSError as error:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(error)) from error

    def _read(self):
        try:
            pending = json.loads(self.path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as error:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(error)) from error
        if not isinstance(pending, dict) or set(pending) != {'pid', 'identity', 'method'}:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed')
        return pending

    def guard(self, pid, identity):
        with self._locked():
            pending = self._read()
            if pending is None:
                return
            previous_identity = _identified_start(pending['identity'])
            current_identity = _identified_start(identity)
            identified = (type(pid) is int and pid > 0 and type(pending['pid']) is int
                          and pending['pid'] > 0 and current_identity is not None)
            different_lifetime = identified and (
                pending['pid'] != pid or previous_identity is not None and previous_identity != current_identity
            )
            if not different_lifetime:
                raise AdapterError('restart_required', 'hades.error.restartRequired')
            self.path.unlink()

    def begin(self, pid, identity, method):
        pending = {'pid': pid, 'identity': identity, 'method': method}
        with self._locked():
            temporary = None
            try:
                fd, name = tempfile.mkstemp(prefix='.runtime-request-', dir=self.path.parent)
                temporary = Path(name)
                with os.fdopen(fd, 'w') as stream:
                    json.dump(pending, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Only connect's fresh lifetime check may retire an old record.
                # Publish exclusively so an obsolete client cannot replace one.
                os.link(temporary, self.path)
                return pending
            except FileExistsError as error:
                raise AdapterError('restart_required', 'hades.error.restartRequired') from error
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def complete(self, pending):
        with self._locked():
            current = self._read()
            if current is not None and current == pending:
                self.path.unlink()
