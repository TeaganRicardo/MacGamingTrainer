# Tech-debt audit: build tooling, CI and test suite

Source: `main@73697aef`. This was a read-only review. Commands run: `validate_game_module.py --all` (ok), `supported_build.py` (ok), `discover_linux_tests.py` (322 portable tests), `mutation_gate.py --list` with `check_manifest` (28 entries, 0 problems), the `ci_docs_only` / `select_macos_pr_tests` functions called in-process, and git log/diff queries. I did not run `build.sh`, macOS fixtures or CI.

Labels used below:
- **[F]**: confirmed fact, from a file:line reference or a mechanical check I ran.
- **[I]**: inference or judgement.

---

## 0. Executive summary

The **generic build core keeps the module contract**. The following contain no `hades` or `reference_fixture` strings and are driven by `app.json` and the module manifests:
- `build.sh`
- `Tools/module_support.py`, `product_support.py`, `module_inventory.py`
- `generate_game_binding.py`, `validate_game_module.py`, `build_module_native.py`
- `verify_module_build.py`, `write_build_provenance.py`, `verify_build_provenance.py`
- `supported_build.py`, `check_runtime_revision.py`, `summarize_macos_coverage.py`
- `direct-release.yml`

There is also **no drift**: every path and test named in the selector tables exists (details in finding 3).

The debt sits around that core:

1. **CI workflows and checks with Hades names written in.** Two workflows hard-code Hades module IDs and resource filenames. A Hades II test forbids adding `hades2` to the isolated build matrix. As a result the Hades II isolated diagnostic build has not run in CI since #184.
2. **Hand-maintained routing tables that grow with every change.** The macOS PR test selector started on 2026-10-28 as about six convention rules. Three weeks later it has:
   - 97 exact-path entries (36 of them Hades-specific);
   - a 151-edge dependency JSON that a test already derives automatically from imports;
   - a Core-UI-to-Hades-tests mapping, so a third module gets no coverage when Core UI changes.

   In the last 30 days, 29% of merged PRs (37 of 127) edited these tables.
3. **Tests that pin source text.** About 2,245 assertions check that a literal string is (or is not) in a file, across 216 of 365 test files. 58 of the 91 merged PRs that touched production code in the last 30 days also had to edit a test that mostly pins source text. These tests pin `Sources/Core` Swift lines, `build.sh` lines and individual Swift file layout, which taxes exactly the refactors the owner wants.
4. **Gates that outgrew their purpose.**
   - Mutation-gate text anchors are checked on every PR, although the docs call mutation testing a convergence audit.
   - The gate keeps unused "equivalent mutant" evidence machinery.
   - Governance tooling totals about 8.2k lines (code plus tests).
   - A stale x86_64 Time Warp slice is still compiled for a consumer that no longer uses it.

---

## 1. What adding a third module touches today (contract vs reality)

The contract (GAME_MODULES.md:19) says: "Ordinary module additions require no edits to `Sources/Core/**`, `Sources/App.swift`, `Backend/core/**`, or `build.sh`." That holds [F]. These shared files outside the module's own directories are also touched:

| Shared file | When needed | Kind | Finding |
|---|---|---|---|
| `app.json` | always | contract | n/a |
| `Tools/macos_only_tests.txt` | always (the selector raises `ValueError` if no module smoke entry exists, `select_macos_pr_tests.py:304-307`) | hand-maintained | F5 |
| `Tools/macos_test_dependencies.json` | each native test with helpers | hand-maintained, derivable | F4 |
| `tests/fixture_budgets/<id>.py` | each native journey (unknown journey fails closed) | hand-tuned from hosted runs | F13 |
| `Tools/select_macos_pr_tests.py` tuples | only if the module's journeys should run on Core changes; silent otherwise | hand-maintained | F3 |
| `.github/workflows/module-build-matrix.yml` | isolated diagnostic build; the isolation step is Hades II-specific | hardcoded | F1 |
| `.github/workflows/build2-macos.yml` | the package check lists Hades files only | hardcoded | F2 |
| `tests/test_cross_game_isolation.py` | to protect Core from the new module's vocabulary | hand list | F8 |
| `tests/test_app_identity_contract.py` | **breaks** if the module declares `supportedBuild`: the fixture copies only `docs/reference/hades{,2}` (lines 15-16), and `supported_build.py:91` requires that `referenceDirectory` exists | hardcoded | F2b |
| Both workflows plus `select_macos_pr_tests.py:324` | if the module needs a non-Lua-5.2 test toolchain | hardcoded | F14 |
| `Tools/generate_<id>_*.py` | per-game generators have no module-owned home | ownership | F15 |

---

## 2. Findings

