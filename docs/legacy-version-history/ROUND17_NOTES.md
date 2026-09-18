# Round 17 — Runtime Reliability

Version: **0.17.0**  
Build: **23**  
Host protocol: **v5 (unchanged)**  
Hades II module protocol: **v4 (unchanged)**  
Lua runtime revision: **19 (unchanged)**

Round 17 is deliberately a reliability pass. It does not add trainer features, change the Hades wire schema, or introduce another framework abstraction layer.

## Core runtime

- Added per-request timeouts to `BackendClient`; timeout starts only when a request is actually dispatched, not while queued.
- A timeout is treated as an **unknown backend outcome**: current + queued requests fail, the backend is stopped, and no automatic retry is attempted.
- Added a hard request queue limit (default 64). Coalescing can still replace an already-queued request without consuming another slot.
- Fixed reply-completion ordering: completion callbacks can enqueue follow-up work, but cannot jump ahead of requests that were already queued.
- Added strict stdout protocol failure handling. Invalid/non-object JSON or an unbounded line now fails outstanding work and stops the backend instead of silently leaving the UI busy.
- Unknown request IDs remain non-fatal and are ignored; a later correct reply can still finish the active request.
- Added a bounded stdout buffer (1 MiB production default).
- `BackendProcess.stop()` now escalates from terminate to `SIGKILL` after a grace period if a worker refuses to exit.
- Send/dispatch failure is terminal for the current backend instance; queued commands are not attempted against a broken pipe.

## Hades II request policy

Hades owns game-specific timeout policy instead of Core knowing command names:

- scan/status: 4 s
- connect/disconnect: 12 s
- launch: 10 s
- signature prepare/restore: 30 s
- backup/restore/file operations: 15 s
- diagnostics/export: 15 s
- normal mutations: 6 s

## Delayed mutation ordering

- Replaced ad-hoc `[String: DispatchWorkItem]` handling with `Hades2MutationScheduler`.
- Same-key edits use tokens, so replaced work cannot execute late.
- Global state barriers advance a generation and discard every pre-barrier delayed edit.
- Barrier operations include disable-all, profile load, save restore, disconnect, backend termination, process identity change, and app termination cleanup.
- Profile save uses `flushAll()` instead of discard: the latest delayed edits are submitted in user-action order before the profile-save command is queued.

This closes the race where a 350 ms delayed stat/resource/multiplier mutation could execute after `disable_all` or profile load and silently restore an old value.

## Restore/backend teardown

Unexpected backend termination now also clears:

- pending restore timer
- pending restore ID
- tracked game PID
- delayed mutations
- activation grace state

This prevents restore polling and stale process identity from surviving a crashed/restarted backend.

## New executable fault-injection tests

`tests/test_runtime_reliability_round17.py` compiles the real Swift Runtime files and drives them against a fake Python JSONL worker. It covers:

- worker hangs and ignores SIGTERM
- request timeout + forced kill
- malformed stdout JSON
- overlong stdout without a newline
- wrong request ID followed by a valid reply
- process exit with an active request
- queue overflow
- completion callback ordering relative to already-queued requests

`tests/test_hades2_mutation_scheduler_round17.py` executes the real scheduler and verifies:

- same-key replacement
- barrier invalidation
- post-barrier reuse
- ordered flush of the latest pending mutation per key
- no double execution after flush

## Explicitly deferred

Round 17 does **not** attempt the remaining audit items that belong to later rounds:

- strict preferences/profile schema validation and atomic persistence (Round 18)
- strict Swift state decoding / shared protocol fixtures (Round 18)
- LLDB outcome-unknown semantics and command idempotency classes (Round 19)
- read-only diagnostics split (Round 19)
- permanent reference second-game module and macOS integration proof (Round 20)
- Hades-local Model/View/Lua cleanup (Round 21)
