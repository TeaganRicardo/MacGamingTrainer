# v0.17.11

App version: **0.17.11**  
Build: **34**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **22**

## Spawn catalog completeness

The Spawn catalog is no longer limited to the old curated subset. The curated list now includes the full-release room-reward families that were visibly missing, including:

- Soul Tonic: `MaxManaDropSmall`, `MaxManaDrop`, `MaxManaDropBig`
- Path of Stars: `MinorTalentDrop`, `TalentDrop`, `TalentBigDrop`
- small/tiny Obol and small Centaur variants
- Nectar, Bones, Ash and Psyche (including known large variants)
- Fire / Water / Earth / Air elemental rewards

In addition, the runtime now walks the game's own `RewardStoreData` and automatically adds direct entries that resolve to real `ConsumableData` or `LootData`. Curated entries retain stable grouping/order; newly introduced game rewards fall into an `其他房间奖励` section instead of silently disappearing from the trainer.

## Localization cleanup

Official SJSON display names are now presentation-tag sanitized before they reach the catalog. Markers such as `(#Echo)`, `（#Echo）`, `#Echo` and `{#Echo}` / `{#Emph}` no longer appear as literal UI text. This applies to both Chinese and English lookup values.

## Session metric card geometry

`TrainerMetricCard` no longer imposes the old artificial 82-point minimum height. The title/lock row and value row now determine the card height with 7-point vertical padding, removing the extra blank strip above the title and making the contents vertically compact without Hades-specific layout code.

## Development planning

`NEXT_PHASE_TODO.md` records the next development stage. The priority is now reliability/performance acceptance and protocol/persistence hardening before any further framework abstraction.
