# MacGamingTrainer Project Status

## Current release state

- Product: 0.1 / Build 2.
- Stable `main`: Build 1.
- Release PR: #7, still DRAFT.
- Release branch `feature/post-v0.1-improvements`: revision-35 acceptance head `17fb237e0e609623b7f4c281c744382804a42e9a`.
- Revision-35 manual acceptance: FAILED; do not merge and do not use r35 as a final PASS artifact.
- Active repair branch: `fix/batch-a-native-modals`.
- Batch A current code head before this handoff-doc update: `0c3b5b7b7cf8f1128899dc3fe9d915102f130906`.
- Hades II resident runtime in Batch A: revision 36.
- Host protocol 5; module protocol 5; desired-state schema 3; Profile schema 4.
- Target game build audited: Hades II 1.139672 / Steam build 24556151.

## Revision-35 manual acceptance findings

User retained two run logs and reported:
- Test 1: initial/transition stutter remains, but is materially reduced.
- Test 2/5: same-process recovery is basically usable, but game-speed falls back after combat and cannot be re-applied in non-combat/crossroads-style states. This is a contract/design defect for Batch B.
- Test 3: not tested.
- Test 4: first-toggle latency can swallow feedback; Glass/Pop/Tink do not read as one sound family and deferred/disabled are too weak. Redesign in Batch C.
- Test 6: native boon selling opens and can sell, but cannot exit. Batch A root cause found and fixed in code.
- Test 7: direct-add works; native three-choice repeatedly fails. User requires one `触发原生三选一` item inside each supported source group, not a separate global button. Batch A implements this.
- Test 8: Hecate polymorph still bypasses God Mode. Broader hostile-debuff audit is Batch B.
- Test 9: exit/desired-state cleanup passed and is carried forward unless touched by later work.

## Batch A — native modal correctness

Design: `docs/superpowers/specs/2026-09-19-batch-a-native-modals-design.md`.
Plan: `docs/superpowers/plans/2026-09-19-batch-a-native-modals.md`.

Implemented on `fix/batch-a-native-modals`:
- trainer-opened sell screen temporarily uses a copied `ScreenData.SellTraits` whose Close button calls a trainer-owned close handler;
- the close handler delegates to native `CloseStoreScreen` only when a real room Store exists, otherwise performs equivalent generic cleanup without fabricating Store state;
- fallback close disables purchase inputs before screen teardown;
- special-choice source lookup now uses installed-game globals `EnemyData` and `PresetEventArgs` instead of nonexistent `NPCData` entries;
- source data is deep-copied before native choice generation;
- runtime revision advanced 35 → 36;
- special picker derives one synthetic `触发原生三选一` row per supported source;
- the standalone bottom native-choice button is removed;
- direct-add and `spawnSpecial` hotkey share the same special-reward action path;
- Heracles/Moros remain without a native-choice row.

## Batch A verification evidence

- RED→GREEN `test_native_sell_traits_contract.py`: PASS.
- RED→GREEN `test_native_special_choice_contract.py`: PASS.
- Full `bash Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`.
- Full `bash Tools/run_macos_checks.sh`: PASS / `macos_checks_ok`.
- Ponytail review: no worthwhile abstraction/refactor to remove; keep the localized model/runtime changes.
- Correctness review added native-equivalent `UseableOff` cleanup before trainer sell-screen teardown.
- Clean `./build.sh hades2`: PASS on code head `0c3b5b7b7cf8f1128899dc3fe9d915102f130906`.
- Build checks: 0.1 / Build 2, one module, runtime 36, Mach-O arm64, debugger entitlement present, strict codesign PASS, clean worktree.

Final Batch A RC is intentionally built only after this handoff documentation commit. Exact final HEAD, ZIP size and SHA256 are recorded in PR #7 so artifact identity does not require a self-referential repository commit.

## Remaining Phase 0 repair batches

1. Batch A manual retest: sell Cancel/exit + sell-then-exit; one loot-style native choice; one fixed-choice native choice; direct-add regression; Heracles/Moros no native row.
2. Batch B: global game-speed semantics plus comprehensive hostile-debuff/God Mode audit.
3. Batch C: coherent Trainer Host enabled/deferred/disabled sound family and reliable delayed playback behavior.
4. Batch D: remaining attach→Lua/world readiness stutter after correctness work is stable.

## GitHub gates

- PR #7: keep DRAFT; do not merge until repair batches and required manual acceptance are complete.
- #1/#11: remain open until lifecycle/performance acceptance completes.
- #16: hosted Actions admission/startup failure remains infrastructure-only when `steps=null` / `logs_url=null`.
- #17: non-blocking partial hand-edited schema-4 Profile shortcut collision; proven fix remains deferred.
- PR #10: keep DRAFT and do not synchronize/merge until Phase 0 closes.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No game-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Exit must never be permanently blocked by cleanup failure.
- Runtime source changes require a revision bump.
- Every manual-test request must ship a prebuilt signed `.app` ZIP; the tester does not compile.
