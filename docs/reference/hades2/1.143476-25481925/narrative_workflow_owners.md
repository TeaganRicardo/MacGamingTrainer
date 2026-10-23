# Narrative workflow ownership

The current #425 foundation joins a quest's observed lifecycle, completion,
viewed/update markers and played interstitial beside the existing quest action.
Absent status is labelled unrecorded, rather than proof of never unlocking.
Conditions open on demand through the existing investigation interface. The
source index admits only immediate members of `QuestData` or its explicit
`OverwriteTableKeys` owner; nested look-alikes do not become quest definitions.
Named inherited definitions and native `SetupEvents` remain distinguishable.
Dynamic stage selection, named functions and future eligibility remain unknown;
the Trainer neither executes installed Lua nor claims to evaluate the game.

`QuestLogLogic.lua:586–652` owns unlock/completion and `QuestsCompleted`.
`QuestPresentation.lua:104–113,400–407` records viewing, clears update hints and
records interstitial playback. Claimed-reward status has its separate reward
transaction. These observations do not authorize pretending that a reward was
granted. Existing source-verified quest status writes keep their linked owner.
`AudioLogic.lua:853–864` increments speech records in persistent, run and room
owners. Source-identified cue counts now join the same NPC entity as interaction,
gift and dialogue records. Unknown and duplicate physical data remain preserved.

Source and translation freshness reuse the existing byte-captured narrative
source identity. The supported StoryReset digest only authorizes its existing
dialogue-reset boundary; it does not certify the complete installed source set
or grant new mutations. The original reset/gift/choice-history policy is retained
by this context foundation.

The user's later 2026-10-23 maximum-editability contract supersedes blanket
read-only domain delivery. This foundation is **not completion of #425**:
physical presentation flags, speech/gift values, broader semantic operations and
Advanced typed writes must receive editing support or a specific technical
limitation under #397. Computed authored-source context itself is observational.
Unknown purpose alone is not a reason to deny reliably encoded physical writes.

`test_hades2_save_quest_workflow.py` first reproduced the missing joined quest
subject on baseline `b4d3bac` (RED). Temporary source/save fixtures cover native
bilingual lookup, all observed status families and missing status, on-demand
AND/OR/dynamic/stage requirements, explicit inheritance, NPC interaction/gift/
dialogue/speech grouping, the existing linked completion action, duplicate
physical owners, and source replacement/ambiguity without widening reset
authority. Existing dialogue/entity regressions retain their owning contracts.
These checks are separate from user-only rendered/game/load acceptance.

SHA-256 of read-only supported installed scripts inspected on 2026-10-23:

```
QuestData.lua df9888d6586e0f8644e31db093bf35452bc3ac057d0f144be2f2f1e8d1e64336
QuestLogLogic.lua 0dff8cb49c54715ffe13c1c2986553087688e9dbd2aec3fa1fe61943ba91c254
QuestPresentation.lua 5ba3b6ad50c82b503415c6e4c29873972f8ccc47fbd089a72fd5d31bed30ef99
AudioLogic.lua 24f1a827d15310fddb8bf551fde255537bd7d42242c1d094bb0931189b56a62b
```
