# Hades II buff operation matrix

Target: Hades II **1.139672** / Steam build **24556151**

This document is the operation-safety handoff for planning package P17 / F14. It does not create a second legality catalog. The existing snapshot remains authoritative for identifiers and trainer-facing exposure decisions; this matrix answers a different question: **which native owner and lifecycle must a future add, replace, level, or remove operation preserve?**

## Evidence and confidence rules

Evidence is ordered from strongest to weakest for operation semantics:

1. target-build raw script evidence retained in the private evidence bundle described by `../README.md`;
2. curated ledgers in this snapshot (`catalog_legality.csv`, `native_interactions.csv`, `well_shop.csv`);
3. generated inventories/reference indexes such as `generated/traits.csv` and `generated/trait_references.csv`.

`generated/trait_references.csv` is a static reference index, not an acquisition pool. It can contain prerequisites, aspects, keepsakes, temporary helpers, or other trait references from the same source file. It must not be flattened into a list of addable boons.

The matrix uses three values for lifecycle facts:

- **proven** — the supported build contains a concrete native path that establishes the behavior;
- **false** — the supported build establishes that the behavior does not apply;
- **unknown** — evidence is insufficient; do not treat this as false or implement by guess.

## Closed trait boundary

The generated trait inventory contains 968 rows / **670 unique IDs**. That is deliberately broader than the Trainer-facing trait catalog.

The closed independent trait catalog is exactly **96** targets:

- 83 special-NPC traits from ten native sources;
- 13 Charon-Well traits.

Within those 96 targets:

- **74** special-NPC traits are already classified `direct`;
- **8** Arachne costume traits are `special`;
- **1** Echo trait, `EchoLastRunBoon`, is `special`;
- **13** Well traits are `special`.

The canonical IDs remain in `catalog_legality.csv`; this file does not duplicate that ledger. Ordinary Olympian/Hermes boons, Chaos, Selene, Hammer traits, aspects, keepsakes, Arcana/meta traits, familiar traits, and internal state markers remain owned by their native systems rather than becoming independent catalog rows merely because they exist in `TraitData`.

## Operation matrix

