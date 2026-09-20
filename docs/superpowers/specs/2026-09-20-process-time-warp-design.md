# Process Time Warp Design

**Date:** 2026-09-20

## Goal

Provide one macOS process-level Time Warp capability that game modules can reuse. Hades II is the first consumer, but the implementation must not depend on Hades Lua or game-specific frame hooks.

## Required behavior

- Trainer factor changes the game simulation clock globally, including combat, non-combat and hub scenes.
- Native game slow-motion and time-stop remain owned by the game and continue to compose with the trainer factor.
- Audio clocks are not modified.
- Changing speed is continuous: no virtual-time jump at the moment the factor changes.
- Reapplying a value never multiplies the previous factor.
- Setting 0.0 freezes the selected game clock domain without stopping the process or debugger control path.
- Setting 1.0 removes only the trainer factor.
- The helper may remain resident at 1.0; runtime unloading is deliberately out of scope.
- A backend reconnect to the same PID must discover/reuse the existing helper instead of injecting a second copy.
- A new PID gets a fresh helper instance.
- Supported numeric factor for the process capability is 0.0x-10.0x. 0.0x freezes the selected game clock domain. The UI slider exposes 0.1x-5.0x while direct numeric input retains the full process range.

## Architecture

The existing debugger remains the only injector/control channel.

1. build.sh builds and ad-hoc signs a tiny arm64 dylib into Contents/Resources/Backend/core/native/.
2. Backend/core/process_time_warp.py uses the already attached LLDB process to load the helper and call a small exported C ABI.
3. The helper uses the pinned Facebook fishhook per-image API (rebind_symbols_image) rather than a global process hook.
4. Each game module supplies an exact image-name allowlist. Initial Hades II scope is the main Hades II image only. System frameworks, CoreAudio and Steam images are not rebound.
5. The helper supports mach_absolute_time, mach_continuous_time, monotonic clock_gettime and CACurrentMediaTime. Only references imported by selected images are replaced.

## Virtual clock

The helper stores one real-time anchor, one accumulated trainer offset and one speed factor.
Returned virtual time = real domain time + accumulated offset + (real reference now - anchor) * (speed - 1).
A speed change first folds the old factor into the accumulated offset, then installs the new factor. This preserves continuity and avoids factor stacking.

## Helper ABI

- uint32_t MGTTimeWarpABI(void)
- int MGTTimeWarpInstall(const char *imageNames, size_t length, double speed)
- int MGTTimeWarpSetSpeed(double speed)
- double MGTTimeWarpGetSpeed(void)
- uint32_t MGTTimeWarpHookMask(void)

ABI version starts at 1. Install fails if no selected image imports any supported clock symbol.

## Signing

The target application is already re-signed for debugger attachment. Loading the helper additionally requires disabling library validation on that prepared debug copy. The original executable backup/restore path remains unchanged.

## Explicit non-goals

- No second IPC channel.
- No Frida runtime.
- No Dobby unless fishhook is proven insufficient on the exact target binary.
- No global rebinding of system/framework/audio images.
- No periodic LLDB polling.
- No runtime unload.