# Build 2 Hotkeys and Native Boon UI Implementation Plan

> For agentic workers: use subagent-driven-development or executing-plans task-by-task. Steps use checkbox syntax.

Goal: Add generic hotkey feedback, self-reflowing default shortcuts, native boon selling, and native special-blessing choice screens without expanding the debugger lifecycle architecture.

Architecture: Core owns only generic hotkey feedback and Carbon registration mechanics. Hades II owns shortcut semantics/persistence and all game-native boon operations. Native Hades UI is invoked through new one-shot module commands; no custom blessing screen or synthetic in-world object is introduced.

Tech Stack: Swift, SwiftUI, AppKit, Carbon, Python backend protocol, embedded Hades II Lua runtime, GitHub Actions.

Spec: docs/superpowers/specs/2026-09-19-build2-hotkeys-native-boon-ui-design.md

## Global Constraints

- Product remains 0.1 / Build 2.
- No polling/timers for runtime state.
- No automatic replay of native-screen-opening mutations.
- No original Hades II file modification.
- Core cannot contain Hades-specific semantics.
- TDD RED must be observed before each production change.

---

### Task 1: Shortcut default reflow and v5 migration

Files:
- Modify Sources/Hades2/Services/Hades2ShortcutStore.swift
- Modify tests/test_shortcut_chord_semantics.py

Interfaces:
- Consumes ShortcutAction.uiOrder and HotkeyChord.controlOptionDefault(index:).
- Produces v5 shortcut persistence where only explicit overrides are stored.

- [ ] Step 1: Write failing tests for v4-derived defaults reflowing and explicit overrides surviving.
- [ ] Step 2: Run the shortcut harness and verify RED.
- [ ] Step 3: Implement minimal v5 override persistence and migration.
- [ ] Step 4: Run shortcut tests and verify GREEN.
- [ ] Step 5: Commit.

### Task 2: Core generic hotkey feedback

Files:
- Create Sources/Core/Input/TrainerHotkeyFeedback.swift
- Modify Sources/Hades2/Hades2Model.swift
- Create or modify a Swift contract test under tests/.

Interfaces:
- Produces TrainerHotkeyFeedback with enabled, deferred, disabled.
- Produces TrainerHotkeyFeedbackPlayer.play(_:).
- Hades calls the player only after successful async completion.

- [ ] Step 1: Write failing tests for generic Core ownership, state mapping and no feedback on failure.
- [ ] Step 2: Run tests and verify RED.
- [ ] Step 3: Implement Core system-sound player and Hades completion mapping.
- [ ] Step 4: Run tests and verify GREEN.
- [ ] Step 5: Commit.

### Task 3: Native boon sell screen

Files:
- Modify Sources/Hades2/Hades2API.swift
- Modify Sources/Hades2/Hades2Model.swift
- Modify Sources/Hades2/Hades2View.swift
- Modify Backend/games/hades2/adapter.py only if explicit allowlisting requires it.
- Modify Backend/games/hades2/runtime/hades.lua
- Add or modify backend contract tests.

Interfaces:
- Produces request/command open_sell_traits.
- Runtime requires active run, stable scene, no conflicting active screen, and OpenSellTraitMenu.

- [ ] Step 1: Write failing command/runtime/UI contract.
- [ ] Step 2: Run tests and verify RED.
- [ ] Step 3: Implement one-shot command and UI button.
- [ ] Step 4: Run tests and verify GREEN.
- [ ] Step 5: Commit.

### Task 4: Native special-blessing choice mode

Files:
- Modify Backend/games/hades2/runtime/hades.lua
- Modify Sources/Hades2/Hades2API.swift
- Modify Sources/Hades2/Hades2Model.swift
- Modify Sources/Hades2/Hades2View.swift
- Modify catalog payload parsing/types only if a nativeChoice capability field is needed.
- Add or modify backend and Swift contract tests.

Interfaces:
- Produces command open_special_choice with source.
- Catalog exposes whether a special source supports native choice.
- Direct-add remains unchanged.

- [ ] Step 1: Write failing tests for direct-add preservation, audited native sources, native screen use and one-shot semantics.
- [ ] Step 2: Run tests and verify RED.
- [ ] Step 3: Implement audited source mapping and command.
- [ ] Step 4: Add UI dual actions 直接添加 / 原生三选一.
- [ ] Step 5: Run tests and verify GREEN.
- [ ] Step 6: Commit.

### Task 6 (superseded below): Integrated verification and RC

- [ ] Step 1: Run full Linux contracts on exact final head.
- [ ] Step 2: Run full macOS Build 2 workflow on exact final head.
- [ ] Step 3: Review diff for Core/Hades boundary leakage and non-idempotent replay.
- [ ] Step 4: Package RC and record artifact ID plus inner SHA256.
- [ ] Step 5: Update parent PR #7 and Phase 0 issues with new manual acceptance checklist.

### Task 5: God Mode hostile effect immunity

Files:
- Modify Backend/games/hades2/runtime/hades.lua
- Modify existing runtime contract tests.

Interfaces:
- God Mode continues to own Damage routing and unit invulnerability.
- Adds a reversible ApplyEffect hook scoped to the current Hero and explicit hostile-effect denylist.

- [ ] Step 1: Write RED tests proving HecatePolymorphStun and MiasmaSlow are blocked for CurrentRun.Hero while unrelated effects still pass through.
- [ ] Step 2: Verify RED.
- [ ] Step 3: Implement the minimal ApplyEffect hook and clear already-active audited effects when enabling God Mode.
- [ ] Step 4: Verify GREEN and cleanup restoration.
- [ ] Step 5: Commit.

### Task 6: Integrated verification and RC

- [ ] Step 1: Run full Linux contracts on exact final head.
- [ ] Step 2: Run full macOS Build 2 workflow on exact final head.
- [ ] Step 3: Review diff for Core/Hades boundary leakage, non-idempotent replay and over-broad effect suppression.
- [ ] Step 4: Package RC and record artifact ID plus inner SHA256.
- [ ] Step 5: Update parent PR #7 and Phase 0 issues with new manual acceptance checklist.
