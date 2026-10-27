# Hades I Save Editor

[#584](https://github.com/TeaganRicardo/MacGamingTrainer/issues/584) owns the independent Hades I editor. Compatibility comes from `Backend/games/hades/module.json.supportedBuild`; native semantic rows and official bilingual identities come from `save_catalog.json`. This implementation adds no product release, resident Lua or persisted Profile revision. The adapter commands are additive within the existing module protocol.

## Static artifact evidence

The investigation inspected the declared supported x86_64 `Game.macOS` executable and its bundled `Content/Scripts` and `Content/Game/Text` files. The executable SHA-256 was `f69aab08ba6d12da66252a198d3c6c6606fc9de2e1b277458fae442526a75279`, matching the module's supported artifact. Addresses below are absolute unslid addresses in that artifact; they are research anchors, never feature offsets.

REA opened an immutable copy with Ghidra 12.1.4, profile digest `c027fac311b23874c52441ed55610273dff33987b0370a0589c90be8f6d72b7a`, run `6e04b10d-9d2e-4674-be8f-b8b5f2555af3`. Full procedure discovery timed out and supplied no decompilation evidence. The session was closed. Targeted, symbol-resolved Apple LLVM 21.0.0 static disassembly supplied the native format evidence. No game process or real save tree was involved.

| Native owner | Observed representation |
| --- | --- |
| `sgg::BinaryLoadData::fromStream(FileStream*)`, `0x100061870` | Checks `SGB1` at `0x1000619f8`; computes Adler-32 over bytes after offset 8 at `0x100061a8c`. |
| `sgg::ProgressManager::Save(...)`, `0x1003d0b90` | Writes version literal 16 as four bytes at `0x1003d2ab1..0x1003d2adc`, then the fields below. Calls raw `LZ4_compress_default` at `0x1003d3189`, writes compressed length at `0x1003d31c1`, and checksum at `0x1003d342a`. |
| `sgg::ProgressManager::Load(...)`, `0x1003cdd70` | Reads a uint32 version at `0x1003cdfe8..0x1003ce003`; recognizes 1..16. Historical field layouts remain unproven, so the editor explicitly supports version 16. |
| `sgg::ProgressManager::PreScriptLoad()`, `0x1003d6570` | Versions at least 15 use raw LZ4. `LZ4_decompress_safe` at `0x1003d6656` receives the native Lua buffer; Lua `Load` receives the decompressed length. |
| `sgg::adler32`, `0x100148510` | Initial a=1, b=0, modulo 65521. |

All numeric fields are little-endian. `bytes32` means uint32 length followed by raw bytes, with no terminator or UTF-8 requirement.

```
SGB1                         4 bytes
Adler32(file[8:])             uint32
version = 0x10               uint32
timestamp                    uint64
location                     bytes32
completed_runs               uint32
accumulated_meta_points      uint32
active_shrine_points         uint32
easy_mode, hard_mode         uint8 each
notable_count                uint32
notable_strings              notable_count × bytes32
map_name, next_map_name      bytes32 each
compressed_luabins           bytes32, one raw LZ4 block
```

The header before the compressed field is below `0x4000`. Uncompressed Lua is below `0x8f4000` bytes; the native destination buffer is `0x8f4000`. Compressed output is 1..`0x2fc000` bytes. The codec validates checksum, version, each length, these bounds and the absence of trailing bytes. Header byte strings use reversible surrogateescape internally and typed base64 at the JSON boundary when required.

The separate `activeProfile` naming file also begins `SGB1`, followed immediately by a uint32 string length. Its naming parser provides inventory defaults and backup labels; it establishes no `.sav` codec validity. Validation marker `.v.sav` files are excluded from editable documents. Other declared profile variants remain explicit physical choices.

## Lossless luabins and reuse boundary

`luabins_load` is at `0x10000220c`, recursive `load_value` at `0x10000236f`; `luabins_save` is at `0x100014430`, recursive `save_value` at `0x1000145bc`. The first byte counts 1..250 top-level values. Native `Main.lua` writes one root table; additional encoded values are retained.

| Tag | Payload |
| --- | --- |
| `-`, `0`, `1` | nil, false, true |
| `N` | Eight original IEEE-754 double bytes |
| `S` | uint32 length and arbitrary Lua string bytes |
| `T` | uint32 array count, int32 hash count, then their sum of ordered physical key/value pairs |

`lbs_writeNumber` (`0x10000d711`) and `lbs_writeString` (`0x10000d75d`) copy raw representations. `save_value` permits table depths 0..249 at `0x100014686`, and serializes keys and values recursively at `0x100014722` and `0x10001473a`. Native `load_value` rejects nil and NaN keys at `0x1000024d6..0x100002502`, accepts table-valued keys and applies `lua_rawset` at `0x100002523`.

Hades-owned `LuaTable` retains allocation counts and every physical entry. Bool and number keys remain distinct; numeric aliases and duplicate entries remain separate occurrences. Unmodified doubles retain their original bytes, including negative zero and NaN payloads. Unchanged documents retain their original compressed block. Edits preserve unmodified encoded values; recompression can change compressed bytes after a Lua edit. The format provides no shared-reference or cycle representation.

Opaque paths identify the top-level occurrence and each physical entry's key or value. Semantic helpers require one matching native key; ambiguity leaves the occurrences editable through Advanced. Advanced supports typed set, unset, append, key edits and whole-subtree replacement, including table keys, raw byte strings and explicit IEEE-754 values. Invalid nil/NaN keys, an invalid main root, an unavailable occurrence or native size/depth limits produce a concrete error. Unknown gameplay impact produces an editable warning.

Only `Backend/core/lz4_block.py` is shared with Hades II. Both supported containers use raw LZ4 blocks with the same token/offset/extension representation; each game supplies its own byte limits and translates primitive errors. The existing Hades II codec remains the owner of its version 17/18 container and luabins policy. Its uint16 version/flags, extra header fields, smaller Lua bound, UTF-8 header policy, table-key policy and depth limit differ from Hades I. No Hades II domain schema or UI was copied into the Hades I editor.

## Persistent owners and edit meaning

`Main.lua:1008..1035` strips transient rooms, applies `RunSaveWhitelist` to older history and serializes eligible globals outside `SaveIgnores`, functions, userdata and threads. `Main.lua:1071..1081` restores saved globals while protecting ignored globals and existing functions. The editor retains the encoded state rather than reconstructing stripped runtime owners.

`Tools/generate_hades_save_catalog.py` reads native text statically. It extracts the 12 paired Mirror rows, six weapons' four aspect definitions/rank bounds and official same-ID bilingual terms. Native language-independent localization aliases resolve against each language's keyword text. `save_catalog.json.sourceEvidence` owns the source hashes; the generator executes no game Lua.

| Ordinary domain | Native owner and implemented behavior |
| --- | --- |
| Resources | `RunManager.lua:157` and `RoomManager.lua:3384,3419` distinguish balance, lifetime gains, spending and native event hooks. Seven direct balance setters edit `GameState.Resources`; lifetime ledgers remain separately editable. A direct setter does not simulate a grant, spend or gift event. |
| Progression | `RunManager.lua:175..202` owns Mirror active/stored ranks, unlocks, stages and selection. `MetaUpgrades.lua:1631..1637` unlocks both members of one `MetaUpgradeOrder` row. The linked paired-unlock operation previews both booleans. Active/stored ranks and selection remain directly typed editable. Native live-Hero swapping at `:1704..1723` is distinct from these stored edits. |
| Equipment | `WeaponUpgradeScripts.lua:514..528` owns aspect rank increments and newly unlocked selection; `:582..615` writes `LastWeaponUpgradeData` and `LastInteractedWeaponUpgrade` and applies live weapons/traits. Rank and explicit **next-equip** selection update their proven persistent records. Creating a positive previously absent rank also selects it. Current-run Hero weapons/traits are separately editable; no live equip callback is implied. Locked next-equip selection requires a positive rank in the completed candidate unless native data declares it initially unlocked. |
| Relationships | `GiftScripts.lua:1..5,190..220` owns Gift values, progression, spending and recorded gift events. Gift values, trait records, NPC interactions and companion ownership are editable under their character/table owners. A direct value change remains separate from the complete native gift event. |
| Narrative | Saved scene records, choices, flags, prophecies, renovations and Codex records expose direct typed edits under their persistent owners. Unknown effects are labelled. |
| Statistics and history | `RunManager.lua:1724..1958` owns run caches, history and clear/weapon records. Direct counters and history entries are independently editable. Editing a counter creates no fabricated run. A later native recalculation can replace a directly edited cache or derived counter. |
| Advanced/header | All encoded top-level values, physical keys/values and container header projections remain typed editable. Header timestamp uses a decimal uint64 string to avoid JSON floating-point loss. Summary labels use an ordered 1-based string table. |

Native Save reads `GameState.CompletedRunsCache` at `0x1003d1106`, `AccumulatedMetaPointsCache` at `0x1003d1161`, `SpentShrinePointsCache` at `0x1003d11b8`, `GameState.Flags.HardMode` at `0x1003d1258`, and `ConfigOptions.EasyMode` at `0x1003d127d`. Changing the three proven caches also previews/writes their header projection for finite integral nonnegative int32 values, including edits through a parent subtree. A changed boolean HardMode likewise projects to its header byte. Other encoded types remain writable with an impact warning. Explicit contradictory header actions are rejected. EasyMode's configuration owner is outside this saved-global contract, so its header byte is directly editable without an invented Lua link.

Rows carry separate physical `ownerId`/`groupId` and localized labels. Bilingual search checks native keys, official terms, owner paths and displayed content; a matching field returns its whole owner card. Pagination preserves whole owners. Unknown encoded fields remain reachable in Advanced. The Changes basket revises/removes one user action and recomputes its links against the original in-memory baseline; conflicting overlapping actions are rejected before the basket changes.

## Workspace and transaction ownership

Hades' adapter owns UUID workspaces. A secure Core read pins source kind, snapshot ID where applicable, root ID, relative path, original hash and document bytes. Inventory refresh and active-profile changes cannot retarget an opened document. Targets are explicit declared physical identities, resolved independently of the source. Verified backups use Core's contained manifest reads and independent editor workspaces.

`HadesSaveEditSession` encodes and reparses a complete candidate, fsyncs a temporary file, then calls Core's selected-file replacement with its captured target path. Core captures the complete pre-write save set, creates a recoverable automatic pre-edit snapshot, detects target races, atomically installs only the selected file and checks its hash. The Hades callback rereads/decodes installed bytes and compares the exact candidate; Core checks again after the callback and during hot replacement. Unrelated files retain independent mutation ownership. A verified rollback preserves the basket. Incomplete rollback retains Core recovery evidence and permanently blocks Apply in that workspace.

On success the workspace adopts **its own verified candidate** as the in-memory baseline for successive edits and clears the basket. The originally read source/hash remain fixed; Apply never reopens or rebases from a later external target. The receipt names the actual target, installed hash and pre-edit snapshot. A deliberate Read selects a new document ownership session; replacing a document with pending changes asks to discard them. Hot disk replacement reports `runtimeReloaded=false`; a running game can retain its own state and later overwrite the file.

The frontend reuses Host `TrainerToolWindowStore` and the optional module `managedBackupEditor` factory. Reopening one tool focuses its existing model/drafts; different managed backups have different window IDs/workspaces. Native controls commit completed valid drafts; requests are guarded by session lifecycle, workspace and query/detail generation. Close/quit waits for pending writes and releases only the affected workspace.

## Authored verification and pending execution

`tests/fixtures/hades_save.py` independently writes synthetic version-16 headers, literal LZ4 and luabins bytes from this evidence. It contains no captured user/game save data. `test_hades_save_document.py` covers no-op bytes, unrelated-edit raw-bit/string preservation, duplicate/typed/table keys, physical paths, extra top-level values, malformed input/native depth and cross-game raw-LZ4 use. Existing Hades II save regressions continue to own its differing representation.

`test_hades_save_workspace.py` authors complete temporary read/edit/revise/remove/Apply/reread journeys for resources, paired Mirror links, weapon ranks/selection, Gift/narrative, direct statistics/header projections and typed Advanced data. It covers independent snapshots, fixed source versus changing active slot/target, successive candidate edits, duplicate occurrence removal, per-game isolation and adapter replay. `test_hades_save_editor_recovery.py` authors capture/verification races, unrelated-file preservation, verified rollback, retained recovery and uncertain non-replay. Existing selected `test_hades_frontend.py` adds native-control/window journeys for those wire contracts, draft ownership, basket effects and recovery.

These tests and compiler/native-control checks were **not executed locally** under the current pause. Static source inspection, metadata extraction and whitespace review are the implementation evidence. The complete committed head requires fresh independent review and the authorized normal hosted Linux contracts, macOS build/smoke and module-matrix contexts. Because the raw-LZ4 primitive moved into Core, the hosted portable run must include full Save behavior discovery. Native-compatible file loading, rendered UI and later game-authored persistence remain separate user acceptance.
