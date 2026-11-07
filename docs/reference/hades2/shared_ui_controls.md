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
| Panels, grouped-row clipping, spacing and Picker width tokens | `Sources/Core/UI/TrainerTheme.swift` | Section and multi-control composition |
| Sheets, tool windows and feedback | Core sheet/window/feedback components | Profiles, diagnostics, Save workspaces and receipts |
| Native popup menus and contextual actions | SwiftUI `Picker`, `Menu` and `Button` | Trait lifecycle actions, shortcut capture, save selection and contextual menus; every in-window Picker uses the Core presentation owner and a Core width role |

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

## Picker presentation, widths and material editor layout

Every in-window native SwiftUI `Picker` uses `.trainerPicker(...)` from Core. The
caller selects a semantic width role and a presentation state:

- width roles: compact (152 pt), standard (216 pt), wide (288 pt), flexible
  (minimum 216 pt, then fills its parent row);
- presentation states: `interactive` and `unavailable`.

Width is geometry only and stays independent from presentation. Call sites do
not set independent widths, content-driven maximums or raw `.disabled(...)` on
the Picker. Two selectors in the same comparison row use the same role so their
columns remain balanced.

Both states are the native macOS popup, as released in v0.5.1: `interactive`
is the enabled control with the product purple indicator and `unavailable` is
the native disabled control. Core never repaints the bezel, title, indicator,
focus ring or height. On macOS 26 and later SwiftUI draws the Picker itself
rather than hosting an `NSPopUpButton`, so a SwiftUI fill or AppKit view-tree
bridge cannot replace the native drawing; the removed #654/#675 repaint left the
native body visible on top of its own surface and indicator.

The appearance and accent each have one application-level owner:

- `NSApp.appearance = .darkAqua` is declared once at launch, so every window,
  sheet, panel, menu and reconstructed control resolves the dark appearance;
  per-view `.preferredColorScheme` is not the AppKit appearance owner.
- The product purple is the application accent color
  (`Resources/Assets.xcassets/AccentColor`, compiled by `build.sh` and declared
  as `NSAccentColorName`). AppKit resolves the popup indicator, open-menu
  selection and focus ring from it, including when a control is redrawn outside
  a SwiftUI update such as a system appearance change. The colour equals
  `TrainerTheme.accent`. macOS applies an application accent only while the
  user's system accent is Multicolor (the default); the Picker owner's SwiftUI
  tint keeps the product purple for SwiftUI-driven updates under an explicitly
  chosen system accent.

The Hades II material editor is a two-row control: the first row holds its
icon/title and search field; the second holds the flexible material Picker,
numeric amount field and lock action. The Picker owns the remaining horizontal
space while the amount and lock controls keep their established widths. Editing,
focus, resource identity and lock semantics remain unchanged.

## Verification boundary

`test_runtime_text_edit_completion.py` exercises native controls, bilingual row
geometry/clipping, rarity toggles, occurrence edits and reset/generation.
`test_hades2_boon_rarity_control.py` covers fresh/legacy preference projection,
the native rarity floor, preservation of special/higher rarities, native return
values and disabling the effect. These isolated fixtures do not establish
rendered application or real-game acceptance.
