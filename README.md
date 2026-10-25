# MacGamingTrainer

MacGamingTrainer is a native macOS trainer host with game-specific modules. The unified App includes **Hades II** and an initial **Hades** module, selected from the left sidebar. Switching the displayed game keeps other game contexts connected, with their pending operations and tool windows intact. Only the displayed trainer responds to global shortcuts.

## Build

Requirements:

- macOS 14.0 or later;
- the full Xcode toolchain for the game-owned LLDB Python paths;
- Rosetta for the Intel macOS edition of Hades on Apple Silicon.

Build the unified App with:

```bash
chmod +x build.sh
./build.sh
```

The bundled module list and product build identity are declared in `app.json`. `./build.sh <game-id>` produces an isolated diagnostic App for module verification. Hades currently provides connection/status and a current-hero invincibility toggle; its gameplay coverage is recorded in `PROJECT_STATUS.md`.

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
- `Backend/games/hades/` — Hades x86_64 debugger/Lua bridge and initial runtime feature.
- `Backend/games/hades2/` — Hades II backend, transport, persistence, catalog, and resident runtime.
- `ContractFixtures/reference_module/` — executable cross-game module contract fixture.
- `docs/reference/hades2/` — versioned Hades II research/reference data.
- `Tools/` and `tests/` — build, validation, and executable contracts.

## Development references

- [AGENTS.md](AGENTS.md) — coding-agent entrypoint and verification routing.
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — compatibility, operating limits and manual-acceptance evidence.
- [ENGINEERING_INVARIANTS.md](ENGINEERING_INVARIANTS.md) — stable ownership, lifecycle, replay, and Save-safety rules.
- [GAME_MODULES.md](GAME_MODULES.md) — Core/game-module contract.
- [VERSIONING.md](VERSIONING.md) — release and versioning policy.
