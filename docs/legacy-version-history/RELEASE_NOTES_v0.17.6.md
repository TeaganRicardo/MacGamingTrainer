# v0.17.6

App version: **0.17.6**  
Build: **29**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Fixed

- Removed the duplicate `TrainerSectionHeading` declaration from `Core/UI/Components/TrainerStatControls.swift`.
- `TrainerSectionHeading` now has a single canonical implementation in `Core/UI/StatusComponents.swift`.
- Added a full `Sources/**/*.swift` top-level declaration uniqueness test. Duplicate `struct`, `class`, `enum`, `protocol`, `actor`, or `typealias` names now fail validation before packaging.

This is a compile-integrity hotfix only. UI behavior, runtime protocol, backend behavior and Hades gameplay logic are unchanged from v0.17.5.
