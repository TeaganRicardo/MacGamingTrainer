# Working on MacGamingTrainer

MacGamingTrainer is a macOS trainer platform: one Swift Host App, one Python backend, and one module per game (today Hades II and Hades). Each game gets live cheats and a Save Editor. This is the only development guide. Game research is in `docs/reference/`. Incident write-ups and the supported-build runbook are in `docs/development/`.

## Where things live

| Path | Owns |
| --- | --- |
| `app.json` | Product name, bundle ID, Host architectures, minimum macOS, bundled game list |
| `Info.plist` | Product version (`CFBundleShortVersionString`) and build number (`CFBundleVersion`) |
| `Sources/App.swift` | App entry point. It sees only the generated game bindings |
| `Sources/Core/**` | Shared Host: game contexts, backend sessions, process monitoring, hotkeys, UI primitives, Save tools |
| `Sources/<Game>/**` | One game's frontend, compiled as its own Swift module |
| `Backend/core/**` | Shared backend: JSONL protocol, module loading, sidecars, Save transactions, versioned stores |
| `Backend/games/<id>/**` | One game's backend: `module.json`, adapter, transport, resident Lua, catalogs, save codec |
| `ContractFixtures/reference_module/` | A minimal module that never ships. Start a new game from it |
| `Native/` | Native helpers, such as Process Time Warp |
| `Tools/` | Build, packaging and validation scripts. Game generators are in `Tools/games/<id>/` |
| `tests/` | Behavior tests, named `test_<subject>.py` |
| `docs/reference/<id>/` | Versioned game research. Some files are packaged data; `module.json` says which |

Game meaning stays in the game's module: commands, names, rules and save fields. Core gets a mechanism once two games need it, and it never learns game words such as "boon". Core cannot import a game, and games cannot import each other; the Swift module graph (`Tools/product_support.py`) enforces both.

## Build

You need the macOS version in `app.json`, the full Xcode (for LLDB Python), and Rosetta for the Intel Hades build.

```bash
./build.sh                                       # unified App, written to dist/
./build.sh --typecheck --all                     # fast Swift typecheck; no link or sign
./build.sh <game-id>                             # diagnostic App with one module
MGT_BUILD_OUTPUT_DIR=/absolute/local/path ./build.sh   # use when the repo is in a cloud-synced folder
```

## Test

```bash
bash Tools/run_linux_checks.sh                   # every portable test (Linux or macOS)
bash Tools/run_macos_checks.sh                   # every macOS test
python3 Tools/validate_game_module.py --all
python3 Tools/supported_build.py
```

- Both runners give tests a temporary `HOME` and `TMPDIR`. They find tests with `git ls-files`, so untracked copies never run.
- Python lint and types: `pip install -r Tools/python_static_requirements.txt`, then run `ruff check`, `ruff format --check` and `mypy` from the repo root.
- Resident Lua tests need Lua 5.2 (`bash Tools/ci_prerequisites/lua52.sh`). `MGT_LUA52` can name the executable.
- A test with `MGT_PLATFORM = "macos"` at top level runs only on macOS. Every other test runs in the portable lane.
- A native UI journey gets one watchdog from `tests/macos_fixture_policy.py`.
- A few foreground-activation journeys fail on a busy local desktop. The hosted runner is authoritative for them.

## CI

Every PR needs two checks, and both always run:

- `backend-contracts` (Linux): Lua 5.2, backend compile, module validation, `Tools/check_runtime_revision.py`, then every portable test.
- `build` (macOS): `./build.sh --all`, `codesign --verify`, then every macOS test except the foreground-activation journeys, and uploads the App.

Each job reads `git diff --name-only` against the base and skips its work when the PR changes nothing it builds or tests, so a docs-only PR finishes in seconds. A manual `workflow_dispatch` run of `build` runs all macOS tests, including the foreground journeys. A separate manual workflow publishes a release. Workflows pin third-party Actions to commit SHAs.

Until #822's CI change merges, the older routed workflows still run, including `build (reference_fixture)`.

## Add a game

1. Copy `ContractFixtures/reference_module/backend/` to `Backend/games/<id>/` and `ContractFixtures/reference_module/frontend/` to `Sources/<Game>/`. Use a short lowercase ID.
2. Fill in `Backend/games/<id>/module.json`. Add an optional block only when you need it:

| Block | Use it when |
| --- | --- |
| `targetApplication` | Always: `processName`, plus `bundleIdentifier`, or `executablePathSuffix` when the game has no bundle ID |
| `steamAppId` | The App launches the game through Steam |
| `supportedBuild` | Code depends on one exact game image: offsets, symbols, injected code |
| `nativeLibraries` | The module builds C code that loads into the game |
| `residentRuntime` | The module injects resident Lua that has a revision number |
| `saveManagement` | The module offers backups and a Save Editor |
| `commandContract` | Typed commands with timeouts. Regenerate the Swift side with `python3 Tools/generate_module_commands.py --all` |
| `buildRequirements` | The module needs an LLDB bridge, a debugger entitlement, Process Time Warp (`processTimeWarp`) or a CI prerequisite |
| `appResources` | The App bundles data files. `@supportedBuild/<file>` resolves to the reference directory |

