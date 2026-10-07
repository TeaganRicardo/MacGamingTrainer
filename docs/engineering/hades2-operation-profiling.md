# Hades II operation profiling

Issue [#376](https://github.com/TeaganRicardo/MacGamingTrainer/issues/376) owns
operation latency and resident maintenance measurements. Run the opt-in offline
tool before proposing an optimization:

```sh
python3 Tools/profile_hades2_operations.py --output /tmp/hades2-profile.json
```

This creates temporary processes and in-memory game-shaped tables. It never
starts or attaches to Hades II and never loads user/game saves. Transport mode
needs macOS, Xcode Python and LLDB; resident mode needs Lua 5.2 (`MGT_LUA52` may
name its executable). On Linux, run `--mode resident`.

The JSON records Git HEAD, working-tree changes, production source hashes,
runtime/toolchain versions, sample counts, raw durations, median and nearest-rank
p95. Use a clean committed checkout when attributing evidence to an exact SHA.
Run identical arguments and toolchains for comparisons; a dirty report is a
development probe, not verification of its recorded HEAD.

## Transport measurements

`--mode transport --samples 30` runs the production `execute()` and `boundary()`
against a compiled native helper. Fake Lua entrypoints return `{}`; there is no
Lua dispatch workload. The helper's main thread calls its update function every
16,667 microseconds by default. `--tick-microseconds 0` selects a busy loop for
isolating debugger cost from update cadence. Neither is a game FPS measurement.

The first attachment has three warmups followed by the requested steady-state
sample count. Three fresh helper attachments each contribute one cold execution
sample. Fixture attachment includes process setup, debugger attachment and symbol
lookup; it bypasses production Hades identity validation and is not a production
reconnect benchmark.

The wall-time measurements include total execution, boundary acquisition,
expression evaluation, stop/resume, event draining, breakpoint creation/deletion,
and memory operations. Nested measurements overlap: do not add them. Every call
checks its result, terminal trust, breakpoint cleanup and focus-recovery state.
After each attachment, the tool verifies the target's actual focus flag and
native call count before killing and reaping the temporary helper.

The launcher owns a separate temporary process group, so a worker timeout or
interruption also terminates its helper. A portable lifecycle regression covers
this failure path; it does not assert a latency threshold.

The shared breakpoint-lifetime regression holds its fake native call until LLDB
interrupts it and verifies an entry marker, restored focus and terminal trust.
A finite slow call can complete before a delayed halt is delivered; LLVM's
[expression execution loop](https://lldb.llvm.org/cpp_reference/Process_8cpp_source.html)
explicitly accepts that completed result. The regression therefore forces the
unknown path without assuming that elapsed wall time alone proves an unknown
outcome.

## Resident measurements

`--mode resident --samples 30` runs the shipped Lua source with explicit native
stubs. It measures initial load/catalog status, warm dispatch, JSON encoding,
resource edits with unique request identities, durable replay after cleanup, and
`UpdateTimers` with/without desired features. Frame samples average 100 calls;
their p95 describes these batch averages, not individual frame spikes.

The active set is infinite health, infinite mana, damage multiplier, money and
resource multipliers, and base UpgradeChoice Force Enable Rerolls, plus health,
resource and reroll locks. The fixture verifies activation, returned resource
counts and completed one-shot receipts. Native stubs are inexpensive, the trait
inventory is empty, and the optional Selene/door/store/Nemesis reroll families are
absent. This is a resident CPU baseline, not a measurement of game engine cost,
full mounted-trait inventories, presentations or gameplay frame time.

## Interpretation and remaining work

Initial probes of production source `42ea316f39f99d6e63ee2a2705293eac4e9a5a42`
on Apple LLDB `2103.0.34.103` located about 106 ms of a 126 ms busy-loop helper call
inside `SBProcess.Stop()`. A temporary differential probe using
`SendAsyncInterrupt()` still required about 109 ms to confirm the stop; total
latency did not improve. The probe was rejected. LLVM's
[Process::Halt implementation](https://lldb.llvm.org/cpp_reference/Process_8cpp_source.html)
also sends an asynchronous interrupt and waits for the stop; changing API names
does not establish a faster stop mechanism. The installed Apple implementation
must still be measured independently.

The explicit resident fixture initially measured about 32 microseconds per guard
call and 0.3–0.4 ms for warm observation/resource edits/replay. These measurements
do not justify weakening ownership checks, changing frame cadence, caching live
state or altering native/replay semantics. Performance assertions are deliberately
not an always-on CI gate; the existing behavior gates continue to own correctness.

These offline baselines complete only one slice of #376. Remaining measurements
include a user-run exact-build trace of representative operations, Host scheduling,
sidecar/RPC overhead, real resident dispatch/synchronization/materialization, UI
projection, actual reconnect/replay, populated trait catalogs and gameplay frame
cost. Keep #376 open until that evidence and any demonstrated owning-seam fixes
are complete. Consolidated game/visual acceptance remains deferred.
