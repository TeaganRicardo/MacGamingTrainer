"""Parent-owned lifetime for temporary Hades LLDB fixture workers.

This module can load under any Python ABI; native LLDB imports stay in the worker.
"""
import os
import signal
import subprocess


def run_lldb_worker(command, environment, timeout):
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
            try:
                os.killpg(worker.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            worker.wait()
