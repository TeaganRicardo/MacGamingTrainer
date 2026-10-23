"""Typed editing of the SGB1 header, main root and extra luabins values.

Namespaces are transport objects, never Lua keys. Existing main-root members
keep their Advanced identities; this owner adds only its root structure action.
Header constraints are validated by the same writer/parser as disk Save bytes.
"""
import math
import struct

from . import save_advanced
from .save_document import Hades2SaveDocument, HadesSaveFormatError, LuaTable, _Writer

_PREFIX = "save-container:"
_NAMES = {"header": ("Save container header", "存档容器头"),
          "payload": ("Extra Lua payloads", "额外 Lua 数据"),
          "main": ("Main Lua root · structure", "主 Lua 根 · 结构编辑")}
_HEADER_LABELS = {
    "game_version": ("Save format version", "存档格式版本"),
    "save_flags": ("Save flags", "存档标志位"),
    "timestamp": ("Timestamp · uint64 decimal", "时间戳 · 64 位无符号十进制"),
    "location": ("Location", "位置"), "completed_runs": ("Completed runs", "已完成轮次数"),
    "accumulated_meta_points": ("Accumulated meta points", "累计强化点数"),
    "active_shrine_points": ("Active shrine points", "当前誓约点数"),
    "meta_upgrade_level": ("Meta upgrade level", "强化等级"),
    "cosmetics_points": ("Cosmetics points", "装饰点数"),
    "easy_mode": ("Easy mode byte", "简单模式字节"), "hard_mode": ("Hard mode byte", "困难模式字节"),
    "notable_lua_data": ("Notable Lua data names", "关键 Lua 数据名称"),
    "map_name": ("Map name", "地图名称"), "next_map_name": ("Next map name", "下一地图名称"),
}
# Reuse the codec writer for range validation instead of copying its limits.
_UINT_WRITERS = {"game_version": "u16", "save_flags": "u16", "timestamp": "u64",
    "completed_runs": "u32", "accumulated_meta_points": "u32", "active_shrine_points": "u32",
    "meta_upgrade_level": "u32", "cosmetics_points": "u32", "easy_mode": "u8", "hard_mode": "u8"}


def namespace(path):
    if not isinstance(path, (list, tuple)) or not path or not isinstance(path[0], dict):
        return None
    component = path[0]
    if "saveContainer" not in component:
        return None
    if set(component) != {"saveContainer"} or component["saveContainer"] not in _NAMES:
        raise save_advanced.AdvancedMutationError("Save Editor container namespace is invalid.")
    return component["saveContainer"]


def is_id(identifier):
    return isinstance(identifier, str) and identifier.startswith(_PREFIX)


def _view(document):
    header = []
    for field in _HEADER_LABELS:
        value = getattr(document.header, field)
        if field == "cosmetics_points" and document.header.game_version != 0x12:
            continue
        if field == "timestamp":
            value = str(value)
        elif field == "notable_lua_data":
            value = LuaTable(len(value), 0, list(enumerate(value, 1)))
        header.append((field, value))
    extras = list(enumerate(document.lua_values[1:], 1))
    return LuaTable(0, 3, [("header", LuaTable(0, len(header), header)),
        ("payload", LuaTable(len(extras), 0, extras)), ("main", document.lua_state)])


def _inner(identifier):
    if not is_id(identifier):
        raise save_advanced.AdvancedMutationError("Save Editor container identity is invalid.")
    native = "advanced:" + identifier[len(_PREFIX):]
    path, suffix = save_advanced.parse_id(native)
    if path[0] not in _NAMES or (path[0] == "main" and len(path) != 1):
        raise save_advanced.AdvancedMutationError("Save Editor container identity is invalid.")
    if path[0] == "header" and len(path) > 1 and path[1] not in _HEADER_LABELS:
        raise save_advanced.AdvancedMutationError("Save Editor header field is not encoded by this codec.")
    return native, path, suffix


def _wire(path):
    return [{"saveContainer": path[0]}, *save_advanced.wire_path(path[1:])]


def _external(info):
    result = dict(info)
    result["id"] = _PREFIX + info["id"][len("advanced:"):]
    result["path"] = _wire(info["path"])
    # Namespace roots cannot be removed. Header fixed fields are required by
    # the container; only members of their sequence field can be removed.
    path = info["path"]
    if len(path) == 1:
        result["mutationKinds"] = ["set"] + (["addMembership", "removeMembership"]
            if path[0] in ("main", "payload") else [])
    elif path[0] == "header" and len(path) == 2:
        result["mutationKinds"] = ["set"] + (["addMembership", "removeMembership"]
            if path[1] == "notable_lua_data" else [])
    return result


