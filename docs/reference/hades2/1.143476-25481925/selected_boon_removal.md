# Selected ordinary-boon removal (#546)

Target: Hades II **1.143476** / Steam **25481925**. The installed app's
`Contents/Info.plist` and Steam `appmanifest_1145350.acf` were read on 2026-10-23.
The raw `Contents/Resources/Content/Scripts` files below were inspected read-only;
the game was not launched or attached and no user/game save was read.

This narrows the earlier `operation_revalidation.md` sell-safe removal finding.
Native selling remains name-level. Trainer removal from a selected ordinary
Olympian/Hermes runtime row instead addresses that row's current instance ID.
Dedicated Selene, Chaos, Hammer, costume, temporary-effect, Familiar and Keepsake
owners retain their separate lifecycle paths.

## Native ownership evidence

| Source | Supported-build behavior |
| --- | --- |
| `TraitLogic.lua:1202-1219` | `RemoveWeaponTrait` loops until no trait of that name remains. `RemoveTrait` selects the first matching name. Neither function expresses a selected instance. |
| `TraitLogic.lua:1221-1245` | `RemoveTraitData` removes the supplied table from `unit.Traits`, reverses its property changes, refreshes native dictionaries/UI, and tears down the name's armor/ammo projections. |
| `UpgradeLogic.lua:330-373` | Weapon/projectile/effect property removal deletes every record whose `ParentTraitName` matches, including records belonging to same-name survivors. |
| `TraitLogic.lua:958-1003,1259-1283`; `CombatLogic.lua:183-194,212-223,240-251,265-276` | Modifier records carry a trait name rather than an instance ID. Removal consumes the first matching name; registry order cannot identify the selected instance after a trait-list reorder. |
| `TraitLogic.lua:1250-1257` | `OverrideWeaponFireNames` reversal shares the `SkipActivatedTraitUpdate` switch. Reversing a selected cast boon while a same-name sibling remains would remove the sibling's weapon swap. |
| `TraitLogic.lua:1285-1295` | Weapon data overrides are already recomputed from surviving traits by native teardown. |
| `TraitLogic.lua:600-770` | Dictionary, slot, element, rarity and value caches are rebuilt. The nonempty path does not first clear `FirstTraitWithPropertyCache`, so a final rebuild must clear that cache before repopulating survivor references. |
| `UpgradeLogic.lua:699-735,757-778` | Native weapon-target expansion/recording and the `ForceWeaponRefreshOnRemove` branch provide a weapon-only repair without reapplying survivor unit/Lua/health properties. |
| `HUDLogic.lua:1023-1098,1120-1127,1732-1788` | Exact removal destroys the selected trait's HUD anchor. A same-name survivor may need icon handover or an existing icon's count refresh. |
| `CostumeLogic.lua:47-72,155-201`; `PowersLogic.lua:3204-3232,3321-3327` | Ordinary Hephaestus armor uses a single current source per trait name, while remaining armor lives on its native trait owner. Unconditional source removal also erases a surviving ordinary armor boon's projection and temporary flag. |

The ordinary-boon helper therefore snapshots the actual modifier records, removes
the selected source-matching record (recursive processed-value comparison,
allowing extra live fields), and preserves surviving records and their live
state. It does not infer modifier ownership from the order of `Hero.Traits` and
does not reconstruct modifiers by reacquiring a boon. Equal source-valued
modifier records are mathematically interchangeable; the game exposes no
instance ID on those registry records. If no record matches the processed source,
command preflight refuses removal before the action ledger begins mutation;
it does not guess from trait-list position or rebuild a possibly used modifier.

With same-name survivors, the helper invokes exact native teardown once with
expiration and activated updates deferred, restores the surviving modifier
records, and rebuilds only this name's weapon property records through native
`RecordTraitPropertyChange`. For each affected weapon it invokes
`ProcessHeroTraitChanges({ Name = name, ForceWeaponRefreshOnRemove = weapon }, true)`.
That synthetic input has no unit properties or setup callbacks; the native
branch resets/reapplies the weapon before `CheckActivatedTraits` runs once.
Surviving trait objects are neither removed nor re-added. A callback error after
removal still allows each distinct repair once, then retains the failure for the
existing outcome-unknown action ledger.

## Last-instance expiration

