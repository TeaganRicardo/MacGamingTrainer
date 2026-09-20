# MacGamingTrainer Project Status

Updated: 2026-09-21

This is the canonical development handoff. Historical plans, closed PRs and old branches are evidence only; current code, this file and roadmap issue #8 are execution authority.

## Current baseline

- Default branch: `main`.
- Latest main observed by the pre-feature audit: `6e1069dd9ff69283f132b5edfacf07d638db3160`.
- Active audit candidate: PR #40, `audit/pre-feature-deep-review-20260920`.
- New product features remain frozen until PR #40 closes its final verification gate.
- Hades II resident runtime in the audit candidate: revision 42.
- Hades II module protocol: 5.
- Target game baseline: Hades II 1.139672 / Steam build 24556151.
- Process Time Warp + mapped speed slider remain shared Host/Core infrastructure.
- Core Save Management remains cross-game optional; Hades save semantics remain module-owned.
- Permanent `reference_fixture` continues to prove second-module isolation.

## Pre-feature deep audit

Segments A-F are complete. Detailed evidence is in:
`docs/audits/2026-09-21-pre-feature-deep-audit.md`.

Confirmed Important fixes in PR #40:

1. Host preserves one deferred target-exit refresh when the game exits while a backend request is busy, preventing stale connected UI state.
2. Any Lua `outcome_unknown` result-read failure taints the LLDB transport; later Lua mutations require restart instead of continuing on an uncertain session.
3. Core Save cold restore rechecks target-process state before real-save mutation and stages instead of writing through a stale stopped decision if the game launches.
4. Save restore / staged restore fail closed across SIGTERM -> `KeyboardInterrupt` and hard-loss indeterminate states; no interrupted staged restore is guessed/replayed automatically.
5. One-shot next-room reward intent is versioned with a durable token and resident consumption receipt so an already-consumed reward cannot resurrect after backend restart.
6. A durable desired-state write error no longer prevents best-effort resident runtime teardown; the persistence error is still surfaced.
7. Remaining bespoke Hades number/primary-action styling was replaced with existing shared UI components; no new shared abstraction was introduced.

Runtime source changed for item 5, so resident revision was bumped 41 -> 42. Desired-state schema was bumped 3 -> 4.

## Current verification gate

Final PR #40 verification is still pending at the time of this status update.

The audit branch was re-compared with main and was `ahead`, `behind=0`, with merge base equal to current main `6e1069dd...`; no upstream product-code conflict was present.

Evidence already obtained during the final cycle:
- Linux contracts on `b5f63ca...`: PASS.
- Module build matrix on `b5f63ca...`: PASS.
- macOS Build 2 on `b5f63ca...` progressed through the full suite until a stale test-only schema assertion; the production-path tests before it passed.
- the stale schema assertion was corrected in `304d8597...`.

Before merge:
1. remove the temporary audit-source workflow from the branch;
2. obtain fresh Linux, module-matrix and macOS Build 2 PASS on the final non-temporary tree;
3. update the audit report with exact final evidence;
4. perform final whole-diff review;
5. merge PR #40 only if no Critical/Important finding remains.

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

## Next product gate after audit merge

**Hades II save-editor design — no binary save mutation is approved yet.**

Boundary remains:
- Core owns generic snapshot/restore/rollback/staged-restore infrastructure.
- Hades II owns save codec/schema, field validation, edit semantics and game-specific editor UI.
- no Hades save-field semantics enter Core/Host;
- automated editor tests use temporary fixtures only, never the user's real Hades II save tree.

The previously researched Hades II codec references remain candidates only; no third-party codec/dependency is integrated.

After PR #40 merges, first run the requested fresh exact-main Linux code review from a CI source snapshot. Only after that review is clean should save-editor design/implementation resume.

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
