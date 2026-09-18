# Round 14.1 — macOS build regression hotfix

Version: **0.14.1**  
Build: **20**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Fixed

- Fixed the real multi-file Swift access-control regression reported on macOS/Swift 6.4. `ResourceSectionGroup` and `BoonSectionGroup` were declared `private` in `Hades2TrainerModel.swift` but referenced from `Hades2TrainerView.swift`. They are now private view-only helper types in the view file.
- Simplified the boon picker `spawnRow` builder by precomputing groups/selection state and extracting display-name formatting. This reduces constraint-solver complexity around the exact function shown in the Swift frontend crash stack.
- Added an unoptimized `swiftc -typecheck` semantic preflight before the optimized build. `swiftc -parse` cannot detect this class of cross-file access-control error; the build now reports semantic errors before entering the optimized compiler path.
- Added a generic Swift file-boundary regression test that rejects top-level private Swift types referenced from other source files.
- Improved LLDB Python diagnostics: failure output now prints the selected Xcode developer directory and explicitly explains the CommandLineTools-only case.

## Environment note

Hades II still requires LLDB Python at runtime. If `xcode-select -p` reports `/Library/Developer/CommandLineTools` and LLDB Python cannot import, install/open full Xcode and select `/Applications/Xcode.app/Contents/Developer`. This is a host development-environment requirement, not a Hades runtime/Lua protocol change.
