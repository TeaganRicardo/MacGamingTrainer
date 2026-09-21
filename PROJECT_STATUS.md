# MacGamingTrainer Project Status

Updated: 2026-09-21

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; planned work lives in roadmap issue #8; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- The mandatory audit freeze is **closed**. Normal bug-fix and user-selected feature work may resume.
- PR #43 (independent full-audit continuation) is superseded and closed; it is not an execution requirement.
- Governance PR #44 is merged. It added exhaustive Linux-portable test discovery, diff-based Hades resident-runtime revision enforcement, the low-context agent entrypoint and stable engineering-invariant authority.
- Lifecycle PR #45 is merged. Target-process presence and connection-lifetime validity are now distinct: exit/new-lifetime invalidation survives busy work and rapid replacement launches instead of leaving stale `connected=true`.
- PR #57 is merged. The Hades II consumable census now closes at 91/91 concrete `ConsumableData` targets classified: `SeedMysteryDrop` and `MixerMythicDrop` were recovered as direct pickups, while weapon-owned `LobAmmoPack` is explicitly excluded.
- Hades II resident runtime revision: 44.
- Hades II desired-state schema: 4.
- Host protocol: 5. Hades II module protocol: 5.
- Target reference: Hades II 1.139672 / Steam build 24556151.
- Core Save Management remains optional cross-game infrastructure; Hades save codec/schema/edit semantics remain Hades-owned.
- The permanent `reference_fixture` remains the executable proof that a second module does not require Hades-shaped Core APIs.

## Verification baseline

The latest behavior-changing Hades consumable-census head before squash merge was:

`28d4b779f6d95f7a1f15e7e00530b221844902c2`

Fresh exact-head CI on that tree:

- Linux contracts `35588010831`: PASS;
- module build matrix `35588010870`: Hades II + reference fixture + package isolation PASS;
- Build 2 macOS `35588010825`: full macOS contracts/build/package PASS.

Build 2 artifact `10633691034` has digest `sha256:6c32a24402a4d55d10a71be73c20d2afa11fb283f8acde7c2434a26f5573a900`. Static package inspection confirmed resident revision 44 and the recovered `SeedMysteryDrop` / `MixerMythicDrop` reward rows.

PR #57 was squash-merged as `31c1f1ecc956d5fe94a274cb99045cc4948ca766`.

Real Hades II acceptance for resident revision 44 is still pending. The CI and package evidence above prove contracts/build/package, not final in-game behavior.

Documentation/CI-only cleanup may advance `main` after that behavior baseline. Always query the current remote HEAD before making or verifying a new change.

## Current development gate

There is no mandatory repository-wide audit before ordinary work.

For the next task:

1. confirm current `main` HEAD;
2. create a focused branch;
3. read the subsystem code and nearest behavior tests;
4. preserve the ownership/replay/safety contracts in `ENGINEERING_INVARIANTS.md`;
5. use RED -> GREEN for demonstrated correctness defects;
6. run the applicable Linux/module/macOS gates on the final changed SHA.

Hades II Save Editor is not implicitly authorized by lifting the audit freeze. If selected as a product task, its binary mutation design still requires a separate explicit design/safety approval.

## Known non-blocking risks

- Repository `main` is protected by required checks. Docs-only changes keep the same required check names but use a fast path: when every changed path is under `docs/` or ends in `.md`, the heavy Linux/module/macOS work is skipped.
- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

These are not feature freezes. Promote them only when new evidence or requirements justify work.

## Historical evidence

Historical material is evidence only and must not be used as current instructions.

The retained repository-level synthesis is:

- `docs/audits/2026-09-21-ai-development-governance.md` — system map, debt/test audit and governance rationale.

Older round/version diffs, validation transcripts, completed implementation plans/specs and superseded audit reports were removed from the current tree because Git history and closed PRs already preserve them. Recover them from Git only when investigating a specific historical cause.

Do not reopen historical audit scopes without a new user request or new code evidence.
