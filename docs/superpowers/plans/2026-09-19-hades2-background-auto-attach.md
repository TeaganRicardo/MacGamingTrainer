# Hades II Background Auto-Attach Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make Hades II attach and become ready without foregrounding Trainer, while eliminating the timer/focus-driven Lua-boundary behavior that previously froze fullscreen gameplay.

**Architecture:** A true target-process launch may consume the existing automatic-connect intent even while Trainer is backgrounded. Hades II keeps its game-specific readiness detection inside the module: a filesystem-event watcher observes new Hades log load-completion lines and requests one status only while the module is attached but waiting. LLDB Lua execution switches from a broad `lua_pcallk` breakpoint/caller filter to the uniquely resolved `sgg::World::Update(float)` symbol and reads the existing global LuaInterface pointer there.

**Tech Stack:** Swift/AppKit DispatchSource, Python LLDB API, Lua 5.2 resident runtime, GitHub Actions.

**Spec:** GitHub issue #11 and roadmap #8 Phase 0.

## Global Constraints

- No periodic LLDB/Lua status polling.
- No background attach on mere target activation; only a true process launch may bypass Trainer foreground gating.
- Manual disconnect suppression remains authoritative until a true game restart or explicit user reconnect.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- Hades-specific log/readiness logic stays under `Sources/Hades2` / `Backend/games/hades2`.
- Existing desired-state replay/error semantics remain unchanged.
- Build 2 stays product version 0.1 / build 2 until Phase 0 acceptance.

---

### Task 1: Direct World-update LLDB boundary

**Files:**
- Modify: `Backend/games/hades2/symbols.json`
- Modify: `Backend/games/hades2/transport.py`
- Test: `tests/test_runtime_boundary_efficiency_dev8.py`

**Interfaces:**
- Consumes: existing `address(name)`, `ScriptManager::LuaInterface`, stop/resume/focus cleanup.
- Produces: `boundary(timeout=3) -> (thread, lua_state_pointer)` with unchanged caller interface.

- [ ] Add a failing static contract requiring `_ZN3sgg5World6UpdateEf` and forbidding a boundary breakpoint on `lua_pcallk`.
- [ ] Verify the contract fails.
- [ ] Add the known-build symbol RVA/prefix and switch `boundary()` to one breakpoint at World::Update; accept only MainThread and nonzero validated LuaInterface.
- [ ] Run Linux contracts.

### Task 2: Hades run-log readiness watcher

**Files:**
- Create: `Sources/Hades2/Services/Hades2RunLogWatcher.swift`
- Modify: `Sources/Hades2/Hades2Model.swift`
- Test: `tests/test_passive_ready_transition.py`

**Interfaces:**
- Produces: callback when newly appended Hades II.log contains `World::Begin()` or `Finished loadScreen onExit`.
- Model consumes the signal by sending one silent status only when connected + waiting + backend available + not busy; otherwise records one pending signal.

- [ ] Add source-contract RED assertions for an event-driven Hades log watcher and no timer.
- [ ] Verify failure.
- [ ] Implement directory DispatchSource watcher with truncation/replacement-safe incremental reads.
- [ ] Wire pending-signal consumption into connect/status request completion and model state reset.
- [ ] Run Linux contracts and macOS semantic build.

### Task 3: Background connect on true process launch only

**Files:**
- Modify: `Sources/Core/Host/TrainerHost.swift`
- Test: `tests/test_passive_ready_transition.py`
- Test: `tests/test_host_connection_policy_dev8.py`

**Interfaces:**
- Uses existing `TrainerConnectionPolicy.targetStateChanged(running:)`.
- `reconcileAutomaticConnection(allowBackground: Bool = false)` may bypass `NSApp.isActive` only for a false->true target-running transition.

- [ ] Add RED assertions: target activation never consumes; true running transition may request background reconciliation.
- [ ] Verify failure.
- [ ] Implement the minimum Host change without new game-specific Core concepts.
- [ ] Run Linux contracts + macOS Swift policy harness.

### Task 4: Phase 0 acceptance artifact

**Files:**
- Modify only docs/issues/PR metadata as needed.

- [ ] Verify Linux contracts.
- [ ] Verify Build 2 macOS semantic build/package/codesign.
- [ ] Produce normal ZIP RC.
- [ ] Update #1/#11 and PR #7 with exact new behavior and manual acceptance steps.
