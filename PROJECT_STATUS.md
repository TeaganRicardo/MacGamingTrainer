# MacGamingTrainer Project Status

## Current baseline

- Product version: 0.1
- Development build: 2
- Latest release: v0.1 / Build 1
- Stable branch: main
- Active development branch: feature/post-v0.1-improvements
- Host protocol: 5
- Hades II module protocol: 5
- Desired-state schema: 3
- Profile schema: 4
- Hades II Lua source revision: 25
- Target game build last verified: Hades II 1.139672 / Steam build 24556151

## Verified on target Mac

- Native arm64 build succeeds.
- App bundle passes codesign --verify --deep --strict.
- com.apple.security.cs.debugger=true entitlement is present.
- Hades process discovery works without attaching.
- Runtime diagnostics revision 26 is verified on target Mac; a valid Hero object was confirmed both in Crossroads and in a real run.
- Main-menu waiting quit regression is fixed: quit persists desired-off state, disconnects best-effort, and does not block app termination.
- Save backup 修改器测试 was restored successfully; a pre-restore backup was created automatically.
- Real-run acceptance reached status=ready / scene=run with Hero object 40000, 97 resources, 129 rewards, 11 stats and 5 elements.
- All 83 NPC trait entries in the observed catalog resolved official Chinese names; none required fallback naming.
- forceLegendary and forceDuo OFF/ON/both state transitions were exercised in a real run; boon rarity hooks engaged and returned to fully disabled state after cleanup.
- Selene SpellDrop first-Hex spawn path is confirmed operational in-game.

## In progress

1. Passive waiting -> ready transition: bounded two-shot status probe per connection lifetime at 15s / 30s; no repeating timer. Code + regression test are present; full main-menu-to-run acceptance remains open.
2. Post-v0.1 Build 2 implementation:
   - Selene `TalentDrop` is exposed as a distinct Selene special reward for native Path of Stars upgrades; target-Mac interaction verification pending.
   - Dynamic catalog entries carry Chinese + English labels and name provenance.
   - Profile schema 4 stores arbitrary supported hotkey chords; local layout-v3 UserDefaults receive a one-time migration.
   - Static toggle/apply/spawn actions have configurable global shortcuts; defaults follow visible order (Control+Option 1-9, then A-Z).
   - Shortcut rows without an assignment no longer reserve an empty badge column.
   - Fire/Water/Earth/Air/Aether use distinct symbols and colors.
3. Build 2 target-Mac acceptance pending:
   - full Python regression suite and native arm64/codesign build from the GitHub branch;
   - shortcut capture and one custom chord;
   - native `TalentDrop` -> Path of Stars interaction;
   - bilingual live catalog audit for any remaining identifier-only English names;
   - visual check of element icons and row alignment.

## Deferred until correctness is stable

- LLDB attach latency profiling and optimization.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No legacy Profile compatibility layer.
- No 4+ boon-choice UI/hack.
- Hades-specific semantics remain outside Core.
- Exit must never be permanently blocked by cleanup failure.
