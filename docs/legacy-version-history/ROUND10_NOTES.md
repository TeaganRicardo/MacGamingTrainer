# Mac Gaming Trainer v0.10.0 — Round 10

- App version: 0.10.0
- Build: 15
- Backend protocol: v2
- Lua runtime revision: 18
- Base: v0.9.1 Build Hotfix

Round 10 deliberately continues feature development before the deferred full physical refactor. Existing transport, save, spawn and verified combat paths are retained.

## 1. Enemy health multiplier

A new top in-run stat, `敌人生命`, uses a percentage target from 10–1000%.

- 100% is neutral.
- Changing the value rescales active enemies while preserving their current health percentage.
- Enemies initialized later through the game's `SetupUnit` path inherit the active multiplier automatically.
- Unlocking restores living tracked enemies to their pre-trainer health scale where it is still meaningful.
- The trainer modifies per-instance `Health` / `MaxHealth`; it does not rewrite `EnemyData`, and it does not scale armor/HealthBuffer.
- The stat participates in the existing Stat Registry, desired-state replay, custom profiles and cross-run lifecycle.

## 2. Blessing choice count

Added persistent `祝福选项数量` control.

The implementation hooks the game's own `CalcNumLootChoices()` and `GetTotalLootChoices()` functions instead of truncating generated options after the fact.

The range is intentionally **1–3 only**. The current game defines `ScreenData.UpgradeChoice.MaxChoices = 3` and lays choices out at a fixed vertical spacing; advertising values above three can create choices outside the normal screen layout. This control therefore stays within the native UI envelope.

It is a persistent toggle and is saved/restored in custom profiles.

## 3. Expanded next-room reward control

The existing next-room reward selector keeps individual Olympian-source entries and adds additional safe native room reward families:

- Ashes (`RoomRewardMetaPoint`)
- Psyche (`RoomRewardPsyche`)
- Fate Fabric (`RoomRewardMixerFabric`)

Existing entries such as money, Centaur Heart, Pom, Hammer, Selene and individual god sources remain available. The control continues to affect the next safe room reward rather than rewriting whole map generation.

## 4. Protocol/version boundary

Round 10 uses Backend protocol v2. GUI and Backend must come from the same release package. A mixed Round 9/Round 10 bundle fails explicitly at the protocol handshake rather than continuing with mismatched command semantics.

## 5. Build hotfix retained

The 0.9.1 LLDB preflight hotfix is inherited. `build.sh` first queries `xcrun lldb -P`, prepends that directory to Python's `sys.path`, and only then imports `lldb`, matching the runtime loader. The old false-negative bare `xcrun python3 -c 'import lldb'` build gate is not used.

## 6. Refactor status

The full physical refactor remains deferred as requested. Feature Registry / Stat Registry remain the canonical logical architecture, but the Swift/Python files are not split yet. Round 10 only extends those registries where required by the new functionality.

## Live verification priorities

1. Set enemy health to 200% with enemies already alive; verify their health percentage is preserved while MaxHealth doubles.
2. Spawn a new enemy/enter another encounter while the 200% lock remains active; verify new enemies inherit it.
3. Unlock enemy health and verify living enemies return to their natural scale without being healed/damaged by percentage drift.
4. Test blessing choices at 1, 2, then disable the feature and confirm normal three-choice behavior returns.
5. Force Ashes, Psyche, Fate Fabric and one specific Olympian as the next-room reward.
6. Build with the supplied build.sh and confirm the previous false LLDB-import error does not return.

Live Hades II/macOS integration is not available in the Linux validation environment, so these items remain target-Mac verification tasks.
