# MacGamingTrainer operational state

Updated: 2026-10-21

[AGENTS.md](AGENTS.md) routes development; [#124](https://github.com/TeaganRicardo/MacGamingTrainer/issues/124) owns current priority and dependencies. This file owns compatibility, operating limitations and manual-acceptance evidence. Detailed completed implementation evidence remains in the owning issues/PRs and Git history.

## Compatibility and operating limits

- Supported Hades II target: game 1.143476 / Steam build 25481925 / arm64 UUID `35CD2E50-2D78-3A63-835B-3EB1224C6D65`.
- Read current product SemVer/build from `Info.plist`, module protocol from `Backend/games/hades2/module.json`, and resident revision from `Backend/games/hades2/runtime/hades.lua`. Compatibility revisions are independent of product version; use their production declarations for the affected persistence/Profile/Host contract.
- Connection acceptance for #473 is complete with the user's selected **Game Mode OFF** workaround. Both isolated old/new comparisons connected with OFF and hit the initial sidecar timeout with ON. ON reliability remains a shared scheduling limitation. Keep the existing debugger settings, request budgets and recovery policy; there is no global merge hold.
- Invincibility's native query library is tied to the exact supported arm64 UUID and verified function prefixes. It observes Unit identity/block membership; unknown builds cannot reuse its offsets. It remains loaded for the game process lifetime because Lua may retain callbacks after detach. Hostile-effect, room remount and reconnect gameplay checks remain pending. Build/image-selection evidence is in #456/#474.
- `docs/reference/hades2/1.139672-24556151/` is a frozen historical research snapshot. The packaged terminology resource is now `docs/reference/hades2/1.143476-25481925/ui_terminology.json`, with current-build bilingual source hashes and icon-prefix normalization recorded in its `sourceEvidence` metadata. Catalog legality is generated from curated policy and declared reference sources.
- Backend execution uses bundled CPython from `Tools/python_runtime.json`; Hades owns the separate Xcode Python/LLDB bridge. Build toolchain/provenance policy is in `GAME_MODULES.md` and the existing workflows, not a copied status table.
- Host startup claims one per-user lease for the module-declared target before constructing its backend session or model. A second updated Trainer launch focuses the existing owner when possible; otherwise it exits with instructions to use or quit the other Trainer. The kernel releases ownership on normal exit or process death; a stale PID file does not block recovery. Isolated concurrency/focus/crash fixtures verify development behavior; actual multi-instance app activation and game attachment remain user-run (#548).
- Save Editor and backup management use independent native tool windows. Reopening an already-open entry focuses its existing document and drafts; different managed backups use separate Hades workspaces on the same backend session. Requests and cleanup address an explicit workspace ID. Closing a tool releases only that tool; its pending document operations finish before closing. The fixed originally-read source and explicitly selected physical target retain their existing transaction/recovery semantics. Native window/temporary-document checks are automated; rendered app and real save-load acceptance remain user-run (#539).
- Hades resident commands use a shared-memory mailbox serviced by the supported game's main-thread `App::Update` entry. LLDB installs the process-lifetime helper and still owns attachment and Time Warp; ordinary resident status, mutations and preference batches use the mailbox. `MGT_HADES2_TRANSPORT=lldb` selects the explicit comparison path. An unclaimed deadline can be cancelled safely; a claimed request without trustworthy completion permanently closes its lease and requires a game restart. If the command result arrived but its acceptance connection failed, keep the reported action result and restart both the game and Trainer before reconnecting; do not repeat a completed one-shot action. Implementation and exact-head offline verification are tracked in [#499](https://github.com/TeaganRicardo/MacGamingTrainer/issues/499) / [PR #501](https://github.com/TeaganRicardo/MacGamingTrainer/pull/501). Native game-process acceptance has not been performed.
- #433 retains an unlocated historical LLDB test stall. #491 corrected a separately reproduced aggregate test-watchdog ownership defect; it did not establish that the historical stall is fixed. A new relevant reproduction can change its priority; the historical observation alone is not a blanket merge blocker.

## Accepted and pending real-game behavior

The user accepted the focused revision-96 / #392 / PR #393 patch on 2026-10-08: native prompt/backing lifetime and narrative-choice presentation. QA source `24e06cbab2e7049aef923d674a71ddf77d958fac` has the same resident source as merged baseline `46c99d8479a2c650961a1d51c0791b46b1fa7831`, SHA-256 `4fad5a44efbb4608267ffef9440f63100eed8f50b0199aa79bd9237f24117c8c`.

That focused acceptance does not certify earlier feature families or subsequent resident changes. Revision 51 (`a6cf37b41639229bd64938d9587a9735fb16dd91`, accepted 2026-09-28) remains the earlier accepted baseline. The supported target also has user-run attach/status and representative feature smoke evidence; neither is blanket feature acceptance.

Retain these unperformed scope families in the consolidated user-run pass; detailed scenarios remain in their owning issues/PRs:

- Transformed/thrown Cast repetition and infinite-ammo fired/death/pickup bookkeeping.
- Exact acquisition and mounted level/rarity/removal/teardown across ordinary/Hermes, Chaos pairs, Selene/Path of Stars, Hammer, Arachne, Echo previous-run, Well/temporary effects, Familiar, Keepsake, Arcana and direct special-NPC owners; applicable cancellation/expiry and effect recomputation.
- Native reroll/menu families, reward doors, currency/history, complete menu unwind and owner changes, including non-consuming gold/rerolls with retained gains and deliberate numeric edits. The focused revision-96 presentation acceptance above remains valid.
- Independent gathering-tool/plant probabilities and deliberate generation, native collection/minigame accounting, garden instant maturity followed by native harvesting, Chaos Gate eligibility/cost/routing and disable/reset/load behavior. Retired Garden Convenience preferences/shortcuts are discarded; they never authorize the new one-shot maturity action.
- Invincibility native protection/Chronos behavior; Crossroads/session/Hero/run transitions; NPC/Charon occurrence and token consumption; desired/active/dormant state, Profile/restart/reconnect and unknown-outcome non-replay.
- Save Editor fixed source/explicit target, managed backups, load/recovery and running-target disk replacement. Disk-write success does not establish in-memory game reload or survival of a later game-authored save.
- Shared input/focus/commit, transient feedback/recovery access, bilingual layout and game-management placement, including affected narrow-window/accessibility behavior.
- Current runtime observation, unrelated external value updates, mounted-effect/menu handoff, generation changes and reconnect, plus perceived latency/FPS. Offline performance measurements do not establish native frame cost or FPS improvement.

### Runtime-observation performance continuation

- Fixed source: `d0fa25a8c7254cbde9e2aafce9640d8d27a9ecbe`, tree-identical to merged baseline `faaa1ebf77af73779ba9f249e4ac22d71c264486`. Resolve the live remote tip separately for new work.
- Package: `MacGamingTrainer-0.3.0-b6-d0fa25a8-rc.zip`.
- ZIP SHA-256: `b646a3e1b557f67e521629478e70df552fa14450649f8abab22cb9f27cb84f81`.
- Exact-source convergence: [Linux](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/38718472130), [macOS/mutation/package/provenance](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/38718487236), [reference module](https://github.com/TeaganRicardo/MacGamingTrainer/actions/runs/38718508214). Download checksum/provenance and extracted strict signing were verified in the owning handoff.
- User-local package/procedure: `/Users/gao/Downloads/MacGamingTrainer-rev110-d0fa25a8/README.md`.
- Historical status: this revision-110 package was the frozen artifact selected when the earlier performance gate was written. It is retained as exact-source evidence, not as the current runtime revision.
- On 2026-10-17 the user reported completing real-game perceived-performance testing on the current product line and explicitly authorized continuing #470. That clears the earlier performance-continuation gate only; it does not silently certify unrelated feature families or unreported owner/reconnect/rendering scenarios.
- Live `main` at the start of #470 completion was `86e91fa2a701026a51671fef1cb3c8a2e8c2e83c`, resident revision 113. The #470 completion candidate changes resident observation semantics and therefore advances the resident revision again; its exact-head runtime-observation/reconnect/perceived-latency acceptance remains user-run after automated/review convergence.

## Execution authorization

The user authorizes independently reviewed, automated-green merges before consolidated final manual acceptance of the selected work. Coordinate actual overlapping owners and review the final head; missing manual-only evidence does not itself reopen coding tasks or block unrelated work.

On 2026-10-23 the user authorized task verification on local macOS or in a Linux container to reduce GitHub Actions usage. Retain the executing SHA, logs and actual toolchain for equivalent owning checks; distinguish local portable/macOS/build/package/signing evidence from hosted checks and their pinned toolchain. Remote CI is not required merely to repeat already-passing local checks.

For [#499](https://github.com/TeaganRicardo/MacGamingTrainer/issues/499), the user replaced the earlier partial feasibility plan with complete Hades-owned mailbox implementation and retained independent review/merge authority. **Later on 2026-10-17, the user expressly prohibited any RDC/agent validation involving the Hades II game process and waived real-game performance-efficiency testing as a development gate.** Remote macOS code builds and isolated synthetic tests remain allowed. Game launch, attach, gameplay/save-load, scene, UI and FPS/frame-time acceptance remain unperformed and user-only. Do not infer real-game reliability or latency improvement from offline CI.

Outside that task authorization, game launches, gameplay/load tests and visual acceptance remain user-executed. Build, fixtures, package provenance and source review must not be described as real-game acceptance.

## Conditional risks

Some Core metadata updates lack parent-directory fsync after atomic replacement, and Hades Profile storage does not mirror every Core Save symlink guard. Neither has a demonstrated normal-operation loss/exploit path here. Promote stronger hardening only for new evidence or an explicitly selected requirement.
