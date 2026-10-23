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

Actual Boolean flags, playback records, choice strings, quest presentation
markers and legacy Boolean/integer speech records now have typed physical
writes. This authority comes from their reliable saved type and unique owner,
independently of source availability or membership in the native reset list.
Absent known quest status and companion tables can be created. Quest status
supports unrecorded, unlocked, complete and claimed states, updating the
completion companion. Direct status editing does not grant/reclaim a reward;
its controls explain that distinction. Direct record editing preserves current-
run counters, gift order and unrelated data instead of inventing an event.

The existing native narrative-reset operation now has the separate identity
`dialogueReset:<scene>`. It keeps the verified reset boundary, gift/choice/run
companion validation and complete removal of the proven linked records. Direct
`dialogue:<scene>` playback editing remains available when that separate native
operation cannot be established. Conflicting explicit status/completion and
playback/reset requests reject the new action and retain the accepted basket.

Source and translation freshness reuse the byte-captured narrative source
identity. The supported StoryReset digest only certifies that reset boundary,
not the full installed source set. Authored context is observational rather than
a saved field. Unknown purpose alone does not deny reliably encoded physical
writes; Advanced provides typed tables, unknown fields and actual type changes.

The temporary Core/codec journey in `test_hades2_save_narrative_editing.py`
reproduced the claimed-status blanket restriction and the arbitrary resource
balance cap before their corrections. It stages and applies status transitions,
absent completion/presentation records, arbitrary Boolean flags, gift-linked and
unknown playback records, choice text preserving whitespace, legacy speech
Boolean/count values, invalid-input/basket recovery and the separate native
reset. Reopening and independent decoding verify saved values, original prewrite
backup, untouched current-run/gift/unknown records and cleared intent. Save
resource balance input uses the exact-integer boundary of its Lua number type;
the runtime resource-spawn limit is not a native save-format limit.

`test_hades2_save_quest_workflow.py` separately covers native bilingual lookup,
all observed and absent status families, on-demand AND/OR/dynamic/stage
requirements, named inheritance, NPC interaction/gift/dialogue/speech grouping,
duplicate physical owners and source replacement. These fixtures do not establish
real-game/load/rendered user acceptance.

Gift quantity and reward transactions
------------------------------------

`GiftLogic.lua:203–212` adds a purchased quantity to persistent/current-run
resource/person counters, then appends **one** ordered resource-name event.
The quantity and event count therefore need not match. `save_relationships.py`
edits a reliable existing `GameState.GiftRecord[person][resource]` quantity
without inventing an event. A batch combines all person deltas before updating
`GameState.GiftResourceRecord[resource]`; an absent total is rebuilt from every
reliable saved contributor. Duplicate keys or a malformed required contributor
block that particular total, while independent resources remain editable.
Gift event order, dialogue history, inventory and `CurrentRun` stay unchanged.
Missing known NPC/special-interaction and objective-counter tables can be
created; observed unregistered counters remain editable with a purpose warning.

`questClaim:<quest>` is a separate Boolean intent named **Grant reward and mark
claimed / 发放奖励并标记已领取**. The shared byte-captured investigation index
resolves literal quest rewards and named inheritance. Amounts are not copied
into a second registry. `save_native_ids.py` owns the verified mutation-script
digests; changing a staged reward's source invalidates its preview/apply.

For `CashOutQuest` (`QuestLogLogic.lua:211–224`) and `AddResource`
(`ResourceLogic.lua:7–38`), the explicit offline transaction adds the reward to
`GameState.Resources`, `GameState.LifetimeResourcesGained` and
`CurrentRun.ResourcesGained`, updates `GameState.UnviewedLastResourceGained`
unless the native resource policy skips it, and sets `QuestStatus=CashedOut`
with `QuestsCompleted=true`. Repeated grants to an already-claimed status do
not award again. Multiple claims combine resource deltas in canonical quest-ID
order; the last non-skipped resource in that order owns the last-resource marker.
The basket lists concrete physical linked changes. Revise/remove recomputes
them; conflicting direct fields, ancestors, callback inputs or other semantic
effects reject the new intent and preserve the existing basket.

The operation does not evaluate eligibility or replay native Lua. In particular,
`AddResource:43–48` can invoke `CheckObjectiveSet("OpenInventory")` or flag the
current encounter. `ObjectiveLogic.lua:29–117` uses session state, UI animation
configuration, current-hub context and runtime screen state before showing an
objective and possibly writing `GameState.ActiveObjectiveSet`. Offline grants
preserve these objective-prompt owners and disclose that presentation boundary.

Of resources used by supported quest rewards, only GiftPoints has an OnAdded
callback. `ResourceLogic.lua:158–169` sums the saved traits'
`GiftPointHealthMultiplier` through `GetTotalHeroTraitValue` and calls
`AddMaxHealth` for a positive sum. Supported TraitData defines no producer of
this legacy field. A zero/non-positive saved sum has no health effect. A custom
or legacy positive sum needs `GetProcessedTraitData`, `PropertyChanges` and
`AddTraitToHero` (`RoomLogic.lua:2722–2741`), not a fabricated MaxHealth delta.
That specific grant reports the unresolved processed-health-trait owner.
Typed Advanced and direct quest/resource editing remain available.

`test_hades2_save_relationship_transactions.py` and
`test_hades2_save_quest_rewards.py` use temporary Core/codec documents to cover
Stage → review → revise/remove → Apply → reopen, exact pre-write backups,
nonmatching gift event counts, aggregate reconstruction, combined deltas,
missing-owner creation, repeated claims, reward inheritance/source changes,
duplicate definitions, callback dependencies, explicit overlaps (including
source-equal values), and preservation of unknown/run/narrative data. No real
game, user save or rendered acceptance is implied.

SHA-256 of read-only supported installed scripts inspected on 2026-10-23:

```
QuestData.lua df9888d6586e0f8644e31db093bf35452bc3ac057d0f144be2f2f1e8d1e64336
QuestLogLogic.lua 0dff8cb49c54715ffe13c1c2986553087688e9dbd2aec3fa1fe61943ba91c254
QuestPresentation.lua 5ba3b6ad50c82b503415c6e4c29873972f8ccc47fbd089a72fd5d31bed30ef99
AudioLogic.lua 24f1a827d15310fddb8bf551fde255537bd7d42242c1d094bb0931189b56a62b
```
