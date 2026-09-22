# Hades II reference data

This directory stores versioned research/reference snapshots extracted from an installed Hades II build. It is documentation data only: production code, packaging, tests, and runtime behavior must not depend on it.

Current snapshot:
- Hades II 1.139672
- Steam build 24556151
- Path: `1.139672-24556151/`

The snapshot records identifiers and relationships from the game's data tables rather than copying Lua source. It intentionally preserves normal entries, debug/internal entries, inheritance-only stubs, aliases, and names that may not be safe trainer targets.

## Private raw-source evidence bundle

The project owner also keeps a private, version-frozen raw-source evidence bundle for this supported build in Google Drive:

- folder: `MacGamingTrainer/ReferenceEvidence/Hades2/1.139672-24556151/`;
- Drive folder: https://drive.google.com/drive/folders/1lughi1ucofi9EwqqJmD0GUPuCA0lu3Ld
- captured against repository baseline: `c19cc6678fe1946e3853ebdf342ec29d30329c43`;
- archive SHA-256: `9149fc79e5898964ac429ae5c1380e27e54fef52c58119fa108e5283ea7874c6`.

It contains the full installed `Content/Scripts` tree, non-localization Game SJSON sources, English and Simplified Chinese text trees, Steam/app version metadata, per-file SHA-256 hashes, and a compressed bundle. It is private evidence, not a production dependency or replacement for the curated files in this directory.

For later catalog/census work on build 1.139672 / 24556151, use this GitHub snapshot first and fetch the specific raw source from the private Drive bundle when source-level confirmation is needed. Use the target Mac again only when the evidence bundle lacks the required material or when the supported game build changes.

Snapshot contents include:
- full inventories for consumables, loot, traits, resources, stores, rooms, encounters, units, weapons, projectiles, progression, requirements, and UI data;
- `trait_references.csv`, `store_references.csv`, and `static_room_links.csv` static-reference indexes;
- `aliases.csv` for reference-only selector/alias identifiers;
- curated `catalog_legality.csv`, `well_shop.csv`, `reroll_ledger.csv`, and `native_interactions.csv` research ledgers;
- `provisional_catalog_names.md` with the supported-build rationale for Trainer-authored/composed catalog labels;
- `manifest.json` with source build and row counts.

## Usage

Use these files as the first lookup point when investigating whether an Hades II identifier exists, what table owns it, where it is referenced, or whether previous research classified it as direct, special, alias, internal, or excluded.

Do not infer runtime safety from existence in a generated table. The generated tables are intentionally exhaustive and include stubs/debug/internal data. Prefer the curated ledgers when a trainer-facing classification has already been recorded.

The historical filename `catalog_legality.csv` is retained for continuity, but its current `classification` column is the single trainer-facing decision field:

- `direct`: the target is concrete and the normal generic trainer spawn/apply seam is sufficient to preserve its game semantics;
- `special`: the target is valid game content, but Trainer use must preserve a native dedicated handler or interaction flow;
- `exclude`: the object exists, but should not be exposed as an independent Trainer target; the reason is recorded;
- `alias`: the identifier is an abstract selector, pool, or event alias rather than a concrete standalone target.

Whether the current build normally instantiates a particular pickup is evidence only. It does not create another classification axis.


### Direct spawn semantics

The Trainer's generic `spawn_reward` seam means "create this concrete pickup/loot object now", not "replay every contextual transformation that one possible natural source would have applied".

This distinction matters for consumables. Hades II calls `ApplyConsumableItemResourceMultiplier` in several room-reward, Echo, trade, store, combat-drop, and random-consumable paths, but the result depends on source context. NPC reward paths mark the item `NPCDrop=true`, which deliberately suppresses the room-style money/health/resource bonus handling, while room-reward paths can apply current reward bonuses. The same concrete consumable can therefore legitimately reach the player with different contextual processing.

Because the catalog combines objects from multiple acquisition paths, there is no single natural multiplier context for a generic Trainer spawn. The direct seam therefore keeps the item's base/ramped definition and preserves the item's own `UseFunctionName`, `UseFunctionNames`, `ReplaceWithRandomLoot`, `SetupEvents`, and pickup behavior, but does not invent a room/NPC/store reward context. A future feature that explicitly simulates a room reward should use a separate native room-reward path rather than changing this generic contract.