### F1. Module build matrix hard-codes Hades; Hades II isolated build is forbidden and never runs
- **Category:** hardcoded-module, stopgap that became a constraint. **Severity: high.**
- **Evidence [F]:**
  - `module-build-matrix.yml:67-69`: `game: [reference_fixture, hades]`.
  - The isolation step at `:118-120` asserts that Hades II resource names are absent (`test ! -e ".../hades2.zh-CN.json"`, `ui_terminology.json`, `hades2.en.json`). Hades II itself could never pass this step.
  - `tests/test_hades2_terminology_packaging.py:108`: `assert "- hades2" not in module_matrix`. A game-owned test forbids adding a module to shared CI.
  - `tests/test_ci_workflow_contract.py:133`: `assert 'hades' in games`.
  - History: `hades2` was removed in #184 (`145172b4`, "remove duplicate Hades build"), and `hades` was added in #657.
  - `./build.sh hades2` (the isolated diagnostic) has no CI execution at all. Build 2 only builds `--all`.
- **Why it raises cost:**
  - A third module must hand-edit the matrix.
  - The absence checks don't generalize: each module would need to assert that every other module's resources are absent.
  - The diagnostic route for the reference implementation can rot unnoticed.
- **Remediation (M):**
  - The scope job emits a JSON matrix from `app.json` plus `reference_fixture`; the build job uses `strategy.matrix.game: ${{ fromJSON(needs.scope.outputs.games) }}`.
  - Move the resource presence/absence checks into `verify_module_build.py`: the expected `appResources` destinations are derived from the selection, and destinations owned by modules outside the selection must be absent.
  - Delete the workflow `test ! -e` lines and the test pins.
  - Keep PRs to `reference_fixture` only, as today.
- **Verify:**
  - A unit test of `verify_module_build` against a synthetic app that has a foreign resource.
  - One `workflow_dispatch` of the matrix covering hades, hades2 and reference_fixture.

### F2. Build 2 package check lists Hades files; packaged resources are not verified generically
- **Category:** hardcoded-module. **Severity: medium.**
- **Evidence [F]:**
  - `build2-macos.yml:234-238` hard-codes `games/hades2/module.json`, `ui_terminology.json`, `hades2.zh-CN.json`, `hades2.en.json` and `games/hades/module.json`.
  - These lines are pinned by `test_hades2_terminology_packaging.py:103-106`.
  - `verify_module_build.py:60-113` checks manifests, the Python runtime, the debugger directory and native libraries, but **not `appResources`**. That gap is why the YAML lines exist.
- **Why it raises cost:** a third module's packaged resources are unverified unless someone edits shared YAML and a Hades II test.
- **Remediation (S):** same owner move as F1: `verify_module_build` asserts that every declared `appResources.destination` exists. Then delete the YAML lines and the test pins.

### F2b. A portable test fixture copies only the two Hades reference directories
- **Category:** hardcoded-module. **Severity: medium.**
- **Evidence:**
  - [F] `tests/test_app_identity_contract.py:15-16` copies `'docs/reference/hades', 'docs/reference/hades2'` and then runs `product_support.py all`.
  - [F] `supported_build.py:91` rejects a `referenceDirectory` that is not a directory, and `module_support.py:153` calls it.
  - [I] Therefore a third module with `supportedBuild` and `docs/reference/<id>/` turns this Linux test red.
- **Remediation (S):** copy each module's declared `referenceDirectory` (read through `supported_build`), or copy `docs/reference` whole.

### F3. The macOS PR selector became a growing hand-maintained mapping biased toward Hades
- **Category:** hand-maintained-table, stopgap that became a constraint. **Severity: high.**
- **Evidence [F]:**
  - At creation (`5a369d07`, 2026-10-28) the selector had zero exact-path entries: `SHARED_SMOKE`, a few `if` rules, and the per-module convention.
  - Now (`Tools/select_macos_pr_tests.py:22-206`) it has:
    - 97 `EXACT_PATH_TESTS` keys, of which 36 are Hades-specific;
    - 5 `PREFIX_TESTS`;
    - 6 named tuples;
    - a deferral table (`:222-235`).
  - The docstring (`:4`) still says "Only a few shared ownership boundaries are mapped here".
  - `_CORE_SHARED_UI_TESTS = ("test_hades_frontend.py", "test_hades2_view_state_flow.py")` (`:35`). 29 of the 47 mapped `Sources/Core` files route to Hades-named tests.
  - The Hades II entry in that tuple is in `PR_DEFERRED`. In practice, a Core UI PR gets rendered coverage only from Hades I. Example, from running the selector: `Sources/Core/UI/TrainerShell.swift` selects `test_global_hotkey_routing`, `test_hades_frontend`, `test_multi_game_context_state` and `test_reference_fixture_session_integration`, and defers `test_hades2_view_state_flow` and `test_multi_game_contexts`.
  - Of 73 Core Swift files, 47 have exact entries. Of 30 Hades2 files, 25 are mapped; of 13 Hades files, 7.
  - Churn: 14 commits to the selector in its 3-week life. 37 of 127 first-parent merges in the last 30 days touched the selector, the inventory, the dependency JSON, the fixture budgets, or their contract tests.
  - Drift check (mechanical): **0 missing**. All 97 keys and the 5 prefixes exist; every referenced test is in the inventory and on disk; no inventory test is unreachable.
