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
- Passive waiting -> ready handling uses two independent one-shot probes scheduled at +15 s and +30 s from the waiting transition. No repeating live-status timer was introduced.
- Full Python regression, Swift parse/typecheck/build and target-Mac Build 2 acceptance were completed before the final passive-probe timing correction; the timing correction itself is covered by source-level regression and still needs the manual scenario below.

### Manual target-Mac acceptance still required

The user is the owner of Mac/gameplay validation from this point forward.

1. **Passive waiting -> ready**
   - Start Hades II and leave it at the main menu.
   - Start/connect Trainer and confirm waiting/main-menu state.
   - Enter a save without pressing Trainer refresh/reconnect.
   - Confirm Trainer reaches ready/run automatically.
   - Repeat once with the save transition occurring after the first +15 s probe so the +30 s probe is exercised.

If this passes, close GitHub issue #1.

### Deferred performance work

GitHub issue #4 remains intentionally open: profile LLDB attach latency by phase before optimizing anything. Measure first; do not change transport behavior from intuition.

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