`SpellDrop` is intentionally different: its useful gameplay semantics are the native Selene choice flow itself, so it remains `special` and is spawned through `SpawnRoomReward`.

`native_interactions.csv` records native handlers and interaction relationships. Presence in that file does not by itself mean `classification=special`. For example, `ChaosWeaponUpgrade`, `BlindBoxLoot`, and `RandomStoreItem` are concrete consumables whose own use logic preserves their native behavior, so they remain `direct`; `RandomLoot`, `BoostedRandomLoot`, `WeaponUpgradeDrop`, `ShopHermesUpgrade`, and `SpellDrop` require dedicated spawning/choice semantics and are `special`.


## Reference-label semantics

Several snapshot files are static extraction indexes, not claims about complete runtime ownership or acquisition semantics:

- `generated/trait_references.csv` records static references from the tables scanned by the snapshot extractor. It must not be read as a complete list of all ways a Trait can be acquired.
- `generated/store_references.csv` expands the active nested item memberships of `RewardStoreData` and `StoreData`. It is a static membership index, not a legality decision or a claim that every listed item is currently eligible to appear.
- `generated/static_room_links.csv` records statically visible Room → unit/encounter/reward references. Runtime-generated or indirect relationships may not appear.
- `generated/aliases.csv` contains reference-only selector and compatibility-alias identifiers. When the game provides an explicit compatibility remap, `target_id` records the current identifier. The old `aliases_and_stubs.csv` name was misleading because the current file contains aliases, not definition stubs.
- `native_interactions.csv` records native handlers/flows and is independent from the `direct/special/exclude/alias` Trainer classification. It contains both concrete reward/wrapper rows and source-level special-choice rows; source IDs such as `Artemis` or `Arachne` are interaction sources, not additional catalog-legality targets.

`BountyData.ShrineBountyNameSwapMap` contributes 42 legacy Shrine/Testament bounty IDs to `generated/aliases.csv`, each mapped through `target_id` to its current `BountyShrine*` identifier. These compatibility IDs are reference aliases and must not be counted as additional bounties.

The `state` column in generated inventory tables is an **extractor state**, not a legality, runtime-validity, or gameplay-source classification. Do not use values such as `defined`, `debug_only`, or `stub` as a Trainer-facing decision.

The historical snapshot extractor also under-counted anonymous array members inside `NamedRequirementsData`. That specific defect has now been corrected in `generated/requirements.csv`; all installed named requirements are represented as defined tables with source-derived top-level member counts.


### Manual review of generated `state` values

A second-pass review against the installed Hades II 1.139672 scripts confirmed that `state=stub` mixes several structurally different cases. It must not be interpreted as "missing", "invalid", "unused", or "unsafe".

| Shape seen in generated data | Verified examples | Interpretation |
| --- | --- | --- |
| Pure inheritance definition | `BossEris02 -> BossEris01`, `BossHecate02 -> BossHecate01`, `WeaponSuitDash -> WeaponSuit`, `VanillaState -> BiomeState`, Anomaly `B_Combat*` rooms | Valid runtime definitions whose local body contains little beyond `InheritFrom`. |
| Deliberately minimal or empty definition | `WeaponStaffBall2` ("Only used for misnamed objective"), `ArtemisHuntersMark` | A real named table entry can intentionally carry no local fields. Source usage must decide its significance. |
| Container/list mistaken for an entity | `RewardStoreData.RunProgress`, `RewardStoreData.SubRoomRewards`, `RewardStoreData.Secrets`, `WeaponSets.HeroPrimaryWeapons` | These are lists/pools or lookup structures. Their keys are not standalone game objects. |
| Scalar/config field mistaken for an entity | `SurfaceShopData.DelayMin`, `SurfaceShopData.DelayMax`, `ScreenData.*.AllowAdvancedTooltip` | Configuration properties, not selectable entities. |
| Anonymous-array semantic tables under-counted by the legacy extractor | `NamedRequirementsData.BlindBoxLootRequirements` and other list-only named requirements | Historical snapshot defect now corrected in `generated/requirements.csv`; anonymous condition entries count as real top-level members. |
| Namespace helper data | `LootSetData.Apollo.Using`, `EncounterData_Nemesis.SetupEvents` | Presentation/event helper data that shares a parent table with actual entities but is not itself an entity of that type. |

