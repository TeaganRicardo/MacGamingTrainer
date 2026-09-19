# Batch A Native Modal Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make trainer-opened boon selling exit correctly and replace the broken global native-choice button with working per-source native three-choice entries.

**Architecture:** Keep both native modal commands as one-shot Hades II runtime commands. Fix sell by overriding only its close callback for the trainer-owned invocation; fix special choices by reading `EnemyData` and `PresetEventArgs`. Swift derives UI-only native-choice rows from existing catalog metadata and routes UI/hotkey selection through one action.

**Tech Stack:** Swift/SwiftUI, Python contract harnesses, injected Hades II Lua, native Hades II script APIs.

**Spec:** `docs/superpowers/specs/2026-09-19-batch-a-native-modals-design.md`

## Global Constraints

- Product remains 0.1 / Build 2.
- Runtime source changes require revision 36.
- No periodic LLDB/Lua polling.
- Native modal commands remain one-shot and never preference-replayed.
- Do not fabricate room Store state or persistent engine NPC objects.
- Do not touch game speed, God Mode, sound feedback, or connection timing.
- Final tester receives a prebuilt signed `.app` ZIP.

---

### Task 1: Native sell screen can always exit

**Files:** `tests/test_native_sell_traits_contract.py`, `Backend/games/hades2/runtime/hades.lua`

**Interfaces:** Consume native `OpenSellTraitMenu`, `ScreenData.SellTraits`, `CloseStoreScreen`; produce a trainer-owned named close callback for only the trainer-opened screen.

- [x] **Step 1: Write the failing contract**

Assert the runtime deep-copies `ScreenData.SellTraits`, replaces the copied Close button handler, restores the original definition, delegates only when a real Store exists, and never creates `CurrentRun.CurrentRoom.Store`.

- [x] **Step 2: Verify RED**

Run: `python3 tests/test_native_sell_traits_contract.py`
Expected: FAIL because r35 directly threads `OpenSellTraitMenu`.

- [x] **Step 3: Implement the minimal runtime fix**

Add the trainer close function and threaded wrapper; reuse native cleanup calls and keep sell option/selection behavior unchanged.

- [x] **Step 4: Verify GREEN**

Run: `python3 tests/test_native_sell_traits_contract.py`
Expected: `native_sell_traits_contract_ok`.

- [x] **Step 5: Commit**

`git commit -m "fix: allow trainer sell screen to close"`

### Task 2: Native special choices use actual game data globals

**Files:** `tests/test_native_special_choice_contract.py`, `Backend/games/hades2/runtime/hades.lua`

**Interfaces:** Consume `EnemyData`, `PresetEventArgs`, existing `nativeSpecialChoiceDefinitions`; produce working `open_special_choice(source)` for the ten audited sources.

- [x] **Step 1: Write the failing contract**

Require `EnemyData[definition.npc]`, `PresetEventArgs[definition.choices]`, and a deep-copied source. Reject any `NPCData[...]` lookup in the command block.

- [x] **Step 2: Verify RED**

Run: `python3 tests/test_native_special_choice_contract.py`
Expected: FAIL because r35 uses `NPCData`.

- [x] **Step 3: Implement the minimal data-source fix**

Switch only availability/lookups and source copy; retain current filtering, special cases, cleanup, and threaded menu behavior.

- [x] **Step 4: Bump runtime revision to 36**

- [x] **Step 5: Verify GREEN**

Run: `python3 tests/test_native_special_choice_contract.py`
Expected: `native_special_choice_contract_ok`.

- [x] **Step 6: Commit**

`git commit -m "fix: use native special choice data sources"`

### Task 3: Put native three-choice entries inside each source group

**Files:** `tests/test_native_special_choice_contract.py`, `Sources/Hades2/Hades2Model.swift`, `Sources/Hades2/Hades2View.swift`

**Interfaces:** Consume existing `BoonOption.sourceId`, `BoonOption.nativeChoice`, and raw boons; produce derived special options and one unified special action for UI/hotkey.

- [x] **Step 1: Extend the failing contract**

Require `native-choice:` synthetic ids, kind `native_choice`, no standalone `Button("原生三选一")`, native rows routing to `.openSpecialChoice(source:)`, normal rows routing to `spawnBoon`, and `.spawnSpecial` hotkey using the same route.

- [x] **Step 2: Verify RED**

Run: `python3 tests/test_native_special_choice_contract.py`
Expected: FAIL on the r35 standalone-button behavior.

- [x] **Step 3: Implement the smallest Swift model change**

Derive one synthetic option per distinct supported source and add one lookup/action path. Do not change backend protocol.

- [x] **Step 4: Update the special picker**

Use the derived option list, remove the standalone button, and route the picker action through the unified method.

- [x] **Step 5: Verify GREEN**

Run: `python3 tests/test_native_special_choice_contract.py`
Expected: `native_special_choice_contract_ok`.

- [x] **Step 6: Commit**

`git commit -m "feat: embed native choices in special source lists"`

### Task 4: Full preflight and tester artifact

**Files:** handoff/status docs only after code verification.

- [x] **Step 1: Run targeted contracts**

`python3 tests/test_native_sell_traits_contract.py`
`python3 tests/test_native_special_choice_contract.py`

- [x] **Step 2: Run full automated suites**

`bash Tools/run_linux_checks.sh`
`bash Tools/run_macos_checks.sh`
Expected: both PASS.

- [x] **Step 3: Clean build and verify package**

`rm -rf dist && ./build.sh hades2`
Verify 0.1 / Build 2, one module, runtime 36, arm64, debugger entitlement, strict codesign, clean git tree.

- [ ] **Step 4: Package tester RC**

Create `~/Downloads/MacGamingTrainer-0.1-build2-rc-r36.zip`; run ZIP integrity and record size/SHA256.

- [ ] **Step 5: Update GitHub handoff**

Record exact RC/head/test scope in PR #7 and relevant issues. Keep PR #7 DRAFT. Do not touch PR #10.

- [ ] **Step 6: Hand off only affected manual checks**

Tester verifies:
1. open sell screen, cancel without selling;
2. open sell screen, sell once, then exit;
3. one loot-style native source (Artemis or Athena);
4. one fixed-choice source (Arachne or Narcissus);
5. direct-add still works;
6. Heracles/Moros show no native-choice row.
