# MacGamingTrainer

MacGamingTrainer is a native macOS trainer host with game-specific modules. The current supported game module is **Hades II**.

## Requirements

- macOS 14.0 or later.
- The Hades II build path uses the repository toolchain and expects LLDB Python support from Xcode.

## Build

```bash
chmod +x build.sh
./build.sh hades2
```

The packaged app is written under `dist/`. See [BUILDING.md](BUILDING.md) for build details and troubleshooting.

## Repository guide

- `Sources/Core/` — shared Host, runtime, input, UI, and optional Save infrastructure.
- `Sources/Hades2/` — Hades II frontend and game-owned presentation/state.
- `Backend/core/` — shared backend infrastructure.
- `Backend/games/hades2/` — Hades II backend, transport, persistence, catalog, and resident runtime.
- `ContractFixtures/reference_module/` — executable cross-game module contract fixture.
- `docs/reference/hades2/` — versioned Hades II research/reference data.
- `Tools/` and `tests/` — build, validation, and executable contracts.

For current development state, see [PROJECT_STATUS.md](PROJECT_STATUS.md). Stable engineering rules live in [ENGINEERING_INVARIANTS.md](ENGINEERING_INVARIANTS.md). The game-module contract is documented in [GAME_MODULES.md](GAME_MODULES.md).

Coding agents should start with [AGENTS.md](AGENTS.md).