Current snapshot counts still illustrate why `stub` cannot be used as a legality signal: `ui.csv` has 480 stub rows, `projectiles.csv` 290, `other_data.csv` 1079, `stores.csv` 17, and the corrected `progression.csv` 12. `requirements.csv` now has zero stub rows after the NamedRequirementsData extraction correction. Manual review of each group found structural/parser shapes rather than a corresponding population of invalid game objects.

For future census work:

1. use `catalog_legality.csv` for Trainer exposure decisions where it applies;
2. use the generated inventories only to establish that an identifier/table relationship exists;
3. inspect the owning Lua definition when a generated row is `stub`, especially for UI, stores, sets, and helper namespaces;
4. do not create an additional legality axis from extractor shape alone.

## Requirement census completeness check

Manual review against the installed Hades II 1.139672 `RequirementsData.lua` corrects the previous interpretation of `NamedRequirementsData`.

- `generated/requirements.csv` contains 179 rows / 179 unique IDs, all from `NamedRequirementsData`.
- All 179 installed values are real Lua requirement tables. None is an empty table and none is a function-valued top-level requirement.
- 151 requirements are **list-only** tables: their top-level content consists entirely of anonymous condition entries such as `{ Path = ..., Comparison = ... }`.
- 28 requirements are **mixed** tables: they contain anonymous condition entries plus named top-level combinators such as `NamedRequirements`, `NamedRequirementsFalse`, or `OrRequirements`.
- The historical extractor counted only named top-level fields. That made all 151 list-only requirements appear as `state=stub, field_count=0`, even though they were populated and gameplay-valid.
- The corrected snapshot marks all 179 requirements `defined` and records `field_count` as the true number of top-level table members, counting both anonymous conditions and named combinators. Counts range from 1 to 25.

This is reference-shape information only. Requirement contents encode eligibility and sequencing rules for many separate systems; they do not form an additional Trainer legality axis and should not be rewritten into direct/special/exclude classifications.

## Progression census completeness check

`generated/progression.csv` is a cross-namespace inventory, not a single progression-object type. The current snapshot contains 867 rows / 832 unique IDs across World upgrades, bounties, quests, objectives, objective sets, achievements, badges, Arcana/meta upgrades, fishing/harvest/garden configuration, spells, and costume data.

A manual source audit found and corrected a legacy snapshot-extraction defect in `ObjectiveData`. Most objective definitions in `ObjectiveData.lua` are compact single-line Lua tables such as `GiftPrompt = { Description = ... }`; the original snapshot had reduced 64 of the 65 objective rows to `state=stub, field_count=0`. All 65 installed objective IDs are real table definitions. Their `state` is now `defined`, and `field_count` has been recomputed from the actual top-level fields; this also corrects `NemesisKills` from three to four fields.

After that correction the progression inventory is:

- 818 `defined`;
- 37 `debug_only`;
- 12 `stub`.

The remaining 12 `stub` rows are structural configuration keys rather than omitted progression entities:

- `FishingData`: `SpawnChance`, `SpawnLimitPerBiome`, `ToolName`, `RoomChanceName`, `HarvestPointName`, `DefaultGameStateRequirements`, and `FidgetInterval`;
- `GardenData`: `JustPlantedAnimation` and `PlotOrder`;
- `HarvestData`: `DefaultSpawnChances`, `DefaultGameStateRequirements`, and `WeightedOptions`.

The 35 repeated IDs are also intentional cross-namespace reuse rather than duplicate entities. Thirty-three names occur once as an `ObjectiveData` objective descriptor and once as an `ObjectiveSetData` objective-set definition; `BaseMetaUpgrade` is separately defined in `MetaUpgradeCardData` and `MetaUpgradeData`; and `DefaultGameStateRequirements` is a configuration key in both the fishing and harvesting views. Consumers must therefore identify progression rows by at least `(table, id)`, not by `id` alone.

The historical extractor that produced this static snapshot is not part of the repository, and production code/tests intentionally do not depend on `docs/reference/**`. This correction is therefore recorded in the versioned snapshot and audit notes rather than introducing a new runtime/test dependency solely to regenerate documentation data.

## Native interaction census completeness check

The native-interaction ledger has been manually checked against the installed 1.139672 scripts and now records two distinct but related sets:

