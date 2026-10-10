"""Parent-owned lifetime for temporary Hades LLDB fixture workers.

This module can load under any Python ABI; native LLDB imports stay in the worker.
"""
import os
import signal
import subprocess
from contextlib import contextmanager
import json
import time

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
    return decoded(error.stdout) + decoded(error.stderr)


def run_lldb_worker(command, environment, timeout, *, diagnostics=False):
    # A killed/interrupted worker cannot run its Python finally to clean up its
    # native target. Own the whole temporary process group from the parent.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=environment, start_new_session=True) as worker:
        try:
            stdout, stderr = worker.communicate(timeout=timeout)
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
