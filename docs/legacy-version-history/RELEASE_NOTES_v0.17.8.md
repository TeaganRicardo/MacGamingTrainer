# v0.17.8

App version: **0.17.8**  
Build: **31**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Switch unification

- Replaced the custom 44×25 capsule `TrainerToggleControl` with the native macOS small switch used by the older Hades panel: `.toggleStyle(.switch)`, `.controlSize(.small)`, purple `theme.accent` tint and native thumb animation.
- Runtime state no longer recolors switches. An enabled switch is purple regardless of active/pending/detached state; status is communicated separately by row/icon/help state.
- Detached/deferred state no longer uses the obsolete green color; it now shares the orange warning color.
- `TrainerFeatureToggleRow`, `TrainerFeatureMultiplierRow`, `TrainerCompactMultiplierRow`, inline stat locking and Hades boon persistent switches all use the same `TrainerToggleControl`.
- Hades2 source now contains no direct `Toggle(...)`; Legendary/Duo checkboxes use the shared `TrainerCheckboxControl`.

## Shortcut badge alignment

- Added `TrainerShortcutBadgeSlot`, a fixed 52-point shortcut column.
- Normal feature rows, damage multiplier rows and compact multiplier rows all use the same badge component and slot.
- Removed the multiplier row's previous plain monospaced `Text`, which caused the badge style and vertical/horizontal alignment mismatch.

No backend/Lua/connect/Spawn behaviour is changed in this release.