- ten concrete reward/wrapper/event interactions already used by the reward catalog: `ChaosWeaponUpgrade`, `BlindBoxLoot`, `WeaponUpgradeDrop`, `ShopHermesUpgrade`, `RandomLoot`, `BoostedRandomLoot`, `RandomStoreItem`, `Devotion`, `TrialUpgrade`, and `SpellDrop`;
- ten special-NPC choice sources used by the Trainer's native special-choice entry: Artemis, Athena, Dionysus, Hades, Arachne, Narcissus, Echo, Medea, Circe, and Icarus.

The first set preserves the distinction between concrete self-contained consumables and wrappers that require native shop/loot resolution. The second set records source-level ownership rather than adding another Trainer legality classification.

The source review also confirmed that Athena's distinct `AthenaUse` entry is a thin wrapper around `UseLoot` followed by the physical NPC exit presentation; it does not introduce a separate boon-selection state contract. The fixed-choice NPC handlers remain the source of their eligibility/priority behavior, including Arachne's costume refresh, Echo's menu-dependent previous-run boon, and Circe's familiar preprocessing.

## Store and reward-pool census completeness check

Manual review against the installed Hades II 1.139672 store/reward sources shows that `generated/stores.csv` is a **top-level store-related table inventory**, not a list of 153 purchasable items.

- 129 rows come from `WeaponShopItemData`. These are permanent weapon/aspect/tool progression definitions: 24 weapon/aspect roots, 96 rank-up rows for those 24 tracks, eight tool/tool-upgrade rows, and the `BaseWeaponUpgrade` template. They are not run-shop reward entries.
- 13 rows come from `RewardStoreData`. They are reward-pool/container keys such as `RunProgress`, `SubRoomRewards`, and `Secrets`; their generated `state=stub` shape reflects list/container extraction rather than invalid content.
- seven rows are `StoreData` shop/configuration objects (`RoomShop`, `SurfaceShop`, `WorldShop`, `I_WorldShop`, `Q_WorldShop`, `ZagPedestalOptions`, and `ZagreusContractRequirement`);
- four `SurfaceShopData` rows are scalar timing/price configuration fields. Together with the 13 RewardStore containers, these account for all 17 `state=stub` rows in `generated/stores.csv`.

Because top-level extraction hides the useful nested membership, `generated/store_references.csv` records the active source-to-item relationships after excluding Lua comments. It contains 175 source/item rows: 68 RewardStoreData pool memberships and 107 StoreData shop memberships.

The reviewed build resolves those memberships to:

- 34 unique active reward IDs across `RewardStoreData`;
- 57 unique active shop item IDs across `StoreData`;
- exactly 25 unique `RoomShop` entries, with set equality to `well_shop.csv`.

All 34 RewardStore IDs and all 57 StoreData item IDs already exist in `catalog_legality.csv`. The 57 shop items resolve to 39 `direct` and 18 `special` Trainer targets; no new catalog omission was found in this store pass.

A source-wide search found no other script appending to or overwriting `RewardStoreData` or `StoreData`; other references read these tables through reward/store selection logic. Therefore the static memberships above close the store/reward-pool census for the supported build.

## Loot census completeness check

Manual review against the installed Hades II 1.139672 LootData sources closes the semantic loot census at 16 concrete targets.

- `generated/loot.csv` has 38 rows but only 19 unique IDs. Each source entry is represented once through its `LootSetData.*` definition and once through the runtime `LootData` view populated by `OverwriteTableKeys(LootData, LootSetData.*)`. Treat those pairs as one runtime loot object, not two rewards.
- Three unique IDs are not standalone Trainer targets: `BaseLoot` and `BaseSoundPackage` are inheritance templates, while `LootSetData.Apollo.Using` is a namespace helper (`Animation = "ApolloAoEStrikeRapid"`) that the generic extractor mistakes for a loot entry.
- The remaining 16 IDs are concrete loot targets and now have 16/16 rows in `catalog_legality.csv`.
- Ten are regular Olympian `GodLoot` objects: Zeus, Hera, Poseidon, Demeter, Apollo, Aphrodite, Hephaestus, Hestia, Ares, and Hermes. The native room-reward path starts from the abstract `Boon` selector, then `SetupRoomReward` / `ChooseLoot` resolves it to one of these concrete `LootData` objects. `Boon` therefore remains an alias, while the ten concrete god loot IDs are `direct`.
- The other six concrete loot targets are `SpellDrop`, `StackUpgrade`, `StackUpgradeBig`, `StackUpgradeTriple`, `TrialUpgrade`, and `WeaponUpgrade`.
- `StackUpgrade` and `WeaponUpgrade` retain `DebugOnly = true` in their definitions even though `RewardStoreData` / `StoreData` use them in normal gameplay. This is another case where generated `state=debug_only` is source shape, not Trainer legality.
- Names such as `ArtemisUpgrade`, `AthenaUpgrade`, `DionysusUpgrade`, and `HadesUpgrade` occur in NPC flavor/codex data but are not `LootData` entities in this build; their native encounters are owned by the separate special-choice/trait paths and are not missing loot rows.

