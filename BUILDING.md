# Building MacGamingTrainer 0.1

Current development branch: **0.1 / Build 2**.

The supported build path is the repository `build.sh` script:

```bash
chmod +x build.sh
./build.sh hades2
```

The build script performs Swift semantic validation before optimized compilation, then packages and signs the app. Cross-file scope errors, missing helpers and invalid type names should therefore fail before delivery.

If the LLDB Python check fails, install/select the full Xcode toolchain:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
xcrun lldb -P
```

The output app is written under `dist/`; the exact path is printed by `build.sh` after a successful build.

Version source of truth:
- product version and build: `Info.plist`;
- release/development policy: `VERSIONING.md`;
- runtime/protocol/schema status: `PROJECT_STATUS.md`.

Do not treat the historical v0.17.x notes under `docs/legacy-version-history/` as current build instructions.
