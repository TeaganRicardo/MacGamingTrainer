# Advanced typed Save editing

The user selected broad Save editability on 2026-10-23. A known number, boolean,
text value, collection member or selection is editable by default when its
physical path and codec round trip are reliable. Unknown purpose is an impact
warning. A read-only decision needs a concrete technical reason such as an
ambiguous physical key or an unsupported nonfinite value. This extends the
ordinary entity workflow rather than requiring a new catalog allow-list.

Advanced keeps scalar inputs inline. Completed numeric, boolean and text edits
join Changes; empty text and leading/trailing spaces are data. “Edit type or
structure” reads a tagged Lua value on demand. It supports explicit type
changes, nil, tables with separately typed keys and values, and binary Lua
strings encoded as base64. Ordinary browsing does not copy whole table trees.
The table form adds/removes a typed key as an independent requested action.
Changes retains the distinction between a present nil value and an absent
field, and permits revision or removal before Apply. Typed before/after values
remain available through the same structure editor.

The owning backend policy and wire representation are documented in
[Advanced typed Save mutations](../reference/hades2/advanced-typed-save-editing.md).
The frontend uses that existing stage/detail/review/apply interface; it does not
grant authority from a displayed name or discard the workspace's source/target
ownership. Error feedback remains scoped to the field or operation. A language
or detail refresh preserves a focused draft. Completed invalid typed drafts
remain in that Save document when the value editor closes and reopens; a valid
correction or explicit document abandonment clears the corresponding draft.

`tests/test_hades2_advanced_save_frontend.py` uses actual native controls in the
SwiftUI tool window and sheet, the production Save-only worker, temporary codec
documents and real Core disk transactions. The old UI on the new backend
(`00cccb7`) reproduced the missing inline numeric control. The complete native
journey then edits numbers, booleans, exact/empty text, binary strings and Lua
types, replaces a table preserving boolean/number/string/binary keys, removes a
field, adds a member, removes and re-adds its requested action, and revises that
new member in Changes. It checks a focused typed draft through bilingual
refresh, applies two acknowledged batches, independently decodes installed
bytes, and closes/reopens the target to read its values. Every fixture path is
temporary; no game transport or real save tree is constructed.

This establishes native control dispatch, codec bytes and document lifecycle.
It does not establish rendered app layout, keyboard/VoiceOver behavior, actual
picker navigation, or real game loading and persistence. The native journey
selects the Advanced category and source/target through their production model
owners; those actual menus remain part of the consolidated user-run acceptance.

For that pass, use the final selected artifact/checksum, an expendable copied
save set, and both languages. Navigate Advanced through its actual picker,
edit a scalar in place, and confirm that merely typing does not stage it.
Change its type and inspect the typed Changes entry. Add a numeric or boolean
table key through the key-type picker and verify it is distinct from the text
spelling of the same key. Revise/remove individual requests, inspect the impact
warning and any concrete read-only reason, then Apply to the explicit target.
Close/reopen to observe installed values. Keep disk-write evidence, actual
game loading, runtime behavior and later game-authored saves as separate
observations, following the [whole Save journey procedure](hades2-save-editor-usability-gate.md).
