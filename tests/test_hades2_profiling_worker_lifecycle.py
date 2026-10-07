"""A profiler timeout must terminate the worker's temporary native target too."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from profile_hades2_operations import run_transport_worker

WORKER = r'''
import subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
print(child.pid, flush=True)
try:
    time.sleep(60)
finally:
    child.kill()
    child.wait()
'''


def running(pid):
    result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                            capture_output=True, text=True, check=False)
    # A killed orphan may briefly await OS reaping. It must not keep executing.
    return bool(result.stdout.strip()) and not result.stdout.strip().startswith('Z')


with tempfile.TemporaryDirectory(prefix='mgt-profile-lifetime-') as temporary:
    worker = Path(temporary) / 'worker.py'
    worker.write_text(WORKER)
    child_pid = None
    try:
        try:
            run_transport_worker([sys.executable, str(worker)], dict(os.environ), timeout=1)
        except subprocess.TimeoutExpired as error:
            output = error.stdout
            if isinstance(output, bytes):
                output = output.decode()
            child_pid = int(output.strip())
        else:
            raise AssertionError('profiling worker unexpectedly returned before timeout')
        deadline = time.monotonic() + 2
        while running(child_pid) and time.monotonic() < deadline:
            time.sleep(.01)
        assert not running(child_pid), 'timed-out profiling worker left its target running'
    finally:
        if child_pid is not None and running(child_pid):
            os.kill(child_pid, signal.SIGKILL)

assert run_transport_worker([sys.executable, '-c', 'print("profile-result")'],
                            dict(os.environ), timeout=2).strip() == 'profile-result'
try:
    run_transport_worker([sys.executable, '-c', 'import sys; sys.exit(7)'],
                         dict(os.environ), timeout=2)
except subprocess.CalledProcessError as error:
    assert error.returncode == 7
else:
    raise AssertionError('profiling worker failure was swallowed')

print('hades2_profiling_worker_lifecycle_ok')
