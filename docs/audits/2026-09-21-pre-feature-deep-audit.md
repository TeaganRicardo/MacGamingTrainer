# Pre-feature deep audit

Updated: 2026-09-21

Branch: `audit/pre-feature-deep-review-20260920`
Baseline main: `efa14e984dd619cc1db859047fe986469838d27f`
Verified code baseline: `9b15d8393918ceab8de89688d1d08dcaef89dfa1`

## Segment A — repository and evidence integrity

Status: in progress.

### CI baseline

Exact merged-code verification for `9b15d839...` was rechecked:

- Linux contracts run `35515313374`: success.
- Module matrix run `35515313389`: Hades II success; reference fixture success.
- Build 2 macOS run `35515313401`: full contract suite/build/package artifact job success.

`Tools/run_macos_checks.sh` enumerates `tests/test_*.py`, so every repository test file is part of the exhaustive macOS contract gate. Linux contracts intentionally run a curated cross-platform subset.

### Remote branch classification

#### Fully contained by main

These branches are strictly behind main with no unique files in the compare result:

- `audit/preacceptance-hardening`
- `feature/generic-speed-control-ui`
- `feature/post-v0.1-improvements`
- `fix/batch-a-native-modals`
- `fix/batch-b-runtime-semantics-r40`
- `fix/special-choice-native-r39`
- `fix/special-choice-refresh-r38`
- `refactor/save-management`
- `spike/generic-process-time-warp`
- `spike/generic-process-timewarp`

#### Squash-merged / absorbed by current main

The branch graph still reports divergence because the feature work was squash-merged or superseded by later commits, but the branch commit intent/file sets are represented on main:

- `architecture/reference-module-proof`, `architecture/reference-module-proof-v2` -> `d084f383...`
- `feature/game-speed-r41-integration`, `feature/mapped-speed-slider`, `feature/process-time-warp-host` -> `8d99d743...`
- `fix/append-only-shared-trainer-log` -> `4eab391e...`
- `fix/proactive-runtime-reset-bootstrap` -> `72d8c8c0...`
- `fix/defer-launch-runtime-probe` -> `07493f1b...`
- `fix/deferred-log-availability-guard` -> `b65126df...`
- `fix/profile-shortcut-partial-conflict-v2` -> `7471edf9...`
- `fix/save-rollback-recovery-path` -> `347480ac...`
- `fix/save-storage-root-containment` -> `40f73d79...`
- `fix/save-empty-error-code` -> `dc565f59...`
- `fix/invalid-snapshot-row-sanitization` -> `9b15d839...`

The Save hardening branch commit subjects match the corresponding squashed main commit bodies exactly, including their RED -> GREEN test/fix sequence.

#### Superseded and must not be restored

- `fix/profile-shortcut-partial-conflict`: first implementation of the Profile collision fix. The v2 branch deliberately replaced it and v2 is what main contains.
- `maintenance/current-status-20260920`
- `maintenance/status-after-lifecycle-fixes`
- `maintenance/status-after-log-qa`
- `maintenance/status-after-save-hardening`

The maintenance branches contain only older `PROJECT_STATUS.md` states. Current canonical status is newer.

- `maintenance/repo-hygiene-20260920`: historical cleanup work represented by `2fbb747e...` and subsequent status commits.

#### Unrelated repository contamination

- `ci/lidkeep-rc1-build`: contains LidKeep workflow/source payloads and is unrelated to MacGamingTrainer product code. It must never be merged into main.

### Documentation conflicts found

1. `REFACTOR_ASSESSMENT.md` referenced deleted `NEXT_PHASE_TODO.md` as a current source.
2. `DEFERRED_REFACTOR_PLAN.md` also referenced deleted `NEXT_PHASE_TODO.md`.
3. `DEFERRED_REFACTOR_PLAN.md` described LLDB attach profiling issue #4 as future work even though issue #4 was measured and closed.
4. The same file described the reference fixture as future work even though it is now a permanent tested module.

These stale execution pointers were corrected on the audit branch. The documents are now explicitly historical and defer current authority to `PROJECT_STATUS.md` and roadmap issue #8.

### Current conclusion

No unique unmerged MacGamingTrainer product behavior has been found in historical remote branches so far.

Physical deletion of stale refs is not attempted because the current connector exposes no branch-delete mutation; repository transport policy forbids working around that through container network access or RDC.

### Remaining Segment A checks

- inspect remaining current-root documentation for contradictory execution authority;
- verify workflow triggers and build/test source selection against the current module contract;
- materialize an exact source snapshot for local non-macOS test execution if a supported GitHub/CI source transport is available;
- record the final Segment A verdict before moving to framework-boundary review.
