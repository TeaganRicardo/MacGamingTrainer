# Next development stage

The v0.17.x line accumulated enough corrective work that the next stage should optimize for **stability, observable behaviour and contract integrity**, not new framework abstractions. Hades II is the behavioural reference implementation; a second game will later be used to prove the framework boundary.

## P0 — Stabilization gate for 0.1

### Runtime performance budget

- Add a request-level performance ledger for LLDB/Lua boundary operations (command, duration, outcome) without introducing automatic status polling. **Working tree: implemented in `trainer.log`; target-Mac timing validation still pending.**
- Define a hard rule: background UI maintenance must never cross the live Lua/debugger boundary unless the user explicitly asked for a live operation.
- Add regression checks for accidental periodic `status`, `scan`, save-list refresh or reconnect loops. **Working tree: repeating-timer contract added; the staged-restore watcher is the sole allowed repeating Hades timer and may only issue its guarded process `scan`.**
- Separate UI-local loading state from backend-global `busy`; no sidebar/sheet should flash or become unusable because an unrelated request is active.

### Hades functional acceptance matrix

Create a compact manual target-Mac checklist and keep it release-blocking for the functions that cannot be proven on Linux mocks:

- connect/reconnect after 10–60 s LLDB attach
- God/health/mana/cast/hex/ammo toggles
- multiplier/stat/resource locks across room transitions
- all Spawn families, including Selene/Chaos/special NPC traits and room-reward consumables
- next-room override before exits appear and after exits are already materialized
- save backup/restore/staged restore
- Crossroads-safe editors and desired-state activation when entering a run

For every regression, first identify whether the failure is Swift state, backend command routing, transport, or Lua runtime; do not patch multiple layers speculatively.

### Catalog contracts

- Treat game-owned runtime tables (`RewardStoreData`, `LootData`, `ConsumableData`, `UnitSetData`, localization SJSON) as authoritative wherever practical.
- Keep a curated presentation order only as an overlay; do not use a hand-maintained allow-list as the sole source of truth.
- Add catalog diagnostics: discovered count, hidden/unsupported count, unresolved localization count.

## P1 — 0.1.x Persistence & protocol integrity

- strict preferences/profile schema validation and versioned migration
- corrupt-file quarantine + safe defaults
- atomic/fsync persistence with surfaced write errors
- typed distinction between missing / null / invalid fields in Hades Swift state decode
- shared protocol fixtures/contracts across Python and Swift
- one-shot state (for example next-room override) must have explicit owner and consume semantics; desired-state overlay must never resurrect consumed runtime state

### Unreleased working status (not target-Mac accepted)

The current post-v0.17.11 working tree has completed only the Linux-testable
parts below; it remains versioned as v0.17.11 / Build 34 until target-Mac
acceptance is available again.

- nested desired-state lock maps are normalized before replay, including safe
  migration of integral legacy floats such as `12.0 -> 12`
- desired-state and profile writes use same-directory atomic replacement with
  a pre-rename file `fsync`; persistence failures are surfaced as
  `persistence_failed` instead of being logged-and-ignored
- desired-only mutations persist before becoming the in-memory owner, so a
  failed write cannot continue into the live Lua boundary
- the generic JSONL router rejects non-JSON-safe adapter results and unsafe
  error-state payloads; the server loop has a final serialization fallback so
  one malformed module reply cannot terminate the backend process
- corrupt desired-state files and corrupt Profile envelopes are moved out of
  the live JSON namespace with unique `.corrupt-*` names before safe defaults
  are used; if an existing desired-state cannot be read or a corrupt file cannot
  be quarantined, the store becomes write-protected for that backend lifetime so
  the preserved file cannot later be mistaken for first-run state and overwritten
- current-schema Profile shortcut payloads normalize duplicate/invalid
  assignments into a deterministic unique 0-9 layout using the same swap
  semantics as the Swift editor; Profile compatibility migrations are no longer
  retained in the current product path
- a localization lookup made before the game path exists no longer caches an
  empty result for the rest of the backend lifetime
- desired-state and Profile documents are explicitly versioned. Desired-state
  schema `3` uses canonical `forceLegendary` / `forceDuo` fields. Live durable
  state still migrates older documents conservatively: v2's force semantics are
  mapped exactly from its temporary `allow*` field names, while v0/v1's literal
  allow/filter semantics reset both force controls off. Retired boon-choice-count
  state is no longer part of the current schema. Profile files are current-schema-
  only (schema 3) and are not migrated for compatibility. Unknown desired schemas
  remain preserved/read-only with `unsupported_schema` rather than being
  quarantined or overwritten
- a newer desired-state schema is distinct from "no preferences yet": status
  reads may still connect and inspect runtime state, but the adapter will not
  adopt, replay or save defaults through the protected file
- Profile envelopes validate their exact current top-level contract, embedded
  name/file identity, timestamp/container types and requested save input types.
  Old/future Profile schemas are excluded from list/load without migration; an
  explicit same-name save atomically replaces them with the current format, and
  explicit deletion remains allowed
