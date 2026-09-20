# Historical deferred-refactor notes after the 0.1 baseline

This file is retained as architecture history. It is not a current execution queue.

Current execution authority is:
- `PROJECT_STATUS.md`;
- roadmap issue #8;
- current code and tests.

Several items that were deferred when this note was written have since been completed:

- LLDB attach latency profiling was completed and issue #4 was closed with a measured baseline.
- the permanent non-production `reference_fixture` now exists and continuously proves the second-game module boundary in tests and CI.
- strict Profile/persistence envelopes, corrupt-file quarantine, atomic durable writes, typed Hades payload boundaries and protocol fixtures remain established.
- Process Time Warp, shared Host UI/input infrastructure, lifecycle hardening and the first Core Save Management hardening pass are integrated.

## Potential future cleanup

These are candidate cleanups only when a concrete requirement or reproduced defect justifies them:

- make diagnostics read-only at the Lua/runtime level if current diagnostics can be shown to mutate runtime state;
- improve explicit debugger ownership recovery if externally-held debugger sessions produce a reproducible failure that current recovery cannot handle;
- reduce `Hades2Model.swift` or other large Hades-local files only along demonstrated responsibility boundaries;
- modularize `runtime/hades.lua` only after a multi-file loader is proven against the real game.

## Framework rule

Do not introduce another generic feature/stat/resource abstraction solely from Hades II requirements. Framework changes require evidence from an independent game/module requirement.
