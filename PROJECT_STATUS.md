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
- Hades II resident runtime revision: 42.
- Hades II desired-state schema: 4.
- Host protocol: 5. Hades II module protocol: 5.
- Target reference: Hades II 1.139672 / Steam build 24556151.
- Core Save Management remains optional cross-game infrastructure; Hades save codec/schema/edit semantics remain Hades-owned.
- The permanent `reference_fixture` remains the executable proof that a second module does not require Hades-shaped Core APIs.

## Verification baseline

The latest behavior-changing lifecycle head before squash merge was:

`0418cb3666518d47bed5f507fc8a9ff6cf72c5dd`

Fresh exact-head CI on that tree:

- Linux contracts `35552079532`: PASS;
- module build matrix `35552079488`: Hades II + reference fixture + package isolation PASS;
- Build 2 macOS `35552080294`: full macOS contracts/build/package PASS.

PR #45 was squash-merged as `646a707163f6d7b8cd7a31fe759c8e3bd126da0b` on top of governance merge `62d77423abc6a68aae8b7733a11abf0749c2e8c4`.

Documentation-only cleanup may advance `main` after that behavior baseline. Always query the current remote HEAD before making or verifying a new change.

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

- Repository `main` currently has no enforced branch protection/ruleset. CI exists but can still be bypassed by repository settings; enabling required checks remains recommended.
- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

These are not feature freezes. Promote them only when new evidence or requirements justify work.

## Historical evidence

Historical material is evidence only and must not be used as current instructions:

- `docs/audits/2026-09-21-ai-development-governance.md` — system map, debt/test audit and governance rationale;
- `docs/audits/2026-09-21-full-repository-audit-round2.md` — earlier full repository audit;
- `docs/audits/2026-09-21-pre-feature-deep-audit.md` — earlier deep-audit bug lineage;
- `docs/audits/2026-09-21-post-merge-linux-review.md` — earlier exact-source review evidence.

Do not reopen those audit scopes without a new user request or new code evidence.
