# Core Save Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the non-UI foundation for game-agnostic save management: validated manifest declarations, exact real-save resolution, and verified snapshot storage/hot backup.

**Architecture:** Game modules declare allowed roots and include patterns, with an optional provider for dynamic discovery. Backend Core is the only layer allowed to resolve files and create snapshots. It never falls back to recursively dumping a save root.

**Tech Stack:** Python 3 standard library only.

**Spec:** `docs/superpowers/specs/2026-09-20-core-save-management-design.md`

## Global Constraints

- One snapshot represents all actual save files for one game at one point in time.
- Core never recursively backs up an entire save root by default.
- Declarative resolution is preferred; optional providers cannot escape declared roots.
- Hot backup is preferred when allowed and retries bounded racing writes.
- Internal storage is directory + manifest; no ZIP export or retention policy.
- Hades II legacy migration is out of scope.
- No UI work in this plan.
- All filesystem tests use explicit temporary roots.

---

### Task 1: Save-management manifest contract

**Files:**
- Modify: `Backend/core/module_manifest.py`
- Create: `tests/test_core_save_manifest.py`

**Produces:**
- `SaveRootSpec`
- `SaveManagementSpec`
- `GameModuleManifest.save_management`
- capability-only public metadata

- [ ] Write a failing test for a valid save declaration and invalid root IDs, duplicate roots, unsafe include patterns, empty include lists, invalid provider targets, invalid booleans and invalid restore policies.
- [ ] Run `python3 tests/test_core_save_manifest.py` and verify the failure is due to missing save-management support.
- [ ] Implement the minimal parser and dataclasses.
- [ ] Re-run the focused test until it passes.
- [ ] Run existing manifest/module contract tests.
- [ ] Commit as `feat: add core save manifest contract`.

### Task 2: Exact real-save resolver

**Files:**
- Create: `Backend/core/save_resolution.py`
- Create: `tests/test_core_save_resolution.py`

**Produces:**
- `ResolvedSaveFile`
- `resolve_save_files(spec, module_dir, provider_loader=None)`

- [ ] Write failing tests proving unrelated config/log/cache files are excluded, no implicit recursive enumeration occurs, symlink roots/files are rejected, results are unique/sorted, and provider output outside declared roots is rejected.
- [ ] Run the test and verify RED because the resolver is missing.
- [ ] Implement explicit glob resolution plus a single containment/symlink validator used for declarative and provider results.
- [ ] Re-run focused tests until GREEN.
- [ ] Commit as `feat: resolve declared save files`.

### Task 3: Verified snapshot store and hot backup

**Files:**
- Create: `Backend/core/save_snapshots.py`
- Create: `tests/test_core_save_snapshots.py`

**Produces:**
- `SaveSnapshotStore`
- create/list/load/rename/delete/reveal-path operations
- bounded live snapshot retry

- [ ] Write failing tests for directory+manifest format, exact-file copying, SHA-256/size validation, invalid snapshot visibility, rename metadata, deletion containment and symlink rejection.
- [ ] Run and verify RED.
- [ ] Implement minimal durable snapshot store; write manifest last so partial attempts never list.
- [ ] Add a failing racing-write test where the source changes during the first live copy.
- [ ] Implement bounded hot retry that rechecks file set and hashes before commit.
- [ ] Run all three new Core save test files and existing backend core/module tests.
- [ ] Commit as `feat: add verified core save snapshots`.

### Stop point

Do not start restore/protocol/UI work after Task 3. Re-review the resulting API and diff first. UI will receive a separate design pass before implementation.
