# Hades II operation phase evidence

`Tools/profile_hades2_operations.py` is an opt-in, bounded offline evidence tool.
It never launches Hades II and uses temporary native stubs, preferences, sources
and LuaTable save state. It does not read the installed game or real saves.
Production probes emit small `OperationProfile` JSON records through existing
Python logging and Host diagnostic callbacks only when
`MGT_PROFILE_OPERATIONS=1`. Log rotation, sessions, retention and export policy
remain owned by the existing diagnostic path and #454.

Run with the declared application Python runtime and Lua 5.2. `all` additionally
needs macOS/Xcode Python/LLDB and uses only a newly compiled temporary helper.
`offline` runs resident, Host/RPC, Save queries and the native clock CPU fixture;
`resident`, `end-to-end`, `save`, `time-warp` and `transport` select one workload.
Swift is needed for Host observations; an unavailable compiler is explicitly
reported as unobserved. No timing threshold is an always-on correctness gate.

```sh
python3 Tools/profile_hades2_operations.py --mode offline --samples 30 --trials 3 \
  --probe-control --baseline-ref <current-main-full-sha> --output /tmp/operation-profile.json
```

The tool writes JSON and a neighboring `.summary.txt`. Freeze/commit the harness
before collecting evidence. `source_sha` identifies the executed production
source, `harness_sha` identifies the measuring code, and both source and harness
input digests are recorded. `working_tree_changes`, `source_clean` and
`exact_head_evidence` make an uncommitted measurement explicitly provisional.
A baseline uses a temporary immutable `git archive`; its archive digest is also
recorded. Baseline source bytes are never rewritten to add probes. When measuring
pre-probe sources, external harness wrappers observe the routing/RPC totals and
native fixture phases; absent Host/serialization decomposition stays unobserved.
Matched `--probe-control` trials turn off all optional phase emitters to expose
instrumentation overhead. Enabled/disabled totals must be considered together;
phase emitters themselves are not an optimization.

| Workload | Observable phases and limits |
| --- | --- |
| Host → Backend → sidecar → resident → Host | Real BackendProcess/BackendClient/TrainerBackendSession, JSONL router/cache, Hades Adapter/resident session, generic JSONL sidecar and worker dispatch, Lua 5.2. Host admission/queue, encode/write, decode/main-queue delivery, opaque payload callback and total are separate. Application is a dictionary fixture; SwiftUI invalidation/rendering remains unobserved. |
| Resident | Default 32 resource rows plus Money, 32 live ordinary God traits, 96 exact-catalog entries, nonempty stats/elements, six enabled durable feature owners, and resource/vital/reroll/element/grasp/movement/critical locks. Cold catalogs, warm catalogs, warm status, replay and distinct one-shot edits are separate. `frame_without_desired` and `frame_with_desired` average 100 UpdateTimers calls per sample. Native stubs are inexpensive and do not model presentation/yield/engine cost. |
| Save query | Public NativeDialogueInvestigation on 1000 synthetic bilingual scenes, 5500 known-scene records and 5000 synthetic history entries. Empty, recorded-filtered, ID and bilingual-text queries use the same static save observations. Constructor cold index, changed-source refresh, warm public query and post-refresh query are independently timed. Warm queries still include the production freshness check. No Save workspace source/target/write semantics are altered. |
| Time Warp | Production native warped clock function in a private portable fixture: never enabled, active 2×, enabled then reset to 1.0. Each CPU sample averages 100000 calls after three warmups. OS clock/dyld binding stubs are explicit; real hook frequency, contention, binding and game FPS remain unobserved. |
| LLDB helper | Existing production execute/stop/boundary/drain/resume and memory/breakpoint work against a private compiled helper, three fresh attachments. Real Lua/game code and supported-game identity are absent. These timings cannot be added to offline Host totals as an end-to-end game estimate. |

Dialogue queries reuse normalized names and bilingual text for the current
candidate identities while their captured native source remains unchanged.
Save record state, ambiguity, permissions and page rows are evaluated on each
query. Removed candidates leave that query index; source replacement invalidates
it through the existing freshness/capture owner. The first query and the first
query after refresh include construction of this metadata, so keep them in the
comparison rather than reporting only already-indexed timings.

Records correlate by `request_id`; sidecar records include `method`, count and
actual UTF-8 request/reply sizes, including liveness. Fixture resident CPU phases
join the same identity. Each result is classified as a full observation or
handoff marker at the Hades owner. Current mutations emit full observations;
there are no production sparse patches to benchmark yet. Full/patch semantics
remain owned by Hades; Core treats payloads opaquely. Separate cold, warm status,
resource edit, active status and intentionally queued burst distributions appear
under `paths`. Warmup/setup requests are retained but not mixed into those paths.

All durations are local intervals, not comparable process timestamps. Nested
routing/adapter/RPC/dispatch and callback/application phases overlap and must not
be summed. CPU time, wall time, payload bytes and method counts are different
measurements. Use per-request rows when summing only disjoint serial phases.
The human summary reports median/p95; JSON retains samples and exploratory p99.

## Evidence thresholds

The report carries the same explicit thresholds used for task selection:

- Match environment, fixture scale and probe configuration. Use at least three
  independent processes and 30 warm samples per operation; compare baseline,
  candidate, baseline. Cold-only promotion needs at least five fresh processes.
- An interactive bottleneck needs p95 ≥ 5 ms and ≥ 10% of queue-excluded total in
  every trial, or a repeatable improvement ≥ 2 ms and ≥ 10%.
- A bounded low-blast owner can be investigated when its repeated disjoint
  phase sum is ≥ 1 ms and ≥ 10% of the warm operation in every trial. Stable
  duplicate counts alone do not establish a material latency bottleneck.
- A canonical JSON serialization candidate must additionally preserve the
  independent reference-module envelope/cache behavior. Liveness optimization
  must preserve authoritative disconnect, terminal unknown outcome and explicit
  recovery ownership; a timer is never justification for a retry.
- A steady-state redesign needs ≥ 0.1 ms/frame and ≥ 10% measured CPU difference
  at the actual target call/frame frequency. Offline stub clock/UpdateTimers
  numbers cannot meet this real-target evidence gate. Values at the timer floor
  are non-actionable; p99 below 100 samples is exploratory.

No benchmark result establishes real-game FPS acceptance. If later attached
measurement is warranted, hand the user one exact build/checksum and a short
procedure to capture ordinary status/mutation operations and compare never-enabled,
active, and reset Time Warp during the same reproducible game scene. Keep native
presentation/gameplay acceptance separate from fixture, CI and packaging evidence.
