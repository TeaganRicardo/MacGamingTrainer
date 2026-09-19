# Hades II Background Auto-Attach Implementation Plan

Goal: make Hades II attach/become ready without foregrounding Trainer while avoiding periodic debugger/Lua probes.

## Implemented

- [x] Direct LLDB boundary on `sgg::World::Update(float)`; no `lua_pcallk` breakpoint.
- [x] Event-driven Hades II.log watcher with truncation/replacement-safe incremental reads.
- [x] Main-menu detection uses `Loading package: MainMenu.pkg`; `World::Stop()` is not treated as main menu.
- [x] Runtime reset detection covers App.Reset / Lua interface destruction.
- [x] A true process launch may consume the bounded background-connect opportunity.
- [x] Ordinary activation/Alt-Tab does not create a new debugger attach opportunity.
- [x] Same-PID Lua-generation recovery stays in the existing debugger attachment.
- [x] Persistent desired state recovery is batched into one Lua/LLDB execution.
- [x] Host policy + Hades log watcher harnesses exist.
- [x] Linux/macOS verification passed for the revision-32 integrated candidate.
- [x] #1/#11/PR #7 document the exact manual acceptance gate.

## Current closure state

Revision 33 was added during interrupted-session audit for a separate native special-choice source-identity bug. That change invalidates the revision-32 RC as a final acceptance artifact.

Before target-Mac acceptance:
- [ ] exact revision-33 final head passes Linux contracts;
- [ ] exact same head passes macOS Build 2;
- [ ] replacement RC is produced and recorded;
- [ ] PR #7 / #1 / #11 point to that exact head/artifact.

Manual Phase 0 acceptance remains the only lifecycle closure gate. Do not add timer polling, a second debugger attachment, or automatic replay of non-idempotent commands.
