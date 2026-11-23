import json
import os
from pathlib import Path
import tempfile

from core.adapter import AdapterError
from core.target_probe import bounded_run
from .operation_budgets import PROCESS_IDENTITY_TIMEOUT_SECONDS


def process_identity(pid):
    result = bounded_run(
        ['/bin/ps', '-p', str(pid), '-o', 'lstart='],
        PROCESS_IDENTITY_TIMEOUT_SECONDS,
        text=True,
        check=False,
    )
    return result.stdout.strip()


class HadesRecoveryJournal:
    def __init__(self, path):
        self.path = Path(path)

    def guard(self, pid, identity):
        try:
            pending = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(error)) from error
        if not isinstance(pending, dict) or set(pending) != {'pid', 'identity', 'method'}:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed')
        if pending['pid'] == pid and pending['identity'] == identity:
            raise AdapterError('restart_required', 'hades.error.restartRequired')
        self.complete()

    def begin(self, pid, identity, method):
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix='.runtime-request-', dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'w') as stream:
                json.dump({'pid': pid, 'identity': identity, 'method': method}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(error)) from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def complete(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError as error:
            raise AdapterError('recovery_failed', 'hades.error.recoveryFailed', diagnostic=str(error)) from error
