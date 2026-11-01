# Temporary LLDB worker lifetime

`tests/hades2_lldb_worker_support.py` owns the isolated native fixture workers used by the LLDB lifetime regression and opt-in operation profiling. A worker starts a new process group, which the parent kills and reaps on success, failure, timeout or interruption. LLDB launches debugserver in a separate process group and passes `--setsid`, so that group alone does not own debugserver's complete lifetime.

## Escaped debugserver ownership

Native consumers select `xcode_lldb=True` in `run_lldb_worker`. The parent runs `xcrun lldb -P` in an owned process group under the same original deadline as the worker, then uses its output for both the matching Python module path and debugserver resolution. Lookup failure or timeout preserves its stdout/stderr, cleans up its process group and prevents the worker from launching. Explicit executable paths remain available to the portable/native cleanup fixtures. Before launching the worker, `DebugserverOwner` verifies the required Darwin symbols and copies the selected executable into a private directory. The worker receives that unique path through `LLDB_DEBUGSERVER_PATH`. The native bytes and signature remain unchanged; LLDB still launches the real executable, owns its original PID and forwards its original arguments, file descriptors and signals.

After the ordinary worker group has been killed and reaped, the parent queries processes referencing that exact executable vnode, restricted to its own user. Each candidate must also have that exact native executable path. Path validation and the single cleanup signal both use a Darwin audit token containing the PID and its version. The kernel validates that version again while finding the process to signal, so a reused numeric PID cannot authorize signaling its replacement. A process that merely opens the copied file is excluded by the executable-path check.

Preparation consumes the original worker deadline. Cleanup waits at most two seconds for signaled debugservers to disappear. Successful cleanup removes the private copy. An API, inventory or cleanup failure remains visible and retains the executable path as evidence; there is no process-name sweep or numeric-PID signal fallback. If the worker already failed, its original exception, stdout and stderr are preserved and the cleanup diagnostic is appended.

These APIs are private Darwin interfaces, so symbol availability is checked before launch and the normal macOS PR consumer must verify the installed runner. The signal interface is present in Apple's published `xnu-10063.101.15` source; the current implementation is checked against the pinned sources below. This test support does not change the application's minimum macOS version or production transport.

## Verification and remaining limits

`tests/test_debugserver_ownership.py` checks API layout, exact-executable filtering, PID reuse, cleanup failure evidence and interruption semantics through an injected kernel interface. The macOS lifetime test compiles a temporary native helper, launches its private copy in a separate session, and waits for its main-function readiness marker before querying its audit token. It verifies cleanup after success, failure, timeout and parent interruption while an unrelated process remains alive. Compiling the owned helper avoids assuming that a protected system executable remains runnable after relocation. Its original LLDB scenarios still use the copied SDK debugserver and retain their original deadlines and detach/progress assertions. `Tools/macos_test_dependencies.json` owns the support-file dependency edges alongside the available-test inventory, `Tools/macos_only_tests.txt`. The shared CI scope classifier and bounded PR selector consume this metadata to select the native consumer.

This addresses the escaped temporary debugservers recorded in [#433](https://github.com/TeaganRicardo/MacGamingTrainer/issues/433#issuecomment-6396027225). It does not establish the cause of the historical long stall or the separately observed delayed stop after detach. Those remain in #433; this fixture is not actual-game acceptance.

## Source basis

- LLVM [`ProcessGDBRemote.cpp`](https://lldb.llvm.org/cpp_reference/ProcessGDBRemote_8cpp_source.html), `GetDebugserverPath` and `LaunchAndConnectToDebugserver`: environment override, support-executable resolution and separate process group.
- LLVM [`GDBRemoteCommunication.cpp`](https://lldb.llvm.org/cpp_reference/GDBRemoteCommunication_8cpp_source.html), `StartDebugserverProcess`: native arguments, inherited connection descriptor and `--setsid`.
- LLVM [`debugserver.cpp`](https://github.com/llvm/llvm-project/blob/main/lldb/tools/debugserver/source/debugserver.cpp): the `--setsid` option calls `setsid()` directly.
- Apple [`proc_info_private.h`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/sys/proc_info_private.h): `proc_uniqidentifierinfo` layout and `PROC_PIDUNIQIDENTIFIERINFO`.
- Apple [`libproc.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/wrappers/libproc/libproc.c): token-bound path query and signal wrapper.
- Apple [`proc_info.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/proc_info.c) and [`kern_proc.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/bsd/kern/kern_proc.c): token-version comparison, retained process identity and caller signal permissions.
- Apple [`proc_listpidspath.c`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libsyscall/wrappers/libproc/proc_listpidspath.c): exact-vnode candidate query and user filter.
- Apple [`xnu-10063.101.15/libproc.h`](https://github.com/apple-oss-distributions/xnu/blob/94d3b452840153a99b38a3a9659680b2a006908e/libsyscall/wrappers/libproc/libproc.h): published historical symbol declaration.
