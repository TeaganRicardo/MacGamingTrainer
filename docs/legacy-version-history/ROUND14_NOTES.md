# Round 14 — Multi-game hardening

Version: **0.14.0**  
Build: **19**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Hades II Lua runtime revision: **19 (unchanged)**

Round 14 is a framework hardening release. It does not intentionally change Hades II gameplay behavior or its wire schema, so neither host protocol nor Hades II module protocol was bumped.

## Why another refactor pass was necessary

The first multi-game refactor removed most obvious Hades II coupling, but a stricter packaged-app review found two real blockers:

1. runtime manifest discovery still performed build-time frontend validation, which would reject a shipped `.app` because `Sources/<Game>` is intentionally not packaged;
2. build/app identity was still effectively Hades-shaped: the Swift target was hard-coded to arm64/macOS 14 and every game would reuse the same App name/bundle preference domain.

Those are fixed in Round 14.

## Build-time and runtime validation are now separate

`GameModuleManifest` now exposes two validation levels:

- `validate_backend_layout(...)` — safe for packaged runtime discovery;
- `validate_project_paths(...)` — full source/build validation including frontend and entitlement paths.

`Backend/games/registry.py` uses only backend validation. `tools/game_module_tool.py` uses full project validation.

A packaged-module smoke test now constructs an App-like `Contents/Resources/Backend` tree **without any Sources directory**, starts `server.py --game other`, and verifies `hello` plus a custom command round-trip.

## Per-game frontend build contract

`module.json` may now declare:

```json
"frontend": {
  "architectures": ["arm64", "x86_64"],
  "minimumMacOS": "14.0"
}
```

`build.sh` no longer contains a Hades-specific `-target arm64-apple-macosx14.0`.

- no architecture declared → use build machine architecture;
- one architecture → build one binary;
- multiple architectures → build each slice and combine with `lipo`.

Hades II explicitly declares `arm64` and macOS 14.0 in its own manifest.

## Per-game App identity

`module.json` may declare:

```json
"app": {
  "bundleIdentifier": "com.example.trainer.game",
  "displayName": "Mac Gaming Trainer - Example"
}
```

This prevents different trainer builds from overwriting each other or sharing bundle-scoped `UserDefaults` unintentionally.

Hades II explicitly retains:

```text
com.gao.macgamingtrainer
Mac Gaming Trainer
```

so existing Hades preferences/hotkeys remain in the same domain.

If a new module omits `app`, it receives safe per-game defaults. Underscores in the game ID are converted to hyphens for the default bundle identifier.

## Registry error boundary improvement

`create_adapter()` now verifies the adapter class is a `GameAdapter` subclass before construction. A `TypeError` raised *inside* a valid adapter constructor is no longer rewritten into a misleading “constructor signature” error.

## Generic log isolation

A game module without an explicit legacy `data_dir` now gets its generic backend log under:

```text
~/Library/Application Support/MacGamingTrainer/<game-id>/trainer.log
```

Hades II keeps its historical data location through `adapter.data_dir`.

## Python compatibility

The generic manifest layer avoids Python 3.10-only union type syntax and is syntax-checked against Python 3.9 grammar, reducing dependence on a particular Xcode Python minor version.

## What remains intentionally shared

The framework still assumes:

- macOS + SwiftUI frontend;
- Python JSONL backend host;
- one selected game module per App build;
- common trainer lifecycle actions: connect / refresh / disable-all.

These are framework product boundaries, not Hades II leakage.

## Hades II regression scope

No Hades gameplay code was intentionally changed. Existing Round 9/10/11 compatibility tests, Hades adapter tests, preparation tests, and both Lua runtime mocks remain passing.

Target-Mac priorities remain the same as Round 11 for actual game behavior, plus one new packaging check:

1. build `./build.sh hades2` on target Mac;
2. launch the produced App and verify backend starts (this specifically validates packaged manifest discovery);
3. repeat existing Cast/Crossroads/next-room/game-speed regressions from Round 11.
