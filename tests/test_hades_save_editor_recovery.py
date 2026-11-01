"""Selected-file races, verified rollback and outcome-unknown non-replay."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))
sys.path.insert(0, str(ROOT / 'tests/fixtures'))

from hades_save import build_save, environment
from core.save_restore import SaveRestoreTransaction, SaveRestoreError, SaveRollbackError
from games.hades.save_document import HadesSaveDocument
from games.hades.save_workspace import HadesSaveWorkspace


def stage(workspace, *args):
    return workspace.stage(*args, baseline_generation=workspace.baseline_generation)


def apply(workspace):
    return workspace.apply(baseline_generation=workspace.baseline_generation)


def rejects(kind, action):
    try: action()
    except kind as error: return error
    raise AssertionError('Unverified transaction reported success')


def opened(base):
    saves, service = environment(base)
    workspace = HadesSaveWorkspace.open(service, source={'rootId': 'main', 'relativePath': 'Profile1.sav'},
        target={'rootId': 'main', 'relativePath': 'Profile2.sav'})
    stage(workspace, 'resource:MetaPoints', 'set', {'luaType': 'number', 'value': 55})
    return saves, service, workspace


with tempfile.TemporaryDirectory(prefix='mgt-hades-editor-recovery-') as temporary:
    base = Path(temporary)
    saves, service, workspace = opened(base / 'post-verify')
    captured_generation = workspace.baseline_generation
    target = saves / 'Profile2.sav'
    original = target.read_bytes()
    original_load = HadesSaveDocument.load
    unrelated = saves / 'Profile1.sjson'

    def racing_load(cls, path):
        decoded = original_load(path)
        Path(path).write_bytes(build_save(777, 'concurrent-target-writer'))
        unrelated.write_bytes(b'concurrent-unrelated-settings')
        return decoded

    with patch.object(HadesSaveDocument, 'load', classmethod(racing_load)):
        rejects(SaveRestoreError, lambda: apply(workspace))
    assert target.read_bytes() == original
    assert unrelated.read_bytes() == b'concurrent-unrelated-settings'
    assert workspace.review()['count'] == 1
    assert workspace.baseline_generation == captured_generation
    assert workspace.session.recovery_path is None
    assert service.list_state()['recoveryPaths'] == []
    assert len(service.list_state()['snapshots']) == 1

    # Target writes during baseline capture are races, even in pinned mode.
    saves, service, workspace = opened(base / 'capture-race')
    target = saves / 'Profile2.sav'
    original_capture = SaveRestoreTransaction._capture_rollback
    foreign = build_save(888, 'after-baseline')

    def racing_capture(self, *args, **kwargs):
        result = original_capture(self, *args, **kwargs)
        target.write_bytes(foreign)
        return result

    with patch.object(SaveRestoreTransaction, '_capture_rollback', racing_capture):
        rejects(SaveRestoreError, lambda: apply(workspace))
    assert target.read_bytes() == foreign
    assert workspace.review()['count'] == 1

    # The replacement happened, acknowledgement failed, then rollback failed.
    # Retained contained recovery evidence prohibits replay in this workspace.
    saves, service, workspace = opened(base / 'unknown')
    captured_generation = workspace.baseline_generation
    target = saves / 'Profile2.sav'
    original = target.read_bytes()
    real_replace = SaveRestoreTransaction._replace_file
    calls = []

    def lost_ack_and_rollback(self, source, destination, digest, **options):
        if Path(destination) == target.resolve():
            calls.append(str(source))
            if len(calls) == 1:
                real_replace(self, source, destination, digest, **options)
                raise OSError('synthetic lost write acknowledgement')
            raise OSError('synthetic failed rollback')
        return real_replace(self, source, destination, digest, **options)

    with patch.object(SaveRestoreTransaction, '_replace_file', lost_ack_and_rollback):
        failure = rejects(SaveRollbackError, lambda: apply(workspace))
        assert workspace.session.recovery_path == failure.recovery_path
        assert workspace.summary()["recoveryPath"] == failure.recovery_path
        assert workspace.summary()["recoveryUnresolved"] is True
        assert workspace.summary()["recoveryPaths"] == [failure.recovery_path]
        blocked = rejects(ValueError, lambda: apply(workspace))
        assert blocked.code == "rollback_failed"
        assert blocked.recovery_path == failure.recovery_path
        assert len(calls) == 2, 'Uncertain Apply was replayed'
    recovery = Path(failure.recovery_path)
    assert recovery.is_dir() and (recovery / 'files/main/Profile2.sav').read_bytes() == original
    assert str(recovery.resolve()) in service.list_state()['recoveryPaths']
    assert workspace.review()['count'] == 1
    assert workspace.baseline_generation == captured_generation
    # A later Core service discovers evidence without restoring or deleting it.
    from core.save_service import CoreSaveService
    reloaded = CoreSaveService('hades', service.spec, base / 'unknown/data', lambda: False)
    assert str(recovery.resolve()) in reloaded.list_state()['recoveryPaths']
    assert recovery.is_dir()

print('hades_save_editor_races_rollback_and_non_replay_ok')