- **Why it raises cost:**
  - A table entry is needed per Swift file. Changes to that file are covered only if someone remembers to add it.
  - A third module's journeys never run on Core changes unless it edits shared tuples.
  - Growth is roughly O(files × modules).
- **Simpler rule [I]:** derive consumers from what each native harness compiles.
  - `tests/swift_test_compiler.py` already hashes "every support file" for its cache key. Record that list (or the harness's source set) as the test's source inputs.
  - Selection becomes: tests whose compiled sources or imported helpers intersect the diff, plus a rule that a Core change selects each `app.json` module's stable smoke entry by naming convention.
  - Exact entries remain only for genuinely non-compiled relationships (for example `build.sh` and `Native/` to `BUILD_SMOKE`).
- **Remediation (M–L):** implement the derived selector next to the current one. Replay the last 30 days of PR diffs through both, require new ⊇ old on real consumers, compare the selected counts, then delete `EXACT_PATH_TESTS` and the tuples.

### F4. `macos_test_dependencies.json` (151 edges) duplicates a derivation the suite already performs
- **Category:** hand-maintained-table, test-the-copy. **Severity: high** (cheap win).
- **Evidence:**
  - [F] `tests/test_macos_test_dependency_inventory.py:1-7` derives each consumer's helpers from source (AST imports and path literals) and checks the JSON against that.
  - [F] My own static import scan: **0 undeclared** test-helper imports. 6 declared edges are not statically imported; they are path-loaded fixtures such as `tests/fixtures/hades2/save_editor_player_journey.py`.
  - [F] The runbook still tells module authors to hand-declare (`add-a-game-module.md:40`): "Declare every imported or executed Python/data helper ... including indirect helpers."
  - [F] The test keeps another hand allowlist, `PORTABLE_BACKEND_FIXTURES` (`:31-46`), containing 6 hades2 Backend files.
  - [F] 17 commits to the JSON in 30 days.
- **Remediation (S–M):**
  - Move the derivation into `Tools/` (for example `module_inventory` or a new `test_inputs.py`) and have `ci_docs_only` and `select_macos_pr_tests` consume it directly.
  - Keep an explicit list only for path-loaded data files, or mark them in-file.
  - Delete the JSON, `metadata_test_changes` for the JSON, and the parity test. Update the runbook.
- **Verify:** derived graph ⊇ current JSON edges. `test_ci_pr_macos_selection.py` regressions (room-picker, save-editor helpers) still pass.

### F5. The `macos_only_tests.txt` inventory is a separate hand list
- **Category:** hand-maintained-table. **Severity: medium-low.**
- **Evidence [F]:**
  - 43 entries; 40 commits historically, 16 in 30 days.
  - Linux discovery excludes by this list (`discover_linux_tests.py:12-22`). The selector diffs it against the merge-base (`select_macos_pr_tests.py:249-264`) only because it lives apart from the tests.
  - No drift: all 43 files exist, and `run_linux_checks.sh:48-58` enforces that.
- **Remediation (S–M):** declare the platform in-file (for example a module constant `MGT_PLATFORM = "macos"` read via AST, or a `tests/macos/` directory). Discovery and selection derive the list. The metadata-delta code disappears.

### F6. Source-text "contract" tests are a large share of the suite and a measurable tax
- **Category:** implementation-pinning-test. **Severity: high.**
- **Evidence:**
  - [F] Counts across 365 test files:
    - 1,652 `assert '<literal>' in <var>`;
    - 536 `assert '<literal>' not in <var>` (retired-string "tombstones");
    - 57 `assertIn`/`assertNotIn` with a literal;
    - total about 2,245 of about 10,148 assertions (about 22%), in 216 files.
  - [F] File-reading tests: 99 read Swift text, 70 read `Sources/Core`, 69 reference `runtime/hades.lua`, 13 read `build.sh`, 13 read workflow YAML.
  - [I] Heuristic classification (a file reads repo source and asserts literals): 36 files source-text-only and 36 source-text-dominant, about 12.3k lines in total (about 14% of test lines); 67 mixed.
  - [F] **Tax:** 58 of 91 production-touching first-parent merges in the last 30 days edited at least one of those 72 files.
  - [F] Most-edited (commits in 30 days):
    - `test_ui_consistency_contract.py`: 26
    - `test_hades2_feature_contracts.py`: 19
    - `test_cross_game_ui_semantics.py`: 16
- **Examples that break on a harmless refactor [F]:**
  - `test_ui_consistency_contract.py:30`: `assert "shortcutBadgeMinimumWidth: 52" in theme`.
  - `test_ui_consistency_contract.py:89`: `primary_button.count("TrainerActionButtonLabel(title: title, fillsWidth: widthRole != .sheet && (widthRole != .automatic || inheritedRowWidth != nil))") == 2`. Any reformat or rename breaks it.
  - `test_hades2_feature_contracts.py:35-37`: exact Swift statements such as `'let primaryName = localization.language == .en && !resource.englishName.isEmpty'`.
  - `test_hades2_feature_contracts.py:48-50`: the comment "#763: ... check the owner shape instead of the retired only-eligible one-line literal". The latest PR had to rewrite the pin.
  - `test_ui_component_boundary_v0175.py:52-56` pins theme property names in `Hades2SaveEditorView.swift`.
  - `test_native_special_choice_contract.py:81-99` pins model and view method signatures and call sites.
- **Contradiction [F]:** `ENGINEERING_INVARIANTS.md:207` says source-text contracts are acceptable only "where they enforce a structural boundary that cannot reasonably be compiled/observed". Theme widths and Swift call shapes are compilable and observable through the existing `swift_test_compiler` harnesses.
- **Remediation (L, incremental):** triage into three buckets.
  - **Keep:** genuine structural boundaries, ideally derived (see F8).
  - **Convert:** compile the value and assert behaviour, using the existing cached harness.
  - **Delete:** negative tombstones guarding retired strings.

  Start with the files listed in F7. Track two numbers (literal-assert count and the PR co-change rate) instead of adding a new gate.

### F7. Source-text and file-layout pins that would block the likely refactors
- **Category:** implementation-pinning-test. **Severity: high** (for the planned refactor).
- **Core UI / Host (Swift) [F]:**
  - `test_ui_consistency_contract.py`: 194 literal asserts over 13 Core and Hades files.
  - `test_cross_game_ui_semantics.py`: 141 asserts over 9 Core/Hades paths.
  - `test_save_editor_shell_parity.py`: 50.
  - `test_sidebar_room_picker_regressions.py`: 46.
  - `test_ui_postpolish_regressions.py`, `test_picker_action_sizing.py`, `test_mapped_slider_contract.py`, `test_hotkey_feedback_contract.py`.
  - The `test_core_save_*_round20/21/22/23` UI-style pins.
  - `test_host_shared_localization_coverage.py:487-498`, which reads `Backend/core/protocol.py`, `server.py` and `process_time_warp.py` text.
- **`build.sh` → Python refactor [F]:**
  - `test_cross_game_isolation.py:52-58`: `'SWIFT_SOURCES=("$ROOT/Sources/App.swift")' in build`.
  - `test_process_time_warp_native_contract.py:33-48`: 12 `build.sh` lines, including the stale x86_64 slice.
  - `test_build_signing_scope.py:106-111` slices `build.sh` at text markers `\nDIST=` and `\nTIME_WARP_ROOT=` and executes the tail under fake tools.
  - `test_host_localization_contract.py:19-21`.
  - `test_picker_presentation_contract.py:58-59`.
  - `test_build_preflight.py:136,214`.
- **Swift file layout [F]:** 45 test files call `swiftc` directly and hand-pick individual `Sources` files; 24 use `swift_test_compiler`.
  - Most-pinned files: `Core/Runtime/TrainerJSON.swift` (14 tests), `BackendProcess.swift` (10), `BackendClient.swift` (4), `TrainerSaveEditorReplyCoordinator.swift` (3).
  - Example: `test_host_connection_policy_dev8.py:348-352` compiles exactly `Sources/Core/Host/TrainerConnectionPolicy.swift`.
  - Moving a type between files breaks compilation of these harnesses.
- **Mutation anchors:** see F11.
- **Remediation (M):**
  - Before the refactor, migrate the direct-`swiftc` tests to `swift_test_compiler` with a directory-level support set (all of `Sources/Core`).
  - Convert or delete the Core-UI and `build.sh` pins first.
  - Expect a large one-time edit; don't re-pin the new shape.

### F8. Cross-game isolation guard only knows Hades II
- **Category:** implementation-pinning-test, hardcoded-module. **Severity: medium.**
- **Evidence [F]:**
  - `test_cross_game_isolation.py:19-32` forbids `'Hades2', 'Hades II', 'games.hades2', 'Hades2Adapter', 'CurrentRun', ...` in shared paths.
  - Hades I identifiers (`games.hades`, `HadesGameModule`) are not checked, and a third module's would not be either.
  - The same file pins `build.sh` text (`:52-58`).
  - It is listed as a canonical protection in `ENGINEERING_INVARIANTS.md:197`.
  - This is the "single-game gate wearing a generic name" anti-pattern that `check_runtime_revision.py:5-9` says was already fixed there.
  - A registry-derived Host check already exists (`test_host_shared_localization_coverage.py`; mutation `core-registry-vocabulary-leak` says "replaces a hand-maintained Core vocabulary sample with registry-derived coverage"). The two mechanisms overlap.
- **Remediation (S):**
  - Derive forbidden tokens for every `app.json` module: `id`, `games.<id>`, `frontend.moduleType`, the source directory name, plus registry terms.
  - Replace the `build.sh` text checks with a check that `product_support` reports the source set as App.swift + Core + the manifest directories.

### F9. Stale x86_64 Time Warp slice, plus a second native build path in `build.sh`
- **Category:** build-script, stopgap that became a constraint. **Severity: medium.**
- **Evidence [F]:**
  - `build.sh:428-433` always adds `x86_64` to `libMGTTimeWarp` ("Package x86_64 alongside the requested Host slices for Intel targets"). This was introduced in `65a739c2` ("WIP(hades): native game speed transport", #571).
  - Hades I no longer uses Core Process Time Warp (`PROJECT_STATUS.md:99`: "The Hades I path no longer ... installs Core's process-clock hook"). `grep` finds no `libMGTTimeWarp` or `process_time_warp` reference under `Backend/games/hades` or `Sources/Hades`.
  - The only consumer is Hades II (arm64), at `Backend/games/hades2/adapter.py:123`.
  - The stale slice is pinned by `test_process_time_warp_native_contract.py:44`.
  - Core native code is compiled by hand-written `clang` in `build.sh:418-465`, while module natives go through `Tools/build_module_native.py`.
- **Remediation (S):** declare Core native helpers in the same native declaration format and build them through `build_module_native.py` with the Host architectures. Drop the forced x86_64 slice and its test pin.
- **Verify:** `lipo -archs` on the packaged dylib; the Hades II Time Warp tests.

### F10. `build.sh` structure: inline Python, schemas duplicated across tools, hard to unit-test
- **Category:** build-script. **Severity: medium.**
- **Evidence [F]:**
  - 578 lines, with **8 inline Python heredocs**:
    - `manifest_field` (`:137-154`, which spawns about 11 interpreters);
    - runtime.json writer (`:261-289`);
    - localization verifier (`:297-307`);
    - appResources copier (`:373-391`);
    - adapter smoke (`:397-416`);
    - `GAME_MODULES.json` (`:474-479`);
    - Info.plist patcher (`:491-514`);
    - entitlements merger (`:535-547`).
  - The `runtime.json` schema is known in 3 places: `build.sh:261-289`, `verify_module_build.py:24-58` and `write_build_provenance.py:188-252`.
  - The `arm64|x86_64` allowlist appears at `build.sh:121-124` and `:174-177`, and in `verify_module_build.py:33`.
  - `en zh-CN` is listed at `:290` and again at `:302`.
  - `clean_signing_metadata` runs at `:462` and `:523`; the dist-symlink check is at `:188` and `:563`.
  - To unit-test packaging, `test_build_signing_scope.py` must slice the script by text and fake `xcrun`, `clang`, `codesign`, `plutil` and `file`.
- **Positive [F]:** no game-specific branches; all module data comes from `product_support.py`.
- **Remediation (M):**
  - Move the packaging stages (stage, resources, runtime metadata, native, plist, entitlements, sign order) into an importable `Tools/package_app.py`.
  - Keep `build.sh` as a thin orchestrator for `swiftc`, `actool` and `codesign` calls.
  - Have `verify_module_build` and provenance import one runtime-metadata function.
- **Verify:** on the same SHA, diff the bundle file tree and plist before and after (ignoring signatures); `verify_module_build all`; provenance verify.

### F11. Mutation gate: per-PR text anchors, unused evidence machinery, weight out of proportion
- **Category:** gate-overhead. **Severity: medium.**
- **Evidence [F]:**
  - `Tools/mutation_gate.py` is 967 lines; `tests/test_mutation_gate_contract.py` is 650; together they cover 28 invariants.
  - Anchors are exact production text: 8 in `Backend/core` (`save_restore.py` ×3, `save_service.py`, `adapter.py` ×3, `protocol.py`), 7 in `Backend/games`, 6 in `Sources/Hades2`, 1 in `Sources/Core/Host/TrainerLocalization.swift`, and 1 each in `write_build_provenance.py` and `publish_module_build.py`.
  - `test_manifest_is_valid` (contract test `:26-29`, which calls `check_manifest` at `mutation_gate.py:674`) runs in the **Linux PR lane**. Editing any anchored line fails PR CI.
  - But `ENGINEERING_INVARIANTS.md:207` says mutation testing is "a periodic/convergence audit, not evidence that must be regenerated for every ordinary feature PR".
  - The full gate runs only on dispatch (`build2-macos.yml:211-213`), and it contributed to raising the dispatch timeout to 60 minutes (`:63-68`).
  - 8 of 127 merges in 30 days edited `mutation_gate.py`.
  - `_is_falsifiable` and `EVIDENCE_DIR` (`mutation_gate.py:117-163`, with symlink-containment and ≥200-character evidence rules) are **unused**: no entry sets `equivalent_reason`, and `docs/audits/mutation-evidence/` does not exist. They are still exercised by `test_mutation_gate_contract.py:369-378`.
- **Remediation (S):**
  - Move anchor validation into the dispatch job, or make it a warning on PRs.
  - Delete the equivalent-evidence machinery until the first real equivalent mutant.
  - Prefer AST or function-scoped anchors over line text.

### F12. Governance machinery outweighs its demonstrated value
- **Category:** gate-overhead. **Severity: medium.**
- **Evidence:**
  - [F] Governance code is about 3,740 lines: mutation gate, runtime revision gate, provenance writer/verifier, toolchain identity, coverage summary, selector, scope classifier, `release_tag`, fixture policy. The tests about them add about 4,500 lines (14 files).
  - [F] `check_runtime_revision.py` hardens against adversarial cases: comment-marker bypass, re-pointed patterns, non-UTF-8 blobs, wrong working directory. At `:233` it says "Review found it: CI happens to run at the root, so it was not exploitable there". The test file is 793 lines.
  - [F] `PROJECT_STATUS.md:128`: the user "rejects unnecessary gates for unlikely hypothetical failures ... do not create a recurring global scan or a new trust system to cover imagined states".
  - [I] Each piece is individually reasonable. Together they create a per-change tax: workflow and selector edits, contract-test edits, fixture budgets. Nearly all of it is single-maintainer self-protection against threat models (gate self-gaming, tampering) that the stated principle de-prioritizes.
- **Remediation (S, policy):**
  - Freeze governance growth: no new gate code without an escaped defect.
  - Delete unused branches (F11) and tombstone tests (F6).
  - Prefer moving checks to dispatch over adding PR checks.

### F13. Toolchain and runner literals duplicated despite the "centralized" claim; budgets tied to one runner
- **Category:** hand-maintained-table, docs. **Severity: medium-low.**
- **Evidence [F]:**
  - `macos-26` and `Xcode_26.6` appear in:
    - `build2-macos.yml:62,75-76`;
    - `module-build-matrix.yml:19-20,54,62-63` (env declared twice in one file);
    - `Tools/macos_toolchain_identity.py:12-17`;
    - `tests/macos_fixture_policy.py:29`.
  - `GAME_MODULES.md:35` says "macOS build/native-test selection is centralized in `Tools/macos_toolchain_identity.py`". In reality it is verified there and declared in 3 other files.
  - Python `3.15.0` is set in 6 workflow `setup-python` steps plus `python_runtime.json`, and a test checks the copies agree (`test_ci_workflow_contract.py:202-203`). That is the "test the copy" pattern `AGENTS.md` warns against.
  - Fixture budgets are hand-derived from observed hosted runs on that profile (`tests/fixture_budgets/hades.py:5-18`). Unknown profiles and journeys fail closed.
- **Why it raises cost:**
  - A new native journey must ship a budget before its first CI run.
  - A runner or Xcode bump touches about 5 files plus re-deriving every budget.
- **Remediation (S):**
  - The scope job reads one JSON (or `macos_toolchain_identity.py --print`) and exports the runner label and `DEVELOPER_DIR`.
  - Use `setup-python`'s `python-version-file`.
  - The fixture policy imports the profile constant.
  - Give a new journey a documented provisional budget (for example the existing local floor), to be tightened after observations.

### F14. Hades's Lua 5.2 test dependency is built into shared CI and the generic selector
- **Category:** hardcoded-module. **Severity: medium.**
- **Evidence [F]:**
  - `linux-contracts.yml:51-53` installs `lua5.2 liblua5.2-dev` unconditionally.
  - `build2-macos.yml:140-188` builds Lua 5.2.4 from source (3 mirrors).
  - The generic selector emits a Hades-specific key: `"requirements": {"lua52_native": ...}` (`select_macos_pr_tests.py:324-327`), consumed at `build2-macos.yml:136,141,149`.
- **Why:** a module with a different runtime test toolchain (another Lua, Mono, a JS engine) must edit the shared selector and both workflows.
- **Remediation (M):** native tests or the module manifest declare named prerequisites; the selector emits a generic `prerequisites` set; the workflow has one installer step per named prerequisite under `Tools/ci_prerequisites/<name>.sh`.

### F15. Per-game generators and profilers live in shared `Tools/` and force full macOS builds
- **Category:** hardcoded-module (ownership). **Severity: low-medium.**
- **Evidence [F]:**
  - Game-specific tools in `Tools/`: 7 `generate_hades*_*.py` and 2 Hades II profilers, about 2,040 lines, roughly 25% of `Tools/`.
  - They are **not** wired into `build.sh` (confirmed). Tests regenerate and compare them, for example `test_hades2_command_binding.py`.
  - `ci_docs_only.py:139-175` treats any `Tools/*.py` not listed in `PORTABLE_TOOL_PATHS` (`:22-30`) as a product build input. Calling `classify_scope(['Tools/generate_hades_catalog.py'])` returns `needs_full_build=True`. A one-off prefix exception exists for `Tools/profile_`.
  - `Tools/mutation_gate.py` and any new tool also trigger the full signed macOS build.
- **Remediation (S):** convention `Backend/games/<id>/tools/` (or `Tools/games/<id>/`), classified as portable module tooling. Invert `PORTABLE_TOOL_PATHS` into an explicit list of build-input tools.

### F16. Publish keeps a one-time legacy migration hard-coded to `('hades2', 'hades')`
- **Category:** hardcoded-module, stopgap. **Severity: low.**
- **Evidence [F]:**
  - `publish_module_build.py:78-88`: `_is_legacy_unified_product` requires `previous == 'hades2'` and `source_modules == ('hades2', 'hades')`. It was added in #693 (`3bc51b0c`).
  - It becomes dead the moment `app.json` changes, and it is safe because it fails closed.
  - The call line is pinned as a mutation anchor (`mutation_gate.py:372`).
- **Remediation (S):** delete it (`dist/` is local output) and move the anchor.

### F17. Key native journeys run only at release convergence
- **Category:** gate-overhead, stopgap that became a constraint. **Severity: medium.**
- **Evidence [F]:**
  - `PR_DEFERRED` (`select_macos_pr_tests.py:222-235`, added in #668 for flaky foreground activation) defers `test_hades2_view_state_flow`, `test_multi_game_contexts` and `test_runtime_text_edit_completion`.
  - These run only on `workflow_dispatch`. The last successful dispatch was `ee0f46d1` (2026-11-15); 9 first-parent merges have landed on main since.
  - Core-UI PRs get rendered coverage only from Hades I's journey (F3).
- **Why [I]:** a third module's rendered journey will likely be deferred too, so regressions in shared UI surface late and in batches.
- **Remediation (S):** a scheduled nightly `workflow_dispatch`-equivalent on `main` (no new gate, only earlier signal). Separately, investigate the foreground-activation root cause.

### F18. Historical round/version test names
- **Category:** test debt. **Severity: low.**
- **Evidence [F]:**
  - 37 files named `*_dev7/_dev8`, `*_round12..24`, `*_v0175..v0190` or `*_u01_u02`.
  - 6 are referenced elsewhere:
    - `ENGINEERING_INVARIANTS.md:191,192` names `*_dev8` as canonical protections;
    - the three `test_core_save_*_round20/24/u01_u02` appear in 4 tooling files each;
    - `test_protocol_fixtures_v0180.py` is a mutation target.
  - `AGENTS.md` permits keeping old names.
- **Remediation (S):** rename the 6 referenced files together with their table entries (or after F3–F5 remove the tables), and rename others opportunistically. Names matter more once selection derives from ownership.

### F19. "Shared" tests are coupled to Hades content; giant files
- **Category:** test debt. **Severity: low-medium.**
- **Evidence [F]:**
  - 98 of the 166 test files without a game prefix reference Hades. For example, `test_ui_consistency_contract.py` and `test_cross_game_ui_semantics.py` read Hades2/Hades views.
  - Largest files: `test_hades_frontend.py` 2,336; `test_hades_runtime.py` 2,270; `test_hades2_save_editor_frontend.py` 2,214; `test_hades2_live_trait_management.py` 1,972.
  - Split by owner: hades2 has 159 files and 41.9k lines; hades 40 files and 13.4k; other 166 files and 31.4k.
- **Why:** shared-contract checks don't extend to a third module, and Hades refactors break "shared" tests.
- **Remediation:** while doing F6, parametrize genuinely shared UI checks over the `app.json` modules (for example using the reference fixture), and move Hades-specific assertions into Hades-owned files.

### F20. Docs that mislead a module author
- **Category:** docs. **Severity: medium.**
- **Evidence [F]:**
  - `GAME_MODULES.md:55-56` ("both Hades II and the fixture ... build/codesign succeeds for both modules") and `:35` ("both isolated module builds run on exact-SHA release dispatch"). In fact the isolated builds are the fixture and Hades I; Hades II isolated is never built (F1). `AGENTS.md:57` "isolated Hades diagnostics" is ambiguous.
  - `AGENTS.md:55` and `VERSIONING.md:85` describe the resident-revision gate as `Backend/games/hades2/runtime/hades.lua` / "Hades II resident runtime revision". It is manifest-driven and also gates Hades I `runtime.lua` (`Backend/games/hades/module.json` declares `residentRuntime`). An author would read it as Hades II-only.
  - `add-a-game-module.md:40` tells authors to hand-maintain the derivable dependency JSON (F4). The `select_macos_pr_tests.py:4` docstring is stale (F3).
  - The PR routing policy is restated in 4 prose places plus code: `AGENTS.md:57`, `GAME_MODULES.md:35`, `add-a-game-module.md:69-73`, `PROJECT_STATUS.md:124`; the code owner is `ci_docs_only.py`. This breaks the project's one-source-per-fact rule.
  - `GAME_MODULES.md`'s "Version ownership" section (`:27-41`) mixes Action pinning, provenance and runner policy into the module contract.
  - The `GAME_MODULES.md:19` contract lists what need not change but not the shared files that *do* (section 1 table above).
  - `GAME_MODULES.md:35` "centralized" toolchain claim (F13). `ENGINEERING_INVARIANTS.md:207` vs suite reality (F6).
  - Positive: every repo path and test name cited in AGENTS, GAME_MODULES, VERSIONING, ENGINEERING_INVARIANTS, PROJECT_STATUS and the two runbooks resolves.
- **Remediation (S):**
  - Correct the isolated-build and resident-gate statements.
  - Make `add-a-game-module.md` the single checklist, including the real shared touch list.
  - Replace routing prose with a pointer to `ci_docs_only.py` and its test.
  - Move CI/provenance policy out of `GAME_MODULES.md` into a CI doc.

### F21. Every Core Swift edit triggers a full linked+signed reference-fixture build
- **Category:** gate-overhead. **Severity: low.**
- **Evidence [F]:**
  - `ci_docs_only.py:50-54` puts `Sources/Core/` in `MODULE_PREFIXES`. `classify_scope(['Sources/Core/UI/TrainerTheme.swift'])` returns `needs_module=True` and `needs_full_build=False`.
  - Build 2 deliberately uses typecheck for this change, while the module matrix runs `./build.sh reference_fixture` (full link and sign).
  - 43 of 127 merges in 30 days touched `Sources/Core`.
- **Remediation (S) [I]:** for Swift-only Core diffs, run the reference fixture in `--typecheck` mode. Keep the full fixture build for manifest, tool and native changes.

### F22. Inconsistent workflow-contract testing style
- **Category:** implementation-pinning-test. **Severity: low.**
- **Evidence [F]:**
  - `test_ci_workflow_contract.py:1-8` promises "Rules read a parsed step model, never incidental line text", via a hand-rolled YAML subset parser (`:22-70`).
  - Other tests assert 33 incidental workflow lines: `test_product_version_contract.py` 19 (for example `'test "$build" = "$expected_build"' in workflow`), `test_test_suite_discovery.py` 4 (including tombstones like `'chmod +x build.sh Tools/*.py' not in workflow`), `test_runtime_revision_gate.py` 4, `test_release_version_identity.py` 3, `test_macos_coverage_summary.py` 3.
  - Plus the Hades II test pins in F1 and F2.
- **Remediation (S):** consolidate workflow assertions into the parsed-model test and delete line-text and tombstone assertions.

---

## 3. Verified non-issues (don't spend effort here)
- **No table drift.**
  - All 97 `EXACT_PATH_TESTS` keys and the 5 prefixes exist.
  - All referenced tests are in the inventory and on disk; no inventory test is unreachable.
  - All 151 dependency edges point to existing paths, with 0 undeclared static imports.
  - All 28 mutation anchors are valid and unique.
- **No silently skipped tests.** Every function-style test file calls each `def test_` it defines, and every unittest file calls a runner.
- **Shared Tools contain no game names:** `write/verify_build_provenance.py`, `module_support.py`, `product_support.py`, `module_inventory.py`, `supported_build.py`, `generate_game_binding.py`, `validate_game_module.py`, `build_module_native.py`, `verify_module_build.py`, `summarize_macos_coverage.py`, `macos_toolchain_identity.py`.
- **`check_runtime_revision.py` reads its declarations from the manifests.** One limit: `strip_lua_comments` is applied to every declared runtime, so a non-Lua resident runtime would need a per-language comment rule. That is fine until such a module exists.
- **`direct-release.yml` reads the module list from `app.json`** (`:61-70`).
- **`appResources` destination collisions across modules are rejected** (`product_support.py:35-45`). Destinations share one flat namespace (`ui_terminology.json` is a generic name), so a `<id>/` prefix convention for new modules would be wise.

## 4. Suggested order (cheapest leverage first)
1. **S:** F4 (derive deps), F2 + F1 (move resource checks into `verify_module_build`, generate the matrix from `app.json`), F2b, F8, F16, F9, F20 doc corrections. Together these remove most edits to shared files when adding a module.
2. **S:** F11 (anchor check to dispatch, delete dead evidence code), F17 (nightly convergence), F13 (single toolchain source), F15 (module tool home).
3. **M:** F3 (derived selector, replayed against 30 days of diffs), F5 (in-file platform marker), F14 (generic prerequisites).
4. **M–L, before the Core refactor:** F7 then F6 (migrate the 45 direct-`swiftc` tests; convert or delete the Core-UI and `build.sh` pins), then F10 (`build.sh` packaging to Python).

Metrics to watch, without adding a gate:
- share of PRs touching selection tables (now 29%);
- share of production PRs editing source-text tests (now 58 of 91);
- literal-assert count (now about 2,245).
