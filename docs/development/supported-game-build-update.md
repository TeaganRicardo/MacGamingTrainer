# Supported game build update

This runbook updates **native game compatibility**, not the MacGamingTrainer product version. The only mutable supported-image identity for a module is `Backend/games/<id>/module.json.supportedBuild`. Keep every superseded native source snapshot and its existing hashes as historical evidence.

## Identify and preserve the input

1. Capture the untouched original game executable before Trainer preparation or patching. Record its SHA-256, exact Mach-O UUID for the game architecture, Steam appmanifest build ID and the game's real bundle or content build identifier. Do not infer a bundle version for a game that only exposes content build information.
2. Preserve the actual game source/text tree and a file-hash manifest. Store any new research/reference snapshot under the owning game in `docs/reference/<id>/`; do not overwrite a frozen earlier-build snapshot. Name the new directory from the actual source build only when a versioned directory is useful.
3. Verify the new image's ABI, symbol RVAs/signatures and native C/Lua offsets against the captured original. A matching UUID or a regenerated header does not verify these addresses.

## Update the owning module and its dependents

4. Edit only `Backend/games/<id>/module.json.supportedBuild` for the verified `architecture`, `steamBuildID`, `uuid`, `originalExecutableSHA256`, `referenceDirectory`, and exactly one of `bundleVersion` / `contentBuildInfo`. Keep `symbols.json` limited to offsets and signatures.
5. Rebuild native reference-backed resources from the **new** source. For Hades I, regenerate `Backend/games/hades/catalog.json` using `python3 Tools/generate_hades_catalog.py --content <captured-Content> --lua <Lua-interpreter> --output Backend/games/hades/catalog.json`, and inspect native source hashes and catalog scope before accepting changes. For Hades II, rebuild `ui_terminology.json` in the new reference directory, revalidate other snapshot-driven references, and regenerate Save identities using `Tools/generate_hades_save_ids.py` when their source owners change. Verify the resulting field semantics and independent native evidence rather than copying new version literals into implementation code.
6. If the module declares `nativeUUIDHeader`, run `python3 Tools/supported_build.py --write-native-header <id>`. Review the generated header diff and rebuild every affected native library. Never manually edit the generated UUID bytes or preserve old native offsets under the new game identity without verification.

## Validate and hand off

7. Run `python3 Tools/supported_build.py` and `python3 Tools/validate_game_module.py --all`; these check the manifest, game-owned catalog/reference identity and generated headers. When testing is authorized, run the owning portable tests, the selected macOS/module build gates and any native/game test needed to verify the changed ABI and behavior. Use temporary save trees for write tests. Avoid repeated intermediate CI pushes.
8. Fix inconsistent native catalog/reference metadata at its generator or actual source, not by weakening the drift check. A changed game image is **unverified** until symbols, offsets and relevant behavior are proven. Record the precise source SHA, game build identifiers, reference hashes, generated data, checks performed and remaining acceptance work in the owning issue/PR.
9. Do not change `Info.plist` merely because the supported **game** build changes. App product SemVer/build and release tags advance only in a separate deliberate release process as defined in `VERSIONING.md`.
