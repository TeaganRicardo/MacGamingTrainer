# Core Save Restore and Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the non-UI Core save backend by adding transactional hot-first restore, staged restore orchestration, and reserved `core.save.*` protocol routing.

**Architecture:** `SaveRestoreTransaction` owns mutation/rollback and knows nothing about protocol. `CoreSaveService` composes the existing resolver/snapshot store with process/provider policy and staged metadata. `JsonlRequestRouter` intercepts only the reserved Core namespace; game adapters remain responsible for game-specific commands.

**Tech Stack:** Python 3 standard library only.

**Spec:** `docs/superpowers/specs/2026-09-20-core-save-management-design.md`

## Global Constraints

- UI/Swift is out of scope for this plan.
- Running process alone does not block `hotPreferred` restore.
- A busy/racing condition may become staged only before mutation begins.
- Every restore captures a transaction-internal rollback copy before mutation.
- Restore never renames/removes a save root.
- Only resolved actual-save files may be deleted.
- Rollback failure preserves the last recoverable copy and exposes its path.
- No polling; staged apply is explicit.
- Existing Hades save commands remain temporarily intact until the UI migration slice.

---

### Task 4: Transactional hot-first restore

**Files:**
- Create: `Backend/core/save_restore.py`
- Create: `tests/test_core_save_restore.py`

- [ ] Write RED tests for stopped restore, stable live restore, preflight race/busy, target-only deletion, root continuity, rollback after partial failure, and preserved recovery copy when rollback also fails.
- [ ] Implement `SaveRestoreTransaction` with individual-file temp+atomic replace, internal rollback capture and exact post-transaction verification.
- [ ] Verify focused RED→GREEN and all foundation tests.

### Task 5: Core save service and staged state

**Files:**
- Create: `Backend/core/save_service.py`
- Create: `tests/test_core_save_service.py`
- Modify: `Backend/core/save_resolution.py` only if a public provider loader is required.

- [ ] Write RED tests for hot backup policy, stoppedOnly behavior, hotPreferred busy fallback to stage, staged persistence/reload/quarantine/cancel/apply, and unsupported/no-save conditions.
- [ ] Implement orchestration without duplicating transaction logic.
- [ ] Verify focused tests and foundation suite.

### Task 6: Reserved Core protocol routing

**Files:**
- Modify: `Backend/core/adapter.py`
- Modify: `Backend/core/registry.py`
- Modify: `Backend/core/protocol.py`
- Create: `tests/test_core_save_protocol.py`

- [ ] Write RED tests proving `core.save.*` never enters game adapter dispatch while ordinary commands still do.
- [ ] Extend adapter context with optional save spec/process identity using defaults that preserve existing callers.
- [ ] Intercept and validate Core save commands in `JsonlRequestRouter`.
- [ ] Run new Core save suite plus `test_backend_core_round12.py`.
- [ ] Stop for another API review before Hades/Swift migration.
