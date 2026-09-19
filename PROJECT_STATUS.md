# MacGamingTrainer Project Status

## Current release state

- Product: 0.1 / Build 2.
- Stable `main`: Build 1.
- Release PR: #7, still DRAFT.
- Active repair branch: `fix/special-choice-native-r39`.
- Revision-35 acceptance remains failed/superseded.
- Revision-36 Batch A native sell/native special-choice functionality: **manual PASS** on 2026-09-19.
- Current r39 code/test head before this handoff-doc update: `e610f3aba74d5878d59d66d6476966ad06effec2`.
- Hades II resident runtime: revision 39.
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
- clean Build 2 package verification on code/handoff head `c027b4157987eb5f714a403624e2ebb8c1e1079a`: PASS;
- r38 tester app: `/Users/gao/Downloads/Mac Gaming Trainer r38.app`;
- r38 ZIP: `/Users/gao/Downloads/MacGamingTrainer-0.1-build2-rc-r38.zip`;
- ZIP size: 1,975,661 bytes; SHA256: `9ad59988f4f4a48da8f7216bfd0b7729ae355fec833a9774ea60c162d3bc59d6`;
- packaged runtime revision 38, arm64, debugger entitlement, strict codesign and ZIP integrity: PASS;
- full exact-head macOS suite/save-tree sentinel is **deferred, not failed**, because Hades II was actively running on the target Mac when the final gate started. The gate exited before tests rather than disturb the live game.

## r39 native-parity re-review

Before manual r38 acceptance, the special-choice implementation was re-audited against the installed Hades II 1.139672 scripts, not only the public mirror.

Findings:
- Artemis / Athena / Dionysus / Hades are the highest-fidelity path: trainer code deep-copies the installed-game NPC source, calls native `SetTraitsOnLoot`, then opens the native `OpenUpgradeChoiceMenu`.
- Arachne / Narcissus / Echo / Medea / Circe / Icarus cannot safely call their top-level native `*Choice` functions from an arbitrary trainer invocation. Those functions assume the live narrative screen and/or real NPC object and room-specific presentation state. Examples include `screen.PortraitId`, `screen.OnCloseFinishedFunctionName`, animations against `source.ObjectId`, Narcissus admirer objects, Circe/Medea cauldron presentation, and Icarus encounter exit state.
- Therefore the fixed-choice path remains a deliberately thin adapter: installed-game `EnemyData` + `PresetEventArgs.*.UpgradeOptions` + native `IsGameStateEligible` / `PassRarityCheck` + native `OpenUpgradeChoiceMenu` + native selection/acquire handling. Only the NPC narrative/presentation wrapper and the trainer-only repeat semantics are reproduced locally.

The re-review found three r38 deviations worth correcting:
1. fixed-choice options were additionally passed through `IsTraitEligible`, even though the game's six fixed NPC choice functions do not use that ordinary-boon eligibility gate;
2. the trainer repeat counter persisted across runs instead of resetting with `CurrentRun`;
3. Trait-vs-non-Trait detection inferred from the presence of `TraitData` instead of the native option's `Type` field.

r39 changes:
- runtime 38 → 39;
- remove `IsTraitEligible` from the fixed-NPC path, preserving the native special-choice eligibility rules;
- use `option.Type == "Trait"` as the discriminator and fail closed if a declared Trait lacks installed `TraitData`;
- retain only the trainer-required duplicate invariant for Trait options: reject a trait already owned by the hero or already recorded in `CurrentRun.PickedTraits`;
- reset the per-source repeat counter whenever the `CurrentRun` table changes;
- first open of a source in each run keeps native `RandomSynchronize(9)`; only trainer-only repeated opens advance 10, 11, ... so a second forced encounter is not deterministically identical.

Verification:
- r39 contract was observed RED against r38, then GREEN after the implementation change;
- exact code/test head `e610f3aba74d5878d59d66d6476966ad06effec2`;
- targeted native-special-choice contract: PASS;
- full `Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`;
- clean Build 2 package: PASS;
- app: `/Users/gao/Downloads/Mac Gaming Trainer r39.app`;
- ZIP: `/Users/gao/Downloads/MacGamingTrainer-0.1-build2-rc-r39.zip`;
- ZIP size: 1,975,675 bytes;
- SHA256: `5f1e8609a60e8b7f4387915b5d22a97d9d7865e7e46552025a068fe3930d1c73`;
- packaged runtime 39, arm64, debugger entitlement, strict codesign and ZIP integrity: PASS;
- full macOS suite/save-tree sentinel was safely skipped because Hades II was actively running; no game process was terminated and no save operation was performed.

## r39 focused manual acceptance — PASS

Manual acceptance completed on 2026-09-19 with the signed r39 tester build.

Observed log evidence:
- runtime 39 active in the tested app;
- repeated `open_special_choice` calls succeeded multiple times in the same run (`runCount=12`);
- after restore/relaunch/reconnect, runtime 39 loaded again in a different run (`runCount=9`) and `open_special_choice` succeeded;
- save restore completed successfully before the second run;
- no r39 special-choice Lua error is present in the focused acceptance segment.

The user completed the visual/behavioral checks and reported no remaining duplicate/re-offer issue. r39 focused acceptance is therefore closed as PASS.

## Remaining Phase 0 repair batches

1. Batch B: global game-speed semantics + comprehensive hostile-debuff/God Mode audit.
2. Batch C: coherent Trainer Host enabled/deferred/disabled sound family + reliable delayed playback.
3. Batch D: residual attach → Lua/world-readiness stutter.
4. Final consolidated regression and release closure.

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
