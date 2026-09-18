# Game module contract — v0.17.11

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

    static func makeModel() -> ExampleModel { ExampleModel() }
    static func makeContent(model: ExampleModel) -> some View { ExampleContent(model: model) }
    static func makeSidebarActions(model: ExampleModel) -> some View { EmptyView() }
    static func makeHeaderActions(model: ExampleModel) -> some View { EmptyView() }
}
```

The descriptor containing id/protocol versions is generated from the manifest. Presentation stays in Swift and does not travel through the Python runtime manifest.

## Shared UI rule

`Core/UI` owns both low-level primitives and game-agnostic visual composites. Examples include:

- `TrainerRow`, `TrainerToggleControl`, `TrainerIconLabel`
- `TrainerFeatureToggleRow`, `TrainerFeatureMultiplierRow`
- `TrainerMetricCard`, `TrainerStatMetricCard`, `TrainerInlineStatEditor`
- `TrainerResourceEditor`, `TrainerGroupedOptionPicker`
- `TrainerConnectionStatusCard`, `TrainerSection`, `TrainerSectionHeader`
- `TrainerSheetScaffold`, `TrainerMessageBanner`

A game maps its own semantics into neutral visual inputs. For example, Hades decides whether a feature is active/dormant/detached and converts that to `TrainerFeatureControlState`; Core never receives `godMode`, `boonRarity`, `CurrentRun` or other game-domain concepts.

Game modules may define pages/screens and compose these controls, but should not redraw reusable switches, cards, fields, lock buttons or list rows locally. A new visual composite belongs in Core only when its API can remain game-agnostic.

The App/Host always supplies the common Shell/Sidebar/Header, connection status card and Theme, so global visual changes propagate automatically. Page width/minimum geometry, row chrome, section rhythm and sheet chrome are theme/Core concerns rather than game-view constants.

The Host also owns target-application lifecycle coordination. It observes launch/activation/termination events and may request a connection while the game remains foreground; game views must not implement process polling or foreground-stealing connection helpers.

## Manifest

The same JSON file has two consumers with separate responsibilities.

Runtime fields read by Backend Core:

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

Build-only fields are parsed by `Tools/module_support.py`:

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

Do not put sidebar labels/icons/header text in the manifest; those are presentation and belong to the Swift module.

## Game protocol rule

The generic host necessarily transports JSON-compatible dictionaries. A game module should isolate this untyped edge immediately:

- central request/command encoder
- central state/payload decoder
- typed game model above that boundary

Hades II uses `Hades2Request/Hades2API` and `Hades2StatePatch` as the reference pattern. A new game does not need to copy Hades feature semantics.

## Request timeout rule

Core provides timeout enforcement but does not know which operations are expensive. Each game request API should choose a timeout appropriate to the command and pass it through `TrainerBackendSession.send(...)`.

Use short timeouts for status/read-only probes, moderate timeouts for normal mutations/connect/disconnect, and longer explicit timeouts for preparation/save/diagnostic operations. A timeout is terminal for the current backend instance because the execution outcome may be unknown. Core may restart the backend process, but it must not replay the timed-out non-idempotent request. Once recovery succeeds, Host-level target lifecycle coordination may issue a fresh `connect` request because connection is a separate idempotent lifecycle action.
