"""Parent-owned lifetime for temporary Hades LLDB fixture workers.

This module can load under any Python ABI; native LLDB imports stay in the worker.
"""
import os
import signal
import subprocess
from contextlib import contextmanager, nullcontext
import json
import time

from hades2_debugserver_owner import DebugserverOwner

_PHASE_STARTED = time.monotonic()


@contextmanager
def phase(name, *, enabled=True):
    """Flush the current native-test phase before entering a blocking API."""
    if not enabled:
        yield
        return
    started = time.monotonic()

    def emit(event):
        print('lldb_phase ' + json.dumps({
            'phase': name, 'event': event,
            'elapsed': round(time.monotonic() - _PHASE_STARTED, 3),
            'duration': round(time.monotonic() - started, 3),
        }), flush=True)

    emit('begin')
    try:
        yield
    except BaseException:
        emit('failed')
        raise
    else:
        emit('end')


def worker_failure_output(error):
    # TimeoutExpired retains bytes even when Popen requested text mode. Preserve
    # both streams so the outer assertion identifies the last flushed phase.
    def decoded(output):
        return output.decode('utf-8', errors='replace') if isinstance(output, bytes) else output or ''
    output = decoded(error.stdout) + decoded(error.stderr)
    cleanup_error = getattr(error, 'debugserver_cleanup_error', None)
    return output + ('\n' + cleanup_error if cleanup_error else '')


def run_lldb_worker(command, environment, timeout, *, diagnostics=False, debugserver_path=None):
    # A killed/interrupted worker cannot run its Python finally to clean up its
    # native target. Own the whole temporary process group from the parent.
    deadline = time.monotonic() + timeout
    owner = DebugserverOwner(debugserver_path) if debugserver_path is not None else nullcontext()
    with owner as debugserver:
        worker_environment = dict(environment)
        if debugserver is not None:
            worker_environment['LLDB_DEBUGSERVER_PATH'] = str(debugserver.executable)
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(command, timeout)
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=worker_environment, start_new_session=True) as worker:
            try:
                try:
                    stdout, stderr = worker.communicate(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired as error:
                    # Report the original whole-worker budget, retaining the
                    # exception's captured streams and the final native phase.
                    error.timeout = timeout
                    raise
                if worker.returncode:
                    raise subprocess.CalledProcessError(worker.returncode, command, stdout, stderr)
                return stdout
            finally:
                with phase('cleanup.workerGroup', enabled=diagnostics):
                    try:
                        os.killpg(worker.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    worker.wait()
