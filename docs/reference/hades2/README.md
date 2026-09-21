# Hades II reference data

This directory stores versioned research/reference snapshots extracted from an installed Hades II build. It is documentation data only: production code, packaging, tests, and runtime behavior must not depend on it.

Current snapshot:
- Hades II 1.139672
- Steam build 24556151
- Path: `1.139672-24556151/`

The snapshot records identifiers and relationships from the game's data tables rather than copying Lua source. It intentionally preserves normal entries, debug/internal entries, inheritance-only stubs, aliases, and names that may not be safe trainer targets.

Snapshot contents include:
- full inventories for consumables, loot, traits, resources, stores, rooms, encounters, units, weapons, projectiles, progression, requirements, and UI data;
- `trait_references.csv` and `static_room_links.csv` static-reference indexes;
- `aliases.csv` for reference-only selector/alias identifiers;
- curated `catalog_legality.csv`, `well_shop.csv`, `reroll_ledger.csv`, and `native_interactions.csv` research ledgers;
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
- `generated/static_room_links.csv` records statically visible Room → unit/encounter/reward references. Runtime-generated or indirect relationships may not appear.
- `generated/aliases.csv` contains reference-only selector/alias identifiers. The old `aliases_and_stubs.csv` name was misleading because the current file contains aliases, not definition stubs.
- `native_interactions.csv` records native handlers/flows and is independent from the `direct/special/exclude/alias` Trainer classification.

The `state` column in generated inventory tables is an **extractor state**, not a legality, runtime-validity, or gameplay-source classification. Do not use values such as `defined`, `debug_only`, or `stub` as a Trainer-facing decision.

In particular, the current extractor does not fully model function-valued `NamedRequirementsData` entries. Some valid requirements therefore appear as `state=stub` / `field_count=0` in `generated/requirements.csv`. Until that extractor is upgraded and the snapshot is regenerated, treat those fields only as parser output and inspect the source requirement before drawing semantic conclusions.


### Manual review of generated `state` values

A second-pass review against the installed Hades II 1.139672 scripts confirmed that `state=stub` mixes several structurally different cases. It must not be interpreted as "missing", "invalid", "unused", or "unsafe".

| Shape seen in generated data | Verified examples | Interpretation |
| --- | --- | --- |
| Pure inheritance definition | `BossEris02 -> BossEris01`, `BossHecate02 -> BossHecate01`, `WeaponSuitDash -> WeaponSuit`, `VanillaState -> BiomeState`, Anomaly `B_Combat*` rooms | Valid runtime definitions whose local body contains little beyond `InheritFrom`. |
| Deliberately minimal or empty definition | `WeaponStaffBall2` ("Only used for misnamed objective"), `ArtemisHuntersMark` | A real named table entry can intentionally carry no local fields. Source usage must decide its significance. |
| Container/list mistaken for an entity | `RewardStoreData.RunProgress`, `RewardStoreData.SubRoomRewards`, `RewardStoreData.Secrets`, `WeaponSets.HeroPrimaryWeapons` | These are lists/pools or lookup structures. Their keys are not standalone game objects. |
| Scalar/config field mistaken for an entity | `SurfaceShopData.DelayMin`, `SurfaceShopData.DelayMax`, `ScreenData.*.AllowAdvancedTooltip` | Configuration properties, not selectable entities. |
| Array-valued semantic data not expanded by the extractor | `NamedRequirementsData.BlindBoxLootRequirements` and many other named requirements | Often fully populated and gameplay-valid in Lua despite appearing as `field_count=0`. |
| Namespace helper data | `LootSetData.Apollo.Using`, `EncounterData_Nemesis.SetupEvents` | Presentation/event helper data that shares a parent table with actual entities but is not itself an entity of that type. |

Current snapshot counts illustrate why `stub` cannot be used as a legality signal: `requirements.csv` has 151 stub rows, `ui.csv` 480, `projectiles.csv` 290, `other_data.csv` 1079, and `progression.csv` 76. Manual sampling of each group found the structural patterns above rather than a corresponding population of invalid game objects.

For future census work:

1. use `catalog_legality.csv` for Trainer exposure decisions where it applies;
2. use the generated inventories only to establish that an identifier/table relationship exists;
3. inspect the owning Lua definition when a generated row is `stub`, especially for requirements, UI, stores, sets, and helper namespaces;
4. do not create an additional legality axis from extractor shape alone.

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

The generated trait inventory is intentionally much broader than the Trainer's trait-facing catalog. Hades II 1.139672 exposes 968 extracted `TraitData` rows, but most are owned by another native reward system rather than being independent Trainer targets.

The product-facing trait boundary for this build is:

- 83 concrete special-NPC traits from ten native sources: Artemis (9), Athena (8), Dionysus (8), Hades (8), Arachne (8), Narcissus (9), Echo (8), Medea (8), Circe (9), and Icarus (8);
- 13 Charon-Well traits already tracked as dedicated store traits;
- total independent trait targets recorded in `catalog_legality.csv`: **96**.

The 83 special-NPC IDs are all unique across those ten sources, all have official zh-CN display names, and none of those official Chinese names collide in the supported build. For Arachne, Narcissus, Echo, Medea, Circe, and Icarus, the `UnitSetData.*.Traits` set was also compared with the corresponding `PresetEventArgs.*Choices.UpgradeOptions` pool. Each source has exact set equality; some source arrays use different ordering, which is presentation data rather than an item-completeness difference.

Do not expand this 96-target ledger to all 968 TraitData rows. Ordinary Olympian/Hermes boons are owned by their LootData choice flow; Chaos, Selene, Hammer, and other contextual traits are likewise owned by their native loot/choice systems. Their presence in `generated/traits.csv` or `trait_references.csv` does not make them independent Trainer trait targets.

### Exact special-trait application semantics

A direct special-trait target must preserve Hades II's normal acquisition seam. Native `HandleUpgradeChoiceSelection` applies selected traits with `AddTraitToHero(..., FromLoot = true)`. The `FromLoot` flag is semantically required: `AddTraitToHero` only runs `HealOnAcquire` and `AcquireFunctionName` while that flag is set.

Manual inheritance-aware review found 28 of the 83 current special-NPC traits with effective acquire functions. Examples include Athena's last-stand effects, Dionysus max-health/bank effects, all nine Narcissus rewards through `NarcissusA`, six Echo rewards, five Circe rewards, and three Icarus rewards. An exact Trainer apply that omits `FromLoot` can therefore add the trait object while silently skipping the effect that acquiring that trait is supposed to cause.

After the resident fix, non-Well special-NPC traits use the native `FromLoot` acquisition semantics. The 75 targets for which that generic apply seam is sufficient are classified `direct`.

Arachne's eight costume traits additionally require `SetupCostume()` after acquisition to refresh the hero costume texture, matching the native `ArachneArmorApply` post-choice behavior. They are therefore classified `special`.

The six fixed-choice sources remain available through the native three-choice interaction as well. Explicit exact-trait application intentionally bypasses source eligibility requirements, but it must not omit the selected trait's acquisition mechanics.

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
