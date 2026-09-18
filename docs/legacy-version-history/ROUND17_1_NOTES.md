# Round 17.1 — macOS Swift semantic-build hotfix

Version: **0.17.1**  
Build: **24**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Fixed

- Removed stale `selectedBackup`, `backupRename`, and `selectedProfile` observers from `Hades2TrainerView`. These states were moved into management subviews during the Round 16 split, but their parent-view observers were accidentally left behind. `swiftc -parse` accepted the file while macOS semantic type-checking correctly rejected the out-of-scope names.
- Moved backup selection/name synchronization into `Hades2SaveManagerView`, which owns those states.
- Moved profile selection synchronization into `Hades2ProfileManagerView`, which owns that state.
- Split the very large `Hades2TrainerView.body` modifier chain into several opaque-view stages (`presentedContent`, connection/stat/config/input/catalog observer stages). This reduces SwiftUI constraint-solver complexity and directly addresses the accompanying Swift 6.4 “unable to type-check this expression in reasonable time” failure.
- Extracted connection-reset and element-sync closures into normal helper functions to further reduce the expression size.
- Added `test_round17_1_swift_scope.py`, which specifically rejects child-local management state references in the parent view and keeps the top-level body free of the previous monolithic observer chain.

## Compatibility

This is a frontend/source hotfix. Runtime request semantics introduced in Round 17 are unchanged. No host, game-module, or Lua protocol revision is required.
