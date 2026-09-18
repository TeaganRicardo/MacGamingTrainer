# MacGamingTrainer Project Status

## Current baseline

- Product version: 0.1
- Build: 1
- Canonical branch: main
- Host protocol: 5
- Hades II module protocol: 5
- Desired-state schema: 3
- Profile schema: 3
- Hades II Lua source revision: 24
- Target game build last verified: Hades II 1.139672 / Steam build 24556151

## Verified on target Mac

- Native arm64 build succeeds.
- App bundle passes codesign --verify --deep --strict.
- com.apple.security.cs.debugger=true entitlement is present.
- Hades process discovery works without attaching.
- Runtime probe previously confirmed revision 24 and a valid Hero object in Crossroads.
- Main-menu waiting quit regression is fixed: quit persists desired-off state, disconnects best-effort, and does not block app termination.
- Save backup 修改器测试 was restored successfully; a pre-restore backup was created automatically.

## In progress

1. Passive waiting -> ready transition: bounded two-shot status probe per connection lifetime; no repeating timer.
2. Gameplay acceptance in a real room:
   - Selene SpellDrop native interaction.
   - forceLegendary semantics.
   - forceDuo semantics.
   - both-on coexistence while keeping native three-choice behavior.
   - spawn/inventory UI grouping and naming.
3. Naming audit:
   - every legal NPC trait must remain visible.
   - fallback order: official Chinese -> official English -> provisional translated/internal name.
   - preserve naming provenance; never label provisional text as official localization.

## Deferred until correctness is stable

- LLDB attach latency profiling and optimization.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No legacy Profile compatibility layer.
- No 4+ boon-choice UI/hack.
- Hades-specific semantics remain outside Core.
- Exit must never be permanently blocked by cleanup failure.
