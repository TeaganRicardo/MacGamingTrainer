# Game module contract

A normal new game should add only:

```text
Sources/<Game>/
  <Game>Module.swift
  <Game>Model.swift
  <Game>View.swift
  ...game-local state/API/views...

Backend/games/<id>/
  __init__.py
  module.json
  adapter.py
  ...game-local services/transport...
```

It should not require edits to `Sources/Core/**`, `Sources/App.swift`, `Backend/core/**`, or `build.sh`.

Hades II is the reference implementation, not a requirement that other games copy Hades-specific desired/dormant/stat/resource semantics.

## Version ownership

The app has one product SemVer, owned by the root `Info.plist`. Game modules do not repeat that version in `module.json` while they are built and distributed as part of the same app.

The selected module manifest owns `app.displayName` and `app.bundleIdentifier` for its output. Build tooling writes these into `CFBundleDisplayName`, `CFBundleName`, and `CFBundleIdentifier` in the packaged plist and derives `dist/<displayName>.app` from the same validated manifest. The root `Info.plist` must not declare those fields; validation rejects their reintroduction. This preserves the Hades II identity and permits a different module to have its own app identity. The root `Info.plist` owns `CFBundleExecutable`; build tooling uses that name for the binary and output verification requires the packaged executable at that path. Product SemVer and bundle build remain root-owned.

`Tools/write_build_provenance.py` owns artifact and sidecar naming. Its local mode requires a clean source checkout; CI mode verifies the executing PR head or push commit. The reference fixture's temporary module copies must match their tracked `ContractFixtures/reference_module` sources and appear as declared generated inputs in provenance. For a module declaring `residentRuntime`, provenance hashes the declared source and packaged ZIP member rather than copying a digest from status prose.

`protocolVersion` is a module-local compatibility revision between that module's frontend/backend surfaces. It is not product SemVer and does not need to match the Host protocol version or another module's protocol version.

Do not introduce module SemVer until modules can actually be installed or updated independently. If that seam is introduced later, module SemVer must be paired with an explicit supported Host compatibility range.

## Executable cross-game reference

The permanent non-production reference module lives under `ContractFixtures/reference_module/` and is the canonical example of the module interface:

- backend adapter: `ContractFixtures/reference_module/backend/adapter.py`;
- manifest: `ContractFixtures/reference_module/backend/module.json`;
- Swift module/model/view composition: `ContractFixtures/reference_module/frontend/ReferenceFixtureModule.swift`.

It stays outside normal runtime module paths, so discovery never exposes it as a user-facing trainer. Tests and CI temporarily install it into the normal paths and exercise the same manifest validator, generated Swift binding, Backend/Core protocol, and `build.sh <game-id>` route used by a real module.

The proof requires:

- shared source graph = `Sources/App.swift + Sources/Core/** + selected frontend`;
- no Hades/reference-fixture branch in Core, App, or build source selection;
- packaged output contains exactly the selected game module;
- a module without `saveManagement` generates `supportsSaveManagement: false` and receives `save_unsupported` for `core.save.*`;
- both Hades II and the fixture consume the shared Host/UI seam;
- macOS semantic typecheck/build/codesign succeeds for both modules.

The fixture is architecture evidence, not a semantic template. It intentionally uses no LLDB, Lua, or sidecar. A real game still owns its commands, transport, persistence rules, optional runtime adapter, and game-specific UI.

## Ownership rules

`Core/UI` owns game-agnostic visual primitives and composites. A game maps its own semantics into neutral visual inputs; Core must not learn Hades concepts such as God Mode, boon rarity, resources, or CurrentRun.

The App/Host supplies the common shell, sidebar, header, connection status, backend session, and theme. Game modules compose those shared interfaces instead of recreating Host behavior locally.

- Runtime manifest fields consumed by Backend Core are limited to module identity/protocol/adapter and target-process identity. Frontend source selection, app metadata, architecture/minimum-macOS/debugger requirements, and declared app bundle resources belong to the build tooling. Presentation labels/icons/header text remain in Swift.
- An optional runtime sidecar is a game-owned adapter over Core's generic child-process/JSONL lifecycle seam. Core may own process lifetime, bounded framing, request/reply identity, reply timeout/interruption cleanup, crash handling and terminal outcome-unknown trust semantics; the game owns whether a sidecar exists, its launch command, handshake and method vocabulary, risk classification, error presentation, debugger/engine bridge and runtime semantics. A game that needs no sidecar adds none.
- `ProcessTimeWarpController` is Core-owned because its helper ABI/install/set/verify behavior is debugger-agnostic. A concrete debugger driver remains game-owned until a second real implementation proves a smaller shared driver seam; LLDB is not a Core requirement.

## Architecture evolution

Module isolation is an ownership rule, not a prohibition on root-cause refactoring.

- A defect that is demonstrably owned inside one game module should be fixed by deepening that game-owned module/interface rather than moving game semantics into Core.
- A defect may legitimately cross the Core/game seam when the root cause proves that the current ownership is wrong or that a genuinely game-agnostic contract already exists. Such a change must update the reference fixture and module-build evidence for the affected seam.
- Repeated Hades-only fixes do not by themselves justify a Core abstraction. Two real adapters or independently proven game-agnostic behavior are the evidence for a shared seam.
- Conversely, do not preserve duplicated Host/Core policy inside a game merely to keep a patch small. When Core is the demonstrated owner, migrate the coherent responsibility and verify both Hades and the reference module.
- Cross-seam refactors still have one causal purpose. They must not absorb unrelated game features or speculative future-game abstractions.

## Protocol and timeout rules

The generic Host transports JSON-compatible dictionaries. Each game isolates that untyped edge immediately behind a typed request encoder and state decoder.

Core enforces request ordering and timeout mechanics but does not decide game-specific timeout budgets. A timed-out backend request is terminal for that backend instance when execution outcome may be unknown. Recovery may restart the backend, but must never automatically replay an outcome-unknown non-idempotent request.

Target-process lifecycle coordination is Host-owned and event-driven. Game views must not add process polling or foreground-stealing connection helpers.

Current protocol revisions are operational state and belong in `PROJECT_STATUS.md`, not in this contract.
