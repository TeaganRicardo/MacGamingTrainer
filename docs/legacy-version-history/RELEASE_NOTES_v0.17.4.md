# v0.17.4

App version: **0.17.4**  
Build: **27**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

## Scope

This release is intentionally UI-only. It does not change Backend, LLDB transport, Lua runtime behavior, Spawn/catalog behavior, desired-state semantics, or request timeout policy.

## Hades II visual rollback

The Hades II frontend now uses the proven pre-decoupling v0.11/v0.14.1 visual treatment again while keeping the decoupled Host/Core structure.

Restored visual details include:

- original purple accent (`0.64, 0.51, 1.0`)
- original 44×25 custom feature switch with 19×19 white knob
- original feature row/icon/shortcut spacing and panel fill
- original native small switches for compact resource multipliers and stat locks
- original stat row geometry and 90pt numeric field
- original metric cards, lock buttons, element cards and status card
- original resource editor layout and lock action presentation
- original save/diagnostics subtle fills instead of the newer raised generic cards

Hades II no longer consumes the newer generic Core visual primitives (`TrainerRow`, `TrainerToggleControl`, `TrainerMetricCard`, `TrainerLockButton`, etc.). Core remains responsible for the host shell, theme values and runtime infrastructure only.

## State colors

This UI-only rollback intentionally preserves existing state semantics. An enabled feature while detached still uses the old deferred green state; active/confirmed features use purple and waiting/mismatch states use orange. The current connection/watchdog regression will be handled separately in the next step.

## Regression protection

Added `tests/test_hades2_visual_baseline_v0174.py` to prevent later framework refactors from silently restyling Hades II again.
