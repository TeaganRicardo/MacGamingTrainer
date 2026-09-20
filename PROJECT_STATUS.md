# MacGamingTrainer Project Status

Updated: 2026-09-20

This is the canonical development handoff. Historical implementation plans are not execution authority; use current code, open issues/PRs, and retained design specs.

## Current baseline

- Default branch: `main`.
- Audited main head before this maintenance slice: `f15a26252b8c383a5d208e4f20b87bf93d8a89e0` (`merge: integrate core save management`).
- Hades II resident runtime: revision 41.
- Hades II module protocol: 5.
- Target game baseline used by the current runtime contracts: Hades II 1.139672 / Steam build 24556151.
- PR #21 integrated the generic Process Time Warp controller/native helper and mapped speed slider.
- Core/Host save management is integrated into `main`; Hades II declares the generic save capability through `module.json`.
- Save management is Host/Core-owned. Game modules own game-specific save declaration/provider semantics.

## Verification status

Previously accepted slices retain their recorded evidence in merged PRs and design/test history. This file does not restate RC-by-RC history.

The current `main` contains changes newer than the r40/r45 handoff documents, including Core Save Management. A fresh consolidated exact-main Linux/macOS verification is therefore required before treating the present baseline as a release candidate.

Hosted GitHub Actions admission failures remain tracked by issue #16. A job that fails before step 0 is infrastructure evidence, not a code-test PASS or FAIL.

## Active work, in order

1. **Repository hygiene**
   - remove obsolete execution plans and the duplicate `NEXT_PHASE_TODO.md`;
   - keep this file as the single current handoff;
   - close superseded PRs;
   - delete obsolete remote branches when a supported ref-deletion interface is available.
2. **Cross-game isolation proof — PR #10**
   - `architecture/reference-module-proof` contains unique Phase 1 work and must be retained;
   - it is based on an older Core boundary and must be synchronized with current `main`;
   - rerun the isolation/module/package contracts against Time Warp + Save Management before merge.
3. **Shortcut partial-profile collision — issue #17**
   - retained branch: `fix/profile-shortcut-partial-conflict`;
   - integrate only after rebasing/revalidating against current `main`.
4. **Trainer Host feedback sounds**
   - keep enabled/deferred/disabled feedback generic and Host-owned;
   - preserve post-result semantics; do not move Hades-specific state into Core.
5. **Attach / world-readiness stutter — issues #1 and #11**
   - trace LLDB attach cost separately from Lua/world-ready recovery;
   - preserve same-PID single-attachment recovery;
   - no periodic LLDB/Lua polling.
6. **Save-editor expansion / Hades I**
   - proceed only after the cross-game boundary has been re-proven on the current architecture.

## GitHub state

- PR #10: OPEN / DRAFT — `architecture/reference-module-proof`; retain and resynchronize.
- PR #19: CLOSED as superseded by merged PR #21.
- PR #21: MERGED — Process Time Warp + mapped slider.
- Issue #1: OPEN — lifecycle/manual-acceptance umbrella.
- Issue #11: OPEN — same-PID attach/readiness performance.
- Issue #16: OPEN — hosted Actions fail before step 0.
- Issue #17: OPEN — partial schema-4 shortcut-profile collision.

## Branch hygiene

Retain:
- `main`;
- `architecture/reference-module-proof` (PR #10);
- `fix/profile-shortcut-partial-conflict` (issue #17);
- the short-lived maintenance branch while this cleanup is under review.

Delete after confirming no unique required work:
- `audit/preacceptance-hardening`;
- `feature/game-speed-r41-integration`;
- `feature/generic-speed-control-ui`;
- `feature/mapped-speed-slider`;
- `feature/post-v0.1-improvements`;
- `feature/process-time-warp-host`;
- `fix/batch-a-native-modals`;
- `fix/batch-b-runtime-semantics-r40`;
- `fix/special-choice-native-r39`;
- `fix/special-choice-refresh-r38`;
- `refactor/save-management`;
- `spike/generic-process-time-warp`;
- `spike/generic-process-timewarp`;
- `ci/lidkeep-rc1-build` (unrelated LidKeep CI transport branch).

Do not delete a branch that still holds required unique work merely because it is old. GitHub history/merged PRs remain the historical record.

## Permanent constraints

- GitHub connector is the authoritative remote-repository interface.
- The development container is for materialized local editing, diffing and non-macOS tests; do not depend on direct container access to github.com.
- RDC is only for macOS-specific build/runtime validation and never for large repository/file transfer.
- Tests must never mutate real user/game data; destructive filesystem tests require explicit temporary roots.
- Target-Mac save-sensitive suites keep a before/after hash sentinel on the Hades II save tree.
- No periodic LLDB/Lua polling.
- No second debugger attachment for same-PID runtime recovery.
- No replay of outcome-unknown non-idempotent mutations or native modal commands.
- No Hades-specific semantics in Core/Host.
- Native modal commands are one-shot and never preference-replayed.
- Save restore must never make a declared save root disappear.
- A failed rollback must preserve the last recoverable copy.
- Runtime source changes require a resident revision bump.
- Each tester handoff is one exact HEAD + one prebuilt signed App/ZIP + SHA256.
- Fix demonstrated/root-caused failures with RED -> GREEN coverage.