## Trait catalog boundary and completeness check

The generated trait inventory is intentionally much broader than the Trainer's trait-facing catalog. Hades II 1.139672 produces 968 extracted trait rows but only **670 unique IDs**. 298 IDs are represented twice through the source `TraitSetData` view and the merged runtime `TraitData` view, so those pairs are not duplicate game traits.

At the unique-ID level the extractor reports 626 `defined`, 43 `debug_only`, and one `stub`. The sole stub ID is `VanillaState`, an inheritance-only biome-state entry (`VanillaState -> BiomeState`) represented through both table views; it is not a blessing or an independent Trainer target. The `debug_only` set is likewise dominated by base/type markers such as `BaseTrait`, elemental markers, `CostumeTrait`, `ShopTrait`, weapon-hammer base traits, Chaos base traits, and other ownership scaffolding. These extractor states do not define the product catalog.

The product-facing trait boundary for this build is:

- 83 concrete special-NPC traits from ten native sources: Artemis (9), Athena (8), Dionysus (8), Hades (8), Arachne (8), Narcissus (9), Echo (8), Medea (8), Circe (9), and Icarus (8);
- 13 Charon-Well traits already tracked as dedicated store traits;
- total independent trait targets recorded in `catalog_legality.csv`: **96**.

The 83 special-NPC IDs are all unique across those ten sources, all have official zh-CN display names, and none of those official Chinese names collide in the supported build. For Arachne, Narcissus, Echo, Medea, Circe, and Icarus, the `UnitSetData.*.Traits` set was also compared with the corresponding `PresetEventArgs.*Choices.UpgradeOptions` pool. Each source has exact set equality; some source arrays use different ordering, which is presentation data rather than an item-completeness difference.

Do not expand this 96-target ledger to all 968 TraitData rows. Ordinary Olympian/Hermes boons are owned by their LootData choice flow; Chaos, Selene, Hammer, and other contextual traits are likewise owned by their native loot/choice systems. Their presence in `generated/traits.csv` or `trait_references.csv` does not make them independent Trainer trait targets.

### Exact special-trait application semantics

A direct special-trait target must preserve Hades II's normal acquisition seam. Native `HandleUpgradeChoiceSelection` applies selected traits with `AddTraitToHero(..., FromLoot = true)`. The `FromLoot` flag is semantically required: `AddTraitToHero` only runs `HealOnAcquire` and `AcquireFunctionName` while that flag is set.

Manual inheritance-aware review found 28 of the 83 current special-NPC traits with effective acquire functions. Examples include Athena's last-stand effects, Dionysus max-health/bank effects, all nine Narcissus rewards through `NarcissusA`, six Echo rewards, five Circe rewards, and three Icarus rewards. An exact Trainer apply that omits `FromLoot` can therefore add the trait object while silently skipping the effect that acquiring that trait is supposed to cause.

After the resident fix, non-Well special-NPC traits use the native `FromLoot` acquisition semantics. The 74 targets for which that generic apply seam is sufficient are classified `direct`.

Arachne's eight costume traits additionally require `SetupCostume()` after acquisition to refresh the hero costume texture, matching the native `ArachneArmorApply` post-choice behavior. They are therefore classified `special`.

`EchoLastRunBoon` is also `special`, but for a different reason. Its acquire function first waits on the active boon-menu signal and then opens Echo's previous-run boon selection. A raw exact-trait injection has no such outer boon-menu context and can leave that acquire thread waiting indefinitely. The exact trait is therefore not advertised as a direct catalog item; it remains reachable through Echo's audited native three-choice flow.

