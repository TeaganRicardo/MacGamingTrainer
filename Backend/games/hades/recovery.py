import json
import os
from pathlib import Path
import subprocess
import tempfile

from core.adapter import AdapterError


def process_identity(pid):
    result = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'lstart='],
                            capture_output=True, text=True, check=False)
    return result.stdout.strip()


class HadesRecoveryJournal:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else (
            Path.home() / 'Library/Application Support/MacGamingTrainer/hades/runtime-request.json')

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
