# MacGamingTrainer Project Status

## Current baseline

- Product version: 0.1
- Development build: 2
- Published/stable baseline: v0.1 / Build 1 on `main`
- Release branch: `feature/post-v0.1-improvements`, intentionally frozen at revision-33 head `efc21268b8c075bd8b8d5ff3726d4548cb6b88e7` until the hardening candidate passes target-Mac preflight
- Pre-acceptance hardening branch: `audit/preacceptance-hardening`
- Hardening code head: `b09e49b15478588dfbd42ee44ef8a70d5f34e07a`
- Parent release PR: #7 (DRAFT)
- Host protocol: 5
- Hades II module protocol: 5
- Desired-state schema: 3
- Profile schema: 4
- Hades II resident Lua revision on the hardening candidate: **35**
- Target game build last audited: Hades II 1.139672 / Steam build 24556151

## Phase 0 hardening state

The interrupted pre-acceptance audit was recovered before final manual testing. It contains 15 commits on top of the previously frozen revision-33 release head and is zero commits behind that head.

The hardening candidate retains all revision-33 behavior and additionally fixes demonstrated release-path problems:

- force-Legendary / force-Duo hotkey feedback now reports enabled when the parent boon-rarity runtime is already active, deferred only when it is actually deferred, and disabled when turned off;
- a failed `/usr/bin/pgrep` query no longer masquerades as game termination or destroys an existing debugger/session state;
- the Hades run-log watcher is idempotently re-armed after a successful connect so a first-ever launch cannot permanently miss lifecycle events when the log directory appears late;
- current Profile shortcut payloads preserve forward-compatible action IDs without backend-side ordering/deduplication decisions;
- macOS CI now runs the complete contract suite rather than two hand-picked harnesses;
- stale Hades Lua hooks are session-owned. Revision 34 made a hook from an old `SessionState` ineligible as a current hook;
- revision 35 rebinds the session-scoped game-speed hook after an App.Reset without dividing the already-applied process/global factor against a newly-created Hero;
- application termination now cleans dormant and desired runtime state as well as state already reported active;
- corrupt staged-restore transaction markers are quarantined instead of poisoning every future save-manager scan;
- global hotkey event-handler installation failure is surfaced to the UI instead of silently accepting registrations that cannot fire;
- orphaned Lua mock harnesses that were outside the active test runners were removed rather than carried as false coverage.

No periodic LLDB/Lua polling, second same-PID debugger attachment, automatic replay of non-idempotent mutations, or game-specific Core/Host semantics were introduced.

## Verification evidence

Revision 33 previously passed the full target-Mac build/package/signing gate and produced:
- `~/Downloads/MacGamingTrainer-0.1-build2-rc-r33.zip`
- SHA256 `b65af9d99221399dd561b54aec479abb4919d9e55828539c0ab75af6204ad4cc`

That artifact is now **superseded for final acceptance** because the recovered hardening audit contains runtime and lifecycle fixes. It may be retained only as a comparison artifact.

Targeted RED→GREEN regression evidence exists on the hardening branch for the fixes above. The effective hardening diff has been re-reviewed for lifecycle/replay boundaries and Ponytail scope; no additional Critical/Important code finding is currently open.

Exact hardening head `b09e49b15478588dfbd42ee44ef8a70d5f34e07a` was also pushed temporarily through the release branch solely to trigger hosted CI. Four independent jobs reproduced issue #16 before step 0:
- push Linux: run 35436986992;
- push macOS: run 35436986984;
- PR Linux: run 35436988750;
- PR macOS: run 35436988751.

Every affected job has `steps=null` and `logs_url=null`. These runs provide no code-test result. The release branch was restored to the frozen revision-33 head after the probe.

## Target-Mac preflight — PASS

Fresh target-Mac preflight passed on the hardening branch after recovering the interrupted audit work:

- `bash Tools/run_linux_checks.sh`: PASS / `linux_checks_ok`;
- `bash Tools/run_macos_checks.sh`: PASS / `macos_checks_ok`;
- two consecutive clean `./build.sh hades2` builds: PASS;
- CFBundleShortVersionString = `0.1`;
- CFBundleVersion = `2`;
- packaged game-module count = `1`;
- packaged Hades runtime revision = `35`;
- executable = Mach-O 64-bit `arm64`;
- `com.apple.security.cs.debugger` entitlement present;
- `codesign --verify --deep --strict`: PASS on both clean builds;
- Git working tree remained clean after both builds.

The final revision-35 acceptance RC is built from the final pre-acceptance handoff head after this evidence-only documentation update. Its exact HEAD, byte size and SHA256 are recorded in PR #7 / the Phase 0 issue comments rather than committed into this file, avoiding an artifact-hash self-reference commit.

Revision-33 RC remains superseded and MUST NOT be used for final PASS.

## Manual acceptance after preflight

Acceptance must cover:
1. background launch and automatic connection;
2. first save entry and two same-process main-menu → save re-entries without the previous multi-second recovery stall;
3. at least one persistent modifier verified by actual gameplay effect, not UI color alone;
4. active / deferred / disabled hotkey sounds, including force-Legendary or force-Duo while boon-rarity control is already active;
5. shortcut list/default order 1-9 then A-Z with explicit overrides preserved;
6. automatic state/indicator recovery after re-entry and no second debugger attach / `attach_denied`;
7. native boon selling;
8. direct-add and native special three-choice paths;
9. God Mode Hecate polymorph + Mourning Fields miasma blocking without suppressing ordinary player/self-selected effects;
10. preserved `trainer.log` for the complete run.

## Phase 0 issues

- #1: OPEN until target-Mac acceptance.
- #11: OPEN until target-Mac acceptance.
- #16: OPEN; hosted Actions startup/admission failure.
- #17: OPEN, non-blocking; partial hand-edited schema-4 Profile shortcut conflict has a proven fix on `fix/profile-shortcut-partial-conflict` and is deferred until after Phase 0.
- PR #7: OPEN/DRAFT; do not merge to `main` before hardening preflight + manual acceptance + healthy hosted CI.
- PR #10: keep DRAFT and do not synchronize with the hardening candidate until Phase 0 is finalized.

## Non-regression constraints

- No periodic LLDB/Lua polling.
- No unsafe replay of outcome-unknown non-idempotent mutations.
- No game-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Exit must never be permanently blocked by cleanup failure.
- Runtime source changes require a revision bump.