The six fixed-choice sources remain available through the native three-choice interaction as well. Explicit exact-trait application intentionally bypasses source eligibility requirements for direct targets, but it must not omit the selected trait's acquisition mechanics.

## Consumable census completeness check

Manual review against the installed Hades II 1.139672 `ConsumableData.lua` closed the remaining consumable-census gap:

- `generated/consumables.csv` contains 97 rows.
- Six rows are structural/template definitions rather than standalone Trainer targets: `BaseConsumable`, `BaseMetaRoomReward`, `BaseResource`, `BaseSuperResource`, `BaseWellShopConsumable`, and `Tier1Consumable`.
- The remaining 91 concrete consumables now have 91/91 entries in `catalog_legality.csv`.
- `SeedMysteryDrop` is a valid direct pickup. Narcissus reward data emits it as a concrete one-seed `SeedMystery` reward.
- `MixerMythicDrop` is a valid direct pickup. `RoomDataQ` emits it from `CheckTyphonReward` as the concrete `MixerMythic` / Entropy reward.
- `LobAmmoPack` is a valid gameplay object but remains `exclude`: `WeaponLogic.WeaponLobAmmoDrop` owns its projectile-volley, magnetism, cooldown, and session-state lifecycle, so exposing it as an independent generic reward would detach it from the owning weapon mechanic.

The two recovered direct pickups use the same generic consumable seam as other resource drops. Their player-facing names are linked to the corresponding official resources: `SeedMysteryDrop -> SeedMystery` (神秘种子) and `MixerMythicDrop -> MixerMythic` (熵).

## Resource census versus pickup wrappers

`ResourceData` is the authoritative census for game resources. A `*Drop` entry is only a concrete world-pickup wrapper for a resource and is not required for the resource itself to exist.

The current build has dedicated pickup wrappers for these otherwise harvest/garden-style resources because they are also emitted through NPC reward logic:

- `OreFSilverDrop` → `OreFSilver` (silver), used by Narcissus;
- `PlantFMolyDrop` → `PlantFMoly`, used by Narcissus;
- `PlantFNightshadeDrop` → `PlantFNightshade`, used by Narcissus;
- `PlantGLotusDrop` → `PlantGLotus`, used by Narcissus.

Other valid resources commonly use Harvest/Garden `AddResources` or `ResourceName` directly and therefore have no equivalent pickup wrapper. For example, the current build contains `OreGLime` and `PlantHMyrtle` in `ResourceData`, but no `OreGLimeDrop` or `PlantHMyrtleDrop` definition.

Do not interpret the absence of a `*Drop` wrapper as a missing resource.


### Resource census completeness check

Manual review against the installed 1.139672 `ResourceData.lua` closed the remaining resource-census ambiguity:

- `ResourceData` contains 103 extracted rows: five `Base*` templates plus 98 concrete resources.
- `ScreenData.InventoryScreen.ItemCategories` contains 97 of those 98 concrete resource IDs.
- `ResourceDisplayOrderData` contains the same 97 IDs.
- the only concrete `ResourceData` entry intentionally absent from both lists is `Money`, which the game and Trainer handle separately as the run currency;
- there are no additional concrete `ResourceData` IDs hidden outside both the inventory categories and the display-order list;
- the 98 concrete resources have unique official zh-CN display names in this build.

This means the resource census itself is complete for the supported build. Apparent omissions found by searching only `*Drop` definitions are pickup-wrapper differences, not missing `ResourceData` entries. Special resources such as `DreamPoints`, `FamiliarPoints`, `HadesSpearPoints`, `DeathAreaPoints`, `MixerMythic`, and `MysteryResource` are explicitly present in the game's own inventory/display data rather than being accidental internal-only rows.

## Source evidence rules

`RoomDataTest.lua`, `DebugSpawnConsumables`, and TestAllThings are useful existence/debug evidence, but they are not authoritative evidence that normal gameplay does or does not instantiate an object.

In particular, the `-- Healing, no interact` grouping in `RoomDataTest.lua` describes the test-room presentation path. It does not make `HealDrop` or `HealDropMinor` invalid game objects. Both have normal production callers.

Likewise, the commented `-- From Traits` block identifies objects owned by trait/gameplay mechanics. It does not imply those objects are invalid. Such objects are generally `exclude` only because they are context-owned transient pickups rather than useful standalone Trainer targets.