- `ContractFixtures/host_protocol_v5.json` is now the language-neutral Host v5
  request/reply fixture consumed by Python router tests (hello, success,
  duplicate replay/conflict, typed module error and invalid params); Swift
  XCTest consumption of the same file remains target-Mac follow-up work

Profile nested desired-state semantics intentionally do not get a second schema
inside `profile_service.py`: `Hades2PreferenceStore.normalize()` remains the
single Hades semantic normalizer, and `Adapter.load_profile()` canonicalizes the
payload before it can become the durable/live desired owner. Still open here:
Swift missing/null/invalid decode and executing the shared Host fixture through
Swift/XCTest. Local Swift/UserDefaults shortcut uniqueness recovery remains
separate from the normalized Profile wire path.


### Dev1-dev5 necessity audit

The post-v0.17.11 work is not treated as uniformly release-critical. Directly
reproduced/data-loss defects (nested preference validation, surfaced durable-write
failure, corrupt-file isolation, localization cache recovery, JSONL serialization
containment) remain required fixes. Schema forward-protection, the boundary
ledger, Profile envelope checks and shared protocol fixtures are defensive
hardening/contract work: retained because their runtime cost is small and they
cover named TODO risks, but they should not justify further duplicate validation
layers. In particular, Profile desired semantics stay single-sourced in the
preference normalizer, and explicit deletion is not blocked merely because a
Profile was written by a newer schema.

### Dev7 — user-reported gameplay/catalog/UI fixes (working, target-Mac pending)

- Retired the visible boon-choice-count control. Current game data fixes
  `ScreenData.UpgradeChoice.MaxChoices` at 3, so the Trainer no longer presents
  a setting that suggests additional visible choices are supported. (Dev8 later
  removes the retired wire/API chain entirely.)
- Dev7 initially reused the legacy `allowLegendary` / `allowDuo` field names for
  explicit **force eligible Legendary / force eligible Duo** actions. Dev8 removes
  that semantic alias from the current product contract and uses canonical
  `forceLegendary` / `forceDuo` names end-to-end. With the controls off, native
  Legendary/Duo generation is left untouched. With a control on,
  the resident runtime asks the game's own `GetEligibleUpgrades` pipeline for
  the current legal pool and replaces a normal native choice without increasing
  the native three-choice count. The sub-controls are disabled in UI while the
  parent boon-rarity control is off so an enabled-looking-but-inactive state
  cannot be created.
- Bumped the resident Hades runtime revision to 23 for this gameplay slice.
  (Dev8 later supersedes this with Hades module protocol v5 / runtime revision 24.)
- Changed manual Selene `SpellDrop` spawn to the native room-reward shape:
  `SpawnRoomReward(... RewardOverride = "SpellDrop" ...)`. This intentionally
  enters the game's generic room-reward/CreateConsumableItem path, which accepts
  LootData, loads packages, runs `SetupEvents`/`PregenerateSpells`, and preserves
  `OpenSpellScreen`/gift interaction metadata. Real-game interaction is still a
  release-blocking target-Mac check.
- Inventory resource presentation now prefers the game's own
  `ScreenData.InventoryScreen.ItemCategories` as the grouping/order source
  (Resources / Garden / Gifts / Fish), then appends uncategorized/future
  ResourceData entries in `ResourceDisplayOrderData` order. Swift now preserves
  the runtime `sortOrder` instead of discarding it and groups matching sections
  globally rather than only when adjacent.
- Spawn catalog presentation carries runtime `sortSection/sortGroup/sortOrder`
  through typed Swift state and sorts explicitly before grouping, so localization
  or filtering cannot accidentally reorder semantic families. Official SJSON
  DisplayName remains the item-label source when available; display cleanup now
  strips all brace-delimited Hades presentation/control markup before UI output.
  Special traits without an official local name remain hidden instead of exposing
  raw internal IDs.
- Shared feature switches can now use the same phase tint as their associated
  icon/indicator (purple active/pending, warning tint for waiting/mismatch);
  native off-state remains the normal system off appearance. Session metric cards
  keep the same total vertical padding but use top 6 / bottom 8 to compensate for
  the previously top-heavy optical spacing.

Target-Mac checks required before release: Selene spawned-object interaction and
spell screen; forced Legendary/Duo across several gods and prerequisite states;
Inventory/Spawn visual grouping with the installed Chinese localization; session
card optical centering; switch/icon warning-state tint.

### Dev8 — global host cleanup/performance/layout (working, target-Mac pending)

This slice intentionally moves cross-game concerns out of Hades-specific code:

- Module manifests now declare the target process/bundle identity and the
  generated game descriptor carries it into the shared Host. `TrainerHostView`
  owns a global `TrainerTargetProcessMonitor` driven by NSWorkspace
  launch/activate/terminate events. There is no periodic process poll: game
  launch and each foreground activation provide bounded automatic-connect
  opportunities while the Trainer remains in the background. The app no longer
  explicitly calls `NSApp.activate(ignoringOtherApps:)` just to make connection
  possible.
