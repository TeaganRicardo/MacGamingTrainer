# Round 13 — Multi-game framework decoupling

Version: **0.13.0**  
Build: **18**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Hades II Lua runtime revision: **19 (unchanged)**

Round 13 is an architecture release. It does not intentionally change Hades II gameplay behavior or its wire schema, so neither host protocol nor Hades II module protocol was bumped.

## Why this refactor was necessary

Round 11 was still effectively a Hades II application with some abstractions layered over it. Round 12 started separating the backend, but a second game still risked duplicating game identity/protocol constants and Swift backend lifecycle code.

Round 13 finishes the minimum refactor needed for adding another game without copying or editing the framework core.

## Framework boundary after Round 13

Generic host/core:

```text
Backend/server.py
Backend/core/*
Backend/games/registry.py
Sources/App.swift
Sources/Core/*
build.sh
tools/game_module_tool.py
```

Hades II module:

```text
Backend/games/hades2/*
Sources/Hades2/*
```

A normal new game should add only its own backend module + Swift frontend and should not modify the generic host files.

## Manifest is now the single source of truth

`Backend/games/<id>/module.json` owns:

- game ID
- display name
- module protocol version
- backend adapter class
- Swift frontend source directory / module type
- LLDB requirement
- entitlement requirement

The build tool generates the Swift `GameModuleDescriptor` from the manifest and the current host protocol. Hades II no longer hardcodes `hades2`, `Hades II`, host v5 or module v4 inside its Swift Model.

Backend registry creates a `GameAdapterContext` from the manifest and passes it into the adapter constructor. This means a new adapter can safely read `self.game_id`, `self.display_name` and `self.module_protocol_version` during initialization without duplicating constants.

## Backend refactor

`Backend/server.py` remains game-agnostic and owns only JSONL framing/router lifecycle.

`GameAdapter.dispatch()` is now explicitly required to return a JSON object/dict. This prevents a game module from returning a scalar/list that the common Swift client cannot decode as a result object.

Manifest validation now enforces:

- Python-package-safe game IDs
- `Backend/games/<id>/module.json` placement
- adapter contained inside `games.<id>.*`
- frontend contained under `Sources/`
- entitlement file contained inside the selected game module

Invalid modules fail loudly instead of silently disappearing from discovery.

## GameSpec refactor

Core no longer assumes every game is:

- a Steam title
- a macOS `.app/Contents/MacOS/...` bundle
- arm64

`GameSpec` now accepts an explicit executable path and optional bundle/architecture metadata. `macos_app_bundle(...)` is an opt-in helper. Hades II explicitly opts into Steam, app bundle layout and arm64 inside its own module.

## Swift host refactor

New generic layer:

```text
Sources/Core/TrainerBackendSession.swift
```

It owns:

- backend process startup
- host/module protocol compatibility state
- busy / operation / error / notice
- stderr forwarding
- unexpected termination handling

`Hades2TrainerModel` no longer duplicates this lifecycle. It only owns Hades II commands, state fields and payload decoding.

`BackendProcess` also now cleans up pipes/readability handlers when process launch itself fails, allowing a clean retry.

## Build / permissions

`build.sh <game-id>` compiles and packages only the selected game module.

LLDB Python and debugger entitlement are not framework-wide requirements. They are read from the selected module manifest. Hades II keeps its existing LLDB/Lua transport and debugger entitlement inside `Backend/games/hades2`.

This means a future game can use a different transport and does not inherit Hades II's LLDB/Lua assumptions.

## Explicit non-goals

Round 13 does **not**:

- split `runtime.lua` into multiple injected Lua files
- replace the known-good Hades II LLDB transport
- convert Hades II UI into a generic schema-driven UI
- provide runtime game switching inside one App bundle

The current model is one shared source tree, one selected game module per App build. Runtime multi-game switching can be added later if it becomes a real product requirement.

## Regression coverage

Validated locally:

- backend core / router contract
- temporary second-game module discovery + adapter load
- manifest isolation rules
- generated Swift descriptor for a second game
- Hades II adapter desired/profile/replay behavior
- Round 9 / Round 10 server compatibility
- Round 9 / Round 10 Lua mocks
- Round 9–11 Swift/static compatibility checks
- preparation/save staging tests
- Python compile
- Swift full-source parse
- `build.sh` shell syntax
- Info.plist + Hades entitlement plist parse

Target-Mac full Xcode build and real Hades II attach remain the final environment-specific validation step.