When available, prefer concrete production references from NPC reward data, Trait acquire functions, Harvest/Garden logic, Dream Run logic, Shrine logic, Room logic, Familiar logic, Event logic, or native store logic.

## Second-pass manual source audit

The following objects were verified to have normal production paths in Hades II 1.139672 / Steam build 24556151:

| Identifier | Verified normal source |
| --- | --- |
| `DreamPointsDrop` | `RewardLogic.ChooseRoomReward` returns it during Dream Runs; `DreamRunLogic` uses its pickup record to advance the run. Official zh-CN calls the mode “梦境深潜”. |
| `EmptyMaxHealthDrop` | Nemesis free-item rewards in `NPCData.lua`. |
| `EmptyMaxHealthSmallDrop` | `LootData.SubRoomRewards`, consumed by Ephyra subrooms in `RoomDataN.lua`. |
| `GemPointsDrop` | `RoomLogic.UnusedWeaponBonusDropGems()` calls `GiveRandomConsumables` after eligible boss encounters. |
| `HealDrop` | Nemesis free-item rewards. |
| `HealDropMinor` | Artemis explicitly uses `SpawnObstacle` + `CreateConsumableItem`; also referenced by Familiar, Harvest, Icarus, Medea, and Poseidon mechanics. |
| `HealDropMajor` | Narcissus reward data. |
| `MetaFabricDrop` | Narcissus and Arachne reward data. |
| `Mixer5CommonDrop` | Narcissus reward data and bounty reward data. |
| `Mixer6CommonDrop` | Harvest data uses it as a concrete `ConsumableName`. |
| `OreFSilverDrop` | Narcissus reward data. |
| `PlantFMolyDrop` | Narcissus reward data. |
| `PlantFNightshadeDrop` | Narcissus reward data. |
| `PlantGLotusDrop` | Narcissus reward data. |
| `RerollDrop` | Narcissus reward data; its Narcissus override can grant +2. The official zh-CN term associated with `ReRollAlt` is “重塑命运”. |
| `RoomMoneySmallDrop` | Poseidon `GiveRandomConsumables` reward logic. |
| `RoomRewardConsolationPrize` | Event/reward fallback logic and Shrine logic directly instantiate the red onion reward. |
| `TrashPointsDrop` | Eris uses `NPCRewardDrop` to throw it in the Crossroads. |
| `BloodDrop` | Ares mechanics create and track the transient pickup through `CreateBloodDrop`. |
| `ManaDropMinorHound` | Hecuba Familiar mana-dig reward. |
| `ManaDropZeus` | Zeus mana mechanics create the pickup during combat. |
| `MedeaMoneyTinyDrop` | Medea trait `DropOnKill` mechanic. |
| `PowerDrinkDrop` | Dionysus trait setup spawns this mechanic-owned pickup. |

These context-owned mechanic pickups remain `exclude` where exposing them independently would bypass or detach them from the owning mechanic.

### Defined targets with no normal pickup instantiation found

The following definitions remain valid `direct` Trainer targets where their standalone behavior is coherent, but the current build search did not find a normal world-pickup instantiation path:

- `MemPointsCommonBigDrop`: functional +20 Psyche pickup definition. Tablet/exorcism gameplay grants `MemPointsCommon` directly through Harvest `AddResources` values such as 30/35/40/50 rather than this pickup.
- `RoomMoneyBigDrop`: functional money pickup definition; current references are definition/test/package-oriented rather than normal gameplay spawn.
- `FamiliarPointsDrop`: functional pickup definition. `MetaRewardStandData` grants the `FamiliarPoints` resource directly and only reuses `FamiliarPointsDrop` as the animation.

The following are excluded because the current build has no normal instantiation path and there is no reason to expose them as standalone Trainer targets:

- `HealDropSuperMinor`: functional 1-HP healing variant, currently referenced only by its definition and test/debug content;
- `ManaDropMinor`: defined base mana consumable with no normal instantiation found;
- `ManaDropMinorPoseidon`: defined Poseidon variant with no normal instantiation found.

## Refresh policy

When the supported Hades II build changes, create a new sibling version directory from the installed target build rather than overwriting this snapshot. Review the diff and carry forward curated classifications only after checking changed game semantics.

The extraction procedure is research tooling, not part of MacGamingTrainer production code. Keep one-off/local extraction scripts outside the repository unless a future task establishes a real product or CI requirement for them.
