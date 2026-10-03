# Hades II 1.143476 / Steam 25481925 operation revalidation

Target: Hades II **1.143476** / Steam build **25481925**

Baseline operation reference: `../1.139672-24556151/buff_operation_matrix.md`.

This is the narrow D00 / #186 delta review for operation-sensitive semantics. It is **not** a new census, legality catalog, or generated inventory. Canonical target IDs and the existing direct/special legality decisions remain owned by the retained 1.139672 reference lineage unless this report identifies a concrete target-build change.

## Evidence scope and method

The current executable identity is the already accepted compatibility target from PR #172:

- Steam build `25481925`;
- app version `1.143476`;
- macOS arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`;
- pristine executable SHA-256 `933a2db2251a3fddd70900016f323338690235c7b3aae63edd4a78ca18c3bfe3`.

PR #172's target-machine static compatibility pass established that all 111 curated reward/trait IDs used by the Trainer remained present on 25481925, along with all resident Lua dependencies and current terminology IDs. This task did not repeat that census.

For D00, the existing installed 1.143476 target's raw Lua files were inspected read-only, without launching the game. Only functions/data that decide the requested operation semantics were inspected:

- `TraitLogic.lua`
- `UpgradeChoiceLogic.lua`
- `LootData_Chaos.lua`
- `LootData_Selene.lua`
- `SpellData.lua`
- `SpellLogic.lua`
- `LootData.lua`
- `SellTraitLogic.lua`

The retained 1.139672 matrix is the comparison baseline. Generated inventories remain existence/reference evidence only and were not used to infer support.

Classification meanings:

- **unchanged** — the 25481925 owner/lifecycle path still establishes the same downstream contract as the baseline;
- **changed** — the owner, pool, requirement, lifecycle, or runtime identity relevant to downstream work changed;
- **unresolved** — current static evidence is insufficient; affected downstream work must remain blocked.

## Result summary

| Operation family | 25481925 classification | Result |
| --- | --- | --- |
| Olympian/Hermes eligibility, replacement, stack | **unchanged** | Native dynamic eligibility remains authoritative; owned exact traits are filtered, replacement removes the occupied slot trait, and `StackUpgrade` levels an existing eligible GodTrait. |
| 74 direct special-NPC acquisition seams | **unchanged** | The approved IDs remain present from the current-target compatibility pass; exact application still must use `FromLoot=true`, which continues to gate acquire/heal mechanics. No new direct IDs are introduced here. |
| Chaos curse → blessing lifecycle | **unchanged** | `TrialUpgrade` remains a transforming pair of 16 permanent blessings and 17 temporary curses; expiry installs the paired blessing and preserves the runtime trait ID. |
| Selene spell / talent-tree ownership | **unchanged** | `SpellDrop -> OpenSpellScreen` still owns the flow; 9 main spell records remain, `MoonBeam` remains skipped, and 93 active named talent IDs remain tree/requirement-owned. |
| Hammer / Daedalus weapon/aspect eligibility | **unchanged** | `WeaponUpgrade` still contains 92 source traits; current eligibility remains dynamic through weapon-slot filtering plus normal `IsTraitEligible`/requirements. |
| Native SellTraits eligibility / teardown | **unchanged** | Native sell generation still admits only `IsGodTrait(name, { ForShop=true })` traits with rarity, then removes by name through `RemoveWeaponTrait`. |
| Runtime trait identity | **unchanged** | New runtime traits still receive `trait.Id`; lifecycle-sensitive equality still uses that ID, and Chaos expiry transfers it to the blessing. Cross-run/reload stability remains unproven. |

No requested family is classified **changed**. No canonical ID/pool ledger update is required.

## 1. Olympian / Hermes eligibility, replacement and stack

Classification: **unchanged**.

The current target retains the same source-owned selection model.

In `TraitLogic.lua`, `SetTraitsOnLoot` still:

- computes rarity through the source loot object;
- uses replacement selection through `GetReplacementTraits`;
- uses priority selection through `GetPriorityTraits`;
- applies trait-level `GameStateRequirements` and `PriorityRequirements`;
- delegates remaining choices to `GetEligibleUpgrades`.

Current-target evidence is around `TraitLogic.lua:1760+`, including the replacement branch near lines 1793-1803 and priority / game-state filtering immediately afterward.

In `UpgradeChoiceLogic.lua:899-937`, `GetEligibleUpgrades` still:

- builds stack choices from `GetAllUpgradeableGodTraits` when `lootData.StackOnly`;
- removes an already-owned exact trait from ordinary non-stack eligibility;
- applies `IsTraitEligible` unless requirements are explicitly stripped.

Existing-owned handling is also unchanged:

- replacement: `HandleUpgradeChoiceSelection` checks `TraitToReplace`, calls `RemoveWeaponTrait`, then adds the replacement with `FromLoot=true` (`UpgradeChoiceLogic.lua:952-955`);
- stack: `StackOnly` calls `IncreaseTraitLevel` on the existing trait (`958-962`);
- normal selection: the chosen trait is added with `PreProcessedForDisplay=true, FromLoot=true` (`971`).

The ten baseline concrete Olympian/Hermes loot sources remain the same operation owners:

`ZeusUpgrade`, `HeraUpgrade`, `PoseidonUpgrade`, `DemeterUpgrade`, `ApolloUpgrade`, `AphroditeUpgrade`, `HephaestusUpgrade`, `HestiaUpgrade`, `AresUpgrade`, `HermesUpgrade`.

Their continued target-build presence is covered by the accepted PR #172 static curated-ID check; this task does not manufacture a new boon list from `TraitData` or generated references.

Downstream contract remains:

- do not flatten GodLoot references into a generic addable list;
- evaluate eligibility at operation time;
- reject an already-owned exact ordinary trait as a new-choice operation;
- model replacement explicitly through `TraitToReplace`;
- use `StackUpgrade` / existing-trait level semantics for stacking.

## 2. 74 direct special-NPC acquisition seams

Classification: **unchanged**.

The canonical set is still exactly the rows already classified `kind=trait, classification=direct` in `../1.139672-24556151/catalog_legality.csv`. This report intentionally does not duplicate those 74 IDs.

Two independent current-target facts preserve the approved seam:

1. PR #172's installed-build static compatibility pass confirmed that all 111 curated reward/trait IDs remained present on 25481925, so the retained 74 direct targets did not disappear from the supported target.
2. The native acquisition mechanic that justified direct exact application remains intact.

In the current target `TraitLogic.lua`:

- `AddTraitData` assigns the new runtime ID at line 897;
- only when `args.FromLoot` is set does it run `HealOnAcquire` and `AcquireFunctionName` (`901-905`).

In current-target `UpgradeChoiceLogic.lua`, native selected traits continue to enter through `AddTraitToHero(... FromLoot=true)` in `HandleUpgradeChoiceSelection`.

The Trainer's existing exact special-trait seam also continues to call:

`AddTraitToHero({ TraitName = entry.trait, FromLoot = true })`

in `Backend/games/hades2/runtime/hades.lua`, while the separately classified Arachne path still performs the extra `SetupCostume()` step. This confirms that no one-language/generated-inventory shortcut has replaced the source-approved acquisition mechanic.

This is an operation revalidation, not a new source census. The 74-target set must continue to come from the existing canonical legality ledger.

Downstream contract remains:

- the 74 retained direct targets may use the exact `FromLoot=true` application seam;
- source eligibility is intentionally bypassed only for that exact direct operation;
- already-owned exact special targets still have no generic duplicate/level policy proven by this evidence;
- Arachne costumes, `EchoLastRunBoon`, Well traits, and other existing special rows stay outside this direct set.

## 3. Chaos curse → blessing lifecycle

Classification: **unchanged**.

Current `LootData_Chaos.lua` still defines `TrialUpgrade` with `TransformingTraits = true`.

The target-build source pools are unchanged from the baseline:

- `PermanentTraits`: **16** blessing IDs (`LootData_Chaos.lua:59-66`);
- `TemporaryTraits`: **17** curse IDs (`67-73`).

`TraitLogic.SetTransformingTraitsOnLoot` still chooses one eligible permanent trait and one eligible temporary trait and emits a `TransformingTrait` pair (`TraitLogic.lua:1710-1744`).

`UpgradeChoiceLogic` still materializes that pair by creating processed blessing and curse data and assigning:

`curseData.OnExpire.TraitData = blessingData`

around `UpgradeChoiceLogic.lua:350-354`.

The teardown/transform path remains lifecycle-significant. In current `TraitLogic.RemoveTraitData`:

- `OnExpire` is processed unless `SkipExpire` is set;
- an `OnExpire.TraitData` replacement receives `expiringActions.TraitData.Id = trait.Id`;
- the replacement is added with `FromLoot=true` (`TraitLogic.lua:1304-1320`).

Downstream contract remains:

- Chaos must be represented as a paired staged flow, not two independent addable trait buckets;
- generic removal is not equivalent to cancellation because normal expiry can transform curse → blessing;
- `SkipExpire` would intentionally bypass the native lifecycle and therefore is not the default removal contract.

## 4. Selene spell and talent-tree ownership

Classification: **unchanged**.

Current `LootData_Selene.lua` still defines:

`SpellDrop.OnUsedFunctionName = "OpenSpellScreen"`

at line 26, so the native Spell screen remains the owner of the acquisition flow.

Static inspection of current `SpellData.lua` gives the same main-spell set as the baseline:

`Polymorph`, `Meteor`, `Transform`, `Leap`, `Laser`, `Summon`, `TimeSlow`, `Potion`, `MoonBeam`.

Count: **9**.

`MoonBeam` still carries:

`GameStateRequirements = { Skip = true }`

at `SpellData.lua:690-695`, leaving eight ordinary selectable main records under the same baseline interpretation.

After removing Lua line comments, the current file still contains **93 active named `*Talent` IDs**. The count is unchanged, but it is not an acquisition list.

`SpellLogic.CreateTalentTree` still owns tree construction (`SpellLogic.lua:1+`) and applies:

- spell-defined repeatable/unique/legendary pools;
- talent `GameStateRequirements`;
- tree-structure `GameStateRequirements`;
- duo/legendary eligibility;
- depth/node structure and linking.

The runtime owner remains broader than a trait row: current spell logic reads and mutates `CurrentRun.Hero.SlottedSpell` and its `Talents` tree.

Downstream contract remains:

- main spell acquisition belongs to the native Spell flow;
- talents must be operated through the tree/requirements model;
- do not expose 93 flat independent “talent add” targets;
- generic trait teardown remains insufficient to define spell/talent removal.

## 5. Hammer / Daedalus weapon and aspect eligibility

Classification: **unchanged**.

Current `LootData.lua` still defines `WeaponUpgrade` as a non-GodLoot native weapon upgrade source.

Its `Traits` array remains exactly **92** IDs (`LootData.lua:257-362`), matching the baseline count.

Current eligibility is still dynamic rather than name-derived:

- `GetEligibleWeaponTraits` removes traits whose slot conflicts with traits already owned by the hero (`UpgradeChoiceLogic.lua:824+`);
- the resulting upgrade set still passes through the ordinary `GetEligibleUpgrades` filter;
- `GetEligibleUpgrades` applies `IsTraitEligible` for non-stack choices (`UpgradeChoiceLogic.lua:924-930`), preserving trait requirements including weapon/aspect constraints.

Downstream contract remains:

- no flat “92 hammers are always addable” operation;
- current weapon/aspect and trait requirements must be evaluated at operation time;
- Hammer remains distinct from ordinary GodLoot stacking/replacement;
- no native SellTraits evidence authorizes generic Hammer deletion.

## 6. Native SellTraits eligibility and teardown

Classification: **unchanged**.

Current `SellTraitLogic.GenerateSellTraitValues` still admits a runtime trait only when:

- `IsGodTrait(traitData.Name, { ForShop = true })`;
- the runtime trait has `Rarity`;
- the name is not explicitly excluded.

Evidence: `SellTraitLogic.lua:45-53`.

Current `TraitLogic.IsGodTrait` still treats a trait as shop-God-owned only through its owning `LootData` / `FieldLootData` source and `GodLoot` or `TreatAsGodLootByShops` semantics (`TraitLogic.lua:1547-1558`).

Current selection teardown remains name-level:

`HandleSellChoiceSelection -> RemoveWeaponTrait(button.UpgradeName, { Silent=true })`

at `SellTraitLogic.lua:327-329`.

`RemoveWeaponTrait` still loops while the hero has that name and removes matching traits (`TraitLogic.lua:1202-1210`). Therefore the native operation continues to prove **name-level/all-matching** removal, not single-instance deletion.

Downstream contract remains:

- the first product-safe removal capability is the currently sell-eligible GodTrait subset;
- do not equate “`RemoveTraitData` can clean up a trait” with “every trait is safe to expose for deletion”;
- Chaos, Selene, Hammer/aspect, Well-duration, costume and other owner-specific lifecycle families remain outside the generic sell-safe subset.

## 7. Runtime trait identity

Classification: **unchanged** for the current-run identity contract.

Current `TraitLogic.GetTraitUniqueId` still produces a runtime ID and `AddTraitData` still assigns:

`newTrait.Id = newTrait.Id or GetTraitUniqueId()`

(`TraitLogic.lua:593-598, 897`).

`AreTraitsIdentical` still compares `Id` for lifecycle-sensitive forms including:

- `DoNotStackIcons`;
- Chaos last-curse / last-blessing shapes;
- traits with `RemainingUses`.

Evidence: `TraitLogic.lua:580-590`.

Chaos expiry still transfers the curse ID into the resulting blessing before adding it (`TraitLogic.lua:1315-1320`).

This keeps `trait.Id` valid as a **current-run instance identity** for D01 observation/planning.

One sub-question remains explicitly **unresolved**, exactly as in the baseline: no evidence here establishes that `trait.Id` is stable across run reload, game restart, or serialized save round-trip. D01 must not persist or compare it as a durable cross-run identifier.

## Changed IDs / pools / requirements

None found within the operation-sensitive scope.

Specifically unchanged counts/sets that would have required a lineage update if they differed:

- Chaos: 16 permanent blessings / 17 temporary curses;
- Selene: 9 main spell records, `MoonBeam Skip=true`, 93 active named talent IDs;
- Hammer: 92 `WeaponUpgrade.Traits`;
- retained curated reward/trait IDs: present on 25481925 per PR #172.

Therefore:

- do **not** copy or fork `catalog_legality.csv`;
- do **not** create a second direct/special legality table;
- keep the existing retained ledger as the canonical ID/classification source;
- use this file only as the 25481925 operation-semantics delta evidence.

## Downstream blockers and permissions

### D01 current-run traits + sell-safe removal

D00 no longer blocks D01 on target-build operation semantics.

The proven inputs remain:

- enumerate current runtime trait instances;
- expose current-run `trait.Id` as instance identity;
- derive delete capability from the native SellTraits predicate/owner semantics;
- implement the first delete mode as native name-level/all-matching sell semantics.

Still blocked/not authorized by this evidence:

- single-instance native sell deletion;
- durable cross-run use of `trait.Id`;
- generic deletion for non-sell categories.

### Ordinary Olympian / Hermes future acquisition

Operation model is revalidated, but future implementation must still reproduce/evaluate native eligibility and replacement rules at operation time. This report does not authorize flat raw `AddTraitToHero` for ordinary boons.

### 74 direct special-NPC targets

The previously approved direct exact-apply subset remains usable through the `FromLoot=true` seam. No additional direct IDs are admitted.

### Chaos

Ready for a dedicated paired native-flow task. Raw independent curse/blessing add and generic delete remain unauthorized.

### Selene

Ready for a dedicated Spell/talent-tree task. Flat talent acquisition/removal remains unauthorized.

### Hammer

Ready for a dedicated weapon/aspect-aware native-choice task if selected. Flat 92-item add/remove remains unauthorized.

## Argent Skull ammo recovery under infinite supply

Target-build 1.143476 / Steam 25481925 confirms that recoverable Argent Skull ammo is owned by the native `WeaponLob` lifecycle rather than by a generic inventory counter.

- `WeaponLob` uses `MaxAmmo = 4`, `OnProjectileDeathFunction = "WeaponLobAmmoDrop"`, and `AmmoPackName = "LobAmmoPack"`.
- Its fired callback exits immediately when the native `UnlimitedAmmo` trait value is present. Otherwise it records the carried-ammo snapshot, increments `SessionMapState.LobAmmoInFlight` (including `NumProjectiles` for spread fire), and spends ammo.
- `WeaponLobAmmoDrop` requires positive in-flight ammo, decrements that bookkeeping, and materializes a native `LobAmmoPack`.
- `LobAmmoPack` adds one `WeaponLob` ammo through `AddAmmo`; that path also executes `OnCollectAmmoFunctionName` effects. The pack escalates magnetism after 10 seconds, so lifetime/cleanup remains game-owned.
- `LobGunAspect` is a distinct native no-recovery mode: its trait data sets `UnlimitedAmmo = true`, hides the ammo UI, and removes the projectile-death ammo-drop callback.

Therefore Trainer infinite ammo must not spoof the native `UnlimitedAmmo` trait value. It may suppress negative `UpdateWeaponAmmo` deltas to keep carried ammo available while leaving the fire, in-flight, projectile-death, pickup and collection-effect paths native. The real `LobGunAspect` signal remains untouched and keeps its own native semantics.

## Verification expectation

This file changes reference documentation only. No runtime, adapter, Host/UI, protocol, Save/Profile, product version, canonical legality CSV, generated inventory, or resident Lua source is changed.

Applicable repository verification is therefore the docs/reference Markdown path plus the existing required-check routing. No game launch or in-game acceptance is required for D00.
