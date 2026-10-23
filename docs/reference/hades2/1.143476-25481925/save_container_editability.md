# Complete Save container editing

The authoritative format remains `save_document.py`: `Hades2SaveHeader`, the
SGB1 reader/writer and the ordered `lua_values` vector. The source document is
pinned; Stage and review do not write. Apply still uses the existing explicit
physical target and recoverable Core Save transaction.

## One physical owner and one namespace

Advanced retains its existing main Lua child paths. Three additional root rows
expose the previously omitted container state:

- `{"saveContainer":"header"}` browses the encoded header fields and permits a
  typed whole-header replacement.
- `{"saveContainer":"payload"}` browses extra `lua_values[1:]`, using their
  actual zero-based vector indices. Each root value can be a table, scalar or
  nil. A typed sequence replacement and membership actions support append and
  removal; positions are normalized after an explicit deletion.
- `{"saveContainer":"main"}` opens a typed structure action for the main root.
  It offers no second child navigation tree. Root member additions/removals
  become the existing canonical `advanced:` child identities, so a missing
  `GameState` or another root member can be created without a new alias.

These are exact object-shaped path components. A native string key named
`header`, `payload` or `saveContainer` remains a native Lua key. Mixed or unknown
namespace objects are rejected rather than guessed. The `save-container:` action
prefix is distinct from native `advanced:` field identities.

The main root must remain a Lua table because that is the supported document
codec's root contract. Header fields that the binary codec cannot represent
cannot be added; required header fields cannot be removed. The list of encoded
header fields is not a native gameplay authorization list. Their actual bit
widths are checked with the codec's existing integer writer; the complete
candidate is encoded and parsed before Stage is acknowledged. This also checks
UTF-8, string/count/size/depth bounds and supported Save format versions. The
synthetic namespace/sequence wrappers do not reduce the native Lua nesting
limit. Extra payload allocation hints, ordering, key types and unknown values
are preserved by the existing typed Lua representation.

## Precision, conditional fields and observation

The timestamp is an unsigned 64-bit codec field. Its wire value and tagged
editor value are decimal strings, avoiding JSON/Swift Double precision loss;
the writer still checks the actual `u64` range. Other unsigned codec fields
retain their full actual widths, including byte values beyond Boolean zero/one.
Labels describe format fields; edits do not claim game-side synchronization.

A direct format change between the two supported versions also handles the
conditional `cosmetics_points` field. Moving to `0x12` supplies zero when the
field was absent; moving to `0x11` removes its encoded field. Review shows that
linked structural change. An explicit staged cosmetics value conflicts with a
format that cannot encode it. A whole-header replacement must itself include
or omit the conditional field correctly; an explicit value is never silently
discarded.

Advanced's shared warning is reused for unknown effects. No resource spending,
runtime reload, callback, derived gameplay-history synchronization or game
acceptance is inferred from an encoded container edit. Checksum, magic,
compressed lengths and luabins counts remain codec-derived structure rather
than independent desired fields.

## Nonfinite Lua values

The binary Lua number codec supports nonfinite values. Existing values can be
replaced with finite values, another typed value or removed. Explicit
`{"luaType":"number","encoding":"nonfinite","value":"nan"}` (and `inf` /
`-inf`) can also be written. Transport JSON never contains a bare NaN or
Infinity. Canonical tagged values provide stable NaN intent/no-op comparison.
Swift retains the tagged JSON instead of converting its value to Double.
Infinite table keys use the same explicit tagged encoding in paths and action
identities. Both signs retain a unique stable Lua numeric identity; finite-key
identities keep their existing encoding. Nil, NaN and unsupported key types
remain invalid. An infinite key does not block unrelated table siblings.

## Batch and verification boundary

One overlap owner covers main-root replacement, canonical native fields,
semantic linked effects, entire headers/fields and extra vectors/nested fields.
Deleting a sequence member changes later physical positions, so another action
in that sequence must first be removed from the batch. A rejected new request
restores the previously acknowledged basket. Header and extra-payload actions
remain independent of unrelated native main-tree actions. Multiple sequence
appends use numeric native positions (9 before 10), without changing stable
physical action identities or weakening removal/shift conflict detection.

`test_hades2_save_container_edits.py` first reproduced the missing header entry,
then the detail/query namespace refusal, a conditional field being silently
dropped from a replacement header, and codec-supported nonfinite values being
policy read-only. Its real temporary Core Save journeys cover precision,
conditional versions, codec limits, membership, root repair, overlap rejection,
finite JSON, Apply, snapshots and reopened bytes. The nearest Advanced tests
continue to cover existing successful raw/semantic operations.

`test_hades2_save_container_frontend.py` uses native Swift controls through the
production JSONL workspace/codec/transaction. It edits header numbers and a
full-width timestamp, extra scalar/table/nil values (including explicit
nonfinite encoding), adds a main-root member, reviews and applies to a selected
second profile, verifies the first source bytes, and reopens the target. All
physical files live under a disposable fixture root. This is automated native
control and file evidence, without a game process or real user saves. Full
integrated macOS/build/signing and real-game/manual acceptance remain separate.
