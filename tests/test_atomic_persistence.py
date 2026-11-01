"""Shared durable replacement and game-owned preference/profile failure semantics."""
from contextlib import contextmanager, ExitStack
import errno
import json
import logging
import os
from pathlib import Path
import stat
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Backend'))

from core import persistence
from core.adapter import AdapterError
from games.hades.preferences import HadesPreferenceStore
from games.hades.profiles import HadesProfileStore
from games.hades.schema import DEFAULT_PREFERENCES
from games.hades2.persistence import PersistenceError
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService


@contextmanager
def fail_write_stage(stage, error):
    """Fail actual filesystem seams while retaining the real temporary stream."""
    real_fdopen = os.fdopen
    descriptors = []

    class Stream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *arguments):
            return self.stream.__exit__(*arguments)

        def write(self, text):
            if stage == 'write':
                self.stream.write(text[:1])
                raise error
            return self.stream.write(text)

        def flush(self):
            if stage == 'flush':
                raise error
            return self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    def fdopen(descriptor, *arguments, **keywords):
        descriptors.append(descriptor)
        if stage == 'open':
            raise error
        return Stream(real_fdopen(descriptor, *arguments, **keywords))

    with ExitStack() as patches:
        patches.enter_context(patch.object(persistence.os, 'fdopen', side_effect=fdopen))
        if stage == 'sync':
            patches.enter_context(patch.object(persistence.os, 'fsync', side_effect=error))
        if stage == 'replace':
            patches.enter_context(patch.object(persistence.os, 'replace', side_effect=error))
        yield descriptors


def assert_closed(descriptors):
    assert descriptors, 'failure did not reach the temporary file'
    for descriptor in descriptors:
        try:
            os.fstat(descriptor)
        except OSError as error:
            assert error.errno == errno.EBADF
        else:
            raise AssertionError('temporary descriptor leaked')


