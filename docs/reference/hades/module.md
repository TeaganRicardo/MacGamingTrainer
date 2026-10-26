# Hades I module

The module targets the Intel Steam image declared in `Backend/games/hades/symbols.json`. It owns its LLDB sidecar, resident Lua, desired settings, command validation, catalog and UI. Hades II runtime and preference data are independent.

## Workbench presentation

Hades I now follows Hades II's ordered workbench navigation: compact and expandable Run Data, Common toggles, unified Boons & Effects (selected current-group editing and exact acquisition), Resources & Gathering, and Management. The current seven permanent resources remain visible as direct rows. The Rooms & Rewards section is reserved but deliberately not shown until source-backed native room controls are delivered by #572; a label or disabled dummy action would falsely imply coverage. Whole-workbench bilingual search resolves existing features, numeric controls, resources and management destinations. The single visible-order registry drives default shortcuts and shortcut settings, including a customizable Disable All binding.

This presentation update uses existing native actions. It does not imply Hades I has the Hades II-only gathering, room, boon or management capabilities: the gaps and their Hades-native implementation are explicitly owned by #571–#573. Native game effects, save/recovery and user acceptance retain their original owners.

## Supported actions

| Domain | Behavior |
| --- | --- |
| Combat | Invincibility, non-consuming Obols and rerolls, full God Gauge while an Aid is available, damage/movement/attack-speed multipliers, additional dashes |
| Boon rarity (new) | On/off minimum Heroic preference for future normal Olympian/Hermes offers and rerolls; does not alter eligibility, fixed rarity, existing offers, Chaos, Hammer or Pom selection |
| Hero values | Set health, maximum health, Obols and rerolls; heal to current maximum |
| Permanent resources | Edit the seven native resource owners declared by `schema.py` and the generated catalog |
| Acquisition | Search the official bilingual reward catalog; acquire Olympian/Hermes boons, weapon-compatible Hammers, Chaos blessings, Keepsakes and Companions through their native owners |
| Current boons | Observe current native effects; edit level/rarity and remove supported boon groups |
| Management | Game-scoped customizable shortcuts, disable all, manual backups, stopped-game restore and staged restore through Core Save |

Multipliers accept 0.1–100 and additional dashes accept 0–20. Additional dashes preserve the native weapon's existing charges. Non-consuming operations preserve actual gains and native purchase/reroll bookkeeping. Direct numeric edits remain intentional absolute edits. Maximum-health edits commit their adjustment through the native `RoomRewardEmptyMaxHealthTrait` contribution, preserving it when later native rewards or traits recalculate maximum health. The God Gauge control preserves the Aid's native active duration. The rarity toggle is off by default; when on, it temporarily raises Rare/Epic/Heroic chances only while the native synchronous SetTraitsOnLoot selection is running, restores the original odds even on failure, and preserves Legendary probability and original offer gating. It does not edit game files or save a forced rarity into existing loot objects. Its behavior is grounded in the supported-build Content/Scripts/TraitScripts.lua (SHA256 473b3a2df05923bdbfe123e35047ff86ee44db4c7f4e3881e1812461d43ee3a6) and RoomManager.lua (SHA256 ca379fe0708af778007aef929822e4cfe8cf3a47dd2a3d37bf57e582ddb1b924).

Hades I stores an upgraded boon as several same-name trait records while presenting one boon in its HUD. A current-boon row therefore represents that native group. Its identity includes the actual current group members; replacing the group invalidates the old token. Mixed-rarity and special-owner effects report a concrete lifecycle limitation. They do not authorize deleting unrelated effects by a stale name.

Acquiring a Keepsake or Companion uses its native equipment owner, replaces the previous item and records the selected rarity's progression. Lucky Tooth receives its native extra life; Companions receive their native assist weapon. Reacquiring the same equipped item and rarity preserves consumed uses. Ordinary Keepsake rank maps to native chamber thresholds; Companion rank maps to the selected assist's upgrade record. Narrative requirements are not fabricated.

## Ownership and recovery

