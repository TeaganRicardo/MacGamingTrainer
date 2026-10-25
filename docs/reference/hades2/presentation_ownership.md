# Hades presentation ownership after navigation acceptance

Assessment for [#441](https://github.com/TeaganRicardo/MacGamingTrainer/issues/441),
2026-10-25, against production baseline
`bec90aff8d2297f375c66ca20d68e208c5586b72` and the user's acceptance disposition
for [#395](https://github.com/TeaganRicardo/MacGamingTrainer/issues/395).

## Decision

Retain the current presentation owners. No extraction or implementation successor
is selected by this assessment. The remaining concentration is principally the
composition of one continuous Hades workbench and the application of Hades
observations, desired intent and actions. Separating those files by section would
leave their callers responsible for the same policy and lifecycle coordination.

This decision accepts the navigation model as instructed by the user. It does
not claim new rendered, menu, keyboard, VoiceOver or actual-game observations.
Those observations retain their disposition in [PROJECT_STATUS.md](../../../PROJECT_STATUS.md).

## Inspected responsibilities and coupling

| Responsibility | Current owner and concrete coupling | Assessment |
| --- | --- | --- |
| Continuous workbench and numeric drafts | [Hades2View.swift](../../../Sources/Hades2/Hades2View.swift) composes sections, owns focused text and slider previews, and projects four value snapshots from [Hades2ViewSnapshots.swift](../../../Sources/Hades2/Views/Hades2ViewSnapshots.swift). Observation refresh updates unfocused values; `editGeneration` invalidates drafts at a process/lifecycle barrier. | Adding a numeric field touches its presentation, synchronization and reset. These are related edits to one draft lifetime. The concrete idle-material defect in #489 was corrected at this view owner in six changed lines; it did not require a second store or a Core policy. |
| Hades observation and command intent | [Hades2Model.swift](../../../Sources/Hades2/Hades2Model.swift) applies [Hades2StatePatch](../../../Sources/Hades2/Hades2BackendState.swift), preserves pending feature/rarity/speed intent, checks operation capabilities, validates completed edits and dispatches Hades commands. | Stat value/lock mappings recur in observation, completion and reset. They serve different transitions of the same Hades state. A separate observable store would require those transitions, pending request identities and exit barriers to be coordinated across owners; no independent consumer or escaped ownership defect currently justifies that migration. |
| Native input and row geometry | [Core UI](../../../Sources/Core/UI) owns number-field completion, shared rows, clipping, switches and sliders. Hades composes native choices and supplies labels, ranges, capability and command meaning. [The control audit](shared_ui_controls.md) records the #556 migration. | The demonstrated neutral control duplication already has its Core owner. No additional Hades policy belongs in Core. #547 and #556 changed the selected product model and its row composition rather than demonstrating a missing general presentation layer. |
| Navigation and tools | [Hades2WorkbenchNavigation.swift](../../../Sources/Hades2/Services/Hades2WorkbenchNavigation.swift) owns Hades section/search identity. [Hades2Module.swift](../../../Sources/Hades2/Hades2Module.swift) exposes module entries to the Host. The workbench opens Save tools through the Host tool-window interface. | Section navigation clears search/reveals numeric controls without issuing runtime mutations. Independent tools have their own document lifetime; they are not sections to extract from the runtime workbench. |
| Save documents and transactions | [Hades2SaveEditorModel.swift](../../../Sources/Hades2/Hades2SaveEditorModel.swift) owns workspace/query/detail identity, user drafts and staged actions. [Core Save](../../../Sources/Core/Save) owns generic file/backup/transaction presentation and mechanics; the Hades backend owns semantic changes. | Save requests use explicit workspace IDs and reject stale query/detail replies. The runtime model only constructs a Save model on the shared backend session. A merged runtime/Save presentation store would combine unrelated lifetimes and weaken the accepted independent-window contract. |

The recent edits inspected were #489 (idle material refresh), #539 (independent
Save tools), #547 (selected navigation, numeric controls and shortcuts), #550
(selected boon instance), #551 (Save workflows/shared tools), and #556 (shared
rows and rarity). They change different Hades meanings while using the existing
Host/backend/Save owners. File length alone does not establish repeated policy
leakage or an independently useful interface.

## Regression boundary and reassessment

No production behavior changes under #441. Existing executable boundaries are
[view state flow](../../../tests/test_hades2_view_state_flow.py),
[runtime text completion](../../../tests/test_runtime_text_edit_completion.py),
[Save Editor frontend](../../../tests/test_hades2_save_editor_frontend.py), and
the [control audit's](shared_ui_controls.md) native control tests. These cover
passive observation without mutations, capability ownership, generation barriers,
draft completion and independent Save workspaces; they are not rendered/game
acceptance evidence.

Reassess a bounded Hades draft/observation owner if another concrete defect
requires the same coordination correction in independent consumers, or a
measured SwiftUI invalidation cost identifies that seam. Such a successor must
move the policy and all affected callers together, preserve focused edits and
pending intent, and exercise both successful completion and lifecycle recovery.
No recurring audit, new global gate or standing refactor batch is introduced.