| Family | Native owner / source | Natural acquisition | Add / replace classification | Existing-owned semantics | Prerequisite / mutual-exclusion evidence | Teardown evidence | Runtime identity | Downstream |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Ordinary Olympian + Hermes boons | Ten concrete GodLoot sources: `ZeusUpgrade`, `HeraUpgrade`, `PoseidonUpgrade`, `DemeterUpgrade`, `ApolloUpgrade`, `AphroditeUpgrade`, `HephaestusUpgrade`, `HestiaUpgrade`, `AresUpgrade`, `HermesUpgrade` | `SetTraitsOnLoot` / `GetEligibleUpgrades` builds a current eligible choice set, then `HandleUpgradeChoiceSelection` applies with `FromLoot=true` | **native-choice-derived**. A raw flat `AddTraitToHero` bypass is not pre-approved. P18 may expose an exact target only after reproducing the source's current eligibility/replacement rules. | Native choices remove already-owned traits from ordinary eligibility. `StackUpgrade` is the separate native level-up operation. Replacement options carry `TraitToReplace` and remove the old weapon-slot trait before adding the new one. | **proven dynamic**: `TraitRequirements`, `IsTraitEligible`, `GameStateRequirements`, `PriorityRequirements`, banned traits, slot/replacement handling and rarity all participate. | **proven subset only**: native SellTraits exposes only `IsGodTrait(name, { ForShop=true })` traits with rarity and removes by `RemoveWeaponTrait(name)`. This is not proof that every GodLoot-referenced trait is sellable. | Game trait instances have `trait.Id`, but Trainer status does not expose it. | **P18 input**; **P22 sell-eligible subset** |
| 74 direct special-NPC traits | Artemis 9, Athena 8, Dionysus 8, Hades 8, plus direct members of Narcissus, Echo, Medea, Circe and Icarus; exact IDs are the `classification=direct` trait rows in `catalog_legality.csv` | Native special-choice source or exact application through the audited `FromLoot=true` seam | **direct exact apply proven**. `FromLoot=true` is mandatory because acquire/heal functions depend on it. | Native special-choice generation excludes an already-owned exact trait. No generic “duplicate/level existing special-NPC trait” policy is proven; P18 should reject already-owned exact targets unless a source-specific rule is demonstrated. | Native special-choice paths check current ownership, picked traits, `GameStateRequirements` and priority requirements. Exact direct application intentionally bypasses source eligibility, but not acquisition mechanics. | Generic `RemoveTraitData` exists, but no blanket product-safe removal set is proven for all 74. Some acquire functions mutate non-trait state. | `trait.Id` is generated on add. Not Host-exposed today. | **P18 ready subset**; P22 requires per-family teardown proof |
| Arachne costumes (8) | `NPC_Arachne_01` / Arachne native choices | Native Arachne choice | **special**. Acquisition additionally requires `SetupCostume()` to refresh the hero presentation after the trait is added. | Native choice excludes already-owned exact options; replacement/stack behavior outside that flow is not generalized. | Choice-pool requirements are source-owned. | **unknown for Trainer deletion**: removing the trait object alone does not prove costume presentation/state is restored correctly. | `trait.Id` exists; no Host projection. | Keep out of generic P18/P22 direct path unless dedicated costume teardown is proven |
| `EchoLastRunBoon` | Echo native choice | Echo previous-run boon flow | **native choice only**. Its acquire function waits on the active boon-menu context; raw exact injection can leave the acquire thread waiting. | Native choice owns eligibility. | **proven source-owned**. | **unknown** as an arbitrary Trainer deletion target. | `trait.Id` exists; no Host projection. | Native-choice only; not a raw P18 direct target |
| Charon-Well traits (13) | `RoomShop`; exact IDs in `well_shop.csv` | Processed store-trait path | **dedicated store handler**. Native semantics include processed trait data, duration/RemainingUses, stacking and store extension handling. | Existing-store-trait behavior is duration/stack dependent rather than a generic duplicate rule. | Store state and duration logic are owner-specific. | **unknown for arbitrary deletion**. `RemoveTraitData` can process expiration, but forcing removal may consume/trigger lifecycle effects at the wrong time. | `trait.Id`; RemainingUses may also distinguish lifecycle state. | Existing reward path remains special; do not fold into generic P18/P22 |
| Chaos | `TrialUpgrade` / `LootSetData.Chaos` | `TransformingTraits`: one blessing and one temporary curse are paired in the native choice | **staged native flow**. The supported build has **16 blessing IDs** and **17 curse IDs** in the source pools. The selected curse receives `OnExpire.TraitData = blessingData`. | Pairing and expiration are the operation. A blessing or curse is not an independent flat add target merely because it is a TraitData row. | **proven pair/lifecycle requirements**; native selection still applies eligibility and rarity rules. | **not generic-delete safe**. Normal curse removal/expiry can transform into the paired blessing; `SkipExpire` would instead bypass intended lifecycle. | `trait.Id` exists, and the expiry transform copies the same ID to the blessing, so a current-run identity can survive the curse→blessing transition. | **P19 input** |
| Selene / Hex | `SpellDrop` → `OpenSpellScreen`; `SpellData` + `SpellTalentData` | Native Spell screen and talent tree | **staged native flow**. `SpellData` defines **9** main spell records; `MoonBeam` is currently marked `Skip=true`, leaving eight ordinary selectable main records. The source contains **94 named talent IDs**, but eligibility is tree/requirement dependent and must not be flattened into 94 independent choices. | Main spell state is held in `CurrentRun.Hero.SlottedSpell`; talents have tree/depth/link structure and requirements. | **proven dynamic**: `CreateTalentTree`, spell/talent `GameStateRequirements`, duo eligibility and tree links. | **dedicated teardown required**. Spell weapons, slotted spell state and talents make generic `RemoveTrait` insufficient as a product contract. | Trait IDs exist, but the controlling identity also includes slotted-spell/talent-tree state. | **P20 input** |
| Daedalus / Hammer traits | `WeaponUpgrade` | Native WeaponUpgrade choice | **native weapon-choice**. The supported source has **92** exact `WeaponUpgrade.Traits` entries. `GetEligibleWeaponTraits` / `IsTraitEligible` decides the current legal subset, including aspect/weapon constraints. | Multiple hammers can coexist subject to weapon-specific incompatibilities; aspect-specific hammer rows are conditional. No flat add policy is proven. | **proven dynamic weapon eligibility**. | No native SellTraits proof for Hammer: `WeaponUpgrade` is not a normal sellable GodLoot source. Generic removal is therefore not approved as product-safe. | `trait.Id` exists. | Distinct mechanism; candidate for **P21** if still required after P18–P20 |
| `StackUpgrade` / level-up | Stack/Pom loot | Native `StackOnly` choice over `GetAllUpgradeableGodTraits` | **level existing**, not “add a new buff” | `IncreaseTraitLevel` updates an existing eligible god trait. | Eligibility includes stackability and trait state. | Not a deletion mechanism. | Existing trait instance remains authoritative. | **P18 existing-owned behavior input** |
| Permanent/meta/equipment ownership | Weapon/aspect progression, keepsakes, Arcana/meta upgrades, familiar systems | Their owning screens/progression systems | **out of run-buff direct-add scope** unless a later task proves a dedicated operation. Representative inheritance markers in the 670-ID inventory include `GiftTrait` (25 unique IDs), `MetaUpgradeTrait` (25), `WeaponEnchantmentTrait` (24) and `FamiliarTrait` (5). | Owner-specific. | Owner-specific. | Owner-specific; do not route through generic boon deletion. | Trait IDs may exist at runtime but do not transfer ownership to the buff subsystem. | Explicitly excluded from P18/P19/P20/P22 generic paths |
| Internal / status / inheritance scaffolding | TraitData implementation state | Not an independent acquisition target | **unsupported as standalone target** unless separately curated | N/A | N/A | N/A | N/A | Excluded. Generated `debug_only` / `stub` state is not itself the reason; ownership is. |

