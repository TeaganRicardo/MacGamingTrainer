# MacGamingTrainer Project Status

## Current release state

- Product: 0.1 / Build 2.
- Stable `main`: Build 1.
- Release PR: #7, still DRAFT.
- Active repair branch: `fix/batch-a-native-modals`.
- Revision-35 acceptance remains failed/superseded.
- Revision-36 Batch A native sell/native special-choice functionality: **manual PASS** on 2026-09-19.
- Current r37 code head before this handoff-doc update: `c66dca0`.
- Hades II resident runtime: revision 38.
- Host protocol 5; module protocol 5; desired-state schema 3; Profile schema 4.
- Target game build audited: Hades II 1.139672 / Steam build 24556151.

## r35 findings carried forward

- Game speed falls back after combat and cannot be applied globally in non-combat/crossroads-style states: Batch B.
- Feedback sounds are not a coherent family and delayed first operations can swallow feedback: Batch C.
- Hecate polymorph bypasses God Mode; broader hostile-debuff audit required: Batch B.
- Residual attach/world-readiness stutter remains: Batch D.
- Exit/desired-state cleanup passed and remains carry-forward PASS unless touched.

## Batch A — native modal correctness

r36 fixed:
- trainer-opened boon selling can sell and close from arbitrary run rooms without fabricating Store state;
- native special-choice data comes from installed-game `EnemyData` / `PresetEventArgs`;
- supported source choices open through the native choice screen;
- direct-add remains separate;
- native choice is embedded into the source list instead of a global button.

User manually confirmed the r36 functionality as normal on 2026-09-19. The uploaded acceptance log also records repeated r36 `open_special_choice`, `open_sell_traits`, and direct `spawn_reward` successes.

## r37 safety/UI follow-up

Implemented after r36 acceptance:
- `祝福管理` renamed/moved to `生成内容` as `出售祝福`; control text is `出售`;
- every generation action button is consistently `生成`;
- native special-choice rows are named `<中文来源>的祝福 · <English Source> Boon`;
- installed-game audit confirmed Heracles and Moros have no legal boon/trait pools in 1.139672; both false special-source registry/codex entries were removed;
- runtime advanced 36 → 37 because `hades.lua` source registry changed;
- restore confirmation now offers `备份当前并恢复` or `直接恢复`;
- `直接恢复` creates no persistent `恢复前自动备份`, but still uses a temporary rollback snapshot and preserves it if rollback itself fails;
- restore no longer renames/removes the whole Hades II save root; target files are verified and atomically replaced in-place.

## Save-loss incident — confirmed root cause

The repeated save wipes during development were caused by **our macOS watcher test**, not r36 native-modal code and not Steam Cloud.

`tests/test_hades2_run_log_watcher.py` constructed the real path
`~/Library/Application Support/Supergiant Games/Hades II` and executed `removeItem(at: directory)` before creating its fixture log. Therefore every execution of that test deleted the real Hades II user directory.

Evidence:
- Steam AutoCloud at 19:35 and 20:55 reported all `Profile1*.sav` files already missing on launch while sync was disabled/offline; Steam was observing the loss, not downloading a replacement.
- The destructive test was part of `Tools/run_macos_checks.sh`, matching the repeated preflight pattern.
- Re-running the old test reproduced the deletion; the repaired test now receives a temporary directory explicitly.
- After repair, a full macOS suite wrapped by before/after SHA-256 snapshots reported `REAL_SAVE_TREE_UNCHANGED`.

A separate audit also found the pre-existing save restore implementation (present since baseline commit `31297c9`) temporarily renamed the entire save root for rollback. That was a genuine additional race risk and is fixed in r37, but it is not recorded as the direct cause of the observed 19:35/20:55 wipes.

## User save recovery

After the final destructive-test reproduction, Steam `remotecache.vdf` SHA-1 values for the user's last post-recovery `Profile1.sav` and `Profile1_Temp.sav` matched backup:
`saves-20260919-042934-zargb7u4` / `修改器测试`.

