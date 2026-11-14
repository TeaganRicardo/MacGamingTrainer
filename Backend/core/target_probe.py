"""macOS target process discovery via full executable paths from `/bin/ps`."""

import subprocess

from core.save_restore import SaveBusyError


def target_process_running(process_name, executable_path_suffix=''):
    """Return whether a target game executable is running on Darwin."""
    if not process_name:
        return False
    # macOS `ps -o comm` prints each executable path; the kernel name that
    # `pgrep` compares is truncated to MAXCOMLEN and cannot identify long names.
    try:
        result = subprocess.run(
            ['/bin/ps', '-axo', 'comm='],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SaveBusyError('无法确认目标游戏是否正在运行，请稍后重试。') from error
    if result.returncode != 0:
        raise SaveBusyError('无法确认目标游戏是否正在运行，请稍后重试。')
    executables = [row.strip() for row in result.stdout.splitlines()]
    if executable_path_suffix:
        return any(executable.endswith('/' + executable_path_suffix) for executable in executables)
    return any(executable.rsplit('/', 1)[-1] == process_name for executable in executables)
