# God Mode Hit Semantics Design

## Scope

This is the first independently testable slice of Phase 0 Batch B. It changes only Hades II resident runtime semantics for God Mode. Game-speed work is a separate sub-project and is not part of this change.

Target game build: Hades II 1.139672 / Steam build 24556151.

## Required behavior

While God Mode is active:

- ordinary hostile damage must not reduce health or armor;
- hostile hit-stun / knockback / ordinary on-damage processing must not run through the vanilla `Damage()` body;
- the save-backed/current-run Hero hit counter must not increase;
- the already-proven Hecate polymorph and Mourning Fields miasma protections must remain active;
- player buffs and self-selected curse mechanics must remain native;
- no broad `ApplyEffect` interception is allowed.

When God Mode is disabled, the exact pre-God-Mode hit count is restored/preserved and later real hits resume native counting.

## Why the hit counter needs an explicit invariant

In the audited 1.139672 `CombatLogic.lua`, the engine `OnHit` handler executes:

```lua
victim.Hits = (victim.Hits or 0) + 1
...
Damage(victim, triggerArgs)
```

The increment therefore occurs before the trainer's existing named `Damage` hook. `SetUnitInvulnerable` and an early return from `Damage` prevent health loss, but they do not by themselves undo `Hero.Hits`.

The trainer must capture the Hero's exact `Hits` value when God Mode binds to that Hero and keep that value invariant for the lifetime of that binding. Preserve `nil` as `nil`; do not normalize it to zero in saved state.

## Runtime design

Keep the existing boundaries:

1. `SetUnitInvulnerable(hero, "MacGamingTrainerGodMode")` remains the engine-level invulnerability source.
2. The shared trainer `Damage` router remains the named Lua damage boundary and returns before the vanilla `Damage` body when God Mode is active.
3. `AddEffectBlock` remains the mechanism for individually audited hostile effects that bypass ordinary invulnerability semantics.
4. The existing `UpdateTimers` guard may enforce the hit-count invariant because it is already resident while a desired feature is active. Do not add another timer or polling loop.

Add only three pieces of state: bound Hero identity, exact baseline `Hits` value, and a boolean distinguishing an intentional nil baseline from an uninitialized baseline.

On a God-Mode-blocked `Damage` call, restore the baseline immediately before returning. The frame guard repeats the same restoration as a safety invariant so an engine hit path that increments `Hero.Hits` but does not reach the vanilla `Damage` body cannot leak the counter into a later save.

On release, restore the baseline one final time before clearing the binding state.

## Hostile-effect policy for this slice

Retain the audited explicit block list:

- `HecatePolymorphStun`
- `MiasmaSlow`

Do not broaden the list merely because an effect has `CanAffectInvulnerable`, `DisableMove`, or a stun-like name. Those fields are also used by player-owned buffs, weapon locks, narrative state, and self-selected Chaos curses.

The broader hostile-effect audit remains a later task in Batch B. In particular, `ChronosPolymorphStun` is presentation/narrative-coupled in the audited scripts and must not be blocked by name without a separate proof that doing so cannot break encounter state.

## Lifecycle

A Hero/session/run identity change already calls `deactivateRuntime(true)`. That releases God Mode on the old Hero, restores the old baseline, and then desired-state reconciliation installs God Mode on the new Hero with a fresh baseline.

A runtime source change increments resident revision 39 → 40.

## Verification

Static contract must prove:

- revision 40;
- a distinct nil-preserving hit baseline exists;
- `installGodMode` captures `hero.Hits`;
- the God Mode branch of the shared `Damage` router restores the baseline before returning;
- the existing guard enforces the baseline while active;
- `releaseGodMode` restores then clears the baseline;
- no `ApplyEffect` hook is introduced;
- existing explicit hostile-effect blocks remain unchanged.

Manual acceptance must compare the save/current runtime hit counter before and after taking repeated enemy hits with God Mode enabled, then disable God Mode and verify the next real hit increments normally.
