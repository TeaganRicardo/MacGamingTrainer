# Hades I boon editing and native save corruption

## Incident and causal evidence

The 2026-11-14 report concerns Athena's Sure Footing / 沉稳步伐
(`TrapDamageTrait`), Common → Heroic. Both rarities are native legal values.
The installed resident and transport matched baseline
`9cd72a428ece146c7d12ae4638c08950b10ebafd`.

The preserved logs show `update_trait` at 10:14:46 UTC, followed by an LLDB
expression interruption at 10:14:48 (`breakpoint 27`, native stack restored).
The Trainer refused further commands, but the game continued. Native autosaves
at 10:15:31 and 10:16:20 wrote 378 and 389 bytes. Both files have a valid v16
header checksum and no compressed Lua body or body-length field. Reload at
10:16:39 reported decompression failure. Steam subsequently uploaded the
389-byte file. The session contains no Save Editor Apply or Core file replacement.

Three owning paths explain how this failure can propagate:

1. The old worker ran trait removal/reacquisition inside an LLDB expression on
   the main Lua state, using `lua_pcallk` without a continuation. Native
   `AddTraitData` inserts the physical trait and then closes an open trait-detail
   menu before installing its effects. `CloseAdvancedTooltipScreen` calls
   `CloseScreen`, which yields. This call needs the game's coroutine scheduler.
   An ordinary protected Lua yield error returns through Lua cleanup; it does
   **not** by itself prove permanent VM corruption.
2. An LLDB expression interruption is different. The old transport enabled
   native stack unwinding, marked only the Trainer connection tainted, and then
   unconditionally resumed the game. Lua's `luaD_rawrunprotected` stores an error
   recovery pointer into its current C stack; `luaD_pcall` also owns CallInfo and
   call-counter cleanup. Debugger stack restoration bypasses that cleanup. The
   supported executable confirms this: `0x10000c8a8` stores the stack-local
   recovery record in `lua_State+0x70`; normal restoration occurs only at
   `0x10000c8cc` and `0x10000c8d0`.
3. The supported executable's `ProgressManager::Save` calls Lua `Save`, then
   inspects `_saveData`. At `0x1003d3090` it sets success before checking the
   string type. A non-string branches from `0x1003d3096` to `0x1003d322c`,
   bypassing compression and the length/body writes, while the success test at
   `0x1003d330a` still permits `SaveToDeviceAsync`. This is an exact native route
   to the observed valid-header-only files.

The original interruption has no captured native/Lua stack. The first blocking
native call and the exact damaged VM fields in that process therefore remain
unknown. The two-second interval alone does not prove timeout. The code defects
and native missing-body write path are confirmed independently of that missing
stack; connecting them to this incident is the best-supported causal inference.

