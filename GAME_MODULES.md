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

`protocolVersion` is a module-local compatibility revision between that module's frontend/backend surfaces. It is not product SemVer and does not need to match the Host protocol version or another module's protocol version.

Do not introduce module SemVer until modules can actually be installed or updated independently. If that seam is introduced later, module SemVer must be paired with an explicit supported Host compatibility range.

## App and artifact identity

Build tooling owns interpretation of app identity. The selected module's `app.displayName` and `app.bundleIdentifier` own the application directory/display name and bundle identifier; omitted values use the existing module-derived defaults. The root `Info.plist` must not redeclare `CFBundleName`, `CFBundleDisplayName` or `CFBundleIdentifier`. Validation rejects those keys instead of silently replacing them. Legitimate alternate-module identities remain independent.

The root `Info.plist` owns `CFBundleExecutable`, product SemVer and the bundle build number. The normalized build manifest derives its executable name from that template; a module cannot declare `app.executable`. Package verification requires that exact executable to exist and be executable. All installed modules must have distinct app output names under Unicode normalization and case folding. Publication also checks the existing app's module marker before replacing it, including when its owning module is no longer installed.

`Tools/write_build_provenance.py` owns artifact, provenance and checksum naming. `build.sh` captures source inputs before compilation and seals a matching receipt as `Contents/Resources/BuildProvenance.json` before signing. That filename is reserved and cannot be declared by module resources. The receipt records the actual checkout commit/tree and input fingerprint, root release identity, selected app/module identity, and hashes of declared resident source and packaged bytes. A changed source tree during compilation aborts the build.

Ordinary local builds may use dirty or unversioned source, but exact-source artifact publication requires a clean Git commit and the matching signed build receipt. Modified, untracked, ignored compiler/package inputs and source symlinks cannot silently receive a clean-commit claim. Local provenance has no fabricated workflow identity; a detected CI environment still requires complete CI metadata. Executing CI checkouts pin and assert the intended head, while change routing continues to compare merge-base to head.

Build and package locally with:

```sh
./build.sh <game-id>
python3 Tools/write_build_provenance.py --package <game-id>
```

The package command derives the selected app path, verifies signing and source binding, and writes the ZIP, provenance JSON and SHA256 sidecar under `artifacts/`. Its JSON output is also the CI upload contract. It uses the root product version for every module; fixture artifacts do not introduce module SemVer.

A verification lane that installs committed fixture files into otherwise untracked build paths must declare `MGT_BUILD_DERIVED_INPUTS` as a JSON mapping from destination directory to committed source directory. Before and after the build, the same tooling verifies the complete copied inventory, contents and executable bits and records those derivations. Undeclared or altered generated inputs fail exact-source publication. The reference module lane retains its verified application and provenance alongside the production lane's evidence.

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

The fixture is architecture evidence, not a semantic template. A real game still owns its commands, transport, persistence rules, and game-specific UI.

## Ownership rules

`Core/UI` owns game-agnostic visual primitives and composites. A game maps its own semantics into neutral visual inputs; Core must not learn Hades concepts such as God Mode, boon rarity, resources, or CurrentRun.

The App/Host supplies the common shell, sidebar, header, connection status, backend session, and theme. Game modules compose those shared interfaces instead of recreating Host behavior locally.

- Runtime manifest fields consumed by Backend Core are limited to module identity/protocol/adapter and target-process identity. Frontend source selection, app metadata, architecture/minimum-macOS/debugger requirements, and declared app bundle resources belong to the build tooling. Presentation labels/icons/header text remain in Swift.

## Protocol and timeout rules

The generic Host transports JSON-compatible dictionaries. Each game isolates that untyped edge immediately behind a typed request encoder and state decoder.

Core enforces request ordering and timeout mechanics but does not decide game-specific timeout budgets. A timed-out backend request is terminal for that backend instance when execution outcome may be unknown. Recovery may restart the backend, but must never automatically replay an outcome-unknown non-idempotent request.

Target-process lifecycle coordination is Host-owned and event-driven. Game views must not add process polling or foreground-stealing connection helpers.

Current protocol revisions are operational state and belong in `PROJECT_STATUS.md`, not in this contract.