Durable desired settings live under the module's own `MacGamingTrainer/hades` directory. Reconnecting applies them to a compatible runtime; hero setup remounts them after native per-room state resets. Manual detach preserves desired intent. Disable All and application termination reset desired settings and attempt resident cleanup. Offline Disable All reports that in-game cleanup needs reconnection or a game restart. A failed preference write is reported while resident cleanup still runs. Native scripted movement temporarily owns speed; its completion or native reset remounts the current movement multiplier. Committed numeric edits remain after Disable All.

One-shot requests carry the observed hero identity and, for existing boons, the selected group token. The worker verifies the hero inside the same Lua execution before mutation. A draft captured for an earlier hero cannot be applied to its replacement, including a fresh Lua runtime in the same game process. Focused number drafts survive observations; unfocused fields follow current values.

The backend records an in-flight native request before sending it. A lost acknowledgement or backend crash retains that record. Reconnecting to the same process lifetime requires restarting the game; the request is never replayed automatically. A new process lifetime clears the obsolete marker. The UI revokes mutation authority when the runtime outcome or protocol is untrustworthy.

One execution cleanup owner observes suspension before deleting the private debugger target's breakpoints, restoring focus and releasing scratch memory. A failed boundary retains its breakpoint in that target until cleanup or detach. Cleanup failure remains an unknown outcome, including when the original native call also failed; it cannot erase the recovery journal or authorize another command.

The resident revision and source path are declared in `module.json` and extracted by the existing shared revision/provenance tooling. A different or legacy resident requires a game restart. Runtime-only tables and temporary Trainer projections must be excluded from native saves.

## Native evidence and validation

`catalog.json.sourceEvidence` records the exact native data and official bilingual text hashes. `Tools/generate_hades_catalog.py` reproduces the acquisition catalog and current-trait name registry. Native sources establish `SetupHeroObject` room resets, `SpendMoney`/`AddMoney` bookkeeping, native property application, the three reroll entry points, and trait acquisition/teardown. `Main.lua:Save` serializes non-ignored global tables; the module excludes its resident state and transient projections.

Portable journeys exercise native-shaped Lua calls, yielding reroll lifecycles, remount/reset, gains, hero/group ownership and crash recovery. The macOS frontend harness compiles the actual Core + Hades Swift graph and exercises AppKit number fields, focused drafts, target changes, bilingual catalog data, shortcuts and fatal-error recovery. Temporary filesystem tests cover save membership, profile naming and Core backup/restore integration.

Development game launches use an isolated `CFFIXED_USER_HOME`, with an OS sandbox denying access to the real Hades save directory. The pre-audit native session on source `22c83b52dda6450de8b7f82a84fe890a49b8f002` preserved all 15 original file hashes and completed 133 requests without errors, including 100 consecutive status requests, hero and seven-resource edits, purchase bookkeeping that preserves gains, boon group acquisition/update/removal, Lucky Tooth's extra life, Companion weapon registration and consumed-use preservation. An already-running native God Gauge drain coroutine remained at the native cap after enabling the control. The native save payload excluded resident tables and temporary Trainer invulnerability/damage projections, while live invulnerability was restored. Room reload retained movement/dash projections; Disable All restored their observed native baselines and removed Trainer invulnerability.

The subsequent whole-module audit found seven defects tracked in [#568](https://github.com/TeaganRicardo/MacGamingTrainer/issues/568), including native maximum-health ownership and completed landing recovery that this earlier pass missed. Its candidate is held pending correction verification. These historical direct-call observations do not establish the corrected source's behavior. Full combat/menu/HUD and save-load acceptance require separate evidence. Attack timing, real reroll menus, every acquisition category and later game-authored persistence still require their own executed evidence. AppKit/control and package checks do not establish those results. Earlier development sessions on macOS 27.0.1 with Xcode 27.1 exited with a Rosetta translation-removal assertion; the final pass did not reproduce it. Its cause remains unconfirmed and is retained in [#565](https://github.com/TeaganRicardo/MacGamingTrainer/issues/565).
