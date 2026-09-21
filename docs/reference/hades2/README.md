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

## Resource census versus pickup wrappers

`ResourceData` is the authoritative census for game resources. A `*Drop` entry is only a concrete world-pickup wrapper for a resource and is not required for the resource itself to exist.

The current build has dedicated pickup wrappers for these otherwise harvest/garden-style resources because they are also emitted through NPC reward logic:

- `OreFSilverDrop` → `OreFSilver` (silver), used by Narcissus;
- `PlantFMolyDrop` → `PlantFMoly`, used by Narcissus;
- `PlantFNightshadeDrop` → `PlantFNightshade`, used by Narcissus;
- `PlantGLotusDrop` → `PlantGLotus`, used by Narcissus.

Other valid resources commonly use Harvest/Garden `AddResources` or `ResourceName` directly and therefore have no equivalent pickup wrapper. For example, the current build contains `OreGLime` and `PlantHMyrtle` in `ResourceData`, but no `OreGLimeDrop` or `PlantHMyrtleDrop` definition.

Do not interpret the absence of a `*Drop` wrapper as a missing resource.

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
