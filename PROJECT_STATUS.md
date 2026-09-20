# MacGamingTrainer Project Status

Updated: 2026-09-21

This is the canonical development handoff. Historical plans, closed PRs and old branches are evidence only; current code, this file and roadmap issue #8 are execution authority.

## Current baseline

- Default branch: `main`.
- Current fully audited baseline: `c2c4f39ffe5c943c76f2190c458d4ece384f6513` (PR #41), on top of corrected baseline `ee258442f89a1e3ad4cb04f02bbfc7146488e148` (PR #42) and deep-audit merge `f1eacae8d8c52605e5d87317a59ddd208aad662a` (PR #40).
- Verified pre-squash audit product-code SHA: `d3e4385054aaeddcad4c9ef10cdc1dbaea9dd8a4`.
- Full repository audit round 2 is closed; the audit freeze is cleared.
- Hades II resident runtime: revision 42.
- Hades II module protocol: 5.
- Target game baseline: Hades II 1.139672 / Steam build 24556151.
- Process Time Warp + mapped speed slider remain shared Host/Core infrastructure.
- Core Save Management remains cross-game optional; Hades save semantics remain module-owned.
- Permanent `reference_fixture` continues to prove second-module isolation.

## Pre-feature deep audit

Segments A-G are complete. Detailed evidence is in:
`docs/audits/2026-09-21-pre-feature-deep-audit.md`.

Confirmed Important fixes in PR #40:

1. Host preserves one deferred target-exit refresh when the game exits while a backend request is busy, preventing stale connected UI state.
2. Any Lua `outcome_unknown` result-read failure taints the LLDB transport; later Lua mutations require restart instead of continuing on an uncertain session.
3. Core Save cold restore rechecks target-process state before real-save mutation and stages instead of writing through a stale stopped decision if the game launches.
4. Save restore / staged restore fail closed across SIGTERM -> `KeyboardInterrupt`, explicit rollback failure and hard-loss indeterminate states; an uncertain `.applying-*` claim is never downgraded to ordinary auto-retry.
5. One-shot next-room reward intent is versioned with a durable token and resident consumption receipt so an already-consumed reward cannot resurrect after backend restart.
6. A durable desired-state write error no longer prevents best-effort resident runtime teardown; the persistence error is still surfaced.
7. Remaining bespoke Hades number/primary-action styling was replaced with existing shared UI components; no new shared abstraction was introduced.

Runtime source changed for item 5, so resident revision was bumped 41 -> 42. Desired-state schema was bumped 3 -> 4.

## Verification gate

PR #40 deep audit is verified and merged.

Final tested product-code SHA:
`d3e4385054aaeddcad4c9ef10cdc1dbaea9dd8a4`

Merged baseline:
`f1eacae8d8c52605e5d87317a59ddd208aad662a`

Deep-audit evidence:
- Linux contracts `35526120496`: PASS.
- Module build matrix `35526120549`: Hades II + reference fixture + package isolation PASS.
- Build 2 macOS `35526120497`: full contract suite, Hades II build, package verification and RC artifact PASS.
- independent container Linux contracts: `linux_checks_ok`.

The requested post-merge Linux code review is also complete. Exact reviewed main source was `c2fe74c2dc6fd42bea48f40878e3c2ba760eb10b`, materialized by workflow run `35526388178` with commit marker and verified source SHA256.

Post-merge review evidence:
- exact-main `Tools/run_linux_checks.sh`: PASS;
- all 85 `tests/test_*.py` attempted: 81 PASS on Linux, 4 platform-only AppKit/Darwin failures;
- those same four platform-only tests: PASS in Build 2 macOS `35526120497`;
- Backend compileall: PASS;
- all Swift source files frontend-parse: PASS;
- Python duplicate-definition scan: PASS;
- conflict-marker / risky execution primitive / ownership / polling scans: no Critical/Important finding.

Detailed record:
`docs/audits/2026-09-21-post-merge-linux-review.md`.

The post-merge review found one additional Important defect and PR #42 fixed it: Save Manager now completes unavailable-backend requests with failure, so optimistic rename state and sequential batch-delete flows cannot be stranded.

PR #42 verification:
- Linux contracts `35527279524`: PASS;
- module matrix `35527279475`: Hades II + reference fixture + package isolation PASS;
- Build 2 macOS `35527279464`: full suite/build/package/artifact PASS, including the backend-stopped rename regression.

Corrected-main re-review of `ee258442...`:
- snapshot/Linux workflow `35527702078`: PASS;
- exact source artifact commit marker matched `ee258442...`;
- container Linux contracts: PASS;
- 81/81 Linux-portable tests: PASS;
- 47/47 Swift source files frontend-parse: PASS;
- compileall, duplicate-definition, conflict-marker, risky-execution, session-ownership, Core/Hades boundary and no-polling scans: PASS.

Full repository audit round 2 found one additional Important Save recovery-discoverability defect. PR #41 repaired and merged it; merged-main verification is complete.

## Repository / architecture audit result

- No unique unmerged MacGamingTrainer product behavior was found in historical feature/fix branches.
- Historical divergent SHAs are predominantly squash-merged/superseded evidence, not missing code.
- `ci/lidkeep-rc1-build` is unrelated repository contamination and must never merge into main.
- The current connector does not expose safe branch deletion; do not work around this using container GitHub access or RDC.
- Core/Host remains free of Hades business semantics.
- App/Host/Hades share one `TrainerBackendSession`; no duplicate backend-session owner was found.
- Shared UI/Input owns generic visual/registration behavior; Hades owns game actions/state meaning.
- Native modal commands remain one-shot and are not durable preference replay entries.

## Minor non-blocking hardening notes

- Some Core file-renames do not parent-directory fsync after `os.replace`; this is an extreme power-loss durability ceiling, not a demonstrated logical corruption/replay bug.
- Hades local Profile storage does not currently apply the same explicit subdirectory symlink guard as Core Save storage. It runs with the same user authority and no privilege boundary; retain as future local-filesystem hardening unless a concrete failure requires change.

## Current product gate

**Hades II save-editor design — no binary save mutation is approved yet.**

Boundary remains:
- Core owns generic snapshot/restore/rollback/staged-restore infrastructure.
- Hades II owns save codec/schema, field validation, edit semantics and game-specific editor UI.
- no Hades save-field semantics enter Core/Host;
- automated editor tests use temporary fixtures only, never the user's real Hades II save tree.

The previously researched Hades II codec references remain candidates only; no third-party codec/dependency is integrated.

The round-2 audit gate is closed. Hades II Save Editor design may resume. Implementation still requires an approved design; no binary save mutation is approved by the audit itself.

## Permanent constraints

- GitHub connector is the authoritative remote-repository interface.
- Container is for materialized local editing/diffing/non-macOS tests; do not depend on direct container access to github.com.
- RDC is macOS-only validation and never repository/file transport.
- Tests must never mutate real user/game data.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-PID recovery.
- No replay of outcome-unknown non-idempotent/native-modal operations.
- No Hades-specific business semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never destroy the last recoverable copy.
- Runtime source changes require a resident revision bump.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256 when manual QA is required.
- Fix demonstrated/root-caused failures with RED -> GREEN coverage.


## Full repository audit round 2

Detailed report:
`docs/audits/2026-09-21-full-repository-audit-round2.md`

New Important finding:
- if backend termination interrupts rollback itself, Core preserves the trainer-owned `.rollback-*` bytes but a restarted Save Manager previously had no persistent way to discover them;
- PR #41 exposes only contained non-symlink rollback directories as generic Core recovery evidence and shows them in the shared Save Manager;
- no automatic restore/delete behavior is introduced.

First repair CI:
- Linux `35528506356`: PASS;
- module matrix `35528506352`: PASS;
- Build 2 macOS `35528506442`: PASS.

Final tested product/test head:
`d4b1bbb1d5215b59e95ebae46cf021def16657c8`

Final merge-candidate CI after temporary workflow cleanup:
- Linux `35528849520`: PASS;
- module matrix `35528849519`: PASS;
- Build 2 macOS `35528849516`: PASS, including exhaustive AppKit/Darwin tests, build, package verification and RC artifact.

PR #41 squash-merged as `c2c4f39ffe5c943c76f2190c458d4ece384f6513`.

Merged-main verification:
- Linux `35529062370`: PASS;
- module matrix `35529062382`: PASS;
- Build 2 macOS `35529062368`: PASS, including exhaustive tests, build, package verification and RC artifact.

The PR final tree and merged-main tree are identical. No Critical or Important round-2 finding remains open.
