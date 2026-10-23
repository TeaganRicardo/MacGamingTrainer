# Advanced typed Save editing

`Backend/games/hades2/save_advanced.py` owns raw writes by actual Lua type and a
unique path; `save_container.py` owns header, main-root structure and extra Lua
payload edits. Unknown game meaning produces a warning; it does not remove write
capability. Semantic workflows remain useful owners for recognizable operations
and linked effects. Advanced edits do not claim the game will accept or reload
an arbitrary value simply because the codec can write it.

## Identity and supported values

Existing field IDs remain `advanced:<JSON key path>:<physical index>`. The
pinned source must resolve every path component uniquely, and the terminal
occurrence must still match its index. Lua boolean, number and string keys are
distinct. A duplicated key or ambiguous ancestor cannot authorize an individual
write; its row gives a specific technical read-only reason. Other fields in the
same document remain editable. A uniquely addressed whole table can still be
edited as an ordered typed value, including preservation of unknown entries.

Scalar `set` accepts the existing actual JSON scalar type. A tagged value makes
an intentional type change explicit. Supported tags are `nil`, `boolean`,
`number`, `string` and `table`:

```json
{"luaType":"table","arraySize":0,"hashSize":1,"entries":[
  {"key":{"luaType":"string","value":"Example"},
   "value":{"luaType":"number","value":3.5}}
]}
```

Tables use ordered entries rather than JSON object keys, preserving physical
order and allocation hints. Omitted hints default to a hash table of the supplied
entries. Strings retain whitespace and empty strings. Lua byte strings use the
string tag with `encoding:"base64"`, preserving bytes that are not UTF-8.
Plain JSON numbers must be finite and exactly representable by the codec's Lua
double. Non-finite Lua values are writable through
`{"luaType":"number","encoding":"nonfinite","value":"nan"}`; the other
accepted spellings are `"inf"` and `"-inf"`. Infinite keys use this same tagged
encoding in IDs and query paths. NaN, nil and table keys are invalid. Unsupported
values are rejected without changing pending intent. Depth validation uses the
actual codec limit; transport namespace wrappers do not reduce it.

`unset` removes the physical entry. `beforePresent` / `afterPresent` distinguish
an existing serialized nil from a removed field. New table membership uses
`addMembership` with `{key:<tagged scalar>,value:<tagged value>}`; it cannot silently
overwrite an existing key. `removeMembership` uses `{key:<tagged scalar>}`.
Each becomes a separate child action with a stable field ID. A new child ID has
the suffix `:new`; it can be revised through `set` or removed from the basket
before Apply. Different members do not overwrite the parent table's one action.

## Save container

Container IDs use `save-container:`; row paths start with
`{"saveContainer":"header"}`, `{"saveContainer":"payload"}` or
`{"saveContainer":"main"}` rather than a game-owned Lua key. Existing main-root
members retain their canonical Advanced IDs. The main root must remain a table;
header fields follow the codec's required types, integer widths and
format-specific fields. Its uint64 timestamp uses decimal text to retain every
bit. Extra payloads and `notable_lua_data` use contiguous one-based positions.
Removing a sequence member conflicts with other edits in that sequence because
later positions shift. These edits use the same Changes and Apply transaction.

## Query, detail, Changes and Apply

Ordinary Advanced queries stay lazy: table rows contain a child count and do not
serialize their subtrees. The existing `save_editor_detail` command accepts an
Advanced ID and returns its `typedValue` from the current acknowledged pending
projection, plus source/effective presence. Binary rows have `valueType:binary`
and no misleading editable display string. Encoded byte keys are represented by
tagged components in query paths.

Changes include the typed before/after values and presence for each raw action.
Revision and removal recompute the projection from the original pinned source.
Parent/child raw actions conflict explicitly. Raw actions also conflict with
the actual physical changes of the combined semantic actions, including linked
effects. The rejected new action never replaces the existing basket. This
prevents canonical apply order from silently choosing a winner.

Apply reuses `Hades2SaveEditSession` and the Core Save transaction: fixed original
document, explicit physical target, verified pre-write backup, atomic install,
installed-byte validation and recoverable rollback. It does not reread or rebase
the source. Source/header/unknown data that are not explicitly edited remain
preserved. The new tests exercise query → stage/revise/remove → Changes → actual
Core Apply → decode/reopen through temporary SGB1 files. Real-game reload,
game-authored overwrite and rendered acceptance remain user-run.