with tempfile.TemporaryDirectory(prefix='mgt-atomic-persistence-') as directory:
    root = Path(directory)
    destination = root / 'settings.txt'
    destination.write_text('old', encoding='utf-8')
    destination.chmod(0o644)
    events = []
    real_fsync, real_replace = os.fsync, os.replace

    def synced(descriptor):
        kind = 'directory' if stat.S_ISDIR(os.fstat(descriptor).st_mode) else 'file'
        events.append(kind)
        return real_fsync(descriptor)

    def replaced(source, target):
        source, target = Path(source), Path(target)
        assert source.parent == target.parent == destination.parent
        assert source.read_text(encoding='utf-8') == '新的配置\n'
        assert target.read_text(encoding='utf-8') == 'old'
        assert stat.S_IMODE(source.stat().st_mode) == 0o600
        assert events == ['file'], 'replacement preceded the successful file sync'
        events.append('replace')
        return real_replace(source, target)

    with patch.object(persistence.os, 'fsync', side_effect=synced), \
            patch.object(persistence.os, 'replace', side_effect=replaced):
        persistence.atomic_write_text(destination, '新的配置\n')
    assert events == ['file', 'replace', 'directory']
    assert destination.read_bytes() == '新的配置\n'.encode('utf-8')
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert list(root.glob('.*.tmp')) == []
    first_run = root / 'new/parent/settings.txt'
    persistence.atomic_write_text(first_run, 'first')
    assert first_run.read_text() == 'first'

    for stage in ('open', 'write', 'flush', 'sync', 'replace'):
        before = destination.read_bytes()
        failure = OSError('injected ' + stage)
        with fail_write_stage(stage, failure) as descriptors:
            try:
                persistence.atomic_write_text(destination, 'replacement')
            except OSError as error:
                assert error is failure, 'Core replaced the original filesystem error'
            else:
                raise AssertionError(stage + ' failure was swallowed')
        assert_closed(descriptors)
        assert destination.read_bytes() == before
        assert list(root.glob('.*.tmp')) == [], stage

    # Interruption still releases both the descriptor and staged partial bytes.
    interruption = KeyboardInterrupt()
    with fail_write_stage('write', interruption) as descriptors:
        try:
            persistence.atomic_write_text(destination, 'interrupted')
        except KeyboardInterrupt as error:
            assert error is interruption
        else:
            raise AssertionError('interrupted write returned success')
    assert_closed(descriptors)
    assert destination.read_bytes() == before
    assert list(root.glob('.*.tmp')) == []

    # Directory failures happen after installation and cannot turn a successful
    # write into an apparent failed action. File sync remains mandatory.
    real_open, real_close = os.open, os.close
    for failing_phase in ('open', 'sync', 'close'):
        directory_events = []

        def open_directory(path, *arguments, **keywords):
            if Path(path) == destination.parent:
                directory_events.append('open')
                if failing_phase == 'open':
                    raise OSError('directory open unavailable')
            return real_open(path, *arguments, **keywords)

        def sync_directory(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_events.append('sync')
                if failing_phase == 'sync':
                    raise OSError('directory sync unavailable')
            return real_fsync(descriptor)

        def close_directory(descriptor):
            is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
            result = real_close(descriptor)
            if is_directory:
                directory_events.append('close')
                if failing_phase == 'close':
                    raise OSError('directory close failed')
            return result

        with patch.object(persistence.os, 'open', side_effect=open_directory), \
                patch.object(persistence.os, 'fsync', side_effect=sync_directory), \
                patch.object(persistence.os, 'close', side_effect=close_directory):
            persistence.atomic_write_text(destination, failing_phase)
        assert destination.read_text() == failing_phase
        assert directory_events == (['open'] if failing_phase == 'open' else ['open', 'sync', 'close'])
        assert list(root.glob('.*.tmp')) == []

    hades_preferences = HadesPreferenceStore(root / 'hades/preferences.json')
    hades_profiles = HadesProfileStore(root / 'hades/profiles')
    hades2_preferences = Hades2PreferenceStore(root / 'hades2/desired-state.json')
    hades2_profiles = Hades2ProfileService(root / 'hades2/profiles')
    desired = {**DEFAULT_PREFERENCES, 'invincibility': True}
    desired2 = {**hades2_preferences.defaults(), 'invincibility': True}
    cases = (
        (hades_preferences.path, lambda value: hades_preferences.save(value),
         hades_preferences.load, desired, AdapterError, 'preferences_failed'),
        (hades_profiles.path('战斗'), lambda value: hades_profiles.save('战斗', value),
         lambda: hades_profiles.load('战斗'), desired, AdapterError, 'profile_write_failed'),
        (hades2_preferences.path, lambda value: hades2_preferences.save(value),
         lambda: hades2_preferences.load()[0], desired2, PersistenceError, 'persistence_failed'),
        (hades2_profiles.path('战斗'), lambda value: hades2_profiles.save('战斗', value),
         lambda: hades2_profiles.load('战斗')['desired'], desired2, PersistenceError, 'persistence_failed'),
    )
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        for path, save, load, value, error_type, error_code in cases:
            save(value)
            assert load() == value
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            baseline = path.read_bytes()
            for stage in ('write', 'flush', 'sync', 'replace'):
                failure = OSError('injected ' + stage)
                with fail_write_stage(stage, failure) as descriptors:
                    try:
                        save({**value, 'invincibility': False})
                    except error_type as error:
                        assert error.code == error_code
                        assert error.__cause__ is failure
                    else:
                        raise AssertionError((path, stage, 'write failure was swallowed'))
                assert_closed(descriptors)
                assert path.read_bytes() == baseline, (path, stage)
                assert load() == value
                assert list(path.parent.glob('.*.tmp')) == []
            save({**value, 'invincibility': False})
            assert load()['invincibility'] is False

        # Game serializers retain their exact existing formatting contracts.
        document = json.loads(hades_preferences.path.read_text())
        assert hades_preferences.path.read_bytes() == json.dumps(document, allow_nan=False).encode('utf-8')
        document = json.loads(hades_profiles.path('战斗').read_text())
        assert hades_profiles.path('战斗').read_bytes() == json.dumps(
            document, ensure_ascii=False, allow_nan=False,
        ).encode('utf-8')
        for path in (hades2_preferences.path, hades2_profiles.path('战斗')):
            document = json.loads(path.read_text())
            assert path.read_bytes() == (json.dumps(
                document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False,
            ) + '\n').encode('utf-8')
    finally:
        logging.disable(previous_logging)

print('atomic_persistence_ok')
