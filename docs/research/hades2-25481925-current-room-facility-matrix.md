# Hades II 1.143476 (Steam build 25481925): current-room facilities

Research dated 2026-11-13. Source files were inspected read-only in the installed supported game under `Hades II.app/Contents/Resources/Content/Scripts`. Candidate names below are issue vocabulary; **official bilingual display IDs for additional facilities remain an acceptance requirement before exposing each family**. Native IDs are from this build, not copied from earlier version reference CSVs.

## Source-backed candidate matrix

| Candidate | Native identity | Native creator / placement owner | Region, limits and activation | Decision |
|---|---|---|---|---|
| Chaos Gate | `ObstacleData.SecretDoor`; `RoomSets.Chaos` | `HandleSecretSpawns` secret branch; authored `SecretPoint`; `SpawnObstacle`, `CreateRoom`, `AssignRoomToExitDoor` | `IsSecretDoorEligible`; `SecretDoorRequirements`; eligible Chaos destination/previous-room return; `ForceSecretDoor`; native health cost/door-use `AttemptUseDoor` | **Implement one-shot now** with live source-room token, only chance branch overridden, postcondition on native exit |
| **地狱宝藏 / Infernal Trove** | `TimeChallengeSwitch_Money`; `EncounterSets.TimeChallengeOptions` | `HandleSecretSpawns` challenge branch, shared authored `ChallengeSwitchBase` | `ChallengeSpawnRequirements`, timed objective, native encounter completion/reward; depth and native chance | **Implemented in draft #732;** native encounter assignment and `ReadyToUse` post-clear unlock; isolated-save combat/claim acceptance remains |
| **明月碑石 / Moon Monument** | `EliteChallengeSwitch_Talent`, `EliteChallengeSwitch_MaxMana`; `EncounterSets.EliteChallengeOptions` | Native elite challenge branch; shared `ChallengeSwitchBase` | Eligible elite challenge/force requirements; encounter reward and cleanup | **Implemented in draft #732;** native elite encounter plus individual reward; isolated-save acceptance remains |
| **匿踪符石 / Unseen Sigil** | `PerfectClearChallengeSwitch_Pom`, `PerfectClearChallengeSwitch_MaxHealth`; `EncounterSets.PerfectClearOptions` | Native perfect-clear challenge branch; shared `ChallengeSwitchBase` | Preserve no-damage/failure state, claim and cleanup | **Implemented in draft #732;** native no-hit encounter with original reward/claim owner; isolated-save acceptance remains |
| **卡戎之井 / Well of Charon** | `ObstacleData.WellShop`; `StoreData.RoomShop` | `RunShopGeneration` produces stock; `HandleSecretSpawns` creates `room.WellShop`; `SetupObstacle` at shared base | `IsWellShopEligible`; native room/region requirements and `LastWellShopDepth`; opens native shop with prices and purchases | **Implemented in draft #731;** native `RoomShop` stock, physical interaction and post-clear unlock; actual game purchases remain acceptance |
| **赫尔墨斯的神龛 / Shrine of Hermes** | `ObstacleData.SurfaceShop`; `StoreData.SurfaceShop` | `RunShopGeneration` + `HandleSecretSpawns` `room.SurfaceShop`; shared base | `IsSurfaceShopEligible`; region/progression requirements; native Surface Shop costs and interaction | **Implemented in draft #731;** native `SurfaceShop` stock/interaction and post-clear unlock; actual game discounts/purchases remain acceptance |
| **净化之池 / Pool of Purging** | `ObstacleData.SellTraitShop` | `HandleSecretSpawns` `room.SellTraitShop`; `GenerateSellTraitShop`; shared base | `IsSellTraitShopEligible`; native menu/selling data and interaction | **Implemented in draft #731;** physical object with `GenerateSellTraitShop`; existing **Open Sell Traits** menu remains separate |
| **黑夜礼赠 / Gift of Night** (official `ShrinePointReward`) | `ObstacleData.MetaRewardStand`; `MetaRewardStandData.WeightedOptions` | `HandleSecretSpawns` reward stand branch; shared base | `IsMetaRewardStandEligible`; `MetaRewardStandRequirements`; `RequiredShrinePoints = 12` in obstacle; `AttemptUseChallengeSwitch` / `UseMetaRewardStand` | **Implemented in draft #733:** native I/Q progression and global `roomData` consistency, ≥12 spent Shrine points, source weighted reward options, `MetaRewardStand` display/exit unlock, real `UseMetaRewardStand` claim owner; exact-game acceptance remains pending |
| Warding Circle | No proven standalone native in-room portable spawn function in audited secret/shop/challenge owners | May be pre-authored interaction/environment | Authored staging or quest ownership is unverified; no verified generic point/claim lifecycle | **Excluded:** `EnemyData_Traps.lua:65` and warding-circle world-upgrade icon definitions exist; no `HandleSecretSpawns` branch or portable scripted claim/setup owner |
| Other props / altars | Ordinary `ExitDoor`, anomalies, gathering points and story-only staging | Distinct route/gathering/story owners | These have existing responsible modules; other independent candidates require additional targeted source audit | Excluded from this picker absent a distinct native facility owner |

