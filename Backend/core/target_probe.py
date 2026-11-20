"""macOS target process discovery via `proc_pidpath` and bounded subprocesses."""

from __future__ import annotations

import ctypes
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Collection, Mapping, NamedTuple, Optional, Sequence

from core.save_restore import SaveBusyError

TARGET_QUERY_TIMEOUT_SECONDS = 2.0


class BoundedCommandTimeoutError(RuntimeError):
    """Subprocess exceeded its configured runtime budget."""

    def __init__(self, argv: Sequence[str], budget: float) -> None:
        self.argv = tuple(argv)
        self.budget = float(budget)
        program = self.argv[0] if self.argv else 'subprocess'
        super().__init__(f'{program} 超时（{self.budget:g} 秒）；操作结果需重新检查。')


class AmbiguousTargetError(RuntimeError):
    """Multiple running processes matched a single target identity."""


class LocatedTarget(NamedTuple):
    pid: int
    executable_path: Path
    bundle_path: Optional[Path]


def bounded_run(
    argv: Sequence[str],
    budget: float,
    *,
    text: bool = False,
    capture_output: bool = True,
    stdout: Optional[int] = None,
    stderr: Optional[int] = None,
    check: bool = False,
    allowed: Optional[Collection[int]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> subprocess.CompletedProcess[Any]:
    """Run `argv` without shell expansion under a hard timeout budget."""
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget <= 0:
        raise ValueError('bounded_run requires a positive numeric budget.')
    command = [str(part) for part in argv]
    run_kwargs: dict[str, Any] = {
        'timeout': float(budget),
        'shell': False,
        'text': text,
        'check': False,
    }
    if env is not None:
        run_kwargs['env'] = dict(env)
    if stdout is not None or stderr is not None:
        run_kwargs['stdout'] = stdout
        run_kwargs['stderr'] = stderr
    else:
        run_kwargs['capture_output'] = capture_output
    try:
        result = subprocess.run(command, **run_kwargs)
    except subprocess.TimeoutExpired as error:
        raise BoundedCommandTimeoutError(command, float(budget)) from error
    if allowed is not None:
        if result.returncode not in allowed:
            raise subprocess.CalledProcessError(
                result.returncode,
                command,
                output=getattr(result, 'stdout', None),
                stderr=getattr(result, 'stderr', None),
            )
    elif check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            command,
            output=getattr(result, 'stdout', None),
            stderr=getattr(result, 'stderr', None),
        )
    return result


def process_executable_path(pid: int) -> Optional[str]:
    """Return the kernel-reported executable path for a PID on macOS."""
    if sys.platform != 'darwin':
        return None
    try:
        libproc = ctypes.CDLL('/usr/lib/libproc.dylib')
        proc_pidpath = libproc.proc_pidpath
        proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        length = proc_pidpath(pid, buffer, len(buffer))
    except (OSError, AttributeError):
        return None
    if length <= 0:
        return None
    return str(Path(os.fsdecode(buffer.value)).resolve())


def enclosing_app_bundle(executable_path: Path) -> Optional[Path]:
    """Return the enclosing `<Name>.app` bundle directory for an executable, if any."""
    resolved = executable_path.resolve()
    if (
        resolved.parent.name == 'MacOS'
        and resolved.parent.parent.name == 'Contents'
        and resolved.parent.parent.parent.name.endswith('.app')
    ):
        return resolved.parent.parent.parent
    return None


def _bundle_identifier(bundle_path: Optional[Path]) -> Optional[str]:
    if bundle_path is None:
        return None
    info_path = bundle_path / 'Contents' / 'Info.plist'
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    value = info.get('CFBundleIdentifier') if isinstance(info, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _bundle_executable_name(bundle_path: Optional[Path]) -> Optional[str]:
    if bundle_path is None:
        return None
    info_path = bundle_path / 'Contents' / 'Info.plist'
    try:
        info = plistlib.loads(info_path.read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException):
        return None
    value = info.get('CFBundleExecutable') if isinstance(info, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def locate_target(
    manifest: Any,
    *,
    timeout: float = TARGET_QUERY_TIMEOUT_SECONDS,
    executable_probe: Optional[Callable[[int], Optional[str]]] = None,
) -> Optional[LocatedTarget]:
    """Locate a single running target matching `manifest` using Host identity rules."""
    process_name = (getattr(manifest, 'process_name', '') or '').strip()
    bundle_identifier = (getattr(manifest, 'bundle_identifier', '') or '').strip()
    executable_path_suffix = (getattr(manifest, 'executable_path_suffix', '') or '').strip().lstrip('/')
    if not bundle_identifier and not executable_path_suffix:
        raise ValueError('Target manifest requires bundle_identifier or executable_path_suffix.')

    probe = process_executable_path if executable_probe is None else executable_probe
    result = bounded_run(
        ['/bin/ps', '-axo', 'pid=,comm='],
        timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=True,
    )
    expected_name = Path(executable_path_suffix).name if executable_path_suffix else process_name
    matches: list[LocatedTarget] = []
    for row in result.stdout.splitlines():
        parts = row.strip().split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1].strip()
        if expected_name:
            command_name = Path(command).name
            truncated_match = len(expected_name) >= 15 and command_name.startswith(expected_name[:15])
            suffix_match = bool(executable_path_suffix) and command.endswith('/' + executable_path_suffix)
            if command_name != expected_name and not truncated_match and not suffix_match:
                continue

        resolved = probe(pid)
        if resolved is None and executable_path_suffix and command.endswith('/' + executable_path_suffix):
            resolved = str(Path(command).resolve())
        if not resolved:
            continue

        executable_path = Path(resolved).resolve()
        executable_text = str(executable_path)
        if executable_path_suffix and not executable_text.endswith('/' + executable_path_suffix):
            continue

        bundle_path = enclosing_app_bundle(executable_path)
        actual_bundle_id = _bundle_identifier(bundle_path)
        if bundle_identifier and not executable_path_suffix:
            if actual_bundle_id != bundle_identifier:
                continue
            if process_name and executable_path.name != process_name:
                if _bundle_executable_name(bundle_path) != process_name:
                    continue
        elif bundle_identifier and actual_bundle_id is not None and actual_bundle_id != bundle_identifier:
            if process_name and executable_path.name != process_name:
                continue

        matches.append(LocatedTarget(pid=pid, executable_path=executable_path, bundle_path=bundle_path))

    if len(matches) > 1:
        label = process_name or bundle_identifier or executable_path_suffix
        raise AmbiguousTargetError(f'检测到多个 {label} 进程，请保留一个。')
    return matches[0] if matches else None


def target_process_running(process_name: str, executable_path_suffix: str = '') -> bool:
    """Return whether a target game executable is running on Darwin."""
    if not process_name:
        return False
    # macOS `ps -o comm` prints each executable path; the kernel name that
    # `pgrep` compares is truncated to MAXCOMLEN and cannot identify long names.
    try:
        result = bounded_run(
            ['/bin/ps', '-axo', 'comm='],
            TARGET_QUERY_TIMEOUT_SECONDS,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError, BoundedCommandTimeoutError) as error:
        raise SaveBusyError('无法确认目标游戏是否正在运行，请稍后重试。') from error
    executables = [row.strip() for row in result.stdout.splitlines()]
    if executable_path_suffix:
        return any(executable.endswith('/' + executable_path_suffix) for executable in executables)
    return any(executable.rsplit('/', 1)[-1] == process_name for executable in executables)
