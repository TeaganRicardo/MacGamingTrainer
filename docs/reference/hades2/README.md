# Hades II reference data

This directory stores versioned research/reference snapshots extracted from an installed Hades II build. It is documentation data only: production code, packaging, tests, and runtime behavior must not depend on it.

Current snapshot:
- Hades II 1.139672
- Steam build 24556151
- Path: `1.139672-24556151/`

The snapshot records identifiers and relationships from the game's data tables rather than copying Lua source. It intentionally preserves normal entries, debug/internal entries, inheritance-only stubs, aliases, and names that may not be safe trainer targets.

Snapshot contents include:
- full inventories for consumables, loot, traits, resources, stores, rooms, encounters, units, weapons, projectiles, progression, requirements, and UI data;
- `trait_sources.csv` and `room_links.csv` relationship indexes;
- curated `catalog_legality.csv`, `well_shop.csv`, `reroll_ledger.csv`, and `special_interactions.csv` research ledgers;
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

`special_interactions.csv` records native handlers and interaction relationships. Presence in that file does not by itself mean `classification=special`. For example, `ChaosWeaponUpgrade`, `BlindBoxLoot`, and `RandomStoreItem` are concrete consumables whose own use logic preserves their native behavior, so they remain `direct`; `RandomLoot`, `BoostedRandomLoot`, `WeaponUpgradeDrop`, `ShopHermesUpgrade`, and `SpellDrop` require dedicated spawning/choice semantics and are `special`.

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
