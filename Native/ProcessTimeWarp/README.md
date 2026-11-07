# Process Time Warp compatibility and ordering

The helper ABI is declared by `MGT_TIME_WARP_ABI` in `ProcessTimeWarp.c` and
expected by `ProcessTimeWarpController.ABI_VERSION`. An incompatible helper
stays loaded for its process lifetime and requires a game restart.

`MGTTimeWarpInstallState` observes uninstalled, installed, partial or in-progress
state and checks an installed helper's immutable image allowlist. Reset never
installs hooks. An original function pointer identifies a callable address;
fishhook's per-binding receipt counts actual verified slot writes. A failed
matched slot makes the helper partial, resets its factor to 1x and prevents
further installation or speed changes until the process restarts. Hook-mask
bits mean at least one slot for that clock was verified, independently of the
partial-state verdict. An image with no matching imports remains uninstalled.

## C11 snapshot proof

The sequence and all three payload fields are atomic. Writers serialize through
`speed_lock`, publish an odd sequence, execute a release fence, store the
payload, then publish an even sequence with release semantics. Readers acquire
the first sequence, read the payload, execute an acquire fence, then re-read
the sequence; only equal even values authorize a snapshot.

Acquiring the completed even sequence orders its preceding payload writes
before reader payload loads, so those loads cannot select an earlier version.
If any payload load instead observes a later writer, that writer's release
fence synchronizes with the reader's acquire fence through that atomic
store/load pair. Its odd sequence therefore happens before the final sequence
load, which cannot select the preceding even sequence. Thus an accepted
snapshot contains one completed generation.

The previous second acquire *load* provided no such payload-to-sequence fence
relationship. The allowed counterexample was: both sequence loads select old
even `S`, while a payload load selects a later relaxed store. The two fences
exclude that execution by atomic coherence; this is a memory-model argument,
not a claim that a real-game race was reproduced. See [C11 draft N1570,
§5.1.2.4 and §7.17.4](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf).

Native installation/slot fixtures exercise serialization, zero-binding retry,
partial binding, neutralization and successful receipt paths. Their execution
does not prove game speed, frame pacing or gameplay acceptance.
