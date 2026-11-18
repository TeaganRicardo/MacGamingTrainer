# Pre-module technical-debt review and remediation plan

Source: `main@73697aef` (2026-11-18). Read-only review; no production code changed.

Live tracking: [#766](https://github.com/TeaganRicardo/MacGamingTrainer/issues/766) (umbrella and owner decisions) and one issue per phase, #767–#774. Those issues own current scope; this folder is the 2026-11-18 evidence snapshot.

Purpose: before more game modules are added, find what a new module would have to copy, work around or edit in shared code, and order the fixes so later work gets cheaper rather than more expensive.

Evidence (each finding has file:line citations and is labelled fact or inference):

| Prefix | Report | Scope |
| --- | --- | --- |
| `S-` | [swift-frontend.md](swift-frontend.md) | `Sources/App.swift`, `Sources/Core/**`, `Sources/Hades/**`, `Sources/Hades2/**`, fixture frontend |
| `B-` | [python-backend.md](python-backend.md) | `Backend/core`, `Backend/debugger`, both game backends, resident Lua structure |
| `T-` | [build-ci-tests.md](build-ci-tests.md) | `build.sh`, `Tools/**`, workflows, `tests/**`, docs |
| `M-` | this file | Cross-cutting checks done during synthesis |

Findings marked ✔ below were re-checked against source during synthesis. Inferences that need reproduction are marked ⚠.

---

## 1. Verdict

The contract in `GAME_MODULES.md` holds for the files it names: no Hades literals in `Backend/core`, `Sources/Core`, `build.sh` or the generic Tools, and the routing tables have not drifted. The debt sits in four places:

1. **The Host does not own the module lifecycle.** Starting the backend, mirroring its status, opening the log session, choosing the hotkey scope, feedback, diagnostics and registering text lookups are all done inside each module, and each module does them differently. The Host then reads lifecycle facts back through the module. One result is a confirmed defect (§2).
2. **Two real adapters now exist, but shared mechanisms were never extracted.** The 2026-09-21 audit correctly refused to share code while only Hades II existed. Hades I arrived on 2026-10-25. Since then, fixes have landed in both games in the same commit, and Hades I has had 12 transport-only fixes that repeat lessons Hades II had already learned. Mechanisms written twice: Save Editor session/workspace (identical `save_edit.py`), LLDB attach/detach state machine, profile/preference storage, diagnostics, shortcut store, Save Editor client, draft sync, feedback/menu/sidebar plumbing.
3. **Single-game stopgaps became constraints.** Hades II declares unprefixed global Swift types (`TrainerProfile`, `ShortcutAction`, …) in a product that compiles as one Swift module. It also uses unprefixed `shortcut.*` UserDefaults keys and keeps its data at the root of `MacGamingTrainer/`, with a hard-coded Steam install path. Core holds Hades II shortcut-migration helpers. `build.sh` always builds a Time Warp helper (including an x86_64 slice) that only Hades II uses. The isolation test bans only Hades II words from Core.
4. **The test suite taxes every refactor.** About 2,245 assertions (≈22%) check literal source text. 58 of the last 91 production merges also had to edit one of those tests. 45 tests compile hand-picked Swift files, so moving a type between files breaks them. The macOS test selector has grown to 97 hand-written path entries. This must be paid down **first**, or the refactors in items 1–3 each pay it again.

Healthy, no action needed: the Core Save transaction stack, `core/sidecar.py`/`framing.py`, the manifest-driven revision gate, the generated module catalog, neutral Core UI primitives (stat/resource/feature controls, Save Editor shell), event-driven target monitoring, and manifest-driven `direct-release.yml`.

## 2. Confirmed defects (fix independently of the refactor)

| ID | Defect | Status |
| --- | --- | --- |
| S-F1 ✔ | **Hades I "Restart Backend" button is disabled exactly when it is shown, and automatic backend restart never fires for Hades I.** `TrainerConnectionStatusCard` switches the primary button to "Restart Backend" when `!backendAvailable` but enables it with `actionsEnabled` (`TrainerStatusControls.swift:35-52`). Hades I defines `hostActionsEnabled = backendAvailable && protocolCompatible && !busy` (`HadesModule.swift:86-87`). `consumeAutomaticBackendRestartIfEligible` returns early when the backend is available and otherwise requires `actionsEnabled` (`TrainerConnectionPolicy.swift:143-158`). The reference fixture teaches the same broken definition. Hades II is affected only after a worker dies mid-request (unknown outcome), because its gate includes `!requiresTargetRestart`; see PR #776. | Source-confirmed. Needs a RED model test first. |
| B-F8 ✔ | Hades II's Lua budget constants (`operation_budgets.py:17-19`) are used only by a test; production hard-codes `+3`/`2.0` (`transport.py:133,292,342,488,491,581`; `native_mailbox.py:138,142`). `scan` (15 s Host budget) can run `dwarfdump` (30 s) plus `pgrep` (5 s); `launch` (10 s) runs `open` plus `scan`. ⚠ A slow `xcrun` would make a read-only `scan` terminal for the backend. | Source-confirmed; the timeout outcome is inferred. |
| B-F9 ✔⚠ | Hades II hard-codes `~/Library/Application Support/Steam/steamapps/common/Hades II/Hades II.app` (`config.py:39,50`). `scan()`/`connect` fail if reading compatibility data there fails. ⚠ An install in another Steam library folder is likely unable to connect. | Path confirmed; failure not reproduced. |
| B-F1 ✔⚠ | Only Hades II sends `SIGCONT` after detach (`hades2/transport.py:614`). ⚠ Either Hades I can leave the game stopped after detach, or Hades II has an unexplained step. | Asymmetry confirmed; impact unknown. |
| S-F13 ✔ | Hades II's "activation pending" is a 0.9 s timer (`Hades2Model.swift:1128-1138`), not request-scoped as in Hades I. The shared phase flips to "mismatch" after a fixed delay regardless of outcome. | Source-confirmed. |
| B-F5 ⚠ | Save Editor workspaces are never evicted; each holds a decoded save until an explicit close. | Inferred memory growth. |

## 3. Cross-cutting findings from synthesis

- **M-1 No compiler-enforced module boundary ✔.** `build.sh:338-349` compiles App, Core and every game in one `swiftc` call. The rule that Core knows no game is enforced by a word list (`tests/test_cross_game_isolation.py:19-32`) that contains only Hades II terms. Two games cannot both declare `ShortcutAction` (S-F4). See decision D2.
- **M-2 Three localization mechanisms ✔.** Host uses `Host.strings` with `{0}`. Hades II loads JSON with `{0}` and `{term:…}`. Its production code also falls back to reading `Backend/games/hades2/module.json` from the source tree via `#filePath` (`Hades2Presentation.swift:209-233`) and silently returns `[:]` when nothing is found. Hades I rebuilds a 269-entry dictionary literal on every lookup and uses sequential `%@`. Core offers no loader, so a new module picks one of the three.
- **M-3 Flat resource namespace ✔.** `appResources` destinations land at the root of `Contents/Resources` (`ui_terminology.json`, `hades2.en.json`). Collisions are rejected at build time (`product_support.py:35-45`), but a second game with a terminology file must rename it, and Hades II code assumes the root name.
- **M-4 Process Time Warp has one consumer ✔.** Since #739/#744 only Hades II uses Core Time Warp. `build.sh:418-465` still builds it for every product, including a forced x86_64 slice, by hand-written `clang` rather than `build_module_native.py`. Hades II reaches it through a hard-coded Core path (`hades2/adapter.py:123`). `Backend/debugger/lldb_time_warp.py` calls itself "shared" but has one consumer. A speed control is plausibly common to future trainers, so keep it in Core but make it a declared, opt-in capability.
- **M-5 No static tooling ✔.** No linter, formatter or type checker for Python or Swift. 17 of 704 Hades II backend functions have return annotations. Semicolon-joined statements are common in `hades2/adapter.py` (45 lines) and `transport.py` (23). Swift compiles in Swift 5 mode with no concurrency checking (S-F16). Large refactors therefore rest entirely on tests, and those tests are the brittle part (§1 item 4).
- **M-6 Dead root file ✔.** The repository-root `ACTIVE_GAME_ID` (content `hades2`, from the first commit) is read by nothing; `build.sh:482` writes its own bundle marker.

## 4. What adding a third module touches today

The contract says a module adds `Sources/<Game>/`, `Backend/games/<id>/` and an `app.json` entry. In practice the author must also:

- **Copy, not import:** backend start and status mirroring (S-F2, S-F3), feedback/logs/diagnostics (S-F5, B-F12), management/sidebar/search factories (S-F6), a localization loader (M-2), a shortcut store (S-F12), a draft-sync scheme (S-F10), a Save Editor client and workspace registry (S-F9, B-F5), a profile/preference store (B-F4), process discovery (B-F9), an outcome-unknown mechanism (B-F3), command timeouts and replay classification (S-F8, B-F8), and an LLDB lifecycle if the game is debugger-driven (B-F1, B-F2).
- **Edit shared files:** `Tools/macos_only_tests.txt`, `Tools/macos_test_dependencies.json`, `tests/fixture_budgets/<id>.py`, selector tuples for Core coverage, `module-build-matrix.yml`, the `build2-macos.yml` package check, `tests/test_cross_game_isolation.py`, `tests/test_app_identity_contract.py` (breaks if the module declares `supportedBuild`) and the Lua 5.2 CI steps if its tests need another runtime (T-§1, T-F1–F5, T-F8, T-F14).
- **Avoid hidden collisions:** Hades II global type names and `shortcut.*` keys (S-F4), its data directories at the shared root (B-F4), flat resource names (M-3), and unordered module text-prefix matching (S-F7).

The plan below is done when a realistic template module (WP2.5) needs none of the "copy" or "edit" items above.

## 5. Remediation plan

Each work package (WP) is sized for one or a few PRs. **Gate** says whether it should land before the next module is started (`pre-module`), before a third module ships (`pre-ship`), or is independent Hades paydown (`independent`). All packages follow the `AGENTS.md` process: reproduce defects first, use owning tests, keep real-game acceptance separate.

### Phase 0 — Confirmed defects, deletions and doc corrections (S each; start now, parallel-safe)

| WP | Scope | Covers | Gate |
| --- | --- | --- | --- |
| 0.1 | Split `hostActionsEnabled`: the Host derives restart eligibility from session state; modules supply only a recovery veto (defaulting to protocol incompatibility). Fix Hades I, the fixture and `real_module_navigation_harness.py:134`. RED model test first. | S-F1 | pre-module |
| 0.2 | Dead and single-use surfaces: root `ACTIVE_GAME_ID`, `TrainerGamePresentation.headerTitle`/`platformLabel`, `ActiveGameModule`, `backendGameID`, `removeModulePresentation`, unused icon cases; `core/game_spec.py`; `core/log_paths.trainer_log_path`; Hades I Time Warp remap; Hades II in-process Time Warp fallback and test-only re-exports; `publish_module_build.py` one-time migration and its mutation anchor. | S-F19, S-F20, B-F10, B-F17, T-F16, M-6 | pre-module |
| 0.3 | Move build-dependent hashes (`save_investigation.py:20`, `save_native_ids.py:11-15`) into the `supportedBuild` reference snapshot; add a `supported_build.py` check and a runbook step. | B-F15 | independent |
| 0.4 | Correct docs: isolated-build statements (`GAME_MODULES.md`), "Hades II-only" resident gate wording (`AGENTS.md`, `VERSIONING.md`), the stale selector docstring, the hand-maintained dependency instruction. Make `add-a-game-module.md` the single checklist and list the shared files a module still touches (shrinks as phases land). Replace restated PR-routing prose with a pointer to `ci_docs_only.py`. | T-F20 | pre-module |
| 0.5 | Move #720 incident logging out of `_execute_runtime`. | B-F16 | independent |

### Phase 1 — Make refactoring cheap (prerequisite for Phases 2–5)

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 1.0 | Per D2, compile `TrainerCore`, each game and the App as separate Swift modules with `-package-name`; mark the Core API that games use `package`; keep `--typecheck` and the full build on the same owner (`build.sh`/`product_support.py`); replace the word-list isolation check with the compiler boundary. | M-1, S-F4, T-F8 | L | pre-module |
| 1.1 | Migrate the 45 direct-`swiftc` tests to `swift_test_compiler` using the module layout from WP1.0 (compile Core once, then the module under test), so moving a type never breaks a harness. | T-F7 | M | pre-module |
| 1.2 | Triage source-text pins on `Sources/Core`, `Backend/core` and `build.sh`. **Keep** genuine structural boundaries, **convert** compilable facts to behaviour asserts in the existing harness, **delete** negative tombstones for retired strings. Start with `test_ui_consistency_contract.py`, `test_cross_game_ui_semantics.py`, the `build.sh` pins (`test_cross_game_isolation.py:52-58`, `test_process_time_warp_native_contract.py`, `test_build_signing_scope.py`) and workflow line-text asserts. Track literal-assert count and PR co-change rate instead of adding a gate. | T-F6, T-F7, T-F22 | L, incremental | pre-module (Core-touching subset) |
| 1.3 | Mutation gate: run anchor validation only in the dispatch job; delete the unused equivalent-mutant evidence machinery; prefer function-scoped anchors. | T-F11 | S | pre-module |
| 1.4 | Derive test routing: generate the dependency graph from imports (`macos_test_dependencies.json` removed), declare the macOS platform inside each test file (inventory derived), then a selector that maps a diff to the tests whose compiled sources or helpers intersect it, plus each `app.json` module's smoke entry for Core changes. Replay 30 days of PR diffs to check new ⊇ old before deleting `EXACT_PATH_TESTS`. | T-F3, T-F4, T-F5 | M | pre-module |
| 1.5 | Scheduled nightly convergence on `main`, so deferred UI journeys give earlier signal. Investigate the foreground-activation flake separately. | T-F17 | S | pre-module |
| 1.6 | Static tooling, scoped to seams: `ruff` (lint + format) on `Backend/core` and new shared packages, type-checking of the new Core Python protocols, `@MainActor` on the Swift module seam and `-strict-concurrency=targeted` in the typecheck lane. This supports refactoring rather than guarding hypothetical failures. Expand scope only as code is touched. | M-5, S-F16 | S–M | pre-module |

### Phase 2 — The Host owns the module lifecycle (Swift seam)

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 2.1 | Introduce `TrainerModuleServices` passed to `makeModel`: session, observable backend status, log sink, scoped hotkeys, descriptor and current target observation. The Context starts the backend, owns log-session ordering, stops the session after the termination hook, and rejects stale-PID observations. Replace the toggle with `connectFromHost`/`disconnectFromHost`. Delete `hostTargetLifetimeChanged(running:)` and Hades II's lifetime-triggered `startBackend()`. | S-F2, S-F3, S-F15, S-F17, S-F18 | M | pre-module |
| 2.2 | Presentation: register module resolvers when contexts are built, delete both `resolveText` bypasses, validate non-overlapping prefixes, standardize `{n}`. Add a Core string-table loader for module JSON tables. Package module resources under a per-module directory (`Resources/Modules/<id>/`) with a Core lookup, and remove `#filePath` source-tree fallbacks from production code. | S-F7, M-2, M-3 | M | pre-module |
| 2.3 | Context-owned feedback center and Host-owned diagnostics actions (open log, history, clear, export). One export path in Swift; modules return only checks (keys plus arguments) and state. Delete Hades II's Python ZIP builder that parses Host log files. | S-F5, B-F12 | M | pre-module |
| 2.4 | Data-driven section catalog, search and management catalog with optional slots. The Host renders sidebar, search, current-issues entry and menu, and injects Save actions into both page and menu. The six-section taxonomy stays in the Hades modules. | S-F6, S-F11 (slots) | M | pre-module |
| 2.5 | **Exit criterion:** upgrade the reference fixture into a realistic template that consumes every Host service (status, feedback, diagnostics, management, localization tables, shortcuts, profile store, a typed command binding). Then re-run the §4 checklist; every remaining shared-file edit is either removed or documented as deliberate. | all above | M | pre-module |

### Phase 3 — Backend and UI contracts with two real adapters

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 3.1 | `GameAdapter` contract: `data_dir`/`log_dir` in `GameAdapterContext` (removes five hard-coded roots); a declared optional `state_for_error()` hook; a `SaveProvider` `Protocol` with a default pass-through `resolve` and a provider context; a typed `PresentableError` base with `host.save.*` keys for Core Save errors; validate `steamAppId` (or a typed `distribution` block) and unify the launch URL; drop unconsumed hello extras. | B-F11, B-F7 step 1 | S–M | pre-module |
| 3.2 | Save Editor: `StructuredSaveEditSession.open_selected(...)` and `apply(candidate)` (remove the public `document` setter), a Core `SaveEditorWorkspaceRegistry` with ids, baseline check, close and a bounded open count; delete both `save_edit.py`. Swift `TrainerStructuredSaveEditorClient` over the existing reply coordinator; caller-defined lanes. | B-F5, S-F9 | M | pre-ship (if the module has a Save Editor) |
| 3.3 | Core `locate_target(manifest)` using the Host's identity rules plus `proc_pidpath`, and a `bounded_run(argv, budget)` helper. Hades II derives its install path from the running process, falling back to Steam `libraryfolders.vdf`; cache compatibility per (path, mtime); add timeouts to Hades I subprocess calls. Reproduce the non-default library failure first. | B-F9, B-F21 | M | pre-module |
| 3.4 | Generic command contract: an optional `commandContract` in `module.json` generates a Swift enum with timeout, trusted-target and offline flags. Budget constants become inputs, with an "outer > worst-case inner" check for every command, including `scan`/`launch`/`status`. Migrate Hades I to typed requests. Retire Hades II's retired `multiplier: 100` field. | S-F8, B-F8, S-F20 | M | pre-module |
| 3.5 | Core `VersionedDocumentStore`/`ProfileStore` (envelope, quarantine, newer-schema refusal, game-supplied normalize and error keys) and Swift `TrainerShortcutStore<Action>` with namespaced keys. Decide product-wide whether Profiles carry shortcuts (D4). | B-F4, S-F12 | M | pre-module |
| 3.6 | UI contracts: Core `TrainerObservedDrafts<Field>` from the Hades I pattern (migrate Hades II groups incrementally, drop the `ViewState` typealias). Make `activationPending` request-scoped and replace the 0.9 s timer. Rename Hades-family Core names to neutral ones (`TrainerTraitManagerLayout`, `TrainerAcquisitionRarity`, icon contexts) or move them into the Hades modules. Restate the "two adapters" rule to require a non-sibling or a documented family exception. | S-F10, S-F13, S-F11 | M | pre-ship |

### Phase 4 — Remove single-game residue and make isolation generic

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 4.1 | Hades II namespacing: migrate `shortcut.*` keys to `hades2.shortcut.*` with a v6→v7 migration; move legacy v4 helpers out of Core `HotkeyChord`. Type-name prefixing is unnecessary once WP1.0 gives each game its own Swift module. | S-F4, S-F12 | M | pre-module |
| 4.2 | Hades II data directory: move root-level `desired-state.json`, `profiles/`, `backups/`, `diagnostics/` under `MacGamingTrainer/hades2/`. This is a persistence-identity change: needs migration and old-version refusal tests per the version-impact procedure. | B-F4 | M | pre-ship |
| 4.3 | Isolation derived from manifests: Swift isolation comes from WP1.0. For Python, an import-boundary check derived from `app.json` (`core` imports no `games.*`; a game imports no other game). A UserDefaults/data-key prefix check per module. Replace `build.sh` text checks with a `product_support` source-set check. | T-F8, M-1 | S | pre-module |

### Phase 5 — CI and build tooling for N modules

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 5.1 | Generate the module-build matrix from `app.json` plus the fixture. Move resource presence/absence checks into `verify_module_build.py` (declared `appResources` exist; other modules' resources absent). Delete the Hades file names from both workflows and their test pins. Copy declared reference directories in `test_app_identity_contract.py`. Run the reference fixture in `--typecheck` mode for Swift-only Core diffs. | T-F1, T-F2, T-F2b, T-F21 | S–M | pre-module |
| 5.2 | Generic CI prerequisites declared by tests or manifests (replaces the Lua 5.2 special case); a module-owned home for game generators/profilers classified as portable tooling; one source for runner, Xcode and Python versions (`python-version-file`); a documented provisional budget for new native journeys. | T-F13, T-F14, T-F15 | M | pre-module |
| 5.3 | Process Time Warp as a declared capability: built through `build_module_native.py` for the declared architectures only when a module opts in (drops the forced x86_64 slice); packaged path resolved through Core rather than hard-coded; move `lldb_time_warp.py` into the debugger package of WP6.1. | M-4, T-F9, B-F17 | S–M | pre-module |
| 5.4 | Move `build.sh`'s 8 inline Python blocks into an importable `Tools/package_app.py`; one owner for the `runtime.json` schema shared by build, verify and provenance. Verify with a before/after bundle tree and plist diff on the same SHA. | T-F10 | M | pre-ship |
| 5.5 | Governance freeze: no new gate code without an escaped defect; delete tombstone tests as WP1.2 proceeds; move CI/provenance policy out of `GAME_MODULES.md` into a CI document. | T-F12, T-F20 | S | independent |

### Phase 6 — Debugger and sidecar consolidation (needs real-game acceptance)

| WP | Scope | Covers | Size | Gate |
| --- | --- | --- | --- | --- |
| 6.1 | Shared LLDB attachment-lifecycle helper in `Backend/debugger/` (not Core): staged cleanup, quarantine errors with a game-injected key factory, failed-attach rollback, the stop → focus → breakpoint cleanup → detach → OS-resume sequence, worker hello/handshake and close loop. Decide one unknown-build policy (recommended: fail closed) and the SIGCONT handoff for Hades I. Set `child_owns_cleanup` by contract. Adopt the thin-worker pattern as the documented template. Record an exit criterion for `MGT_HADES2_TRANSPORT=lldb`. | B-F1, B-F2, B-F13 | M–L | pre-module **if the next game is debugger-driven** (D1) |
| 6.2 | Core `TargetLifetime` identity (`proc_pidinfo` start time) and an optional `OutcomeJournal`; Hades I journals only mutating calls, not `status`. | B-F3 | M | pre-ship if debugger-driven |

Real-game attach/detach acceptance for both games stays user-run, as recorded in `PROJECT_STATUS.md`.

### Phase 7 — Hades II internal paydown (independent; does not block new modules)

- Error presentation at raise sites: convert Hades II prose raises to typed keys module by module, shrinking the 302-rule registry to resident-Lua text only; typed keys for the Hades I Save Editor and Time Warp (B-F7 steps 2–4).
- Split `Hades2Adapter`/`command_contract.py` around the synchronization core; declarative `durable_capture` on `CommandSpec` (B-F18). Split `save_workspace.py`/`save_investigation.py` after WP3.2 (B-F19).
- Retire `damageEnabled` as a durable identity (resident revision bump, schema migration) and `gardenQoL` (B-F14).
- Resident Lua assembly: ordered `residentRuntime.sources` assembled deterministically into one chunk. The first step is a byte-identical split that needs no game acceptance; later restructuring does (B-F20).
- Split `Hades2Model`, `Hades2SaveEditorModel`, `Hades2View`, `HadesModule.swift` and `TrainerLogSink`'s legacy-migration/test-only mode after Phase 2 removes their Host-owned parts (S-F14).
- Family codec library (`Backend/games/_supergiant/`) only if another Supergiant title is planned; decide whether Hades I needs the `_Temp`/`.v` rule (B-F6).

## 6. Sequencing

```text
Phase 0 ──────────────────────────────► (now, parallel)
Phase 1 (1.0 → 1.1) ─────┐
                         ├─► Phase 2 (Swift seam) ──┐
                         └─► Phase 3 (Python seam) ─┼─► WP2.5 template exit check ─► next module
Phase 4.1/4.3, Phase 5.1–5.3 (parallel with 2/3) ───┘
Phase 6 ─► only if D1 = debugger-driven; needs real-game acceptance
Phase 7 ─► independent, opportunistic
```

Parallelism: Phase 2 (Swift) and Phase 3 (Python) touch disjoint files and can run as separate sessions. Within each phase, packages that touch the same files should be serialized.

## 7. Owner decisions (2026-11-18)

| ID | Question | Decision |
| --- | --- | --- |
| D1 | What kind of game comes next? | Not yet known. Phase 6 stays conditional and is re-evaluated when Phase 3 ends. Shared mechanisms in Phases 2–3 must not assume LLDB, Lua or a sidecar. |
| D2 | Module boundary: per-module prefixes plus a lint, or separate Swift modules? | **Separate Swift modules**, chosen for many and varied future games. Compile `TrainerCore` once, then one Swift module per game, then the App module that holds the generated catalog. Core exposes its game-facing API with Swift's `package` access level (`-package-name`), so it is not made `public` to the world. Effects: the compiler rejects Core → game and game → game references; each game gets its own namespace, so `Hades2.TrainerProfile` can no longer collide with another game; test harnesses compile Core once and reuse it. Cost: one annotation pass over the Core API that games use, and build/harness changes. This lands as WP1.0, before WP1.1 migrates the harnesses. WP4.1's type prefixing is then unnecessary; key prefixing still applies. |
| D3 | Scoped static tooling (WP1.6)? | Yes, scoped to seams and touched code. |
| D4 | Do Profiles include shortcuts for every game? | Yes, through the shared Profile store (WP3.5). Existing Hades II profiles keep loading unchanged; Hades I profiles without a shortcut section leave current bindings unchanged when loaded. |
| D5 | How is the plan tracked? | One umbrella issue plus one issue per phase, linked from #124. The owner authorized creating further issues at the implementer's discretion. Live scope belongs to those issues; this document is the 2026-11-18 evidence snapshot. |

## 8. Out of scope for this review

Real-game behaviour, rendered UI, native acceptance (#433, #565, #736, #739, #745, #746, #752) and the semantics of individual Hades features were not re-examined. No tests were run, except `tests/test_host_watchdog_aggregate_budgets.py` (passed), `Tools/validate_game_module.py --all` and `Tools/supported_build.py`.
