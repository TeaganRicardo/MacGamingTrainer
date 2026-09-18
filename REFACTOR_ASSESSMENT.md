# v0.17.11 architecture assessment

## Current verdict

The first decoupling passes solved physical isolation but over-generalized Hades II business semantics into the framework. v0.16.0 corrects that direction.

The acceptance criterion is now:

> A second game may add its own backend package, Swift frontend and manifest without modifying `Sources/Core`, `Backend/core`, `Sources/App.swift` or `build.sh`; at the same time it is not required to model Hades-specific desired/dormant/stat/resource semantics.

The current implementation meets that criterion for the tested module contract.

v0.17.11 tightens the UI side of those boundaries without moving Hades business semantics into Core. Reusable visual controls now live in `Sources/Core/UI`; Hades keeps only page composition and the mapping from Hades runtime semantics to game-agnostic visual state. The shared controls preserve the proven Hades visual language instead of introducing another visual system. In v0.17.11 every switch path still converges on one shared native purple `TrainerToggleControl`; Hades owns no switch rendering logic. The switch now uses regular macOS control size. This release also keeps the current-game reward identifiers and native Selene `GiveLoot` spawning while removing debugger-boundary status polling; runtime state is refreshed only by explicit/user-driven requests. The next-room override remains entirely inside the Hades runtime module and now follows the game's per-exit reward flow.

## Framework responsibilities

### `Sources/Core`

Owns:

- process/JSONL request infrastructure
- backend session lifecycle
- Host/App contract
- mandatory shared Shell/Sidebar/Header
- theme/design tokens
- visual primitives
- generic global-hotkey registration

Does **not** own:

- desired/active/dormant feature semantics
- stat support/availability rules
- resource lock semantics
- boon/reward concepts
- Hades command names or payload keys

### `Backend/core`

Owns:

- `GameAdapter` contract/context
- runtime module discovery
- JSONL host/router/protocol
- minimal runtime module manifest
- distribution-agnostic `GameSpec`

Does not parse frontend/build/UI metadata and contains no Hades/Steam/LLDB policy.

### `Tools`

Owns build-only interpretation of module metadata:

- frontend source/module type
- architectures/minimum macOS
- app identity
- build requirements/entitlements
- generated Swift identity/protocol binding

### Game module

Owns everything game-specific, including state semantics, presentation mapping, protocol fields, commands, persistence, save behavior, memory/debugger transport, diagnostics and game-specific views.

## UI style propagation

Global style propagation is structural now:

1. `App.swift` injects `TrainerTheme`.
2. `TrainerHostView` always owns `TrainerShell`, sidebar and page header.
3. games compose Core UI primitives for their controls.

Changing Core Theme/primitives/chrome therefore propagates without a game opting into a second copy of the shell. Game-specific layout remains game-owned.

## What should not move into Core again

Do not reintroduce generic APIs shaped like:

- feature desired/dormant state machines
- stat supported/available/locked rows
- resource amount/lock editors
- boon/reward catalog concepts

unless a second real game independently demonstrates the same domain model. Shared appearance is not evidence of shared business semantics.

## Remaining boundary to watch

`BackendClient` still transports `[String: Any]` because the host envelope must support arbitrary game schemas. That is acceptable at the framework boundary; each game should decode immediately into its own typed state/request layer, as Hades now does.

The next useful refactors, if needed, are Hades-local (store/view slicing, Lua module organization), not more framework abstraction.