def descriptor(document, identifier, *, include_value=True):
    native, _, _ = _inner(identifier)
    return _external(save_advanced.descriptor(_view(document), native, include_value=include_value))


def row(document, identifier, language):
    native, path, _ = _inner(identifier)
    result = save_advanced.row(_view(document), native, language)
    result.update(id=identifier, path=_wire(path))
    result["mutationKinds"] = list(descriptor(document, identifier, include_value=False)["mutationKinds"]) if result["editable"] else []
    labels = _NAMES[path[0]] if len(path) == 1 else (_HEADER_LABELS.get(path[1]) if path[0] == "header" else None)
    if labels:
        result.update(name=labels[language == "zh-CN"], englishName=labels[0])
    if path == ["main"]:
        result.pop("childCount", None)  # One root action; child navigation stays canonical.
    return result


def root_rows(document, language):
    return [row(document, _PREFIX + save_advanced.entry_id([kind], index)[len("advanced:"):], language)
            for index, kind in enumerate(("header", "payload", "main"))]


def rows(document, path, language):
    kind = namespace(path)
    if kind is None or kind == "main":
        raise save_advanced.AdvancedMutationError("Save Editor container browse namespace is invalid.")
    inner_path = [kind, *save_advanced.decode_path(path[1:])]
    target = save_advanced.resolve_path(_view(document), inner_path)
    if not isinstance(target, LuaTable):
        raise save_advanced.AdvancedMutationError("Save Editor container path must identify a table.")
    result = []
    for index, key, _, _ in target.physical_entries():
        native = save_advanced.entry_id([*inner_path, key], index)
        result.append(row(document, _PREFIX + native[len("advanced:"):], language))
    return result


def member_descriptor(document, info, operation, value):
    native, path, _ = _inner(info["id"])
    if path == ["main"]:
        # Root membership remains the same canonical Advanced child action.
        return save_advanced.member_descriptor(document.lua_state, {"path": [], "valueType": "table"}, operation, value)
    child, operation, value = save_advanced.member_descriptor(
        _view(document), save_advanced.descriptor(_view(document), native), operation, value)
    return _external(child), operation, value


def normalize_set(info, value):
    after, typed = save_advanced.normalize_set(info, value, container=True)
    _, path, _ = _inner(info["id"])
    if path == ["header", "timestamp"] and isinstance(after, str) and after and all(char in "0123456789" for char in after):
        try:
            after = str(int(after))
        except ValueError as error:
            raise save_advanced.AdvancedMutationError("Save Editor timestamp exceeds its codec width.") from error
        typed = save_advanced.typed_value(after)
    return after, typed


def _sequence(value, field, *, allow_gap=False):
    if not isinstance(value, LuaTable):
        raise save_advanced.AdvancedMutationError("Save Editor container sequence must be a typed table: " + field)
    entries = value.entries()
    keys = [key for key, _ in entries]
    if any(type(key) not in (int, float) or not math.isfinite(key) or key < 1 or int(key) != key for key in keys):
        raise save_advanced.AdvancedMutationError("Save Editor container sequence keys must be positive integer positions: " + field)
    if len(set(keys)) != len(keys) or (not allow_gap and set(keys) != set(range(1, len(keys) + 1))):
        raise save_advanced.AdvancedMutationError("Save Editor container sequence positions are ambiguous or noncontiguous: " + field)
    return [value[key] for key in sorted(keys)]


def _commit(document, view, intent, path):
    if not isinstance(view["main"], LuaTable):
        raise save_advanced.AdvancedMutationError("Save Editor main Lua root must remain a table.")
    header = view["header"]
    if not isinstance(header, LuaTable) or any(field not in _HEADER_LABELS for field, _ in header.entries()):
        raise save_advanced.AdvancedMutationError("Save Editor header contains a field the codec cannot encode.")
    for field in _HEADER_LABELS:
        if field == "cosmetics_points" and field not in header:
            document.header.cosmetics_points = None
            continue
        try:
            value = header[field]
        except KeyError as error:
            raise save_advanced.AdvancedMutationError("Save Editor required header field is missing: " + field) from error
        if field == "notable_lua_data":
            value = tuple(_sequence(value, field, allow_gap=intent["operation"] == "unset" and path[:2] == ["header", field] and len(path) == 3))
            if not all(isinstance(item, str) for item in value):
                raise save_advanced.AdvancedMutationError("Save Editor notable Lua names must be strings.")
        elif field in _UINT_WRITERS:
            if field == "timestamp":
                if not isinstance(value, str) or not value or any(char not in "0123456789" for char in value):
                    raise save_advanced.AdvancedMutationError("Save Editor timestamp must be an unsigned decimal string.")
                value = int(value)
            elif type(value) not in (int, float) or not math.isfinite(value) or int(value) != value:
                raise save_advanced.AdvancedMutationError("Save Editor header field must be an unsigned integer: " + field)
            else:
                value = int(value)
            try:
                getattr(_Writer(), _UINT_WRITERS[field])(value)
            except (struct.error, OverflowError) as error:
                raise save_advanced.AdvancedMutationError("Save Editor header value exceeds its codec width: " + field) from error
        elif not isinstance(value, str):
            raise save_advanced.AdvancedMutationError("Save Editor header field must be a UTF-8 string: " + field)
        setattr(document.header, field, value)
    extras = _sequence(view["payload"], "payload", allow_gap=intent["operation"] == "unset" and path[0] == "payload" and len(path) == 2)
    document.lua_values[:] = [view["main"], *extras]


