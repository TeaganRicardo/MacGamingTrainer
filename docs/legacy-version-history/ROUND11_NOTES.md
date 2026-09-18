# Mac Gaming Trainer v0.11.0 — Round 11

- App version: 0.11.0
- Build: 16
- Backend protocol: v3
- Lua runtime revision: 19
- Base: v0.10.0 / Build 15 / Round 10

## 1. Feature-state presentation

Enabled features that are genuinely waiting for a usable game environment now use the same orange warning treatment as a runtime-invalid feature. Detached desired state remains muted gray-green.

A short activation grace window prevents a freshly enabled switch from flashing orange while the Backend/Lua hook is still mounting. The grace path covers direct clicks, reconnect replay and profile-driven false-to-true state changes. Once the runtime reports the feature active, the grace state is cleared immediately.

## 2. Crossroads availability

The runtime now separates build support from scene availability (`statSupport` vs `statAvailable`). This allows save/global controls to remain usable in the Crossroads without incorrectly enabling Hero-bound controls.

Available without a live combat Hero where the underlying game tables/functions exist:

- Grasp target/lock (`GetMaxMetaUpgradeCost` + `GameState.MaxMetaUpgradeCostCache`)
- Garden quality-of-life hooks
- Boon rarity control
- Boon choice count
- Auto fishing/exorcism hooks
- Money/resource multiplier hooks and resource locks
- Save-backed resource editing
- Global game speed
- Pending next-room reward configuration

Combat-Hero features (health/mana/god mode/damage/cast/ammo and Hero-bound stats) retain their desired state and report dormant until a usable run exists. They are reconciled automatically when a run returns.

Resource edits in the Crossroads no longer fabricate a run. When native per-run accounting tables are unavailable, edits are applied to `GameState.Resources` and lifetime gained/spent accounting is updated directly. Native Add/Spend is used only when both `CurrentRun.ResourcesGained` and `CurrentRun.ResourcesSpent` exist.

A pending next-room reward is now part of desired runtime state, so it survives Crossroads -> run transition and is consumed by the first eligible ordinary room reward.

## 3. Repeated Cast / no-cooldown fix

The previous implementation opened the visible cast cooldown/effect gates but could still be blocked while the existing binding circle remained alive.

Round 11 mirrors the engine controls used by repeatable/projected-cast paths more completely:

- `IgnoreOwnerAttackDisabled = true`
- `Cooldown = 0`
- `AllowMultiFireRequest = true`
- `IgnoreForceCooldown = true`
- `ActiveProjectileCap = 32`
- `WeaponCastAttackDisable.Active = false`
- `WeaponCastSelfSlow.Active = false`
- `WeaponCastSelfSlow2.Active = false`

The important new part is `ActiveProjectileCap`: the trainer no longer assumes cooldown is the only gate. Existing cast projectiles are left alive; their duration, damage, boon hooks and visuals are not force-expired. The trainer only raises the live-projectile slot limit while the feature is enabled.

All modified WeaponCast properties are snapshotted and restored on disable. Native cast boons remain authoritative: game writes observed while the trainer is active update the restoration snapshot instead of being discarded.

Runtime diagnostics now identify this path as `nativeMultiCastControlSet` and expose the observed weapon properties plus tracked live casts.

## 4. Scene/hook lifecycle hardening

`installHook` now supports session-scoped hooks in addition to run/Hero-bound hooks. Hooks mounted with no Hero can therefore operate in the Crossroads instead of failing solely because `CurrentRun.Hero` is absent.

Game speed is explicitly session-scoped because its global elapsed-time layer is intentionally preserved across run/Hero transitions. Other runtime groups continue to be released/reconciled on identity changes.

## 5. Protocol

Protocol v3 adds explicit scene availability semantics used by the GUI (`statAvailable`) and prevents mixing this release with the Round 10 Backend.

## Target-Mac regression priorities

1. Enable Cast availability and place several normal casts before earlier circles expire; verify each new cast appears and older circles complete normally.
2. Repeat with cast-altering boons (especially projected/ranged cast variants), then disable the trainer feature and confirm native behavior/cap returns.
3. In the Crossroads, edit/lock Grasp, resources, resource multipliers, boon choices and garden QoL; confirm they act immediately rather than merely storing desired state.
4. Enable a run-only switch in the Crossroads: it should become orange after the activation grace and automatically become active after entering a run.
5. Toggle a feature inside a valid run and watch the switch during the normal hook-mount delay; it should not flash orange.
6. Set a next-room reward in the Crossroads, enter a run and verify the first eligible room receives it.
7. Keep game speed != 1 while moving Crossroads -> run -> next room; confirm the factor remains stable and restores to 1 when disabled.
8. Run the in-app self-check and export diagnostics if any cast or scene transition case differs on the target build.
