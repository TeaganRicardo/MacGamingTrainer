# Player history and statistics ownership

Supported target: see `PROJECT_STATUS.md`. This is source and fixture evidence; it does not establish game/load/rendered acceptance.

`RunLogic.lua:1848-1856` appends a completed run to `GameState.RunHistory`; it then strips history for saving. `RunHistoryData.lua:645-658` defines native result values. `RunLogic.lua:2764-2797` and `RunHistoryLogic.lua:141-165,278-345` use those results, recorded time, ending location, Fear and trait cache for the history screen. The Save projection identifies runs by their preserved numeric history index; unknown result/location/trait identities stay explicitly unidentified and searchable by raw diagnostic identity. The editable result retains its native numeric value; the existing enum wire uses string choice keys with bilingual `choiceNames`, and Stage normalizes the selected key back to an integer. Location and bounty fields retain their original strings instead of substituting display names into saved values. Both native result labels and raw identities remain searchable across languages.

`RunLogic.lua:2082-2121` owns `UpdateLifetimeTraitRecords`: use count, aggregate and route-specific clears, fastest time and highest Fear are linked to run completion, trait membership, route, dream state and eligibility. `GameStatsLogic.lua:172-280` reads these same native measures. These native owners establish the meaning and exact physical path of each stored statistic. Under the selected editing contract, users may correct these stored measures independently: changing a use count, clear count, fastest time or Fear record does not replay completion, fabricate a run, recalculate unrelated totals, or modify `CurrentRun`. Unknown future measures remain losslessly preserved and may be changed through typed Advanced editing.

`HarvestLogic.lua:356-362,738-768,1191` and `HarvestPresentation.lua:956-964,1044` own harvest, shade-pacification, fishing, manual/Familiar successes, failures and named collection counts. These are recognizable editable activity entities. Native names reuse `localization.official_display_names`, including its native SJSON inheritance. The module terminology registry was consulted; new measure labels are explicit Trainer descriptions in both languages, not a second catalog of native names.

Each writable scalar resolves through `save_advanced.resolve_path` and is checked by `save_advanced.validate_scalar`. Counts and Fear use nonnegative integers, while elapsed/fastest times use finite nonnegative numbers; Boolean and string values retain their actual scalar types. This is an edit of stored statistics, independent of historical event replay or purchase/quest side effects. No unproven sum constraint is imposed between manual/Familiar/total successes or between usage and clear counts.

Observed zero values remain visible and editable. A missing `FishingFails` is the explicit exception to observed-only projection: native fishing failure increments from `(GameState.FishingFails or 0)`, so its exact zero default is shown with `beforePresent=false`, an absent-owner state and a visible creation explanation. Setting any valid value, including zero, creates that field. Other missing statistics are not synthesized. Duplicate physical keys, non-table owners and values that fail the finite scalar contract remain specifically explained; unrelated valid statistics stay editable. Unknown fields have no invented semantic dependencies and remain available through typed Advanced.

`tests/test_hades2_save_history.py` covers multiple results, bilingual names and result search, whole-entity paging, observed zero/default distinctions, and source limitations. `tests/test_hades2_save_history_mutations.py` first reproduced `FishingFails=2` incorrectly being read-only, then exercises Stage → review → Apply → reopen with real temporary Hades codec bytes and the Core recoverable transaction. It covers failures, counts/time/Fear, run trait counts, raw destination/bounty strings, numeric RunResult choices, named collection counts, explicit missing-field creation, invalid types/ranges/nonfinite values, ambiguous keys, Advanced/semantic overlap, unknown scalar edits and preservation of `CurrentRun`, unknown records and other statistics. These fixtures never access user saves; rendered controls and actual game loading remain separately accepted.

## Native source hashes (SHA-256)

```
RunLogic.lua 6598c86db8e1b3c7da74215665f0a0d4cf67d4a531323b489f6a3ce575d8c06a
RunHistoryData.lua dff362b73104f494c92b4d3e0fb6e5c80f64d907ecf4cdec0710add57f64fa89
RunHistoryLogic.lua 598241adbe261e6e1bfad703b529c7c8bf6005f51ffdd70e22a3eac54a10fa1e
GameStatsLogic.lua f42ac8081306448e3e6a880e9eea4195dbd4bdf3dc652355b6a9433d6d97c016
HarvestLogic.lua 3c92e790a5e585769e88ecd4dd3d37c9f73b6129532640fe5cfbebf781987b70
HarvestPresentation.lua c15f33964be0f8a9218c82e8c3963aa0e68687ab537ea18232cfa3fa8a9e2a7c
```
