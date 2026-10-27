# Versioning

MacGamingTrainer has one app-level product version in Semantic Versioning `MAJOR.MINOR.PATCH` form and one monotonically increasing macOS bundle build number.

Current release metadata has one source of truth: `Info.plist`.

- `CFBundleShortVersionString` is the product SemVer.
- `CFBundleVersion` is the positive-integer build identity.

Do not copy either current value into documentation, workflows, module manifests, protocol fixtures, or source constants. Consumers should read them from the plist when needed.

Git commit SHA is the authoritative identity of development source. Product SemVer identifies a release line; the build number distinguishes distributable bundle iterations; SHA identifies the exact source.

## Development workflow

Ordinary feature, fix, refactor, catalog, and documentation PRs do not edit `Info.plist` merely because they may be included in a later release. This keeps parallel branches from competing over the same version lines.

Root-cause refactors are classified by product-contract impact, not by diff size or number of seams crossed. A larger internal refactor does not by itself require a MINOR/MAJOR bump; governance-only changes do not change product version.

When a release is deliberately prepared:

1. choose PATCH, MINOR, or MAJOR from the rules below if the product release changes;
2. increment `CFBundleVersion` for the new distributable build;
3. use one focused release-preparation PR for those metadata changes;
4. run the normal release/build gates on that exact SHA;
5. after the release commit is on `main`, publish the exact source and retained artifact under the immutable release tag determined below.

If the same product SemVer needs another distributable build after an earlier build was already used or uploaded, keep `CFBundleShortVersionString` unchanged and increment only `CFBundleVersion`. Its release uses the immutable `vMAJOR.MINOR.PATCH+bBUILD` tag, leaving the original `vMAJOR.MINOR.PATCH` release unchanged. The direct-release workflow rejects non-increasing bundle build numbers across all official three-part release tags, including new product SemVer lines, and refuses to overwrite existing tags. The historical `v0.1` tag is outside this newer naming scheme.

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

## Supported game builds and references

Each native game module declares its exact supported image in `Backend/games/<id>/module.json.supportedBuild`. This is **game compatibility identity**, independent of MacGamingTrainer's `Info.plist` product version:

- `architecture`, `uuid` (Mach-O UUID), `steamBuildID`, `originalExecutableSHA256` and game-owned `referenceDirectory` identify the verified native image and its research input.
- `bundleVersion` is used for games with a verified application bundle version. `contentBuildInfo` identifies a verified game-content build without inventing a bundle version. Exactly one applies.
- Optional `nativeUUIDHeader` declares a derived C header, generated by `python3 Tools/supported_build.py --write-native-header <game-id>` and checked against the manifest. Symbol RVAs and function prefixes remain in `symbols.json`; its duplicated version/UUID fields are removed.
- Packaged assets can use `@supportedBuild/<relative-file>` in `appResources.source`. The build-tool owner resolves the reference directory; the packaged source still has a deterministic SHA. Other raw native offsets remain supported-image-specific evidence and must be reviewed for every new game build.

The repeatable update sequence, source-capture requirements and generated-reference steps are in [Supported game build update](docs/development/supported-game-build-update.md).

Updating a supported **game** build is an explicit compatibility change. Verify the real executable version/Steam manifest/UUID/SHA from the source image, inspect ABI/symbol offsets and source signatures, refresh snapshot-backed reference data and generated C header, then run `Tools/supported_build.py` and the owning verification lanes when testing is authorized. A matching UUID/header is only one necessary check; it never certifies unverified offsets or game behavior. Frozen historical evidence is not rewritten to pretend it belongs to the newer image.

Production code, tests, artifact provenance, terminology loading and CI build routing read those game identities from the module owner. A new module chooses its own supported-build identity, but receives no independent product SemVer until separate distribution exists. Version-only governance does not advance `CFBundleVersion`, which changes with the next intentional distributable build.

## Release identity

- First release of a product SemVer uses `vMAJOR.MINOR.PATCH`; subsequent independently published builds of that same SemVer use `vMAJOR.MINOR.PATCH+bBUILD` (SemVer build metadata). Every tag stays immutable, points at its exact GitHub source commit and is published only with that source’s verified artifact, checksum and build provenance.
- The existing historical `v0.1` tag remains historical evidence; new tags use the three-part form.
- Release/test artifacts include product SemVer, bundle build number, and a short Git SHA.
- Completion and QA claims continue to name the exact tested SHA and actual CI/runtime evidence.
