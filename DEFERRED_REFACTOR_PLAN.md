# Deferred work after the 0.1 baseline

The corrective refactor and reliability work that produced the 0.1 baseline are complete. Do not resume broad structural refactoring unless a concrete requirement demonstrates a missing host capability.

Current execution status and the Build 2 stabilization gate live in `PROJECT_STATUS.md` and `NEXT_PHASE_TODO.md`.

## 0.1.x — Transport and persistence hardening

Already established:
- strict versioned desired-state/Profile envelopes;
- corrupt-file quarantine and safe defaults;
- atomic durable writes with surfaced failures;
- typed Hades Swift payload boundary;
- host protocol fixtures;
- outcome-unknown protection for non-idempotent mutations.

Still deferred:
- make diagnostics genuinely read-only at the Lua/runtime level rather than only suppressing host-side adoption/replay/persistence;
- measure and then optimize LLDB attach latency (#4);
- improve explicit process/debugger ownership recovery for externally-held debugger sessions.

## Second-game integration proof

Add a deliberately small permanent reference module only when needed to prove framework boundaries. It should exercise state, mutation, action, reconnect, error handling and shared Host/UI without modifying Core/App/build.

## Hades-local cleanup

Only after reliability and measured performance are stable:
- reduce `Hades2Model.swift` by real responsibility boundaries;
- split large Hades content sections where useful;
- modularize `runtime/hades.lua` only after a multi-file loader is proven against the real game.

## Framework rule

Do not introduce another generic feature/stat/resource abstraction solely from Hades II requirements. Framework changes require evidence from an independent game/module requirement.
