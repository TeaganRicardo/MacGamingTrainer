# Save Editor field meanings (2026-10-24)

#554 follows the user’s report of meaningless counters, flat result ownership, unnecessary detail clicks and broken search. It supersedes the earlier ordinary-UI requirement to expose source/trigger conditions on demand. Unknown physical data remains editable in Advanced; it receives no invented semantic name in ordinary results.

The investigation used the supported source archive referenced by `ui_terminology.json`. All 1,164 entries of `manifest/FILES.sha256` were verified again. Full native scripts and dialogue remain outside the repository. `Tools/generate_hades_save_ids.py` derives target/handler and objective/description references; `save_native_ids.py` retains the exact data-source hashes. Regeneration is tested with comments, inheritance overrides and LF/CRLF/CR source files.

| Stored field | Native evidence | Display meaning |
| --- | --- | --- |
| `NPCInteractions[source.Name]` | `NarrativeLogic.lua`, `PlayTextLines`, lines 228–229 | Conversations played for that native object. |
| `SpecialInteractRecord[target.Name]` | `GiftLogic.lua`, special-interaction dispatch, lines 144–150 | Count of the action handlers reached for that target: salute, pet, join song, decorate, admire, drink, or another proven action. |
| Same target with alternative handlers | `NPCData_Dora.lua`, `NPCData_Artemis.lua`, `FamiliarData.lua`, `DeathLoopData.lua` and obstacle/room definitions | One combined counter, such as salute / decorate. Individual action counts cannot be separated from this stored value. |
| `ObjectivesCompleted[objectiveName]` | `ObjectiveData.lua` and `RunData.lua`, lines 1183–1188 | Completions of the objective’s `Description`, with native `Objective_` fallback for generated weapon objectives. Tutorial controller instructions are omitted from the title; the named action, keyword and Ω identity are retained. |
| `SpecialInteractRecord.Shrine` | `HubPresentation.lua`, `SpecialInteractChangeNextRunRNG` | “Acceptance of Another Fate” / “命运无常”, which changes the next run seed. It is not a Fear-setting counter. |

The generator follows actual special-action targets rather than assigning a zero special-action field to every known NPC. Non-NPC targets retain their own object/familiar identity and readable native names; Hermes, Selene and Chaos action sources join their respective characters.

Mutation-site SHA-256 evidence:

- `GiftLogic.lua`: `b08efe43b6beb0f5bf621af8937e2cccdead8e46eca8cfd00d2d00150bbb3964`
- `NarrativeLogic.lua`: `fca2790a6104fb2f28e625fe4c8bb0dfb2cdeb4d5f93cf82842019c6d184f02c`
- `RunData.lua`: `604497cb405551a4364ee9d5bb22ee35731c545ce3cef06a53dc4b6ab6e4b86e`
- `HubPresentation.lua`: `5415582f5e0b9051f1ae43bf047d2a8c7390eea53e31ae8ad6fcf4daa4279ff9`

Temporary fixtures reproduce combined owner/action search failing before the fix, a salute field missing its recognizable purpose, and invisible prerequisite text producing unrelated dialogue matches. The owning regression tests cover bilingual action/owner search, tutorial names, absent native handlers, complete entity paging and preservation of typed Advanced access. Native-control journeys cover input, directly visible Changes/effects, Apply, re-read and recoverable backups; see the [usability procedure](../../../engineering/hades2-save-editor-usability-gate.md). Source tracing and fixture success do not establish rendered or real-game acceptance.