The existing native last-instance expiration must remain enabled. Ordinary
`FocusLightningBoon` (`TraitData_Zeus.lua:1878-1894`), `FocusRawDamageBoon`
(`TraitData_Aphrodite.lua:2003-2019`), `DamageShave`
(`TraitData_Poseidon.lua:2212-2229`) and `ReserveManaHitShieldBoon`
(`TraitData_Demeter.lua:1978-2002`) call `TraitUnreserveMana` on expiration.
`PowersLogic.lua:3347-3358` holds these reservations by source name. A same-name
survivor still owns that source; removal of the last instance releases it.
Ares mana/blood boons also use `CheckBloodDropDisplay` on expiration
(`TraitData_Ares.lua:1419,1866`).

The current ordinary Olympian/Hermes/Duo/Elementals source files have no
`ActivatedPropertyChanges`, `WeaponAmmoModification`, or `AddEffectMultiplier`.
They do include ordinary costume-armor state: `ArmorBoon` inherits `CostumeTrait`
(`TraitData_Hephaestus.lua:1743-1799`), and `EncounterStartDefenseBuffBoon` sets
`CostumeTrait` / `IsRenewableArmor` directly (`1823-1872`). Their source family
remains ordinary Olympian/Hermes; the CostumeTrait implementation marker does
not transfer them to Arachne's dedicated owner.

## Remaining armor and the native source owner

`AddHealthBuffer` assigns `HealthBufferSources[name]`, rather than adding a
per-instance entry. `HephaestusArmor` and `EncounterStartTempArmorThread` obtain
the first mounted instance through `GetHeroTrait(name)`
(`TraitLogic.lua:495-500`), set that owner's `CurrentArmor`, then project it into
the name source. `OnHealthBufferDamage` consumes actual `CurrentArmor` and writes
the remaining amount into that source. Acquisition/setup amounts therefore
cannot establish how much armor remains.

When an existing name source has same-name armor-bearing survivors, selected
removal reprojects the first surviving armor owner's current `CurrentArmor` and
restores the existing temporary-source flag. It recalculates total HealthBuffer
from the source map and requests the native health UI refresh. It leaves every
surviving row's `CurrentArmor` unchanged, preserves unrelated sources, and calls
neither acquisition nor armor setup. The selected peer's source amount is not
retained when it differs from the remaining owner. Multiple surviving peers do
not become independently summed sources: the supported native model exposes
one projection per name with first-survivor precedence.

An absent source remains absent even if a mounted peer still has an old
`CurrentArmor` value. Removing the last instance retains native source/flag
cleanup. For temporary armor, the existing coroutine still owns its original
captured source trait, name and deadline; the helper does not restart it, replace
its captured references or extend its duration. The original expiration may
therefore clear the repaired name source at the original deadline.

The owning fixture now includes native-style unconditional
`RemoveTraitData -> RemoveHealthBufferSource` teardown. Before this correction,
the added consumed-armor case reproduced on production base `e3f0134` with:

```text
ordinary removal lost surviving armor source: expected=7 actual=nil
```

After correction, its nine isolated resident scenarios cover renewable and
temporary armor, selected first/second owner direction, differing selected and
surviving amounts, consumed current armor, first-survivor precedence, absent
sources, existing temporary expiry, last-instance cleanup and late native
acknowledgement without replay. This is fixture evidence for those boundaries,
not a real-game duplicate-armor acceptance claim.

## Source identity and evidence limits

SHA-256 of the inspected installed source files:

```text
TraitLogic.lua    268c08251c8b05c6a26ca4f6f9642ea6c6a0314c62fc194dd853d96372b53c5e
UpgradeLogic.lua  cc1e8e58fb8af2390c83e66e3728631dd1691bfd3ee1d0be72dcfd03fdec9657
CombatLogic.lua   bcd39b6b1bc8b8a823b2eb4e9d14bb3a1f45b6fab5721ebe31275733b893226f
CostumeLogic.lua  13bc6918e904db86c9da5072c69d02fd76e3f583e3e3688231fae7c86f847c40
HUDLogic.lua      d52022d6db02823848136f2ea651cba57904b72b35741038952e011621504ffb
PowersLogic.lua   285e31da5d73e83a4f2636c9b88ca242f408479fbfb67581d0630f41f73457e0
TraitData_Hephaestus.lua 91271a44a466cc02354df2406ddad62f9fb5a1f1c22cadd6d1d16cf485cf1904
```

These source semantics and the resident behavior fixture establish the
implementation boundary. They do not establish rendered/native game acceptance
for duplicate-boon removal, HUD handover, weapon effects, or save/reload behavior.
