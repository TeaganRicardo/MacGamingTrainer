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

Standing CI workflows pin third-party Actions to immutable commit SHAs. The inline upstream tag comment is the update breadcrumb: resolve the intended upstream release/tag to its commit, review that release change, and replace the SHA plus comment together before rerunning the exact-head gates. macOS build/native-test selection is centralized in `Tools/macos_toolchain_identity.py`; the selected runner/Xcode contract is verified on each macOS build, while provenance records the actual hosted image version because GitHub services that image in place. Convergence provenance also hashes the producer workflow source so the immutable Action inputs remain directly attributable to the artifact; `Tools/verify_build_provenance.py` is the shared QA/release consumer for that manifest rather than duplicating schema assertions in workflow YAML.

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
- A module may declare optional `nativeLibraries` with module-relative C `source` and a `filename`. Shared tooling compiles these for the selected architectures and signs them inside that module's `native/` directory. Other modules require no library, engine API, layout profile or debugger; library ABI and target-image compatibility remain game-owned.
- An optional runtime sidecar is a game-owned adapter over Core's generic child-process/JSONL lifecycle seam. Core may own process lifetime, bounded framing, request/reply identity, reply timeout/interruption cleanup, crash handling and terminal outcome-unknown trust semantics; the game owns whether a sidecar exists, its launch command, handshake and method vocabulary, risk classification, error presentation, debugger/engine bridge and runtime semantics. A game that needs no sidecar adds none.
- `ProcessTimeWarpController` is Core-owned because its helper ABI/install/set/verify behavior is debugger-agnostic. A concrete debugger driver remains game-owned until a second real implementation proves a smaller shared driver seam; LLDB is not a Core requirement.
- `TrainerGameModule.managedBackupEditor` is an optional tool-content factory, absent by default. Save Management passes a verified neutral snapshot identity to a module that supplies it; the module chooses supported documents and write targets and reuses its Host-owned backend session. `TrainerToolWindowStore` owns independent native windows and focuses an already-open entry before invoking its factory again. Content supplies its close policy and cleanup; closing a tool does not close the main window. Core does not interpret profile names, save codecs or semantic editor commands. The reference module keeps the absent action.

## Architecture evolution

Apply the causal scope and review process in `AGENTS.md`. Module isolation protects ownership while allowing corrections across Core/game interfaces. Two real adapters or independently demonstrated game-agnostic behavior justify a shared contract; Hades-only repetition belongs in the Hades owner. When responsibility moves, migrate its callers and verify both Hades and the reference fixture. A shared contract preserves each adapter's native execution lifecycle.

## Protocol and timeout rules

The generic Host transports JSON-compatible dictionaries. Each game isolates that untyped edge immediately behind a typed request encoder and state decoder.

Core owns byte-identical cached reply delivery without re-executing the action. It notifies the adapter through the optional `reply_replayed()` lifecycle callback. A module retaining a change-aware public projection invalidates its delivery baseline there so its next live reply can reconstruct the receiver; modules producing full observations inherit the no-op default.

Core enforces request ordering and timeout mechanics but does not decide game-specific timeout budgets. A timed-out backend request is terminal for that backend instance when execution outcome may be unknown. Recovery may restart the backend, but must never automatically replay an outcome-unknown non-idempotent request.

Target-process lifecycle coordination is Host-owned and event-driven. Game views must not add process polling or foreground-stealing connection helpers.

Read current protocol revisions from the owning production declarations; `PROJECT_STATUS.md` records compatibility/acceptance constraints rather than a second version table.
