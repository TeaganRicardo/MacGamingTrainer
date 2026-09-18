# v0.17.2

App version: **0.17.2**  
Build: **25**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Compiler fixes

- Fixed the stale `ElementAmount` type reference in `Hades2View.swift`; the actual model type is `ElementCount`.
- Replaced the previous 58 model/input `.onChange` modifiers in the main Hades view with six Equatable snapshot observers.
- Moved numeric formatting out of SwiftUI observer closures so Swift 6.4 does not need to solve Foundation formatting expressions inside the deep ResultBuilder graph.
- Split the main page into named status/session, combat, build, resource and spawn sections.
- Split primary and expanded session metrics into independent ViewBuilder units.
- Preserved the child-owned Save/Profile state fix from v0.17.1.

## Wider semantic checks

- Added a project-wide custom Swift type reference audit. Stale project types such as the removed `ElementAmount` now fail validation even when syntax parsing succeeds.
- Added `model.<member>` and `api.<method>` reference audits for the Hades frontend.
- Added a Foundation-only semantic `swiftc -typecheck` slice covering Runtime, typed Hades API/state/services and the new view snapshots.
- The full selected Swift source graph is still parsed with a generated active-game binding.
- Existing backend, service, packaged-module, mutation-scheduler, runtime-failure and Lua mock regressions remain enabled.

## Double-click compiler

The source package now includes `Build Trainer.app` in the project root. It is a small Finder-launchable helper that runs the same `build.sh` without opening Terminal, writes `build-gui.log`, shows success/failure dialogs, opens the log in TextEdit on failure and can launch the built app on success.

## Naming

New release artifacts use version-only naming. The release package is `MacGamingTrainer_v0.17.2.zip`; new release notes/validation files no longer use Round labels. Historical Round-named files are retained only as old change records.
