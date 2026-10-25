# Hades I module

The module targets the Intel Steam image declared in `Backend/games/hades/symbols.json`. It owns its LLDB sidecar, resident Lua, desired settings, command validation, catalog and UI. Hades II runtime and preference data are independent.

## Supported actions

| Domain | Behavior |
| --- | --- |
| Combat | Invincibility, non-consuming Obols and rerolls, full God Gauge while an Aid is available, damage/movement/attack-speed multipliers, additional dashes |
| Hero values | Set health, maximum health, Obols and rerolls; heal to current maximum |
| Permanent resources | Edit the seven native resource owners declared by `schema.py` and the generated catalog |
| Acquisition | Search the official bilingual reward catalog; acquire Olympian/Hermes boons, weapon-compatible Hammers, Chaos blessings, Keepsakes and Companions through their native owners |
| Current boons | Observe current native effects; edit level/rarity and remove supported boon groups |
| Management | Game-scoped customizable shortcuts, disable all, manual backups, stopped-game restore and staged restore through Core Save |

Multipliers accept 0.1–100 and additional dashes accept 0–20. Additional dashes preserve the native weapon's existing charges. Non-consuming operations preserve actual gains and native purchase/reroll bookkeeping. Direct numeric edits remain intentional absolute edits. The God Gauge control preserves the Aid's native active duration.

Hades I stores an upgraded boon as several same-name trait records while presenting one boon in its HUD. A current-boon row therefore represents that native group. Its identity includes the actual current group members; replacing the group invalidates the old token. Mixed-rarity and special-owner effects report a concrete lifecycle limitation. They do not authorize deleting unrelated effects by a stale name.

## Ownership and recovery

Durable desired settings live under the module's own `MacGamingTrainer/hades` directory. Reconnecting applies them to a compatible runtime; hero setup remounts them after native per-room state resets. Manual detach preserves desired intent. Disable All and application termination reset desired settings and attempt resident cleanup. A failed preference write is reported while resident cleanup still runs.

One-shot requests carry the observed hero identity and, for existing boons, the selected group token. The worker verifies the hero inside the same Lua execution before mutation. A draft captured for an earlier hero cannot be applied to its replacement. Focused number drafts survive observations; unfocused fields follow current values.

The backend records an in-flight native request before sending it. A lost acknowledgement or backend crash retains that record. Reconnecting to the same process lifetime requires restarting the game; the request is never replayed automatically. A new process lifetime clears the obsolete marker. The UI revokes mutation authority when the runtime outcome or protocol is untrustworthy.

The resident revision and source path are declared in `module.json` and extracted by the existing shared revision/provenance tooling. A different or legacy resident requires a game restart. Runtime-only tables and temporary Trainer projections must be excluded from native saves.

## Native evidence and validation

`catalog.json.sourceEvidence` records the exact native data and official bilingual text hashes. `Tools/generate_hades_catalog.py` reproduces the acquisition catalog and current-trait name registry. Native sources establish `SetupHeroObject` room resets, `SpendMoney`/`AddMoney` bookkeeping, native property application, the three reroll entry points, and trait acquisition/teardown. `Main.lua:Save` serializes non-ignored global tables; the module excludes its resident state and transient projections.

Portable journeys exercise native-shaped Lua calls, yielding reroll lifecycles, remount/reset, gains, hero/group ownership and crash recovery. The macOS frontend harness compiles the actual Core + Hades Swift graph and exercises AppKit number fields, focused drafts, target changes, bilingual catalog data, shortcuts and fatal-error recovery. Temporary filesystem tests cover save membership, profile naming and Core backup/restore integration.

Real-game observations are recorded separately from fixture and package checks. Development game launches use an isolated `CFFIXED_USER_HOME`, with an OS sandbox denying access to the real Hades save directory. The original directory's file hashes are compared before and after testing. Full gameplay/HUD, every catalog category and later game-authored persistence require their own executed evidence; a successful fixture or package does not establish those results.
