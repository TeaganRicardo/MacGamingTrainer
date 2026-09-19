# Pre-Acceptance Hardening Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Perform one final correctness, build-system, lifecycle, and complexity audit before Build 2 manual acceptance; fix only demonstrated bugs or low-risk build defects and leave speculative refactors out.

**Architecture:** Audit the frozen Build 2 candidate from an isolated branch. Separate correctness from Ponytail complexity findings. Every production fix requires a root-cause explanation plus a RED regression before implementation. Build/CI changes must preserve the current single-module packaging boundary and Build 2 version.

**Tech Stack:** Swift/AppKit/Carbon, Python JSONL backend, embedded Hades II Lua, Bash build tooling, Git/GitHub Actions.

**Spec:** `PROJECT_STATUS.md` and PR #7 are the acceptance specification.

## Global Constraints

- Product remains `0.1 / Build 2`.
- Runtime source changes require a resident revision bump.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-process runtime recovery.
- No automatic replay of outcome-unknown non-idempotent mutations or native modal actions.
- No Hades semantics in Core/Host.
- No original Hades II file modifications.
- Phase 1/Hades I/save-management work is out of scope.
- Pure style/refactor findings are not merged unless they remove a demonstrated risk.

---

### Task 1: Repository and build inventory

**Files:**
- Read: all tracked source/build/test/workflow files.
- Modify only this plan if findings require scope notes.

**Interfaces:**
- Consumes: exact Build 2 head `efc21268b8c075bd8b8d5ff3726d4548cb6b88e7`.
- Produces: ranked correctness/build/complexity findings with concrete paths and evidence.

- [x] **Step 1:** Inventory tracked files, line counts, largest files, dependency/import surface, test inventory, workflows, generated artifacts, and ignored/untracked build outputs.
- [x] **Step 2:** Scan source for TODO/FIXME/HACK, broad exception swallowing, force unwraps/fatal paths, timers/polling, process/shell mutation, global hook replacement, unbalanced observer/source lifecycle, and duplicate persistence/state owners.
- [x] **Step 3:** Compare all tests against `Tools/run_linux_checks.sh` and macOS workflow coverage.
- [x] **Step 4:** Inspect `build.sh` and module tooling for source-tree mutation, nondeterminism, stale output leakage, over-broad chmod/copy behavior, and package contamination.
- [x] **Step 5:** Run Ponytail repo-wide audit separately; do not apply complexity-only findings yet.

### Task 2: Correctness review of runtime boundaries

**Files:**
- Review: `Backend/games/hades2/adapter.py`
- Review: `Backend/games/hades2/transport.py`
- Review: `Backend/games/hades2/runtime/hades.lua`
- Review: `Sources/Hades2/Hades2Model.swift`
- Review: `Sources/Hades2/Services/Hades2RunLogWatcher.swift`
- Review: `Sources/Core/Host/TrainerConnectionPolicy.swift`
- Review: `Sources/Core/Host/TrainerHost.swift`

**Interfaces:**
- Consumes: process launch/reset/log events and JSONL request/response contract.
- Produces: proven lifecycle/state/replay findings only.

- [x] **Step 1:** Trace launch -> attach -> bootstrap -> ready -> main menu -> same-PID reset -> replay -> ready.
- [x] **Step 2:** Verify every one-shot mutation is excluded from recovery replay.
- [x] **Step 3:** Verify every runtime hook/engine effect block has symmetric cleanup across scene/hero changes and detach/exit.
- [x] **Step 4:** Verify log watcher coalescing cannot silently drop a required reset/ready edge or create unbounded status work.
- [x] **Step 5:** For each demonstrated bug, write the smallest failing contract before any production change.

### Task 3: Correctness review of UI, hotkeys, catalog, and persistence

**Files:**
- Review: `Sources/Hades2/Services/Hades2ShortcutStore.swift`
- Review: `Sources/Core/Input/GlobalHotkeys.swift`
- Review: `Sources/Core/Input/TrainerHotkeyFeedback.swift`
- Review: `Sources/Hades2/Hades2BackendState.swift`
- Review: `Backend/games/hades2/catalog.py`
- Review: persistence/profile modules and tests.

**Interfaces:**
- Consumes: uiOrder, persisted overrides, backend state snapshots, catalog metadata.
- Produces: findings for migration collisions, stale feedback, localization/name identity, and persistence corruption risks.

- [x] **Step 1:** Verify shortcut migration preserves explicit overrides and deterministic defaults.
- [x] **Step 2:** Verify feedback sound is emitted only for successful toggle completion and cannot report stale previous state.
- [x] **Step 3:** Verify catalog source IDs/native-choice capability remain stable independent of localization.
- [x] **Step 4:** Verify atomic persistence/quarantine paths cannot partially overwrite current state.
- [x] **Step 5:** Add RED tests before any fix.

### Task 4: Apply only proven fixes

**Files:** determined by Task 1-3 evidence.

**Interfaces:**
- Produces: minimal production changes with regression coverage.

- [x] **Step 1:** For each finding, state one root-cause hypothesis and reproduce it.
- [x] **Step 2:** Add a RED regression.
- [x] **Step 3:** Implement the smallest fix.
- [x] **Step 4:** Run targeted GREEN test.
- [x] **Step 5:** Commit each independent fix separately.

### Task 5: Integration and handoff closure

**Files:**
- Update: `PROJECT_STATUS.md`, `NEXT_PHASE_TODO.md`, PR #7/#1/#11/#16 only after verification.

**Interfaces:**
- Produces: one new exact acceptance head and RC if any production/build change lands.

- [x] **Step 1:** Run full Linux contracts.
- [x] **Step 2:** Run Host connection policy and Hades log watcher harnesses.
- [x] **Step 3:** Build Hades II arm64 app, verify 0.1 / Build 2, one module, strict codesign.
- [x] **Step 4:** Run build twice from clean state and prove no tracked source mutation/stale package leakage.
- [x] **Step 5:** Review effective diff for correctness and Ponytail scope.
- [ ] **Step 6:** Merge audit branch into `feature/post-v0.1-improvements` only if all Critical/Important findings are resolved.
- [ ] **Step 7:** Reverify exact merged head, rebuild RC, record SHA256, update GitHub handoff state.
