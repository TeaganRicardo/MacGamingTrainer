# MacGamingTrainer Project Status

Updated: 2026-09-24

This is the canonical current-development handoff. It records present state only. Stable engineering rules live in `ENGINEERING_INVARIANTS.md`; release/version rules live in `VERSIONING.md`; planned work and sequencing live in planning issue #124; historical audit evidence lives under `docs/audits/`.

Start every development thread at `AGENTS.md`.

## Current state

- Default branch: `main`.
- The mandatory audit freeze is closed. Normal bug-fix and user-selected feature work may proceed.
- Hades II resident runtime revision: 49.
- Hades II desired-state schema: 4.
- Host protocol: 5. Hades II module protocol: 5.
- Target reference: Hades II 1.139672 / Steam build 24556151.
- The target-build Hades II catalog/reference census lives under `docs/reference/hades2/1.139672-24556151/`; the closed consumable, loot, and trait-facing census results are retained there rather than duplicated here.
- Core Save Management remains optional cross-game infrastructure; Hades save codec/schema/edit semantics remain Hades-owned.
- `ContractFixtures/reference_module` remains the executable proof that a second module does not require Hades-shaped Core APIs.
- Current product release metadata is owned only by `Info.plist`; do not duplicate its current values in status documentation.

## Verification baseline

The latest behavior-changing Hades resident source accepted in the real game is the terminology-normalization PR #112 head:

`6239a770e9a2e3d39d01e9562a8a6a0817bbd2db`

It merged as `a394f2b8eb1170a5085d1e3ac05433e9d78df476`; both commits have the same tree `6a50cab32dc7cf36b08c34eddac474efea52c4c8`.

Exact-head automated evidence:

- Linux contracts `35789142588`: PASS;
- module build matrix `35789142544`: PASS;
- Build 2 macOS `35789142529`: macOS contracts, Hades II build, package verification and RC packaging PASS.

Real Hades II acceptance for resident revision 49 is complete against artifact `10721008543`, digest `sha256:c605bde145f4547611560c52de02647e0237ba01a0fec3b7b6975c817c2bfb1a`.

Documentation, repository-governance, and build-metadata cleanup may advance `main` after that behavior baseline without changing the resident acceptance status. Always query current remote `main` before new work.

## Current development gate

There is no mandatory repository-wide audit before ordinary work.

For each task:

1. confirm current `main` HEAD;
2. create one focused branch/PR;
3. read the owning production files and nearest behavior tests;
4. preserve the contracts in `ENGINEERING_INVARIANTS.md`;
5. use RED -> GREEN for demonstrated correctness defects;
6. run the applicable Linux/module/macOS gates on the final changed SHA.

Hades II Save Editor is not implicitly authorized by lifting the audit freeze. If selected as a product task, its binary mutation design still requires separate explicit design/safety approval.

## Known non-blocking risks

- Docs-only changes keep the normal required check names but use the repository fast path instead of running heavy Linux/module/macOS work.
- Some Core filesystem metadata updates do not parent-directory fsync after every atomic replace. This is an extreme sudden-power-loss durability ceiling, not a demonstrated normal-operation corruption bug.
- Hades Profile storage does not mirror every Core Save subdirectory-symlink containment guard. It runs with the same user authority and has no demonstrated exploit/data-loss path.

These are not feature freezes. Promote them only when new evidence or requirements justify work.

## Historical evidence

Historical material is evidence only and must not be used as current instructions.

The retained repository-level synthesis is:

- `docs/audits/2026-09-21-ai-development-governance.md` — system map, debt/test audit, and governance rationale.

Closed PRs and Git history preserve completed implementation detail. Do not add new round handoffs, audit-continuation files, or duplicate status documents for ordinary development.
