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

`native_interactions.csv` records native handlers and interaction relationships. Presence in that file does not by itself mean `classification=special`. For example, `ChaosWeaponUpgrade`, `BlindBoxLoot`, and `RandomStoreItem` are concrete consumables whose own use logic preserves their native behavior, so they remain `direct`; `RandomLoot`, `BoostedRandomLoot`, `WeaponUpgradeDrop`, `ShopHermesUpgrade`, and `SpellDrop` require dedicated spawning/choice semantics and are `special`.


## Reference-label semantics

Several snapshot files are static extraction indexes, not claims about complete runtime ownership or acquisition semantics:

- `generated/trait_references.csv` records static references from the tables scanned by the snapshot extractor. It must not be read as a complete list of all ways a Trait can be acquired.
- `generated/static_room_links.csv` records statically visible Room → unit/encounter/reward references. Runtime-generated or indirect relationships may not appear.
- `generated/aliases.csv` contains reference-only selector/alias identifiers. The old `aliases_and_stubs.csv` name was misleading because the current file contains aliases, not definition stubs.
- `native_interactions.csv` records native handlers/flows and is independent from the `direct/special/exclude/alias` Trainer classification.

The `state` column in generated inventory tables is an **extractor state**, not a legality, runtime-validity, or gameplay-source classification. Do not use values such as `defined`, `debug_only`, or `stub` as a Trainer-facing decision.

In particular, the current extractor does not fully model positional-array and inline-table Lua records. This is especially visible in `NamedRequirementsData`: complete requirement arrays such as `AllWeaponsUnlocked`, `AlchemyUnlocked`, and `QuestLogUnlocked` appear as `state=stub` / `field_count=0`, while records with top-level named keys such as `DreamRunsUnlocked.OrRequirements` appear as `defined`. The target `RequirementsData.lua` contains no function-valued requirement definitions. Treat `state` and `field_count` in `generated/requirements.csv` only as parser-shape output, not as evidence that a requirement is missing or incomplete. The same caveat applies to one-line `ObjectiveData` records and scalar/config entries surfaced from Fishing/Garden/Harvest tables in `generated/progression.csv`.


## Trait census semantics

`generated/traits.csv` is a table inventory, not a unique-ID count. Runtime identifiers can legitimately appear under both `TraitData` and `TraitSetData` after the game's tables are merged. Classify traits by identifier and owning gameplay system rather than by raw CSV row count.

The game's own `ValidateTraitData()` provides useful ownership evidence: non-debug traits are checked against boon-info data, weapon base/aspect mappings, `MetaUpgradeCardData`, `GiftData`, and `FamiliarData`, plus an explicit allowlist for dynamic/system-owned traits. This is broader than `generated/trait_references.csv`, whose static unit/loot/store references are not a complete acquisition graph.

Manual verification against the installed 1.139672 scripts established these boundaries:

- ordinary Olympian traits resolve through their corresponding loot pools, and all 37 Duo traits have normal loot references; `DummyBloodDisplayBoon` is an Ares HUD/BloodDrop counter, not a boon choice;
- Artemis, Athena, Dionysus, Hades, Arachne, Narcissus, Echo, Medea, Circe, and Icarus expose 87 actual special-NPC choice traits in total; their base/helper traits are not choices;
- Chaos `TrialUpgrade` owns 16 permanent blessings and 17 temporary curses with `TransformingTraits = true`; the native choice pairs a temporary curse with its future blessing, so the 33 component traits are valid definitions but not independent ordinary-boon entry points;
- Selene owns 9 Hex traits and 93 defined Path-of-Stars talents; `SpellDrop` is the native Hex-choice entry point, and `OlympianSpellCountTalent` is a special generated Path-of-Stars talent;
- 25 Arcana cards map one-to-one to 25 defined Arcana effect traits;
- `KeepsakeData.ItemOrder` contains 33 equipable keepsakes; `PersistentDionysusSkipKeepsake` is an internal persistence helper for `SkipEncounterKeepsake`, not a second keepsake;
- Familiar data owns five equip traits and ten hidden growth/effect traits;
- the six weapons own 24 aspect traits and 92 defined Daedalus-hammer traits; dummy weapon traits and per-weapon hammer bases are helpers, not reward choices.