## Special-NPC source coverage

The 83 special-NPC IDs are closed and non-overlapping:

| Source | Count | Direct exact apply | Dedicated/native-only |
| --- | ---: | ---: | --- |
| Artemis | 9 | 9 | 0 |
| Athena | 8 | 8 | 0 |
| Dionysus | 8 | 8 | 0 |
| Hades | 8 | 8 | 0 |
| Arachne | 8 | 0 | 8 |
| Narcissus | 9 | 9 | 0 |
| Echo | 8 | 7 | 1 (`EchoLastRunBoon`) |
| Medea | 8 | 8 | 0 |
| Circe | 9 | 9 | 0 |
| Icarus | 8 | 8 | 0 |
| **Total** | **83** | **74** | **9** |

Together with the 13 Well traits, this reproduces the closed 96-target trait catalog exactly: 74 direct + 22 special.

## Chaos operation input for P19

The native `TrialUpgrade` source owns two different sets.

Blessings (16):

`ChaosWeaponBlessing`, `ChaosSpecialBlessing`, `ChaosCastBlessing`, `ChaosHealthBlessing`, `ChaosRarityBlessing`, `ChaosMoneyBlessing`, `ChaosLastStandBlessing`, `ChaosManaBlessing`, `ChaosManaOverTimeBlessing`, `ChaosExSpeedBlessing`, `ChaosElementalBlessing`, `ChaosManaCostBlessing`, `ChaosSpeedBlessing`, `ChaosDoorHealBlessing`, `ChaosHarvestBlessing`, `ChaosOmegaDamageBlessing`.

Curses (17):

`ChaosNoMoneyCurse`, `ChaosHealthCurse`, `ChaosHiddenRoomRewardCurse`, `ChaosDamageCurse`, `ChaosPrimaryAttackCurse`, `ChaosSecondaryAttackCurse`, `ChaosDeathWeaponCurse`, `ChaosSpeedCurse`, `ChaosExAttackCurse`, `ChaosCommonCurse`, `ChaosCastCurse`, `ChaosDashCurse`, `ChaosManaFocusCurse`, `ChaosRestrictBoonCurse`, `ChaosStunCurse`, `ChaosTimeCurse`, `ChaosMetaUpgradeCurse`.

Static `trait_references.csv` reports 36 IDs referenced from `TrialUpgrade`, but three are unrelated references rather than pool members. The raw `PermanentTraits` / `TemporaryTraits` lists above are therefore the operation input; the static reference count must not be used as a 36-item Chaos choice pool.

## Selene operation input for P20

The main `SpellData` records are:

`Polymorph`, `Meteor`, `Transform`, `Leap`, `Laser`, `Summon`, `TimeSlow`, `Potion`, `MoonBeam`.

Each record owns a `TraitName` plus its own talent sets. `MoonBeam` is currently marked `Skip=true` in the supported build. `SpellData.lua` contains 94 named `*Talent` identifiers across the spell definitions, while `SpellLogic.CreateTalentTree` applies structure, depth, rarity, uniqueness, legendary/duo and GameState eligibility. P20 must therefore treat the talent tree as the authoritative operation model rather than expose a flat 94-item add list.

## Removal / current-instance handoff for P22

### What is proven

The game creates a runtime ID for a trait instance in `AddTraitData`:

- a new trait receives `newTrait.Id = newTrait.Id or GetTraitUniqueId()`;
- `AreTraitsIdentical` uses the ID for several lifecycle-sensitive shapes;
- Chaos expiry explicitly transfers the curse's `Id` to the resulting blessing.

This establishes a useful **current-run instance key**.

The native SellTraits path also establishes a safe **name-level** deletion subset:

1. `GenerateSellTraitValues` only offers a trait when `IsGodTrait(name, { ForShop=true })` and the runtime trait has rarity;
2. `HandleSellChoiceSelection` invokes `RemoveWeaponTrait(name)`;
3. `RemoveWeaponTrait` removes all runtime trait instances with that name through `RemoveTraitData`;
4. `RemoveTraitData` performs broad cleanup of property changes, UI state, modifiers, weapon overrides and `OnExpire` behavior.

### What is not yet proven

- Trainer status currently returns boon/reward **catalogs**, not `CurrentRun.Hero.Traits`; it does not expose `trait.Id`.
- The native sell path is name-level and removes every matching instance. It does not prove single-instance deletion semantics.
- `RemoveTraitData` being comprehensive does not mean every trait should be offered for deletion. Chaos, Selene, Hammer/aspect, Well-duration, costume and other owner-specific state can require dedicated lifecycle handling.
- No evidence in this task establishes an ID that is stable across a run reload/restart. Treat `trait.Id` as current-run identity only.

P22 can therefore start safely by exposing current-run trait instances with their runtime ID and by marking delete capability per category. The first proven delete mode is native sell semantics for currently sell-eligible GodTraits. All other categories should remain disabled with an explicit reason until their teardown path is separately proven.

## Downstream decisions

### P18 — ordinary / direct-add blessings

Ready inputs:

- the **74** already-approved direct special-NPC traits;
- ten ordinary Olympian/Hermes source IDs and their native source-owned selection rules;
- native already-owned handling: ordinary duplicate choices are filtered; `StackUpgrade` is the level path; replacement carries `TraitToReplace`;
- rarity must remain bounded by the processed trait/source rules rather than being treated as an arbitrary label.

P18 should not build its ordinary-boon list from `trait_references.csv`. It should derive source membership from the current game data and evaluate native eligibility at operation time. If it supports exact selection instead of opening a native choice, it must reproduce the relevant `IsTraitEligible` / `TraitRequirements` / slot-replacement behavior before calling the `FromLoot=true` apply seam.

### P19 — Chaos

Ready: the exact 16 blessing + 17 curse source pools and the proven curse `OnExpire.TraitData` → blessing lifecycle. A raw independent curse/blessing add is not approved.

### P20 — Hex

Ready: nine SpellData records, the current `MoonBeam Skip=true` fact, the native SpellDrop/OpenSpellScreen owner, and the source-defined talent-tree model. A flat trait add is not approved.

### P22 — current buffs and safe delete

Partially ready:

- current-run `trait.Id` is a viable identity to expose;
- native SellTraits gives a proven name-level deletion subset for sell-eligible GodTraits;
- generic current trait enumeration and Host projection do not exist yet;
- per-instance deletion and teardown for non-sell categories remain explicit blockers.

### P21 — remaining mechanisms

Hammer remains a distinct candidate after P18–P20 because its 92 source traits use weapon/aspect-specific eligibility. Other owner-specific rows should enter P21 only if a later requirement still needs them; this matrix does not manufacture a generic residual buff bucket.

## Evidence map

Curated repository evidence:

- `README.md` — closed trait boundary, exact special-trait application semantics, loot/native interaction census.
- `catalog_legality.csv` — canonical 96 independent trait targets and direct/special decisions.
- `well_shop.csv` — exact 13 Well traits within the 25 RoomShop entries.
- `native_interactions.csv` — native reward and special-choice owner ledger.
- `generated/traits.csv` — exhaustive TraitData inventory; existence/shape evidence only.
- `generated/trait_references.csv` — static reference evidence only; not an acquisition pool.

Target-build raw-source evidence bundle (not committed to this repository):

- `TraitLogic.lua` — `AddTraitToHero`, `AddTraitData`, `GetTraitUniqueId`, `SetTraitsOnLoot`, `IsGodTrait`, `RemoveWeaponTrait`, `RemoveTraitData`.
- `UpgradeChoiceLogic.lua` — `GetEligibleUpgrades`, `HandleUpgradeChoiceSelection`, TransformingTrait construction.
- `LootData_Zeus.lua` — representative GodLoot `PriorityUpgrades` / `WeaponUpgrades` / `Traits` structure.
- `LootData_Chaos.lua` — exact `PermanentTraits` and `TemporaryTraits` pools.
- `LootData_Selene.lua` — `SpellDrop.OnUsedFunctionName = OpenSpellScreen`.
- `SpellData.lua` / `SpellLogic.lua` — main spell records, talent sets and native talent-tree construction.
- `LootData.lua` — exact 92-entry `WeaponUpgrade.Traits` source list.
- `WeaponUpgradeLogic.lua` — weapon/aspect-specific equip/unequip path.
- `SellTraitLogic.lua` — native sell eligibility and `RemoveWeaponTrait` teardown.
