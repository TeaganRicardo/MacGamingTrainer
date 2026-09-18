# Next development stage

Current product baseline: **0.1**. The active development branch is **Build 2** on `feature/post-v0.1-improvements`. Stable `main` and the published `v0.1` release remain Build 1 until Build 2 is deliberately merged/released.

## Build 2 stabilization gate

### Completed in code and automated regression

- Profile shortcut schema 4: arbitrary supported key chords, deterministic conflict handling, atomic Profile application, and one-time local UserDefaults migration from the previous digit layout.
- All fixed actionable controls have configurable shortcuts. Defaults follow visible order: Control+Option+1...9, then A...J.
- Rows without a shortcut badge no longer reserve the former empty shortcut column.
- Catalog presentation uses Chinese · English labels with source provenance. Trainer-authored/composed names are listed in `docs/PROVISIONAL_CATALOG_NAMES.md`.
- Selene has two distinct native spawn paths: `SpellDrop` for choosing a Hex and `TalentDrop` for Path of Stars upgrades.
- Hades resident runtime revision is 26.
- Fire / Water / Earth / Air / Aether have distinct symbols and semantic colors.
- Fullscreen testing invalidated timer-driven waiting -> ready probes: every live status crosses LLDB, stops/resumes the target and can interact badly with fullscreen focus. Timed +15/+30 background probes have been removed. Automatic debugger work is consumed only while Trainer is foreground; Hades performs one silent waiting-status refresh when Trainer becomes active.
- Hades status watchdog is 15 s so the host deadline sits outside the transport boundary + debugger cleanup deadlines instead of terminating the debugger owner mid-cleanup.
- Linux contract coverage enforces the foreground-only lifecycle and timeout policy. The new lifecycle still needs one manual fullscreen acceptance pass.

### Manual target-Mac acceptance still required

The user is the owner of Mac/gameplay validation from this point forward.

1. **Foreground-only waiting -> ready**
   - Rebuild the latest branch.
   - In fullscreen Hades, confirm Trainer does not issue live status probes merely because time passes while Trainer is backgrounded.
   - Switch back to Trainer. Pending automatic attach or a single waiting-status refresh should happen there, where debugger pauses are visible and do not interrupt active gameplay.
   - Once Trainer reports ready/run, return to Hades and confirm normal play remains smooth.
   - Manual Refresh is the explicit fallback if the foreground refresh misses a scene transition.

If this passes, close GitHub issue #1.

### Deferred performance work

GitHub issue #4 remains intentionally open. The supplied old-build logs show roughly 33 s vs 14 s end-to-end connections but contain no phase-level profile lines. Rebuild after #1’s lifecycle correction, capture one fresh `LLDBAttachProfile` + `ConnectProfile` pair, then optimize only the measured bottleneck.

Useful phases to measure:
- `AttachToProcessWithID`
- symbol/module validation
- process resume / first usable Lua boundary
- resident bootstrap/revision synchronization
- catalog/localization hydration

No optimization should add periodic status polling or unsafe retry of outcome-unknown mutations.

## Reliability constraints

- No periodic LLDB/Lua status polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No legacy Profile compatibility layer.
- No 4+ boon-choice UI/hack.
- Hades-specific semantics remain outside Core.
- Exit must never be permanently blocked by cleanup failure.
- Runtime source changes that affect the resident module must bump its revision so a surviving game process reloads the new code.

## After Build 2

Once issue #1 is manually accepted:

1. profile issue #4 and optimize only measured attach bottlenecks;
2. decide explicitly whether Build 2 should be merged/released as the next 0.1 build or versioned as 0.1.x;
3. only then resume deferred transport/read-only or second-game framework work.