That backup was restored with the new root-stable path while Hades II was stopped. All 17 files were then verified against the backup manifest; the three Profile SHA-256 values matched exactly. The destructive-test residue was separately copied to `/tmp/mgt-destructive-watcher-evidence-20260919-213445`.

## r37 verification evidence so far

- RED→GREEN save-root continuity test: PASS.
- RED→GREEN direct-restore persistent-backup behavior: PASS.
- RED→GREEN failed-direct-rollback preservation: PASS.
- RED→GREEN restore protocol/UI contract: PASS.
- RED→GREEN watcher temporary-directory isolation: PASS.
- Native sell / native special-choice contracts: PASS.
- Full `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`.
- Full `Tools/run_macos_checks.sh`: PASS / `macos_checks_ok`.
- Real Hades II save tree before/after full macOS suite: byte hashes unchanged.
- Test tree audit: no test references the real Hades II Application Support path or `homeDirectoryForCurrentUser`.

Final clean build/package verification is still required after this handoff documentation commit.

## r38 special-choice refresh follow-up

The user accepted the remaining r37 checks, then found one native special-choice regression: repeatedly opening the same source returned the same three-option list and could offer an already acquired special trait again.

Root cause:
- the trainer's fixed-choice path copied the vanilla NPC helper's constant `RandomSynchronize(9)`; vanilla encounters normally open once, but trainer-forced repetition therefore reproduced the same deterministic offer;
- unlike loot-style sources that already pass through `SetTraitsOnLoot -> GetEligibleUpgrades`, the trainer's fixed-choice path only evaluated game-state requirements and skipped the native owned-trait/eligibility filters.

r38 fix on `fix/special-choice-refresh-r38`:
- runtime advanced 37 → 38;
- each special source keeps a session-local open counter; first trainer open keeps seed 9, subsequent opens advance the seed per source;
- fixed-choice options whose `ItemName` resolves to a trait are excluded when the hero already owns them, when the run has already picked them, or when native `IsTraitEligible` rejects them;
- non-trait fixed options preserve their prior game-state eligibility behavior;
- loot-style sources continue to use native `SetTraitsOnLoot` and receive the same per-source refreshed RNG stream.

Verification so far:
- RED was observed on r37 with the new repeated-choice contract;
- targeted `test_native_special_choice_contract.py`: PASS on r38;
- full `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`.
- exact-head macOS/build/package verification is pending before an r38 RC is handed to the tester.

## Remaining Phase 0 repair batches

1. r38 focused manual acceptance: repeated fixed-choice and loot-style special choices.
2. Batch B: global game-speed semantics + comprehensive hostile-debuff/God Mode audit.
3. Batch C: coherent Trainer Host enabled/deferred/disabled sound family + reliable delayed playback.
4. Batch D: residual attach → Lua/world-readiness stutter.
5. Final consolidated regression and release closure.

## GitHub gates

- PR #7 remains DRAFT; do not merge until remaining repair batches and final acceptance close.
- #1/#11 remain open until lifecycle/performance acceptance closes.
- #16 remains hosted Actions infrastructure-only when jobs fail before step 0.
- #17 remains non-blocking/deferred.
- PR #10 remains DRAFT and unsynchronized until Phase 0 closes.

## Non-regression constraints

- Tests must never mutate real user/game data. All filesystem mutation tests use isolated temporary roots.
- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No game-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never make the Hades II save root disappear.
- A failed rollback must preserve the last recoverable copy.
- Runtime source changes require a revision bump.
- GitHub is the durable source of truth for code, versions, RC identity and handoff documents.
- Development/review should run in the development environment or through the GitHub connector; RDC is reserved for target-Mac-only build/game verification.
- Every manual-test request ships a prebuilt signed `.app` ZIP; the tester does not compile.
