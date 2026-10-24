# Hades II control ownership audit

Scope: main workspace, occurrence/gathering panels, current-run management,
Profiles/shortcuts/diagnostics, Save Editor and typed Advanced editing.

## Sources

| Control family | Visual owner | Hades composition |
| --- | --- | --- |
| Feature switches, checkboxes and locks | `Sources/Core/UI/Primitives/TrainerToggleControl.swift` | Feature state, minimum rarity and force options |
| Text and numeric input | `TrainerTextField.swift`, `TrainerField.swift` | Edit identity, validation and completion |
| Search | `Sources/Core/UI/Components/TrainerSearchField.swift` | Workbench, resources, traits and Save search |
| Labeled single-line controls | `TrainerRow.swift`, `TrainerFeatureControls.swift` | Occurrence, rarity, garden, room/encounter selection, gain multipliers and speed |
| Numeric cards | `TrainerStatControls.swift`, `TrainerCard.swift` | Vitals, resources, stats, elements and damage |
| Reward selection/action | `TrainerResourceControls.swift`, `TrainerListControls.swift` | Native drop and character-choice lifecycles |
| Reset action | `TrainerResetButton` in `TrainerListControls.swift` | Restore native occurrence probability |
| Shortcut badges | `TrainerBadge.swift` | Actual action registration and ordered allocation |
| Panels, grouped-row clipping and spacing tokens | `Sources/Core/UI/TrainerTheme.swift` | Section and multi-control composition |
| Sheets, tool windows and feedback | Core sheet/window/feedback components | Profiles, diagnostics, Save workspaces and receipts |
| Native popup menus and contextual actions | SwiftUI `Picker`, `Menu` and `Button` | Trait lifecycle actions, shortcut capture, save selection and contextual menus |

Not every native control is instantiated through a Host wrapper. Game-owned
popup content and some native contextual buttons remain direct SwiftUI calls.
The module has no separate shape/background renderer, switch implementation,
native view representable or custom text-field implementation. The direct
native controls use platform styles; their option identities and actions remain
Hades-owned.

## Corrections

Occurrence panels used Host rows without the Host's grouped-row clipping.
Other single-line actions used padded panels, while common features used rows.
That produced different heights and insets despite sharing icon/input controls.

`TrainerLabeledControlRow` now owns the icon, flexible space, control spacing and
row chrome. Feature and multiplier rows, occurrence controls, rarity, garden,
room/encounter actions, reward generation and speed consume that contract. The
separate compact multiplier layout has been removed. Multi-line editors retain
Host panels and metric cards retain their own Host card geometry.

The rarity title, minimum selector, shortcut and switch occupy one row. Force
Legendary and Force Duo stay below it. Fresh preferences and the resident/model
default to Heroic; an explicitly saved target survives loading. Probability
editing and the native `GetRarityChances` hook are removed. The existing v17
serialized `multiplier` field stays at its neutral value for stored documents
and transport compatibility; old values cannot change native probabilities.

## Verification boundary

`test_runtime_text_edit_completion.py` exercises native controls, bilingual row
geometry/clipping, rarity toggles, occurrence edits and reset/generation.
`test_hades2_boon_rarity_control.py` covers fresh/legacy preference projection,
the native rarity floor, preservation of special/higher rarities, native return
values and disabling the effect. These isolated fixtures do not establish
rendered application or real-game acceptance.
