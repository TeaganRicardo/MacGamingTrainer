# Player history and statistics ownership

Supported target: see `PROJECT_STATUS.md`. This is source and fixture evidence; it does not establish game/load/rendered acceptance.

`RunLogic.lua:1848-1856` appends a completed run to `GameState.RunHistory`; it then strips history for saving. `RunHistoryData.lua:645-658` defines native result values. `RunLogic.lua:2764-2797` and `RunHistoryLogic.lua:141-165,278-345` use those results, recorded time, ending location, Fear and trait cache for the history screen. The Save projection identifies runs by their preserved numeric history index; unknown result/location/trait identities stay explicitly unidentified and searchable by raw diagnostic identity. It does not infer a clear from a missing record or mutate stripped records.

`RunLogic.lua:2082-2121` owns `UpdateLifetimeTraitRecords`: use count, aggregate and route-specific clears, fastest time and highest Fear are linked to run completion, trait membership, route, dream state and eligibility. `GameStatsLogic.lua:172-280` reads these same native measures. The projection reads observed fields only; an absent statistic is not an invented zero. Unknown future measures stay losslessly preserved in Advanced.

`HarvestLogic.lua:356-362,738-768,1191` and `HarvestPresentation.lua:956-964,1044` own harvest, shade-pacification, fishing, manual/Familiar successes, failures and named collection counts. These are recognizable read-only activity entities. Native names reuse `localization.official_display_names`, including its native SJSON inheritance. The module terminology registry was consulted; new measure labels are explicit Trainer descriptions in both languages, not a second catalog of native names.

All new history projections are read-only: changing a scalar would not replay run completion or update its linked statistics, unlocks, quests and provenance. The ordinary result's information affordance explains this limitation. Existing independently source-verified player-stat actions retain their existing owner. The entity paginator explicitly permits observed read-only history in normal Records browsing, including observed zero counts; it keeps each run/entity whole. Source owner ambiguity is reported rather than silently interpreted as missing state; the original document remains unchanged.

`tests/test_hades2_save_history.py` first reproduced the missing run workflow on baseline `293b647` (RED: completed runs are missing from the player-history workflow). It then covers multiple native result types, run context, lifetime measures, known/unknown and missing records, whole-entity paging, manual/Familiar activity counts, unsupported sources and rejected stage attempts. Existing entity query/workspace tests retain editable-entity behavior. These are temporary/in-memory fixtures, never user saves.

## Native source hashes (SHA-256)

```
RunLogic.lua 6598c86db8e1b3c7da74215665f0a0d4cf67d4a531323b489f6a3ce575d8c06a
RunHistoryData.lua dff362b73104f494c92b4d3e0fb6e5c80f64d907ecf4cdec0710add57f64fa89
RunHistoryLogic.lua 598241adbe261e6e1bfad703b529c7c8bf6005f51ffdd70e22a3eac54a10fa1e
GameStatsLogic.lua f42ac8081306448e3e6a880e9eea4195dbd4bdf3dc652355b6a9433d6d97c016
HarvestLogic.lua 3c92e790a5e585769e88ecd4dd3d37c9f73b6129532640fe5cfbebf781987b70
HarvestPresentation.lua c15f33964be0f8a9218c82e8c3963aa0e68687ab537ea18232cfa3fa8a9e2a7c
```
