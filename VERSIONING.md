# Versioning

MacGamingTrainer has one app-level product version in Semantic Versioning `MAJOR.MINOR.PATCH` form and one monotonically increasing macOS bundle build number.

Current release metadata has one source of truth: `Info.plist`.

- `CFBundleShortVersionString` is the product SemVer.
- `CFBundleVersion` is the positive-integer build identity.

Do not copy either current value into documentation, workflows, module manifests, protocol fixtures, or source constants. Consumers should read them from the plist when needed.

Git commit SHA is the authoritative identity of development source. Product SemVer identifies a release line; the build number distinguishes distributable bundle iterations; SHA identifies the exact source.

## Development workflow

Ordinary feature, fix, refactor, catalog, and documentation PRs do not edit `Info.plist` merely because they may be included in a later release. This keeps parallel branches from competing over the same version lines.

When a release is deliberately prepared:

1. choose PATCH, MINOR, or MAJOR from the rules below if the product release changes;
2. increment `CFBundleVersion` for the new distributable build;
3. use one focused release-preparation PR for those metadata changes;
4. run the normal release/build gates on that exact SHA;
5. after the release commit is on `main`, tag the exact released commit as `vMAJOR.MINOR.PATCH`.

If the same product SemVer needs another distributable build after an earlier build was already used or uploaded, keep `CFBundleShortVersionString` unchanged and increment only `CFBundleVersion`.

Transient CI builds do not consume build numbers. Their exact source identity is the Git SHA included in the artifact name.

Do not pre-bump the next product version after a release. Until another release is prepared, Git SHA identifies newer development state.

## Release increments

### PATCH — `X.Y.Z+1`

PATCH is the default release increment for compatible maintenance:

- bug fixes and correctness repairs;
- catalog, localization, or game-data corrections;
- performance and reliability improvements;
- compatibility adjustments that preserve the existing product capability contract;
- internal refactors included in a distributable build.

Docs-only changes and intermediate development commits do not require a version bump by themselves. Increment PATCH when a new distributable maintenance release is deliberately cut.

### MINOR — `X.Y+1.0`

MINOR is for backwards-compatible product expansion:

- a meaningful new user-facing trainer feature or workflow;
- a new supported game module;
- a substantial new Host capability exposed through the product;
- a material product expansion that deserves its own release line.

Reset PATCH to zero when MINOR changes.

While the product remains in the `0.x.y` pre-stable series, an intentionally incompatible experimental redesign may also advance MINOR rather than declaring `1.0.0`. Document the compatibility break explicitly.

An internal Host/module protocol change does not by itself require a product MAJOR or MINOR bump when Host and bundled modules migrate together and no external compatibility contract is broken.

### MAJOR — `X+1.0.0`

`1.0.0` is the first deliberate stability milestone: established user-facing behavior, persisted user data, and any externally relied-on integration surfaces are considered stable enough that incompatible changes require migration or an explicit major release.

After `1.0.0`, advance MAJOR for deliberate incompatible product-contract changes such as:

- dropping compatibility with persisted preferences/profiles/snapshots without an automatic migration;
- breaking an externally relied-on automation, data, or integration interface;
- removing or redefining established product behavior in a way that requires users to adapt;
- breaking a future independently distributed module interface without a compatible migration path.

Reset MINOR and PATCH to zero when MAJOR changes.

## Host, module, and internal revisions

Product SemVer belongs to the shipped MacGamingTrainer app as a whole. Host and game modules do not receive separate product SemVer values while modules are built and distributed together with the app.

Independent compatibility revisions remain integers with narrower meanings:

- Host protocol version: JSONL envelope/request compatibility owned by Core.
- Module `protocolVersion`: per-module frontend/backend compatibility. Different modules may use different values.
- Manifest, persistence, preference, profile, and save schema versions: migration/serialization contracts.
- Hades II resident runtime revision: resident Lua source/runtime identity and acceptance discipline.

These values advance only when their own contract changes. They do not mirror product SemVer and do not automatically force a particular SemVer increment.

If game modules later become independently installable or independently updateable, introduce module-level SemVer at that point together with an explicit supported Host compatibility range. Do not add module SemVer before that seam exists.

## Release identity

- Release tags use `vMAJOR.MINOR.PATCH`.
- The existing historical `v0.1` tag remains historical evidence; new tags use the three-part form.
- Release/test artifacts include product SemVer, bundle build number, and a short Git SHA.
- Completion and QA claims continue to name the exact tested SHA and actual CI/runtime evidence.
