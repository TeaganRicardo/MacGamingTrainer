# Game module contract — 0.1 baseline

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

It should not require edits to:

```text
Sources/Core/**
Sources/App.swift
Backend/core/**
build.sh
```

The current host protocol is 5. Hades II is the reference implementation, not a requirement that other games copy Hades-specific desired/dormant/stat/resource semantics.

## Mechanical cross-game proof

A permanent non-production fixture lives under `ContractFixtures/reference_module`. It stays outside `Backend/games` and `Sources/<Game>`, so runtime discovery never exposes it as a user-facing trainer.

Tests and CI temporarily install the fixture into the normal module paths and exercise the same manifest validator, generated Swift binding, Backend/Core protocol and `build.sh <game-id>` path used by a real game. The proof requires:

- shared source graph = `Sources/App.swift + Sources/Core/** + selected frontend`;
- no Hades/reference-fixture branch in Core, App or build source selection;
- packaged output contains exactly the selected game module;
- a module without `saveManagement` generates `supportsSaveManagement: false` and receives `save_unsupported` for `core.save.*`;
- both Hades II and the fixture consume the shared Host/UI boundary;
- macOS semantic typecheck/build/codesign succeeds for both modules.

The fixture is architecture evidence, not a semantic template. A real game still owns its commands, transport, persistence rules and game-specific UI.

## Minimal backend adapter

```python
from core.adapter import GameAdapter

class ExampleAdapter(GameAdapter):
    def dispatch(self, command, params, request_id):
        return {"connected": False}

    def close(self):
        pass
```

Runtime Core reads module identity/protocol/adapter plus target-process identity from `module.json`; build/UI-only metadata stays outside the runtime contract.

## Minimal Swift module

```swift
import SwiftUI

final class ExampleModel: ObservableObject, TrainerHostModel {
    @Published var backendAvailable = true
    @Published var busy = false
    @Published var connected = false
    var operation = ""
    var statusTitle = "尚未连接"
    var connectionDetailText = ""
    var hostActionsEnabled = true

    func toggleConnectionFromHost() {}
    func refreshFromHost() {}
    func restartBackendFromHost() {}
    func disableAllFromHost() {}
    func openLog() {}
    func prepareForTermination(completion: @escaping (Bool) -> Void) { completion(true) }
}

struct ExampleModule: TrainerGameModule {
    static let presentation = TrainerGamePresentation(
        sidebarIconSystemName: "gamecontroller.fill",
        platformLabel: "",
        headerTitle: "EXAMPLE"
    )

    static func makeModel(session: TrainerBackendSession) -> ExampleModel { ExampleModel() }
    static func makeContent(model: ExampleModel) -> some View { ExampleContent(model: model) }
    static func makeSidebarActions(model: ExampleModel) -> some View { EmptyView() }
    static func makeHeaderActions(model: ExampleModel) -> some View { EmptyView() }
}
```

The Host owns the shared `TrainerBackendSession` and injects it through `makeModel(session:)`. A module may ignore the session when it has no backend-driven model state. The descriptor containing id/protocol/save-capability metadata is generated from the manifest. Presentation remains in Swift and does not travel through the Python runtime manifest.

## Shared UI rule

`Core/UI` owns game-agnostic visual primitives and composites. A game maps its own semantics into neutral visual inputs; Core must not learn Hades concepts such as God Mode, boon rarity, resources or CurrentRun.

The App/Host supplies the common Shell/Sidebar/Header, connection status and theme. Game modules compose those primitives rather than redrawing reusable switches, cards, fields, lock buttons or list rows locally.

## Manifest responsibility split

Runtime fields are consumed by Backend Core:

```json
{
  "id": "example",
  "displayName": "Example Game",
  "protocolVersion": 1,
  "backend": { "adapter": "games.example.adapter:ExampleAdapter" },
  "targetApplication": {
    "processName": "Example Game",
    "bundleIdentifier": "com.example.game"
  }
}
```

Build-only fields are consumed by `Tools/module_support.py`:

```json
{
  "frontend": {
    "sourceDirectory": "Sources/Example",
    "moduleType": "ExampleModule",
    "architectures": ["arm64"],
    "minimumMacOS": "14.0"
  },
  "app": {
    "bundleIdentifier": "com.example.macgamingtrainer.example",
    "displayName": "Mac Gaming Trainer - Example"
  },
  "buildRequirements": {
    "lldbPython": false,
    "debuggerEntitlement": false
  }
}
```

Presentation labels/icons/header text belong in Swift, not the runtime manifest.

## Protocol and timeout rules

The generic host transports JSON-compatible dictionaries. Each game should isolate that untyped edge immediately behind a typed request encoder and state decoder. Hades II uses `Hades2Request/Hades2API` and `Hades2StatePatch`.

Core enforces timeouts but does not decide their game-specific budget. A timed-out backend request is terminal for that backend instance when execution outcome may be unknown. Recovery may restart the backend, but must never automatically replay an outcome-unknown non-idempotent request.

Target-process lifecycle coordination is Host-owned and event-driven. Game views must not add process polling or foreground-stealing connection helpers.