- Backend crash/timeout/send/protocol failures enter a bounded shared recovery
  path (maximum two automatic restarts). If that session-level recovery exhausts
  while the target is still alive, the shared Host retains one event-driven
  fallback restart opportunity and consumes it only after recovery is no longer
  busy. Game launch/foreground activation can also bootstrap a missing backend;
  a recovered backend then produces one fresh connect opportunity. None of these
  paths use a repeating timer, and timed-out/non-idempotent actions are never
  replayed. Explicit debugger detach suppresses automatic reconnect for that
  target-process lifetime; a real target restart or explicit reconnect clears
  the suppression. Queue overload remains a normal user-facing error rather
  than triggering process churn.
- Hades module protocol is now v5 and resident Lua revision 24. Retired external
  surfaces (`set_boon_choice*`, `spawn_boon`, `add_resource`) are removed end to
  end. Runtime-only `set_feature`, `set_boon_rarity` and
  `set_next_room_reward` remain adapter↔Lua implementation details rather than
  public module commands. Profile compatibility migrations are intentionally
  removed: list/load accept only the current Profile schema, while explicit
  same-name save/delete remains user-controlled. Current Profile schema is v3;
  current desired-state schema is v3. The current Hades v5 wire contract uses
  `forceLegendary` / `forceDuo` rather than the retired `allow*` aliases.
- Shared UI now owns page geometry, connection status chrome, section headers,
  row chrome and sheet scaffolding through `TrainerTheme`, `TrainerRow`,
  `TrainerSection/Header` and `TrainerSheetScaffold`. Hades pages consume these
  primitives rather than owning independent 760×740 sizing, 28px sheet margins
  or duplicate connection cards. This is the contract future game modules inherit.
- Backend stdout parsing advances a cursor and compacts once per read batch; the
  shared log sink retains its file handle/formatter. Hades now pays the ~159 KB
  Lua bootstrap cost once per debugger connection/PID rather than before every
  command: the first verified status synchronizes revision 24, then subsequent
  LLDB requests send only the short resident-module dispatch expression. A new
  debugger connection or game PID always forces a full bootstrap again, so this
  optimization does not weaken revision/self-repair checks.
- The resident Lua runtime caches static resource/boon/spawn catalog shape, and
  the adapter requests the Boon/Spawn catalog only until it has captured a
  complete copy. Later status replies keep all dynamic resources, locks,
  capabilities and session state live while the adapter preserves the cached
  catalog in its authoritative state. The catalog dependencies are definition
  and ordering tables (`LootData`, `ConsumableData`, `RewardStoreData`,
  `UnitSetData`, `TraitData`, Codex/Inventory ordering), not per-run eligibility.
  The hot `AddResource` hook likewise uses the cached resource allow-map instead
  of rebuilding the full Inventory catalog for each resource event.

Target-Mac release blockers: semantic Swift build/link/codesign, verify that a
foreground Hades II instance can auto-connect without focusing the Trainer,
verify crash/timeout recovery reconnects cleanly, and visually inspect the shared
Host/page/sheet geometry. The Dev7 gameplay checks remain release-blocking as
well.

## P1 — v0.19.x Transport safety

- classify commands as read-only, idempotent set, or non-idempotent action
- distinguish definite failure from outcome-unknown after LLDB/Lua execution
- prohibit automatic retry of outcome-unknown non-idempotent actions
- keep diagnostics genuinely read-only **Working tree only suppresses host-side adopt/replay/save/consume on the diagnostics status call. The resident Lua `dispatch("status")` still enters `synchronize()`, so a strict transport/Lua read-only snapshot remains open and should not be claimed complete without a Lua/runtime change plus target-Mac validation.**
- tighten `set_desired`/deferred activation semantics and surface exact activation state without polling
- add explicit process/debugger ownership recovery for `already being debugged` cases

## P2 — v0.20.x Second-game integration proof

Add a deliberately small permanent reference game module that exercises:

- scan/connect/disconnect
- typed state decode
- one toggle, one numeric mutation and one non-idempotent action
- reconnect/error handling
- shared sidebar/shell/theme/components
- manifest-driven build/package requirements

Acceptance criterion: adding it changes only the new game module + manifest. `Sources/Core`, `Backend/core`, `Sources/App.swift`, `Backend/core/server.py` and `build.sh` remain untouched.

Also add a target-Mac validation script that performs semantic Swift build/link, app packaging/codesign, backend launch and a module handshake.

## P3 — Hades-local cleanup after reliability is stable

- split `Hades2Model.swift` by actual responsibility only where it reduces state coupling
- split large Hades page sections without recreating visual primitives locally
- consider multi-file Lua organization only after a loader is proven inside the real game runtime
- remove obsolete historical migration shims only when their covered behaviour exists in newer current-contract tests (the stale `tests/legacy` compatibility suite was removed in Dev8 after v5/revision-24 coverage replaced it)

## Explicit non-goals

- no new generic feature/stat/resource framework derived solely from Hades II
- no periodic live-status polling to keep decorative UI state fresh
- no UI redesign during architectural refactors
- no transport replacement until a candidate survives real target-Mac regression
