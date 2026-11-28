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
from core.save_resolution import ResolvedSaveFile  # noqa: E402
from core.save_restore import SaveRestoreError, SaveRollbackError  # noqa: E402
from core.save_service import CoreSaveService  # noqa: E402
from core.structured_save_edit import StructuredSaveEditSession  # noqa: E402

REAL_OPEN = os.open


def refuse_staging(only=None, on_failure=None):
    """Refuse temporary save-file creation: every one, or only the `only`-th."""
    attempts = []

    def opener(path, flags, *args, **kwargs):
        if isinstance(path, str) and path.startswith('.trainer-save-'):
            attempts.append(path)
            if only is None or len(attempts) - 1 == only:
                if on_failure is not None:
                    on_failure()
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
    candidate = bytearray(b'edited-bytes')
    os.open = refuse_staging()
    try:
        session.apply(candidate)
    except SaveRollbackError as error:
        raise AssertionError('an untouched editor target was reported as a failed rollback') from error
    except Exception:
        pass
    else:
        raise AssertionError('refused staging was reported as a successful Apply')
    finally:
        os.open = REAL_OPEN
    assert (saves / 'Profile1.sav').read_bytes() == b'current-bytes'
    session.apply(candidate)
    assert (saves / 'Profile1.sav').read_bytes() == b'edited-bytes', 'the editor session was locked'

# The first replacement is rolled back, preserving a concurrent write to the
# second path, whether the files existed before the restore or not.
for existed in (True, False):
    with tempfile.TemporaryDirectory(prefix='mgt-premutation-') as directory:
        service, saves, _ = service_for(Path(directory))
        first, second = saves / 'Profile1.sav', saves / 'Profile2.sav'
        first.write_bytes(b'one-snapshot')
        second.write_bytes(b'two-snapshot')
        snapshot = service.backup()
        if existed:
            first.write_bytes(b'one-current')
            second.write_bytes(b'two-current')
        else:
            first.unlink()
            second.unlink()

        def concurrent_write():
            assert first.read_bytes() == b'one-snapshot'
            second.write_bytes(b'two-concurrent')

        os.open = refuse_staging(only=1, on_failure=concurrent_write)
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
        if existed:
            assert first.read_bytes() == b'one-current'
        else:
            assert not first.exists()
        assert second.read_bytes() == b'two-concurrent'
        assert not service.list_state()['recoveryPaths']

# Verification must use only the changed paths. If recovery actually fails,
# the surviving process can also identify exactly which targets remain at risk.
for fail_rollback in (False, True):
    with tempfile.TemporaryDirectory(prefix='mgt-premutation-') as directory:
        base = Path(directory)
        service, saves, _ = service_for(base)
        first, second = saves / 'Profile1.sav', saves / 'Profile2.sav'
        first.write_bytes(b'one-snapshot')
        second.write_bytes(b'two-snapshot')
        snapshot = service.backup()
        first.write_bytes(b'one-current')
        second.write_bytes(b'two-current')
        external = base / 'external'
        external.write_bytes(b'two-concurrent')
        attempts = 0

        def fail_after_first_replacement(path, flags, *args, **kwargs):
            global attempts
            if isinstance(path, str) and path.startswith('.trainer-save-'):
                attempts += 1
                if attempts == 2:
                    if fail_rollback:
                        second.write_bytes(b'two-concurrent')
                    else:
                        second.unlink()
                        second.symlink_to(external)
                    raise PermissionError(errno.EACCES, 'Second target rejected staging', path)
                if attempts == 3 and fail_rollback:
                    raise PermissionError(errno.EACCES, 'First target rejected rollback', path)
            return REAL_OPEN(path, flags, *args, **kwargs)

        os.open = fail_after_first_replacement
        try:
            service.restore(snapshot['id'])
        except SaveRollbackError as error:
            assert fail_rollback, error
            recovery = Path(error.recovery_path)
        except SaveRestoreError as error:
            assert not fail_rollback and 'rolled back' in str(error), error
        else:
            raise AssertionError('a partially failed restore was reported as success')
        finally:
            os.open = REAL_OPEN

        assert second.read_bytes() == b'two-concurrent'
        if fail_rollback:
            assert first.read_bytes() == b'one-snapshot'
            assert (recovery / 'files/main/Profile1.sav').read_bytes() == b'one-current'
            replacement = base / 'updated'
            replacement.write_bytes(b'two-edited')
            assert service.replace_files((ResolvedSaveFile('main', second.name, replacement),))['replaced']
            assert second.read_bytes() == b'two-edited'
            try:
                service.replace_files((ResolvedSaveFile('main', first.name, replacement),))
            except SaveRollbackError as error:
                assert Path(error.recovery_path) == recovery
            else:
                raise AssertionError('unresolved target accepted another write')
        else:
            assert first.read_bytes() == b'one-current'
            assert second.is_symlink()
            assert not service.list_state()['recoveryPaths']

print('core_save_premutation_failure_ok')
