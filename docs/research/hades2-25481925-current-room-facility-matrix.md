# Hades II 1.143476 (Steam build 25481925): current-room facilities

Research dated 2026-11-13. Source files were inspected read-only in the installed supported game under `Hades II.app/Contents/Resources/Content/Scripts`. Candidate names below are issue vocabulary; **official bilingual display IDs for additional facilities remain an acceptance requirement before exposing each family**. Native IDs are from this build, not copied from earlier version reference CSVs.

## Source-backed candidate matrix

| Candidate | Native identity | Native creator / placement owner | Region, limits and activation | Decision |
|---|---|---|---|---|
| Chaos Gate | `ObstacleData.SecretDoor`; `RoomSets.Chaos` | `HandleSecretSpawns` secret branch; authored `SecretPoint`; `SpawnObstacle`, `CreateRoom`, `AssignRoomToExitDoor` | `IsSecretDoorEligible`; `SecretDoorRequirements`; eligible Chaos destination/previous-room return; `ForceSecretDoor`; native health cost/door-use `AttemptUseDoor` | **Implement one-shot now** with live source-room token, only chance branch overridden, postcondition on native exit |
| Infernal Trove | `TimeChallengeSwitch_Money`; `EncounterSets.TimeChallengeOptions` | `HandleSecretSpawns` challenge branch, shared authored `ChallengeSwitchBase` | `ChallengeSpawnRequirements`, timed objective, native encounter completion/reward; depth and native chance | Pending verified challenge-end lifecycle |
| Moon Monument | `EliteChallengeSwitch_Talent`, `EliteChallengeSwitch_MaxMana`; `EncounterSets.EliteChallengeOptions` | Native elite challenge branch; shared `ChallengeSwitchBase` | Eligible elite challenge/force requirements; encounter reward and cleanup | Pending elite encounter tests |
| Unseen Sigil | `PerfectClearChallengeSwitch_Pom`, `PerfectClearChallengeSwitch_MaxHealth`; `EncounterSets.PerfectClearOptions` | Native perfect-clear challenge branch; shared `ChallengeSwitchBase` | Preserve no-damage/failure state, claim and cleanup | Pending perfect-clear encounter tests |
| Well of Charon | `ObstacleData.WellShop`; `StoreData.RoomShop` | `RunShopGeneration` produces stock; `HandleSecretSpawns` creates `room.WellShop`; `SetupObstacle` at shared base | `IsWellShopEligible`; native room/region requirements and `LastWellShopDepth`; opens native shop with prices and purchases | Pending coupled inventory and interaction tests |
| Shrine of Hermes | `ObstacleData.SurfaceShop`; `StoreData.SurfaceShop` | `RunShopGeneration` + `HandleSecretSpawns` `room.SurfaceShop`; shared base | `IsSurfaceShopEligible`; region/progression requirements; native Surface Shop costs and interaction | Pending stock/discount and purchase tests |
| Pool of Purging | `ObstacleData.SellTraitShop` | `HandleSecretSpawns` `room.SellTraitShop`; `GenerateSellTraitShop`; shared base | `IsSellTraitShopEligible`; native menu/selling data and interaction | Pending physical object tests; existing **Open Sell Traits** menu remains separate |
| Gift of Night / reward stand | `ObstacleData.MetaRewardStand`; `MetaRewardStandData.WeightedOptions` | `HandleSecretSpawns` reward stand branch; shared base | `IsMetaRewardStandEligible`; `MetaRewardStandRequirements`; `RequiredShrinePoints = 12` in obstacle; `AttemptUseChallengeSwitch` / `UseMetaRewardStand` | Pending official localized title, route/Fear and claim tests |
| Warding Circle | No proven standalone native in-room portable spawn function in audited secret/shop/challenge owners | May be pre-authored interaction/environment | Authored staging or quest ownership is unverified; no verified generic point/claim lifecycle | **Excluded** pending exact creator + native interaction evidence |
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
