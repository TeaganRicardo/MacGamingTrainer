# Core Save RC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the generic save-management migration through a testable RC: provider-driven naming metadata, Host-owned Swift model/UI, Hades save decoupling, event-driven staged restore, and macOS verification.

**Architecture:** Backend Core remains the sole owner of filesystem semantics. Optional game providers may describe snapshot naming but cannot mutate snapshot storage. Swift Host owns one `TrainerSaveManagerModel` and a single-column multi-select save sheet; Hades provides only module declaration/business UI unrelated to saves.

**Tech Stack:** Python 3 stdlib, Swift/SwiftUI/AppKit, existing JSONL backend/session/runtime and Core UI primitives.

**Spec:** `docs/superpowers/specs/2026-09-20-core-save-management-design.md`

## Global Constraints

- Snapshot timestamps and staged timestamps contain no timezone suffix.
- Provider naming is optional and read-only.
- UI is single-column chronological inventory, not inspector/two-pane.
- Double-click name edits inline.
- Multiple snapshots can be selected; initial batch action is delete.
- Restore remains single-snapshot and hot/staged policy stays backend-owned.
- `热备份` badge remains beside the name.
- Ellipsis menus show only working operations while preserving the extension point.
- No save polling timers.
- No Hades legacy backup migration.
- No new dependency.

---

### Task 1: Provider snapshot naming and timezone-free timestamps

**Files:**
- Modify: `Backend/core/save_snapshots.py`
- Modify: `Backend/core/save_service.py`
- Modify: `tests/test_core_save_snapshots.py`
- Modify: `tests/test_core_save_service.py`

**Interfaces:**
- Optional provider hook: `describe_snapshot(files, created_at) -> {"defaultName": str|None, "nameDetails": list[str]}`
- Snapshot row gains `nameDetails: list[str]`.
- `createdAt` and staged `stagedAt` use local `YYYY-MM-DDTHH:MM:SS` with no offset.

- [ ] Write RED tests for timezone-free timestamps, provider default name, at most four validated naming details, explicit user name overriding provider default, and absent hook fallback.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement the smallest naming hook integration in `CoreSaveService.backup`; keep `SaveSnapshotStore` provider-agnostic by accepting validated `name_details`.
- [ ] Run Core save focused suite GREEN.
- [ ] Commit.

### Task 2: Generic Swift save types/model

**Files:**
- Create: `Sources/Core/Save/TrainerSaveTypes.swift`
- Create: `Sources/Core/Save/TrainerSaveManagerModel.swift`
- Create: `tests/test_core_save_swift_model_round20.py`

**Interfaces:**
- `TrainerSaveSnapshot`: id/name/createdAt/fileCount/hot/valid/error/nameDetails/path.
- `TrainerPendingRestore`: snapshotID/preserveCurrent/stagedAt.
- `TrainerSaveManagerModel(session:)`: refresh, backup, rename, delete(ids:), reveal, restore, cancelStaged, applyStagedIfPossible.
- Model decodes only request-specific `core.save.*` replies.

- [ ] Write RED source/compile contract proving no Hades identifiers, batch delete sends one request per selected ID in session order, and Core result decoding stays out of Hades state.
- [ ] Run RED.
- [ ] Implement minimal model and decoding.
- [ ] Run GREEN plus backend reply/session reliability tests.
- [ ] Commit.

### Task 3: Host-owned single-column save UI

**Files:**
- Create: `Sources/Core/Save/TrainerSaveManagerView.swift`
- Modify: `Sources/Core/Host/TrainerHost.swift`
- Create: `tests/test_core_save_ui_round20.py`

**Interfaces:**
- Host receives the App-owned `TrainerBackendSession`.
- Host exposes one save entry when `Module.descriptor.supportsSaveManagement`.
- View-local state: `Set<String>` selection, inline rename ID/text, restore candidate/preserve toggle, delete candidates.
- Row actions: multi-select checkbox, double-click name, Restore, ellipsis {Reveal, Delete}.
- Bulk action: Delete selected.

- [ ] Write RED static contract for single-column/no inspector, multi-select, double-click rename, hot badge, ellipsis menu, bulk delete, restore toggle, invalid restore disabled.
- [ ] Run RED.
- [ ] Implement the view using existing Trainer primitives; do not add a new UI framework/abstraction.
- [ ] Wire Host sheet/entry with one `@StateObject TrainerSaveManagerModel`.
- [ ] Run GREEN plus existing UI/static contracts.
- [ ] Commit.

### Task 4: Target-exit staged apply and Hades save ownership removal

**Files:**
- Modify: `Sources/Core/Host/TrainerHost.swift`
- Modify: `Sources/Hades2/Hades2Model.swift`
- Modify: `Sources/Hades2/Hades2API.swift`
- Modify: `Sources/Hades2/Hades2Types.swift`
- Modify: `Sources/Hades2/Views/Hades2HostActions.swift`
- Modify: `Sources/Hades2/Views/Hades2ManagementViews.swift`
- Modify: `Backend/games/hades2/command_router.py`
- Delete: `Backend/games/hades2/save_service.py`
- Create: `tests/test_core_save_hades_decoupling_round20.py`

- [ ] Write RED contract asserting Hades owns no backup commands/types/state/UI/timer and Core owns staged apply on target stop.
- [ ] Run RED.
- [ ] Remove Hades save code with no forwarding wrappers.
- [ ] On target running -> stopped, Host calls `saveManager.applyStagedIfPossible()` exactly once from the existing monitor event.
- [ ] Update stale Hades/static contracts only where they assert removed ownership.
- [ ] Run focused GREEN.
- [ ] Commit.

### Task 5: Full regression and RC build

**Files:** only fix demonstrated regressions.

- [ ] Run `bash Tools/run_linux_checks.sh`.
- [ ] Run focused Core save tests explicitly and confirm pristine output.
- [ ] Run ponytail review on the branch diff; remove only clear unused flexibility.
- [ ] Use target Mac only for `bash Tools/run_macos_checks.sh` and `./build.sh hades2`.
- [ ] Package/tag the resulting testable artifact using the repository's existing RC convention; do not invent a parallel release process.
- [ ] Record exact commit/build artifact and remaining manual test matrix.
