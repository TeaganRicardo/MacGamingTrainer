# MacGamingTrainer

MacGamingTrainer is a native macOS trainer host with game-specific modules. The unified App includes **Hades II** and a **Hades** module, selected from the left sidebar. Switching the displayed game keeps other game contexts connected, with their pending operations and tool windows intact. Only the displayed trainer responds to global shortcuts.

## Build

Requirements:

- the macOS version declared by `minimumMacOS` in `app.json`;
- the full Xcode toolchain for the game-owned LLDB Python paths;
- Rosetta for the Intel macOS edition of Hades on Apple Silicon.

Build the unified App with:

```bash
chmod +x build.sh
./build.sh
```

The bundled module list is declared in `app.json`; `Info.plist` owns the product version and build identity. `./build.sh <game-id>` produces an isolated diagnostic App for module verification. Hades includes live combat/resource, trait/effect, room/world and management controls, Profiles, diagnostics, and an offline semantic Save Editor with explicit source/target selection. Automated checks cover the implementation. Each module's `module.json` declares its supported game build.

The packaged app is written under `dist/`; the exact path is printed by the build script. For a repository in a cloud-synced directory, use `MGT_BUILD_OUTPUT_DIR=/absolute/local/path ./build.sh` to keep the signed App on a local filesystem.

If the LLDB Python check fails, select the full Xcode toolchain and verify LLDB Python discovery:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcrun lldb -P
```

## Repository guide

- `Sources/Core/` — shared Host, runtime, input, UI, and optional Save infrastructure.
- `Sources/Hades/` — Hades frontend and game-owned state/presentation.
- `Sources/Hades2/` — Hades II frontend and game-owned presentation/state.
- `Backend/core/` — shared backend infrastructure.
- `Backend/games/hades/` — Hades x86_64 debugger/Lua bridge, gameplay controls, and native save workspace.
- `Backend/games/hades2/` — Hades II backend, transport, persistence, catalog, and resident runtime.
- `ContractFixtures/reference_module/` — executable cross-game module contract fixture.
- `docs/reference/hades2/` — versioned Hades II research/reference data.
- `Tools/` and `tests/` — build, validation, and executable contracts.

## Development

See [AGENTS.md](AGENTS.md) for the development guide: layout, build, tests, CI, adding a game, versions and the hard rules.
