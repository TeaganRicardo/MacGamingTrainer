# Hades management and Save Editor scope

Parent: [#573](https://github.com/TeaganRicardo/MacGamingTrainer/issues/573).
Semantic Save Editor delivery: [#584](https://github.com/TeaganRicardo/MacGamingTrainer/issues/584).

## Management entrypoints

| Player task | Hades II owner | Hades I owner |
| --- | --- | --- |
| Refresh connection/runtime observation | Host session + game model | Same Host session, Hades `status` |
| Disable all continuous intent | Game adapter/runtime + process speed | Hades adapter/runtime + process speed |
| Save backups, staged restore, recovery | Core Save tool window | Same Core Save tool window, Hades membership provider |
| Shortcut settings | Host capture controls, game shortcut store | Same controls, Hades shortcut store |
| Feature presets | Hades II Profile service | Hades `HadesProfileStore`, separate `hades/profiles` directory and schema |
| Current session, history, completed-log cleanup | Host `TrainerLogSink` | Same Host owner, Hades target-process lifetime |
| Diagnostics and export | Game observation/report + Host logs | Hades observation/report + current Host-owned log files |
| Semantic Save Editor | Hades II document/workspace and codec | Hades-owned version-16 document, typed domains/Advanced, pinned workspaces and native tool windows; [evidence and execution boundary](save_editor.md) |
| Re-sign/restore game image | Hades II image preparation | No Hades I preparation workflow is claimed |

The Management section uses Daily Actions, Settings & Profiles, and Maintenance & Diagnostics groups. Controls use the existing Host panels/buttons/sheets, collapse into vertical layouts when needed, and appear in bilingual workbench search. Profiles and diagnostics close their page-anchored sheets when the game page is hidden. The existing Save tool window keeps its original persistent game context.

## Feature profile semantics

A profile stores Hades continuous feature preferences and process game speed. It does not store native saves, absolute hero/resource edits, acquisition/removal actions, room tokens or keyboard shortcuts. The profile format is independently owned by `Backend/games/hades/profiles.py`: schema version 1, `gameID: hades`, normalized name, update time, and validated `DEFAULT_PREFERENCES` values. A Hades II/future/invalid profile is rejected without rewriting its bytes. Names map to hashed filenames and cannot select arbitrary filesystem paths.

Save reads the durable preference owner. Apply validates the complete preset and persists desired state before entering the runtime. While connected, one native `configure` call reconciles resident settings through their existing native mounting/teardown, followed by the existing process-speed controller. While disconnected, the preset remains desired until an explicit connection restores it. Feedback distinguishes that pending state. A lost configure result stops the flow; the action is never retried and process-speed mutation does not continue after that unknown outcome. Reconnection retains the existing runtime recovery journal guard.

Diagnostics performs an explicit status refresh only when already connected. An offline report does not attach a debugger or launch a game. The report identifies the supported image from the module manifest, the actual backend/protocol, observed connection/hero/speed, and durable desired settings. A supported-image declaration is not a new live image-verification result. Export refreshes the report, flushes Host diagnostics, and writes the report plus current Trainer log text to a user-selected JSON file. Native game logs and saves are excluded; the Host remains the log writer, retention and cleanup owner.

## Native Save inventory and #584

Read-only source inspection used the supported native image declared in `module.json.supportedBuild`. The local scripts under `Game.macOS.app/Contents/Resources/Content/Scripts` establish these owners:

| Domain | Native evidence | Editor implication |
| --- | --- | --- |
| Serialization/loading | `Main.lua:1008–1040` strips room/run history then serializes eligible globals with `luabins.save`; `1071–1083` restores non-ignored globals | Preserve typed Lua tables and unknown serializable globals; do not infer the enclosing `.sav` format from the Lua payload alone |
| Resources and progression | `RunManager.lua:157–205` initializes `GameState.Resources`, `WeaponUnlocks`, Mirror unlock/selection/levels | Semantic edits must own proven linked state; seven runtime resource setters do not implement offline Save editing |
| Relationships | `GiftScripts.lua:1–5`, `190–220` initializes and changes `GameState.Gift` values | Gift levels and awarded traits need source-backed linked operations; direct stored values remain separately editable |
| Statistics/history/equipment | `RunManager.lua:1724–1958` appends run history, updates caches and weapon projections | Stored statistics remain directly editable; selected equipment and linked derived caches need explicit owner analysis |
| Save membership | Module `saveManagement` + `HadesSaveProvider` | Core manages profile `.sav`, `.sjson`, `.ctrls` and `activeProfile` files; current `SGB1` parsing only identifies the active profile for backup naming |

Native source hashes and official bilingual identity extraction are owned by `Backend/games/hades/save_catalog.json.sourceEvidence`.

#584 implements those owners through the independent [Save Editor](save_editor.md). Its native artifact map, representation differences from Hades II, linked Mirror/aspect operations, direct statistics and typed/path editing, recoverable replacement and authored complete journeys are recorded there. Unknown native impact receives an editable warning. Executed checks and final-head review remain the completion gates under the current pause.

## Verification boundary

`tests/test_hades_management.py` covers profile isolation/validation, disconnected desired state, connected configure/speed reconciliation, durable-write failure, outcome-unknown non-replay and offline diagnostic truth. The existing `test_hades_frontend.py` native harness covers management decoding without erasing runtime authority, profile dispatch and bilingual discovery. These tests were authored while local tests/game/debugger operations remained paused. No local test, build, rendered UI, game save or game process operation was executed for this implementation. Exact-head CI and independent review remain separate scheduling gates; native Save-load and later game-authored persistence remain pending acceptance.
