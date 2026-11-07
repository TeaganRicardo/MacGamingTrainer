"""A Core Save transaction that fails before changing a real file has a known outcome.

Staging a temporary file in the save directory is not a mutation. When it
fails (a locked or permission-restricted folder) the save set is untouched, so
the transaction must not run a rollback that fails the same way, retain
recovery evidence, leave the staged restore indeterminate or lock the editor.
A failure after a real replacement still rolls back. Temporary roots only.
"""
import errno
import hashlib
import logging
import os
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
logging.disable(logging.CRITICAL)

from core.module_manifest import SaveManagementSpec, SaveRootSpec  # noqa: E402
from core.save_restore import SaveRestoreError, SaveRollbackError  # noqa: E402
from core.save_service import CoreSaveService  # noqa: E402
from core.structured_save_edit import StructuredSaveEditSession  # noqa: E402

REAL_OPEN = os.open


def refuse_staging(only=None):
    """Refuse temporary save-file creation: every one, or only the `only`-th."""
    attempts = []

    def opener(path, flags, *args, **kwargs):
        if isinstance(path, str) and path.startswith('.trainer-save-'):
            attempts.append(path)
            if only is None or len(attempts) - 1 == only:
                raise PermissionError(errno.EACCES, 'Permission denied', path)
        return REAL_OPEN(path, flags, *args, **kwargs)
    return opener


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BytesCodec:
    def decode(self, data):
        return bytearray(data)

    def encode(self, document):
        return bytes(document)

    def load(self, path):
        return bytearray(Path(path).read_bytes())


def service_for(base, include=('*.sav',)):
    saves = base / 'saves'
    saves.mkdir()
    spec = SaveManagementSpec(roots=(SaveRootSpec('main', str(saves), include),), provider=None,
                              hot_backup=False, restore_policy='stoppedOnly', staged_restore=True)
    running = {'value': False}
    return CoreSaveService('example', spec, base / 'data', lambda: running['value']), saves, running


# Staged restore: refused staging is an ordinary failure and stays pending.
with tempfile.TemporaryDirectory(prefix='mgt-premutation-') as directory:
    service, saves, running = service_for(Path(directory))
    (saves / 'Profile1.sav').write_bytes(b'snapshot-bytes')
    snapshot = service.backup()
    (saves / 'Profile1.sav').write_bytes(b'current-bytes')
    before = digest(saves / 'Profile1.sav')
    running['value'] = True
    assert service.restore(snapshot['id']).get('staged') is True
    running['value'] = False
    os.open = refuse_staging()
    try:
        service.apply_staged()
    except SaveRollbackError as error:
        raise AssertionError('an untouched save set was reported as a failed rollback') from error
    except SaveRestoreError:
        pass
    else:
        raise AssertionError('refused staging was reported as a successful restore')
    finally:
        os.open = REAL_OPEN
    assert digest(saves / 'Profile1.sav') == before
    state = service.list_state()
    assert state['pendingRestore'] and not state['pendingRestore'].get('indeterminate'), state['pendingRestore']
    assert not state['recoveryPaths'], state['recoveryPaths']
    service.apply_staged()
    assert (saves / 'Profile1.sav').read_bytes() == b'snapshot-bytes', 'the retained instruction did not retry'

# Structured editor: refused staging leaves the session retryable.
with tempfile.TemporaryDirectory(prefix='mgt-premutation-') as directory:
    service, saves, _ = service_for(Path(directory))
    (saves / 'Profile1.sav').write_bytes(b'current-bytes')
    target = {'rootId': 'main', 'relativePath': 'Profile1.sav'}
    session = StructuredSaveEditSession.open(service, target, BytesCodec(), target=target)
    session.document = bytearray(b'edited-bytes')
    os.open = refuse_staging()
    try:
        session.apply()
    except SaveRollbackError as error:
        raise AssertionError('an untouched editor target was reported as a failed rollback') from error
    except Exception:
        pass
    else:
        raise AssertionError('refused staging was reported as a successful Apply')
    finally:
        os.open = REAL_OPEN
    assert (saves / 'Profile1.sav').read_bytes() == b'current-bytes'
    session.apply()
    assert (saves / 'Profile1.sav').read_bytes() == b'edited-bytes', 'the editor session was locked'

# A real replacement followed by a failure still rolls back every file.
with tempfile.TemporaryDirectory(prefix='mgt-premutation-') as directory:
    service, saves, _ = service_for(Path(directory))
    for name, data in (('Profile1.sav', b'one-snapshot'), ('Profile2.sav', b'two-snapshot')):
        (saves / name).write_bytes(data)
    snapshot = service.backup()
    for name, data in (('Profile1.sav', b'one-current'), ('Profile2.sav', b'two-current')):
        (saves / name).write_bytes(data)
    os.open = refuse_staging(only=1)
    try:
        service.restore(snapshot['id'])
    except SaveRollbackError as error:
        raise AssertionError('rollback after a partial restore did not complete') from error
    except SaveRestoreError as error:
        assert 'rolled back' in str(error), error
    else:
        raise AssertionError('a partially failed restore was reported as success')
    finally:
        os.open = REAL_OPEN
    assert (saves / 'Profile1.sav').read_bytes() == b'one-current'
    assert (saves / 'Profile2.sav').read_bytes() == b'two-current'

print('core_save_premutation_failure_ok')
