"""Opt-in, invocation-scoped LLDB trace for the native attach call."""
from contextlib import contextmanager
import datetime
import logging
import os
from pathlib import Path
import shlex
import tempfile
import time

from core.log_paths import trainer_log_path


_CHANNELS = (('lldb', 'dyld process module state'), ('gdb-remote', 'packets'))


def _command(debugger, lldb, text):
    result = lldb.SBCommandReturnObject()
    debugger.GetCommandInterpreter().HandleCommand(text, result)
    if not result.Succeeded():
        raise RuntimeError(result.GetError() or 'LLDB trace command failed')


def _disable(debugger, lldb, channels):
    for channel, categories in reversed(channels):
        try:
            _command(debugger, lldb, f'log disable {channel} {categories}')
        except Exception as error:
            logging.warning('LLDBAttachTrace disable_failed channel=%s detail=%s', channel, error)


@contextmanager
def attach_trace(debugger, lldb, pid):
    if os.environ.get('MGT_HADES2_ATTACH_TRACE') != '1':
        yield None
        return

    channels = []
    path = None
    try:
        directory = trainer_log_path('hades2').parent
        directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f'lldb-attach-{pid}-', suffix='.trace.log', dir=directory)
        path = Path(name)
        with os.fdopen(fd, 'w') as stream:
            stream.write(f'# LLDBAttachTrace targetPID={pid} workerPID={os.getpid()} '
                         f'utc={datetime.datetime.now(datetime.timezone.utc).isoformat()}')
            stream.write('\n')
        for channel, categories in _CHANNELS:
            channels.append((channel, categories))
            _command(debugger, lldb, 'log enable -h stream -T -p -a -f '
                     + shlex.quote(str(path)) + f' {channel} {categories}')
    except Exception as error:
        _disable(debugger, lldb, channels)
        logging.warning('LLDBAttachTrace unavailable pid=%s path=%s detail=%s', pid, path, error)
        yield None
        return

    started = time.monotonic()
    logging.info('LLDBAttachTrace event=begin pid=%s path=%s', pid, path)
    try:
        yield path
    finally:
        _disable(debugger, lldb, channels)
        logging.info('LLDBAttachTrace event=end pid=%s path=%s duration=%.3fs',
                     pid, path, time.monotonic() - started)
