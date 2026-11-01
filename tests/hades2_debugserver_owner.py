"""Own escaped native debugserver sessions without changing LLDB's launcher.

Only isolated test/profiling workers use this helper. A private executable copy
identifies this invocation; Darwin audit-token APIs bind path checks and signals
to a PID version in the kernel. There is deliberately no numeric-PID fallback.
"""
import ctypes
import errno
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time


# Apple xnu f6217f891ac0bb64f3d375211650a4c1ff8ca1ea:
# bsd/sys/proc_info_private.h and libsyscall/wrappers/libproc/libproc.{h,c}.
class _ProcessIdentity(ctypes.Structure):
    _fields_ = [
        ('uuid', ctypes.c_ubyte * 16),
        ('unique_id', ctypes.c_uint64),
        ('parent_unique_id', ctypes.c_uint64),
        ('pid_version', ctypes.c_int32),
        ('parent_pid_version', ctypes.c_int32),
        ('reserved2', ctypes.c_uint64),
        ('reserved3', ctypes.c_uint64),
    ]


_AuditToken = ctypes.c_uint32 * 8


class DarwinProcesses:
    def __init__(self, library=None):
        if ctypes.sizeof(_ProcessIdentity) != 56:
            raise RuntimeError('Unsupported Darwin process identity layout')
        self.library = library if library is not None else ctypes.CDLL(
            '/usr/lib/libproc.dylib', use_errno=True,
        )
        signatures = {
            'proc_listpidspath': [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_char_p,
                                 ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int],
            'proc_pidinfo': [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                             ctypes.c_void_p, ctypes.c_int],
            'proc_pidpath_audittoken': [ctypes.POINTER(_AuditToken), ctypes.c_void_p, ctypes.c_uint32],
            'proc_signal_with_audittoken': [ctypes.POINTER(_AuditToken), ctypes.c_int],
        }
        for name, arguments in signatures.items():
            try:
                function = getattr(self.library, name)
            except AttributeError as error:
                raise RuntimeError('Required Darwin lifetime API unavailable: ' + name) from error
            function.argtypes = arguments
            function.restype = ctypes.c_int

    @staticmethod
    def _error(operation):
        code = ctypes.get_errno() or errno.EIO
        return OSError(code, operation + ': ' + os.strerror(code))

    def path(self, token):
        buffer = ctypes.create_string_buffer(4096)
        ctypes.set_errno(0)
        length = self.library.proc_pidpath_audittoken(ctypes.byref(token), buffer, len(buffer))
        if length > 0:
            return Path(os.fsdecode(buffer.value)).resolve()
        if ctypes.get_errno() in (errno.ESRCH, errno.ENOENT):
            return None
        raise self._error('read token-bound executable path')

    def matching(self, executable):
        # PROC_UID_ONLY=4 restricts this exact-vnode query to the current user.
        arguments = (4, os.getuid(), os.fsencode(executable), 0)
        ctypes.set_errno(0)
        size = self.library.proc_listpidspath(*arguments, None, 0)
        if size < 0:
            raise self._error('size owned debugserver inventory')
        processes = (ctypes.c_int * (size // ctypes.sizeof(ctypes.c_int) + 32))()
        size = ctypes.sizeof(processes)
        amount = self.library.proc_listpidspath(*arguments, processes, size)
        if amount < 0:
            raise self._error('read owned debugserver inventory')
        if amount >= size or amount % ctypes.sizeof(ctypes.c_int):
            raise RuntimeError('Owned debugserver inventory was truncated')
        matches = []
        for pid in set(processes[:amount // ctypes.sizeof(ctypes.c_int)]):
            identity = _ProcessIdentity()
            ctypes.set_errno(0)
            amount = self.library.proc_pidinfo(pid, 17, 0, ctypes.byref(identity), ctypes.sizeof(identity))
            if amount != ctypes.sizeof(identity):
                if ctypes.get_errno() == errno.ESRCH:
                    continue
                raise self._error('read debugserver process identity')
            token = _AuditToken()
            # These APIs use only the token's PID and version for identity;
            # signal permission is checked against the actual calling process.
            token[5], token[7] = pid, identity.pid_version
            if self.path(token) == executable:
                matches.append(token)
        return matches

    def kill(self, token):
        result = self.library.proc_signal_with_audittoken(ctypes.byref(token), signal.SIGKILL)
        if result not in (0, errno.ESRCH):
            raise OSError(result, 'signal owned debugserver pid={} version={}: {}'.format(
                token[5], token[7], os.strerror(result),
            ))


def debugserver_executable(lldb_python_path, environment):
    # Xcode's `lldb -P` names LLDB.framework/Resources/Python; the sibling
    # support executable is also LLDB's own default resolution. Honor overrides.
    return Path(environment.get('LLDB_DEBUGSERVER_PATH') or
                Path(lldb_python_path).parent / 'debugserver')


class DebugserverOwner:
    def __init__(self, executable, *, processes=None):
        self.processes = processes if processes is not None else DarwinProcesses()
        source = Path(executable).resolve(strict=True)
        if not source.is_file() or not os.access(source, os.X_OK):
            raise RuntimeError('Debugserver is not an executable file: ' + str(source))
        self.directory = Path(tempfile.mkdtemp(prefix='mgt-debugserver-')).resolve()
        self.executable = self.directory / 'debugserver'
        try:
            # Copy the signed native bytes unchanged; LLDB still launches and
            # monitors the actual debugserver and retains all original arguments.
            shutil.copy2(source, self.executable)
        except BaseException:
            shutil.rmtree(self.directory)
            raise

    def __enter__(self):
        return self

    def close(self):
        # The worker and its ordinary group have already been terminated/reaped,
        # so no new LLDB launch can acquire this private executable.
        tokens = self.processes.matching(self.executable)
        for token in tokens:
            self.processes.kill(token)
        deadline = time.monotonic() + 2
        pending = tokens
        while pending:
            pending = [token for token in pending if self.processes.path(token) == self.executable]
            if not pending:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Owned debugserver did not exit after cleanup')
            time.sleep(.01)
        if self.processes.matching(self.executable):
            raise RuntimeError('Owned debugserver appeared during cleanup')
        shutil.rmtree(self.directory)

    def __exit__(self, exception_type, exception, traceback):
        try:
            self.close()
        except Exception as error:
            # Keep the executable available to identify any surviving process.
            detail = 'debugserver cleanup failed; retained {}: {}'.format(self.directory, error)
            if exception is None:
                raise RuntimeError(detail) from error
            exception.debugserver_cleanup_error = detail
            print(detail, file=sys.stderr, flush=True)
        return False
