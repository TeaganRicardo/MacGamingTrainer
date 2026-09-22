# MacGamingTrainer

MacGamingTrainer is a native macOS trainer host with game-specific modules. The current supported game module is **Hades II**.

## Build

Requirements:

- macOS 14.0 or later;
- the full Xcode toolchain for the Hades II LLDB Python path.

Build the Hades II trainer with:

```bash
chmod +x build.sh
./build.sh hades2
```

The packaged app is written under `dist/`; the exact path is printed by the build script.

If the LLDB Python check fails, select the full Xcode toolchain and verify LLDB Python discovery:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcrun lldb -P
```

## Repository guide

- `Sources/Core/` — shared Host, runtime, input, UI, and optional Save infrastructure.
- `Sources/Hades2/` — Hades II frontend and game-owned presentation/state.
- `Backend/core/` — shared backend infrastructure.
- `Backend/games/hades2/` — Hades II backend, transport, persistence, catalog, and resident runtime.
- `ContractFixtures/reference_module/` — executable cross-game module contract fixture.
- `docs/reference/hades2/` — versioned Hades II research/reference data.
- `Tools/` and `tests/` — build, validation, and executable contracts.

## Development references

- [AGENTS.md](AGENTS.md) — coding-agent entrypoint and verification routing.
- [PROJECT_STATUS.md](PROJECT_STATUS.md) — current operational state.
- [ENGINEERING_INVARIANTS.md](ENGINEERING_INVARIANTS.md) — stable ownership, lifecycle, replay, and Save-safety rules.
- [GAME_MODULES.md](GAME_MODULES.md) — Core/game-module contract.
- [VERSIONING.md](VERSIONING.md) — release and versioning policy.