def apply_intent(document, intent):
    _, path, _ = _inner(intent["id"])
    view = _view(document)
    owner = save_advanced.resolve_path(view, path[:-1])
    if intent["operation"] == "unset":
        del owner[path[-1]]
    else:
        owner[path[-1]] = save_advanced.value_from_typed(
            intent["typedAfter"], max_depth=save_advanced._MAX_LUABINS_DEPTH + 2)
    _commit(document, view, intent, path)


def finalize_batch(document, intents):
    own = [intent for intent in intents if is_id(intent["id"])]
    if not own:
        return
    whole_header = any(_inner(intent["id"])[1] == ["header"] for intent in own)
    explicit_cosmetics = any(_inner(intent["id"])[1][:2] == ["header", "cosmetics_points"] for intent in own)
    if document.header.game_version == 0x12:
        if document.header.cosmetics_points is None:
            if whole_header:
                raise save_advanced.AdvancedMutationError("Save Editor format 0x12 requires cosmetics points in the replacement header.")
            document.header.cosmetics_points = 0
    elif document.header.game_version == 0x11:
        if explicit_cosmetics or (whole_header and document.header.cosmetics_points is not None):
            raise save_advanced.AdvancedMutationError("Save Editor cosmetics points require Save format 0x12.", conflict=True)
        document.header.cosmetics_points = None
    try:
        Hades2SaveDocument.from_bytes(document.to_bytes())
    except (HadesSaveFormatError, UnicodeError, struct.error, OverflowError) as error:
        raise save_advanced.AdvancedMutationError("Save Editor container cannot round-trip through its codec: " + str(error)) from error


def effective(document, identifier):
    _, path, _ = _inner(identifier)
    return save_advanced.resolve_path(_view(document), path)


def responsibility(intent):
    if not is_id(intent["id"]):
        return "main", intent["path"]
    _, path, _ = _inner(intent["id"])
    kind, path = path[0], path[1:]
    # Removing a vector member shifts later physical positions. A second edit
    # in that vector cannot keep its original identity in the same batch.
    if intent["operation"] == "unset":
        if kind == "payload" and len(path) == 1:
            path = []
        elif kind == "header" and len(path) == 2 and path[0] == "notable_lua_data":
            path = path[:1]
    return kind, path


def validate_overlaps(source, intents, semantic_candidate):
    raw = [intent for intent in intents if intent["domain"] == "advanced"]
    for index, left in enumerate(raw):
        owner, path = responsibility(left)
        for right in raw[index + 1:]:
            other, other_path = responsibility(right)
            if owner == other and save_advanced.paths_overlap(path, other_path):
                raise save_advanced.AdvancedMutationError("Save Editor Advanced actions overlap; revise or remove the existing action first.", conflict=True)
    main = [intent for intent in raw if responsibility(intent)[0] == "main"]
    for intent in main:
        path = responsibility(intent)[1]
        if any(save_advanced.paths_overlap(path, changed) for changed in save_advanced.changed_paths(source, semantic_candidate)):
            raise save_advanced.AdvancedMutationError("Save Editor Advanced and semantic actions affect the same Lua path; revise or remove one action.", conflict=True)


def linked_changes(document, intents):
    own = [intent for intent in intents if is_id(intent["id"])]
    if not own:
        return []
    candidate = Hades2SaveDocument.from_bytes(document.to_bytes())
    for intent in sorted(own, key=lambda item: item["id"]):
        apply_intent(candidate, intent)
    finalize_batch(candidate, own)
    old, new = document.header.cosmetics_points, candidate.header.cosmetics_points
    if old == new or any(_inner(intent["id"])[1] in (["header"], ["header", "cosmetics_points"]) for intent in own):
        return []
    return [{"id": "linked:save-container:cosmetics_points", "domain": "advanced", "rawId": "cosmetics_points",
             "name": "Cosmetics points", "operation": "set", "before": old, "after": new}]
