# v0.17.5

App version: **0.17.5**  
Build: **28**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## UI component consolidation

This release changes UI ownership only. Backend, transport, Lua behaviour and game protocol are unchanged.

- Restored the architectural rule that reusable visual controls live under `Sources/Core/UI` rather than inside the Hades II module.
- Removed `Sources/Hades2/Views/Controls` entirely.
- Removed the game-local `Hades2BoonPicker`; Hades now supplies data/sections to the generic `TrainerGroupedOptionPicker`.
- Moved the proven v0.11 visual treatment into shared Core components without redesigning it:
  - purple accent remains `Color(red: 0.64, green: 0.51, blue: 1.0)`;
  - the main feature switch remains the 44×25 custom capsule with a 19×19 white knob;
  - resource multiplier rows retain the native compact switch used by v0.11;
  - stat cards, lock buttons, resource editor, message cards and selectable list rows retain the old geometry/fills.
- `Hades2FeaturePresentation` still owns Hades runtime semantics (`active / dormant / detached / mismatch`) and now maps them into the game-agnostic `TrainerFeatureControlState`. Core never sees Hades feature IDs or runtime concepts.
- Hades pages now request shared components such as `TrainerFeatureToggleRow`, `TrainerStatMetricCard`, `TrainerResourceEditor`, `TrainerConnectionStatusCard` and `TrainerMessageBanner` rather than drawing their own reusable controls.

## Boundary enforcement

New/updated tests enforce that:

- `Sources/Hades2/Views/Controls` must not exist;
- Hades view files may compose pages but cannot implement reusable visual shapes/backgrounds (`Capsule`, `RoundedRectangle`, `.background`);
- visual controls live in `Core/UI` and contain no Hades-specific semantics;
- the v0.11 palette and switch/card geometry remain pinned;
- Hades uses the shared components rather than local duplicates.

This is intentionally completed before the next functional-recovery step (connect watchdog/catalog/Spawn/Cast), so UI ownership and runtime behaviour remain independently testable.