3. Add the ID to `modules` in `app.json`. A normal game needs no edit in `Sources/Core`, `Sources/App.swift`, `Backend/core` or `build.sh`. The build generates the catalog and the bindings.
4. Frontend files `import TrainerCore` and use only its `package` API. Prefix every `UserDefaults` key with `<id>.`.
5. Text is bilingual (zh-CN and English). Native game names come from the game's own localization through the module's terminology owner; never invent them. Trainer-owned labels go in the module's string tables.
6. Add a behavior test `test_<id>_model_flow.py` with `MGT_PLATFORM = "macos"`.
7. Run `python3 Tools/validate_game_module.py --all`, `./build.sh <id>` and `./build.sh`.

Architectures are separate. The App runs on the `app.json` architectures. The game's architecture belongs in `supportedBuild`, and injected code must match the game. An arm64 App can drive an x86_64 game through Rosetta and LLDB.

## Versions

- **Product version:** only in `Info.plist`, and only a release PR edits it. A new game is a MINOR bump; fixes are PATCH. Tags are `vX.Y.Z`, then `vX.Y.Z+bN` for a later build of the same version. Never move or reuse a tag.
- **Supported game build:** only `supportedBuild` in `module.json`. To move to a new game build, follow `docs/development/supported-game-build-update.md`.
- **Other revisions:** a module's `protocolVersion`, its resident Lua revision and each persisted schema version are separate integers. Bump one only when its own contract changes. A changed resident Lua source needs a revision bump; `Tools/check_runtime_revision.py` checks PRs.
- Never copy a version, UUID or hash into code, docs or workflows. Read it from its owner.

## Hard rules

These protect players. Don't weaken them without the owner's agreement.

1. **Tests never touch real saves or real user data.** Use temporary directories and fixtures. No test, script or agent run may point at a real game save folder or at `~/Library/Application Support/MacGamingTrainer`. Launch the App for a smoke check with a temporary `HOME`.
2. **Unknown outcomes are never replayed.** When a request to the game times out or loses its reply, its result is unknown. Never retry it automatically. Tell the player, and block further changes to that game process until the game restarts. A restarted backend is not a new game process. Only durable settings (toggles, locks, speed) are re-applied, and only after the runtime is verified ready.
3. **A persisted-format change needs a migration.** Profiles, preferences, shortcuts, data folders and save snapshots carry a schema version. A change ships a migration from the previous version, with a test. A newer version is refused, never overwritten. Write the new data before you remove the old.
4. **Supported-build identity comes from `module.json`.** Native offsets and injected code run only on the exact verified game image. An unknown build fails closed.
5. **Save writes are recoverable.** Every Save Editor apply and every restore goes through Core Save: a verified pre-write copy, an atomic replace, verification, and rollback on failure. Recovery copies are never deleted or restored automatically. A write while the game is running needs an explicit opt-in, and it proves only the disk write.
6. **Desired is not observed.** Show what the game reports. Never show a cheat as active just because the player asked for it.

Save Editors favor editability. A field that the codec can round-trip is editable; unknown meaning gets a warning, not a lock.

## Known limitations

- Each module supports one exact game build, declared in its `supportedBuild`.
- Turn macOS Game Mode off; attaching can time out while it is on.
- After an unknown outcome, restart the game before you reconnect.

## Working agreement (owner, 2026-11-23)

This replaces the owner's 2026-11-07 instruction that selected all executable open issues.

Open issues are the work queue, and the owner decides what is open. An agent may develop, review and merge work on any open issue. New features, new games, refactors, and any new gate, process test or governance doc need the owner to ask for them. An agent may open an issue for a defect it has seen.

Agents may build the App, run the tests, and launch the built App with a temporary `HOME`. An agent launches or attaches to a real game only when the owner asks for that run, with an isolated `CFFIXED_USER_HOME` so real saves are out of reach. Real-game and rendered-App acceptance belong to the owner.

Fix a demonstrated defect where it starts. Don't add guards, scans or gates for hypothetical failures. Prefer deleting code to adding it. No version bump or release unless the owner asks.

## Merging

- Branch from current `main`. Keep one change per PR.
- The required checks must be green on the exact head you merge.
- For code changes, someone who didn't write the change approves that head; a fresh subagent counts. Then the author may merge without asking the owner.
- Squash-merge pinned to the head: `gh pr merge <n> --squash --match-head-commit <sha>`.
- In the PR, say what the real App or a real game didn't check. Don't keep an issue open only for acceptance.

## Before a release (owner, about 15 minutes)

1. Build the release head with `./build.sh` and launch it. Switch games; open search, shortcuts, the Save manager and diagnostics; quit. Check for blank pages, raw keys and errors in the log.
2. Upgrade over the previous release using a copy of real data. Check that profiles, shortcuts and backups survive.
3. For each game, launch it from the App, connect, toggle one setting, run one one-shot action, quit and relaunch the game, then check that the App reconnects.
4. Open the Save Editor on a backup copy, apply one edit, and load that copy in the game.
5. Press a global hotkey while the App is in the background, then quit the App while connected.