A temporary C probe linked to Lua 5.2.4 compared an ordinary protected Lua error
with an external native-stack escape. The ordinary return restored `ci`,
`errorJmp`, `nCcalls` and `nny`; the escape left all four dirty, even after
`lua_settop`. This is mechanism evidence, not a reproduction of breakpoint 27.
Probe source, output and exact-game disassembly are retained with the local
incident evidence. [Lua's protected-call implementation](https://www.lua.org/source/5.2/ldo.c.html)
documents the cleanup that a debugger unwind skips.

## Correction and affected commands

The worker submits the seven trait command families once, with a unique receipt,
and reads completion without running observation maintenance during the edit:
`add_trait`, `update_trait`, `remove_trait`, `set_trait_uses`, `expire_trait`,
`refresh_trait`, and `add_chaos_pair`. Native `Main.lua:update` owns their first
resume. Calling native `thread()` at submission would immediately start work
inside the debugger again, so submission only inserts a pending coroutine.

Acquisition, replacement, removal, equipment changes and expiry transformations close
the native trait-detail menu before mutating trait records or modifiers. Saves
during its yields therefore observe the original consistent state. Replacement
and removal resolve the physical group token again after menu closure, so an
expired selection is neither resurrected nor reused for removal. Each continuation retains
its original run, hero, object, room and menu owner. A confirmed pending cancel
cannot execute later; started or unconfirmed work is never replayed.

Removal also closes the menu before touching the selected group: native
`RemoveWeaponTrait` can rebuild its weapon and reacquire unrelated dependent
Hammer traits. Their `AddTraitData` calls otherwise yield after physical
insertion and before dictionary/effect repair. The weapon-removal regression
checks every menu-close save snapshot and retains the dependent Hammer.
Its fixture preserves native `SkipUIUpdate` behavior and verifies the Hammer's
named outgoing damage modifier, so matching trait names alone cannot hide an
effect missing during reacquisition.

The resident compatibility revision changes through its Lua declaration. An
already-running older resident must be replaced by restarting the game.

LLDB expression-engine failure is tracked separately from ordinary protected
Lua errors. A volatile scratch-memory phase marks entry before the Lua calls
and completion after protected return and stack cleanup. A failed expression
whose phase proves it never entered Lua or finished cleanup keeps the ordinary
unknown-result interlock without Force Quit. An unreadable or in-progress phase
requires termination. The user's selected recovery policy is immediate Force
Quit of the attached game, accepting loss of unsaved progress to preserve the last
complete disk save. The transport calls `SBProcess.Kill()` on its owned attachment before
focus/scratch/breakpoint cleanup and requires an observed exited state. It never
resumes the interrupted VM or relies on `Detach(True)`, whose remote support is
not guaranteed. Receipt polling and the Time Warp worker preserve the specific
termination result. Ordinary protected Lua errors retain normal cleanup.

If termination fails or exit cannot be confirmed, the transport retains its
debugger and recovery interlock, instructs immediate manual Force Quit, and
refuses resume or ordinary detach. Disconnect/close retry termination without
another Lua/Time Warp reset; debugger destruction follows successful release.
The Hades debugger child owns shutdown cleanup: normal close, reply loss and
timeout close its input without terminating the worker. On EOF it retries only
interrupted-target termination, retaining the debugger until an observed exit.
Each attempt waits up to three seconds for exit acknowledgement after Kill
returns, with one second between unsuccessful attempts.
Other sidecars keep their existing parent-owned termination policy. This
prevents upper-layer client shutdown from discarding the unsafe attachment.
This does not repair an interrupted VM or restore an already damaged disk save.

## Verification boundaries

`tests/test_hades_boon_edit_lifecycle.py` executes the real worker-generated Lua
under Lua 5.2 with native-shaped removal, acquisition, menu yielding and scheduler
order. It covers Sure Footing's incoming trap multiplier (0.4 → approximately
0.049), unrelated trait retention, trait dictionaries, save snapshots at each
menu-close yield, synthetic v16 save encoding/reload, transient save exclusions,
owner replacement, cancellation and unknown-outcome non-replay. The pre-fix
path fails with `attempt to yield from outside a coroutine`.

Transport fixtures cover pre-Lua and completed-cleanup failures without Force
Quit, unreadable execution phase, termination before any resumable cleanup, Kill API
failure, missing exit acknowledgement, retained ownership on close, a later
successful termination, and ordinary Lua errors that still resume. These are
LLDB interface fixtures; actual-game forced interruption is unexecuted.
Client/sidecar fixtures cover both a received termination failure and a lost
reply, followed by shutdown without killing the child or clearing the recovery
journal. A disposable Python child also proves that EOF cleanup completes after
its client closes; no game process is used.

The user paused game/CUA execution during this investigation. Actual game
modification, native disk persistence and full process restart/load remain
unexecuted for this candidate. Codec round trips do not replace those checks.

When native acceptance resumes, use an isolated home and OS sandbox denying
access to real save trees and real Steam userdata. Pin the candidate SHA and
artifact digest, bind the Trainer to the isolated PID, and retain read-only
before/after hashes of the real save directory. For every row below, first prove
an unmodified native save/load baseline; then edit once, trigger native save,
fully exit, relaunch and load. Perform another native save and a second full
exit/load to check subsequent persistence.

| Case | Required observation |
| --- | --- |
| Sure Footing Common → Heroic, detail menu closed/open | Correct trait, dictionary and native multiplier; both later loads succeed |
| Native pause menu open | Confirmed unstarted cancellation has no delayed execution after unpausing |
| Add / level-rarity update / selected removal | Correct physical group and effects; unrelated groups retained |
| Set uses / expiry / cooldown refresh | Native owner and persistent fields follow their native semantics |
| Chaos pair and curse → blessing expiry | Single transition, correct encounters and no duplicate reward after loading |
| Keepsake and Companion rank changes | Equipment/weapon owner, earned effects and consumed uses preserved |
| Stale token or context replaced during menu closure | No resurrection or edit of the replacement owner |
| Forced expression interruption in a disposable diagnostic fixture | Owned game exits before another save; prior complete file hashes survive; no one-shot replay |

Cover ordinary Olympian, Hermes, legal Hammer, duo/legendary and independent
Chaos categories separately. Exact intermediate-save scheduling and forced
debugger interruption require a dedicated disposable fixture; ordinary manual
timing cannot certify those windows. All native rows currently remain pending.
