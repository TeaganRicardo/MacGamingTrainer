# v0.17.3

App version: **0.17.3**  
Build: **26**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Fixed

- Restored `syncElementInputs(_:)` with the correct `[ElementCount]` type. The v0.17.2 snapshot refactor retained the call site but accidentally removed the helper implementation.
- Expanded Swift integrity checks so Hades2View helper calls must have matching declarations; this specifically covers refactor-time orphaned call sites that `swiftc -parse` cannot diagnose.
- Added a parser-assisted unresolved lowercase identifier audit using `swiftc -frontend -dump-parse` when Swift is available.
- Re-ran custom type, model-member, API-member, private-boundary and full source-graph parse checks.

## Build helper

The experimental `Build Trainer.app` has been removed from the release for now. Manual `build.sh` is the only supported build path until the Finder permission/path behaviour is redesigned.
