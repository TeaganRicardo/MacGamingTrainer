# Round 16 — Corrective architecture refactor

Version: **0.16.0**  
Build: **22**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Hades II Lua runtime revision: **19 (unchanged)**

Round 16 deliberately corrects several over-generalizations introduced during the first multi-game decoupling passes. It does **not** change the Hades II wire schema or intended gameplay behavior.

## 1. Core/UI was reduced back to visual primitives

Round 15 had promoted Hades concepts such as desired/dormant feature state, stat availability, resource locking and multiplier rows into Core. That made the directory look generic while forcing future games to speak Hades semantics.

Core now owns only reusable chrome/primitives:

- `TrainerTheme`
- `TrainerShell` / `TrainerSidebar`
- `TrainerCard` / `TrainerRow`
- `TrainerToggleControl` / `TrainerLockButton`
- `TrainerNumberField`
- badges/message/status components

Hades-specific controls now live under `Sources/Hades2/Views/Controls`, and desired/active/dormant/pending behavior is mapped locally by `Hades2FeaturePresentation`.

## 2. The Host, not the game, owns global chrome and application lifecycle

`TrainerHostView` always wraps the active game's content with the shared Shell/Sidebar/Header. A game module supplies content and actions but cannot silently opt out of the global theme/chrome.

AppKit termination handshake is now owned by `AppDelegate`. A game model only implements:

```swift
prepareForTermination(completion: @escaping (Bool) -> Void)
```

Hades no longer calls `NSApp.reply(...)`.

## 3. Backend runtime session is no longer an ObservableObject inside another ObservableObject

`TrainerBackendSession` is now a runtime service that emits immutable `TrainerBackendStatus` values. The Hades store owns observable presentation state directly; the manual `objectWillChange` bridge was removed.

## 4. Hades protocol boundary is game-local and typed

Added:

- `Hades2BackendState.swift` — central typed decoding of backend payload fields
- `Hades2API.swift` — `Hades2Command` + `Hades2Request`, centralizing command spelling and JSON parameter keys

`Hades2Model.swift` no longer indexes raw backend payload keys or contains protocol command strings such as `"set_stat"` / `"restore_backup"`.

The underlying v4 JSON wire format remains compatible; the typed boundary is entirely inside the Hades frontend.

## 5. Shortcut persistence moved out of the main store

`Hades2ShortcutStore` owns historical shortcut migrations, persistence, profile application and digit collision handling. Global Carbon registration remains the generic `GlobalHotkeys` primitive.

## 6. Hades management sheets were split from the main View

Save manager, profile manager, diagnostics and shortcut settings now live in `Hades2ManagementViews.swift` with their own local state.

This also fixes latent semantic-build errors left by the large view (`saveManager` / `settings` references that a parser-only check could not detect).

## 7. Backend manifest is runtime-only; build schema belongs to Tools

`Backend/core/module_manifest.py` now knows only:

- id
- display name
- module protocol version
- backend adapter entry point

It no longer models Swift source paths, architecture, app identity, entitlements or presentation.

`Tools/module_support.py` owns the build-time view of the same JSON file. The `ui` block was removed; sidebar icon/platform/header title live in the Swift game module where presentation belongs.

## 8. Hades backend was decomposed by responsibility

New game-local services:

- `command_router.py`
- `schema.py`
- `preferences.py`
- `profile_service.py`
- `save_service.py`
- `localization.py`
- `catalog.py`
- `diagnostics.py`

`adapter.py` is now primarily transport/runtime state/replay lifecycle. `preparation.py` is back to executable compatibility/signature preparation, with thin compatibility facades for pre-v0.16 callers.

Approximate high-level size change:

- v0.15 `adapter.py + preparation.py`: ~1408 lines
- v0.16 `adapter.py + preparation.py`: ~705 lines

The extracted logic remains inside the Hades module rather than being pushed into Backend Core.

## 9. Tests were corrected as part of the architecture work

Several Round 15 tests only asserted that specific files/tokens existed, which would have forced the bad abstraction to remain. They now test invariants instead:

- Core contains no Hades desired/dormant/stat/resource semantics
- App owns Host shell + termination reply
- Runtime manifest dataclass contains runtime identity only
- command names/param keys are centralized in `Hades2API`
- payload keys are centralized in `Hades2BackendState`
- a temporary second game can be added with only its module + manifest and reuse Core UI primitives
- packaged backend can launch a second fake module without a source tree
- old Round 9–11 Lua behavior mocks still pass

## Known remaining Hades-local debt

The corrective refactor intentionally stops before another round of abstraction:

- `Hades2Model.swift` is still large (~740 lines)
- `Hades2View.swift` is still large (~770 lines)
- v4 transport still uses JSON-compatible dictionaries internally at the `BackendClient` envelope
- Hades `runtime/hades.lua` remains one file
- `Hades2LuaTransport` remains the verified fallback implementation

These are now **game-local** maintenance issues. They should be reduced only when there is a clear Hades maintenance benefit, not by promoting more Hades concepts into Core.
