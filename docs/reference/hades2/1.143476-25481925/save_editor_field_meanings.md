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

Native host headings distinguish 27 physical counters across 11 people. Context labels live in `save_long_term._INTERACTION_CONTEXTS`; actor reuse is included rather than inferring a context from `_Story`, `_Field` or a number. Supporting native definitions are:

| Person | Native host/context evidence |
| --- | --- |
| Arachne | `RoomDataF.lua:3270`; `NPCData_Arachne.lua:3477`; `NarrativeData.lua:1830` |
| Artemis | `DeathLoopData.lua:764`; `NPCData_Artemis.lua:1828`; `NarrativeData.lua:1856,1887` |
| Cerberus | `RoomDataI.lua:3297`; `NPCData_Hades.lua:6306,6625` |
| Chronos | `NPCData_Chronos.lua:89,1513,1539,1909`; `NarrativeData.lua:5171,5220`; `RoomDataI.lua:4433` |
| Hades | `RoomDataI.lua:3198,4174`; `NPCData_Hades.lua:73,5325,5357`; `NarrativeData.lua:2140` |
| Hecate | `DeathLoopData.lua:653,9244`; `NarrativeData.lua:310`; `RoomDataI.lua:4377` |
| Hypnos | `DeathLoopData.lua:603`; `NPCData_Hypnos.lua:609,849,1030,1172` |
| Narcissus | `RoomDataG.lua:2844`; `NPCData_Narcissus.lua:2983` |
| Nyx | `NarrativeData.lua:7447,7457`; `NPCData.lua:6085`; `EncounterData_Story.lua:2258` |
| Zagreus | `NarrativeData.lua:7518,7541`; `NPCData.lua:7784,9318` |
| Zeus | `NPCData.lua:5903,9491`; `RoomDataQ.lua:2348,3033` |

Hermes's boon object and in-person actor, and Selene's moon-gift object and in-person actor, also retain separate host headings (`LootData_Hermes.lua:4,80`; `NPCData_Hermes.lua:4`; `LootData_Selene.lua:4,25`; `NPCData_Selene.lua:3,251`; `PresentationBiomeI.lua:2005`). Selene's same actor appears both at the Crossroads and in the ending. The child actor uses `PlayerUnit`'s official name with childhood context (`NPCData.lua:11316`). Horse/chariot and leopard scenery actors define no dialogue sets (`NPCData_Selene.lua:413`; `NPCData.lua:7738`); any existing physical values remain in Advanced rather than acquiring synthetic conversation controls.

Dialogue source presentation is shared by search and Changes. Authored scene ownership is required before localization content becomes an ordinary playback field; Event-only voice entries do not create a `TextLinesRecord` path. Eligible native resets remain direct actions beside their scene and keep the existing companion-owner validation. Ordinary quest results omit the diagnostic authored-condition summary, and gift/reward rows omit routine implementation subtitles.

Mutation-site SHA-256 evidence:

- `GiftLogic.lua`: `b08efe43b6beb0f5bf621af8937e2cccdead8e46eca8cfd00d2d00150bbb3964`
- `NarrativeLogic.lua`: `fca2790a6104fb2f28e625fe4c8bb0dfb2cdeb4d5f93cf82842019c6d184f02c`
- `RunData.lua`: `604497cb405551a4364ee9d5bb22ee35731c545ce3cef06a53dc4b6ab6e4b86e`
- `HubPresentation.lua`: `5415582f5e0b9051f1ae43bf047d2a8c7390eea53e31ae8ad6fcf4daa4279ff9`

Temporary fixtures reproduce combined owner/action search failing before the fix, a salute field missing its recognizable purpose, invisible prerequisite text producing unrelated dialogue matches, fabricated voice-event playback fields, lost scene identity in Changes, and the missing direct reset action. The owning regression tests cover bilingual action/owner/context search, tutorial names, absent native handlers, complete entity paging, reset companions and preservation of typed Advanced access. Native-control journeys cover input, directly visible Changes/effects, Apply, re-read and recoverable backups; see the [usability procedure](../../../engineering/hades2-save-editor-usability-gate.md). Source tracing and fixture success do not establish rendered or real-game acceptance.
