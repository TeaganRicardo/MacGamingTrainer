# Deferred work after v0.17.11

The framework-level corrective refactor and the first runtime-reliability pass are complete. Do not resume structural refactoring unless a concrete requirement demonstrates a missing host capability. See `NEXT_PHASE_TODO.md` for the stabilization gate and prioritized execution plan.

## 0.1.x — Persistence & protocol integrity

- strict preferences/profile schema validation and migration
- corrupt-file quarantine + safe defaults
- atomic/fsync persistence with write failures surfaced to UI
- stricter Hades Swift state decode (missing vs invalid)
- shared protocol fixtures/contracts across Python and Swift

## v0.19.x — Transport safety

- distinguish definite failure from outcome-unknown after LLDB/Lua execution
- classify read-only / idempotent-set / non-idempotent action commands
- prohibit unsafe automatic retry of unknown non-idempotent outcomes
- make diagnostics genuinely read-only
- tighten `set_desired` failure semantics

## v0.20.x — Second-game integration proof

Add a small permanent reference module that exercises state, mutation, action, reconnect, error handling and shared Host/UI without touching Core/App/build. Add a target-mac validation script for semantic build/link/codesign/app/backend launch.

## v0.21.x — Hades-local cleanup

Only after the reliability/protocol layers are stable:

- reduce `Hades2Model.swift` by actual responsibilities
- split large Hades content sections where useful
- modularize `runtime/hades.lua` only after a multi-file loader is proven against the target game
- replace LLDB transport only after an alternative survives real target-Mac regression

## Framework rule

Do not introduce another generic feature/stat/resource abstraction solely from Hades II requirements. Framework changes require evidence from an independent game/module requirement.
