# CI and build provenance policy

Standing CI, PR routing, toolchain selection and build provenance rules live here rather than in [GAME_MODULES.md](../../GAME_MODULES.md), which owns the Core/game module contract.

## Workflows and Action pinning

Standing CI workflows pin third-party Actions to immutable commit SHAs. The inline upstream tag comment is the update breadcrumb: resolve the intended upstream release/tag to its commit, review that release change, and replace the SHA plus comment together before rerunning the exact-head gates.

The three required pull-request check contexts are `backend-contracts` (`Linux contracts`), `build` (`Build 2 macOS`), and `build (reference_fixture)` (`Module build matrix`). Missing or skipped checks are never treated as passing gates; the macOS check contexts stay active as fast-path jobs when their platform work is unnecessary, and unclassified diffs fail closed.

## PR routing and build modes

`Tools/ci_docs_only.py` owns PR diff classification (`docs_only`, `needs_linux`, `needs_macos`, `needs_module`, `needs_build`, `needs_full_build`):

- Documentation-only changes run `Linux contracts` without launching macOS compilation.
- Portable backend logic and contracts run in `Linux contracts` (`Tools/run_linux_checks.sh`, using `Tools/discover_linux_tests.py`).
- Ordinary Swift/AppKit changes run selected macOS smoke tests (`Tools/select_macos_pr_tests.py` / `Tools/run_macos_checks.sh --pr`) and shared `--typecheck` preflight (`./build.sh --typecheck --all`), which compiles and typechecks all declared product modules cleanly without linking, signing or packaging an executable.
- Entrypoint, native-library, packaging, module-manifest and build-tool changes retain the full optimized, linked and signed product build (`./build.sh --all`). Mixed changes choose the stricter mode.
- Shared Core/Host/module/build boundary changes also trigger the `reference_fixture` lane in `Module build matrix` (`.github/workflows/module-build-matrix.yml`); game-owned frontend changes do not require duplicate isolated builds. A module-matrix workflow change exercises its reference lane and `Linux contracts` without forcing an unrelated unified product build.
- Both build paths in `build.sh` print `MGT_BUILD_TIMING` phase lines so optimization decisions rely on measured CI/build timings rather than adding new always-on jobs.

## Convergence, isolated modules, and direct release

Full macOS test inventory, full-matrix isolated module builds (`.github/workflows/module-build-matrix.yml`), mutation audits (including anchor validation), and retained release-candidate ZIP packaging/provenance/checksums run on exact-SHA release/convergence dispatch (`workflow_dispatch`). Every full build and isolated matrix build (`build.sh` plus workflow verification in `.github/workflows/build2-macos.yml` and `.github/workflows/module-build-matrix.yml`, including full-build and `reference_fixture` PRs) runs package and code-signature verification (`codesign --verify --deep --strict` and `Tools/verify_module_build.py`). Separately, a nightly `Build 2 macOS` schedule on `main` runs full contracts, the mutation audit, and unified build/package verification for earlier signal without packaging release artifacts or provenance. Merged `main` does not repeat PR checks except during intentional release preparation.

The direct-release coordinator runs on Linux and verifies the retained macOS-generated artifact and recorded toolchain rather than consuming another macOS runner while waiting for convergence.

## Toolchain selection

Workflows read the CI Python version from `.python-version` (kept aligned with `Tools/python_runtime.json`, while `[tool.mypy]` and `[tool.ruff]` share the `3.10` static-check floor in `pyproject.toml` because runtime Backend scripts execute under Xcode Python 3.9). macOS runner labels, `DEVELOPER_DIR` and native build/test profile selection come from `Tools/macos_toolchain_identity.py` (which `tests/macos_fixture_policy.py` imports directly) and are verified on each macOS build, while build provenance records the actual hosted runner image version because GitHub updates hosted images in place. Convergence provenance also hashes the producer workflow source so immutable Action inputs remain directly attributable to the artifact.

External CI test dependencies are declared via `MGT_PREREQUISITES` or `module.json` (`buildRequirements.testPrerequisites`) and installed from `Tools/ci_prerequisites/<name>.sh`. Game-owned generators, profilers and profiler fixtures under `Tools/games/<id>/` stay outside `BUILD_INPUT_TOOL_PATHS` in `Tools/ci_docs_only.py` and run as portable tooling unless a macOS test declares them.

## Build provenance and verification

- `Tools/write_build_provenance.py` owns artifact and sidecar naming and the derivation of packaged-content claims. Its local mode requires a clean source checkout; GitHub mode runs on the `workflow_dispatch` packaging step on a macOS runner and records that workflow run and toolchain.
- `Tools/verify_build_provenance.py` is the shared QA and release consumer for that manifest (do not duplicate its schema assertions in workflow YAML). It requires the retained ZIP and re-derives the App bundle identity, Python runtime and resident runtime claims from it through the same owner; a matching artifact digest alone never certifies packaged content.
- `ContractFixtures/reference_module` temporary copies must match their tracked fixture sources and appear as declared generated inputs in provenance.
- For any module declaring `residentRuntime`, provenance hashes the declared Lua source and packaged ZIP member directly rather than copying digests from status prose.
- For any module declaring `supportedBuild`, provenance records a source-derived snapshot checked against the manifest on the exact same SHA.

## Governance policy

Prefer one behavior test at the owning interface over recurring global scans. Do not add new gate code without an escaped defect or a proven cross-cutting responsibility that local behavior tests cannot protect; when an owner subsumes an old pin or tombstone, delete the superseded check rather than keeping both active.