Other valid but non-pool traits include fallback/state carriers such as `FallbackGold`, the three `RoomReward*Trait` value carriers, `StorePendingDeliveryItem`, `GodModeTrait`, `ErisCurseTrait`, `InfernalContractBoon`, `SurfacePenalty`, `UnusedWeaponBonusTrait` / `UnusedWeaponBonusTrait2`, `SuitInherentSpeedBoon`, elemental Essence traits, `MinorArmorBoon`, and biome states such as `WetState`. `VanillaState` is source-defined by inheritance even though the extractor reports it as a stub.

`RestedFamiliarResourceBonus` is a stale entry in `ValidateTraitData().allowedUnreferenced` for this target build: there is no corresponding `TraitData` definition and no other script reference in 1.139672. Do not treat that allowlist string as evidence of a missing trait.

## Progression and requirement census semantics

`generated/progression.csv` combines fourteen different game-data tables; it is not a save-state ledger and its raw row count is not a count of player progression nodes. After separating base/helper/config records, the current snapshot contains these stable gameplay inventories:

| Family | Actual entries | Notes |
| --- | ---: | --- |
| Achievements | 50 | plus debug base `DefaultAchievement` |
| Badge ranks | 50 | `BaseBadge` is an inheritance helper |
| Bounties | 82 | 48 Shrine/Testament bounties + 34 packaged/Chaos trials |
| Fated List quests | 89 | plus 10 debug quest bases |
| Arcana cards | 25 | plus 2 debug card bases |
| Oaths | 17 | `BaseMetaUpgrade` is a helper |
| Hexes | 9 | owned by `SpellData` |
| World-upgrade shop content | 359 | 95 world upgrades/incantations + 181 cosmetics + 53 songs + 30 familiar costumes |

The 76 rows marked `stub` in `generated/progression.csv` are confined to `ObjectiveData`, `FishingData`, `GardenData`, and `HarvestData`. They are parser-shape artifacts: for example, a valid one-line objective table can appear as `stub`, and scalar config fields such as spawn chances or tool names can be emitted as rows. Do not interpret them as unfinished gameplay content.

`generated/requirements.csv` contains all 179 `NamedRequirementsData` identifiers, but 151 are reported as `stub` because their Lua bodies are positional arrays rather than top-level named fields. These entries are still complete runtime requirements. Inspect the source requirement or a future improved extraction before using its `state` or `field_count` semantically.

High-value requirement facts verified from the target build include:

- `BountyBoardUnlockAvailable` requires at least three `TrialUpgrade` uses and the surface-penalty cure transition;
- `ScreenData.Shrine.BountyOrder` contains exactly 48 current Shrine/Testament bounties, and `AllShrineBountiesCompleted` checks that exact set;
- `ShrineUnlocked` requires reaching Tartarus' boss route, at least one clear, and either a Chronos kill or Story Reset history;
- `HermesUpgradeRequirements` requires `HermesFirstPickUp` and then enforces per-run/per-biome Hermes limits;
- `SpellDropRequirements` requires both `ArtemisFirstMeeting` and `SeleneFirstPickUp`, plus one-per-run/pending-store guards; `TalentLegal` requires at least four lifetime `SpellDrop` uses;
- `ChaosUnlocked` is tied to prior Hermes use and current-run context, while `ChaosLegacyTraitsAvailable` requires at least three Chaos uses;
- `DreamRunsUnlocked` persists once `Dream_Intro` has ever been entered; first unlock otherwise requires `HypnosFinalDreamMeeting01` plus three runs since that event;
- the five Familiar unlocks and their upgrade-completion requirements are explicit `GameState.FamiliarsUnlocked`, `SpecialInteractRecord`, `FamiliarPoints`, and `FamiliarUpgrades` conditions;
- hidden-aspect reveal-in-progress requirements pair Circe/Artemis/Moros/Charon/Medea/Selene reveal dialogue with the corresponding Staff/Dagger/Torch/Axe/Lob/Suit hidden aspect;
- `HasAllMetaCardsUnlocked` and `HasAllMetaCardsMaxed` explicitly enumerate the 25 Arcana cards; `HasAllHiddenAspectsRevealed` explicitly enumerates all six hidden aspects.

`BountyData.ShrineBountyNameSwapMap` is a compatibility map, not another bounty table. It maps 42 legacy IDs such as `BountyStaffHeat1FBoss` to current `BountyShrine*` IDs. Those legacy identifiers are recorded in `generated/aliases.csv` with a `target_id`; they must not be counted as additional bounties.


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