### Shared-geometry constraint

`RoomLogic.lua:4891–5067` uses `ChallengeSwitchBase` for shops, challenge switches and the reward stand. Their eligibility, point consumption and depth bookkeeping depend on the order of native branches. A facility generator must coordinate **all** consumers of a shared authored point and refuse occupied, committed or consumed pedestals. An arbitrary `SpawnObstacle` with a copied ID omits native shop inventory/challenge/reward setup and is not a valid implementation.

### Source anchors

- `RunLogic.lua:624–646` — room creation caches separate secret/challenge/Well/sell/Surface/meta-reward chances.
- `RoomLogic.lua:4858–4890` — native Chaos gate entry, secret marker, destination, cost and exit assignment.
- `RoomLogic.lua:5093–5113` — native gate chance, progression and forced-effect eligibility.
- `RoomLogic.lua:4891–4930` — Well, sell and Surface shops on a mutually exclusive native base.
- `RoomLogic.lua:4931–5034` + `EncounterSets.lua:762–789` — timed, perfect-clear and elite challenge variants.
- `RoomLogic.lua:5037–5067` + `ObstacleData.lua:3384+` — `MetaRewardStand` and claim owner.
- `StoreLogic.lua:436–452` — `RunShopGeneration` stock creation; independent of physical shop spawn.
- `RoomLogic.lua:4098–4104` — `AssignRoomToExitDoor` updates object, map, room-exit records and group.
- `ObstacleData.lua:3499+` — `SecretDoor` definition and its native interaction presentation.

### Implementation boundaries

1. One-shot Chaos generation uses the source game's `HandleSecretSpawns`, validates exact room/point/destination, and verifies a registered native exit; no persistent chance changes.
2. Shop picker entries become enabled only after the combined stock + obstacle + menu + purchase lifecycle is implemented and tested for the exact native build.
3. Challenge entries require the original encounter generation and completion/claim flow, not just an attached obstacle.
4. Official zh-CN/en text mapping, negative scenario tests and a current-room scope-token contract are prerequisites for each subsequent enabled family.
5. Do not generate Warding Circle or any story/region-only object until a supported native owner and cleanup/consumption semantics are demonstrated.

## Acceptance after code integration

- #730: one-shot Chaos Gate with original `AssignRoomToExitDoor`, `AttemptUseDoor` and isolated `ExitDoorUnlockedPresentation`; requires an already cleared `ExitsUnlocked` room and `CheckRoomExitsReady`.
- #731: source-owned Well/Shrine/physical Purging Pool and dynamic native eligible catalog. `DoUnlockRoomExits` cannot be replayed after room clear because it rerolls ordinary exits; the scoped object-local unlock invokes the same game's `RefreshUseButton`, animation/sound and readiness fields.
- #732: three explicit challenge families and original challenge encounter/callback owners with source-linked encounter, generated switch and `ReadyToUse` postconditions.
- No current PR claims isolated-save live-game completion. Verify floor/Surface shop transactions, Purging Pool menu, three challenge success/fail flows and Chaos enter/return before closing #729.
- Gift of Night now has an isolated draft owner in #733: `MetaRewardStand` with `ShrinePointReward` title, the native I/Q eligibility and map-installed `roomData`, ≥12 Shrine points, eligible `MetaRewardStandData.WeightedOptions`, native display object setup, post-clear `ReadyToUse`, original `UseMetaRewardStand` claim and one-shot journal. The static source and synthetic test are evidence only; real-game completion and reward persistence remain unverified.
