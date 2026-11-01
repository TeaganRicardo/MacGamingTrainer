"""Portable contracts for exact-executable, kernel-version-bound cleanup."""
import ctypes
import errno
from pathlib import Path
import signal
import subprocess
import sys
from unittest.mock import patch

from hades2_debugserver_owner import (
    _AuditToken, _ProcessIdentity, DarwinProcesses, DebugserverOwner,
    debugserver_executable,
)
from hades2_lldb_worker_support import worker_failure_output
import hades2_lldb_worker_support as worker_support


class Function:
    def __init__(self, implementation):
        self.implementation = implementation

    def __call__(self, *arguments):
        return self.implementation(*arguments)


class Kernel:
    def __init__(self):
        self.rows = {}
        self.signals = []
        self.signal_error = 0
        self.proc_listpidspath = Function(self.list_paths)
        self.proc_pidinfo = Function(self.identity)
        self.proc_pidpath_audittoken = Function(self.path)
        self.proc_signal_with_audittoken = Function(self.kill)

    def list_paths(self, kind, uid, path, flags, buffer, size):
        assert kind == 4 and flags == 0, 'inventory must be UID and exact-path scoped'
        assert Path(path.decode()).is_absolute()
        if buffer is not None:
            for index, pid in enumerate(self.rows):
                buffer[index] = pid
        return len(self.rows) * ctypes.sizeof(ctypes.c_int)

    def identity(self, pid, flavor, argument, buffer, size):
        assert flavor == 17 and argument == 0 and size == 56
        ctypes.cast(buffer, ctypes.POINTER(_ProcessIdentity)).contents.pid_version = self.rows[pid][0]
        return size

    def path(self, token_pointer, buffer, size):
        token = ctypes.cast(token_pointer, ctypes.POINTER(_AuditToken)).contents
        row = self.rows.get(token[5])
        if row is None or row[0] != token[7]:
            ctypes.set_errno(errno.ESRCH)
            return 0
        value = str(row[1]).encode()
        assert len(value) < size
        ctypes.memmove(buffer, value + b'\0', len(value) + 1)
        return len(value)

    def kill(self, token_pointer, sig):
        token = ctypes.cast(token_pointer, ctypes.POINTER(_AuditToken)).contents
        self.signals.append((token[5], token[7], sig))
        row = self.rows.get(token[5])
        if row is None or row[0] != token[7]:
            return errno.ESRCH
        if self.signal_error:
            return self.signal_error
        del self.rows[token[5]]
        return 0


kernel = Kernel()
processes = DarwinProcesses(kernel)
assert ctypes.sizeof(_ProcessIdentity) == 56
assert _ProcessIdentity.pid_version.offset == 32
assert ctypes.sizeof(_AuditToken) == 32
owned = Path('/private/tmp/unique/debugserver')
foreign = Path('/private/tmp/another/debugserver')
kernel.rows = {101: (7, owned), 102: (9, foreign)}
tokens = processes.matching(owned)
assert len(tokens) == 1 and (tokens[0][5], tokens[0][7]) == (101, 7)

# Reusing a PID after the path check cannot authorize signaling its new owner.
kernel.rows[101] = (8, foreign)
processes.kill(tokens[0])
assert kernel.rows[101] == (8, foreign)
assert processes.path(tokens[0]) is None
assert kernel.signals == [(101, 7, signal.SIGKILL)]
kernel.rows[101] = (10, owned)
processes.kill(processes.matching(owned)[0])
assert kernel.rows == {102: (9, foreign)}

# The native symbols are required before a worker can launch. No unsupported
# platform may silently replace version-bound signaling with os.kill(pid).
try:
    DarwinProcesses(object())
except RuntimeError as error:
    assert 'Required Darwin lifetime API unavailable' in str(error)
else:
    raise AssertionError('missing kernel identity API was accepted')

missing_signal = Kernel()
del missing_signal.proc_signal_with_audittoken
try:
    DarwinProcesses(missing_signal)
except RuntimeError as error:
    assert 'proc_signal_with_audittoken' in str(error)
else:
    raise AssertionError('missing version-bound signal API was accepted')

owner = DebugserverOwner(sys.executable, processes=processes)
kernel.rows[201] = (11, owner.executable)
with owner:
    assert owner.executable.read_bytes() == Path(sys.executable).read_bytes()
assert not owner.directory.exists()
assert kernel.rows == {102: (9, foreign)}, 'cleanup crossed executable ownership'

owner = DebugserverOwner(sys.executable, processes=processes)
kernel.rows[202] = (12, owner.executable)
interruption = KeyboardInterrupt()
try:
    with owner:
        raise interruption
except KeyboardInterrupt as error:
    assert error is interruption
else:
    raise AssertionError('owner swallowed interruption')
assert not owner.directory.exists() and 202 not in kernel.rows

# A refused cleanup retains executable evidence and the original timeout's
# stdout/stderr and exception identity rather than claiming success.
owner = DebugserverOwner(sys.executable, processes=processes)
kernel.rows[203] = (13, owner.executable)
kernel.signal_error = errno.EPERM
failure = subprocess.TimeoutExpired(['worker'], 30, output=b'last stdout\n', stderr=b'last phase\n')
try:
    try:
        with owner:
            raise failure
    except subprocess.TimeoutExpired as error:
        assert error is failure
        report = worker_failure_output(error)
        assert 'last stdout' in report and 'last phase' in report
        assert str(owner.directory) in report and 'cleanup failed' in report
    assert owner.directory.exists() and 203 in kernel.rows
finally:
    kernel.signal_error = 0
    owner.close()

owner = DebugserverOwner(sys.executable, processes=processes)
kernel.rows[204] = (14, owner.executable)
kernel.signal_error = errno.EPERM
try:
    try:
        with owner:
            pass
    except RuntimeError as error:
        assert 'cleanup failed' in str(error) and str(owner.directory) in str(error)
    else:
        raise AssertionError('cleanup failure was reported as success')
    assert owner.directory.exists()
finally:
    kernel.signal_error = 0
    owner.close()

assert debugserver_executable('/X/LLDB.framework/Resources/Python', {}) == Path('/X/LLDB.framework/Resources/debugserver')
assert debugserver_executable('/unused', {'LLDB_DEBUGSERVER_PATH': '/selected/debugserver'}) == Path('/selected/debugserver')

# Slow preparation consumes the original budget and must not launch a worker
# after that budget expires. The unlaunched owner's cleanup still runs.
clock = [0]
closed = []


class SlowPreparation:
    executable = Path('/private/selected/debugserver')

    def __init__(self, source):
        clock[0] += 6

    def __enter__(self):
        return self

    def __exit__(self, *arguments):
        closed.append(True)


with patch.object(worker_support, 'DebugserverOwner', SlowPreparation), \
     patch.object(worker_support.time, 'monotonic', side_effect=lambda: clock[0]), \
     patch.object(worker_support.subprocess, 'Popen') as launch:
    try:
        worker_support.run_lldb_worker(['worker'], {}, timeout=5, debugserver_path='selected')
    except subprocess.TimeoutExpired as error:
        assert error.timeout == 5 and error.cmd == ['worker']
    else:
        raise AssertionError('preparation reset the worker timeout budget')
    assert not launch.called and closed == [True]
print('debugserver_ownership_ok')
