# Process Time Warp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Build a reusable macOS process Time Warp helper controlled through the existing LLDB transport, then migrate Hades II gameSpeed onto it.

**Architecture:** A signed native dylib owns selective per-image clock rebinding and virtual-time math. A game-agnostic Python controller owns helper discovery/loading/export calls over an already attached LLDB process. Hades II supplies only its target image name and lifecycle integration.

**Tech Stack:** C11, fishhook, Mach time APIs, dyld, LLDB Python, existing Python backend, shell build pipeline.

**Spec:** docs/superpowers/specs/2026-09-20-process-time-warp-design.md

## Global Constraints

- Process factor range: 0.1x-20.0x.
- Initial Hades II image allowlist: exact basename Hades II.
- Audio/system/Steam images must not be rebound.
- Existing LLDB debugger is the only control/injection channel.
- No periodic polling and no helper unload.
- fishhook is pinned to upstream commit aadc161ac3b80db07a9908851839a17ba63a9eb1.

---

### Task 1: Native helper and build contract

**Files:**
- Create: Native/ProcessTimeWarp/ProcessTimeWarp.c
- Create: Native/ProcessTimeWarp/vendor/fishhook/fishhook.c
- Create: Native/ProcessTimeWarp/vendor/fishhook/fishhook.h
- Create: Native/ProcessTimeWarp/vendor/fishhook/LICENSE
- Modify: build.sh
- Test: tests/test_process_time_warp_native_contract.py

**Interfaces:**
- Produces the exported ABI listed in the design spec.
- Produces packaged Backend/core/native/libMGTTimeWarp.dylib.

- [ ] Write a failing static/native contract asserting ABI symbols, image-selective fishhook use, factor bounds, continuity anchors and build packaging.
- [ ] Run the contract and observe failure because the helper does not exist.
- [ ] Add the minimal helper and build steps.
- [ ] Run the contract again.
- [ ] On macOS, build the dylib and verify architecture/signature/exported symbols.

### Task 2: Generic LLDB controller

**Files:**
- Create: Backend/core/process_time_warp.py
- Test: tests/test_process_time_warp_controller.py

**Interfaces:**
- Produces ProcessTimeWarpController.set_speed(speed), reset(), and current_speed().
- Consumes an existing transport exposing pid, process, target, alive(), stop(deadline), and resume(deadline).

- [ ] Write a fake-LLDB failing test for validation, same-PID reuse, new-PID load, hook-mask rejection and 1x reset.
- [ ] Run it and observe failure.
- [ ] Implement only the controller behavior required by the test.
- [ ] Re-run the focused test and backend compile checks.

### Task 3: Prepared-game entitlement

**Files:**
- Modify: Backend/games/hades2/preparation.py
- Test: tests/test_process_time_warp_preparation_contract.py

**Interfaces:**
- Prepared debug executable has both com.apple.security.get-task-allow and com.apple.security.cs.disable-library-validation.

- [ ] Write the entitlement contract first.
- [ ] Add the second entitlement to the existing reversible prepare path.
- [ ] Run focused preparation contracts.

### Task 4: Hades II migration

**Files:**
- Modify: Backend/games/hades2/adapter.py
- Modify: Backend/games/hades2/runtime/hades.lua
- Modify: Backend/games/hades2/schema.py
- Modify: relevant Hades contracts.

**Interfaces:**
- Hades gameSpeed durable preference remains the module-facing field.
- Runtime application routes to ProcessTimeWarpController, not Lua speed hooks.
- Lua revision increments and removes obsolete game-speed ownership.

- [ ] Add RED contracts proving no Lua speed application and correct reconnect/disable lifecycle.
- [ ] Route set_desired(gameSpeed), preference replay and disable-all cleanup through Process Time Warp.
- [ ] Remove obsolete Lua speed hooks/state and increment runtime revision.
- [ ] Run focused Hades contracts, then Linux checks.

### Task 5: Exact-target macOS acceptance

**Files:** no new production files unless evidence shows a real defect.

- [ ] Audit the Hades II main image imports for supported time APIs.
- [ ] Run full macOS checks and build.
- [ ] Verify packaged helper is arm64, ad-hoc signed, ABI exports are present, and App strict codesign succeeds.
- [ ] Connect to Hades II and test 0.5x, 1x, 2x in Crossroads and a run.
- [ ] Verify native slow/time-stop still composes and audio pitch/timing is not warped.
- [ ] Disconnect/reconnect same PID and confirm helper reuse/no factor multiplication.
- [ ] Disable all and confirm only trainer factor returns to 1x.