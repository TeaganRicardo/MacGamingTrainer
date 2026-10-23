"""Typed, lossless Lua-path editing, independent of game-field vocabulary.

Semantic owners can reuse the unique-path and scalar checks. Unknown game
meaning is a warning; only an unaddressable path or unsupported codec value
prevents a raw mutation.
"""
import base64
import json
import math
import struct

from .save_document import (
    AmbiguousLuaKeyError, LuaTable,
    _MAX_LUABINS_DEPTH, _encode_luabins, _same_lua_key,
)


class AdvancedMutationError(ValueError):
    code = "invalid_request"
    presentation = "hades2.saveEditor.error.typedLuaMutation"
    arguments = ()
    _hades2_presentation_ready = True

    def __init__(self, message, *, conflict=False):
        super().__init__(message)
        self.diagnostic = message
        if conflict:
            self.presentation = "hades2.saveEditor.error.typedLuaConflict"


def validate_scalar(value, value_type):
    if value_type == "nil":
        valid = value is None
    elif value_type == "boolean":
        valid = type(value) is bool
    elif value_type in ("integer", "number"):
        try:
            valid = type(value) in (int, float) and math.isfinite(float(value))
            if valid and type(value) is int:
                valid = int(float(value)) == value
            if valid and value_type == "integer":
                valid = float(value).is_integer()
        except (OverflowError, ValueError):
            valid = False
    elif value_type == "string":
        valid = isinstance(value, str)
        if valid:
            try:
                value.encode("utf-8", errors="surrogateescape")
            except UnicodeError:
                valid = False
    else:
        valid = False
    if not valid:
        raise AdvancedMutationError("Save Editor value does not match its writable Lua type: " + str(value_type))
    return value


def value_type(value):
    if isinstance(value, LuaTable):
        return "table"
    if value is None:
        return "nil"
    if type(value) is bool:
        return "boolean"
    if type(value) in (int, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "unsupported"


def typed_value(value):
    kind = value_type(value)
    if kind == "table":
        return {"luaType": kind, "arraySize": value.array_size, "hashSize": value.hash_size,
                "entries": [{"key": typed_value(key), "value": typed_value(item)}
                            for key, item in value.entries()]}
    if kind == "string":
        try:
            value.encode("utf-8")
        except UnicodeError:
            return {"luaType": kind, "encoding": "base64",
                    "value": base64.b64encode(value.encode("utf-8", errors="surrogateescape")).decode("ascii")}
    if kind == "number" and not math.isfinite(value):
        # Explicit encoding keeps JSON finite and gives NaN stable intent
        # equality. NaN remains forbidden as a table key.
        return {"luaType": kind, "encoding": "nonfinite", "value": repr(value)}
    if kind == "unsupported":
        raise AdvancedMutationError("Save Editor Lua value cannot be encoded.")
    return {"luaType": kind, "value": value}


def value_from_typed(node, depth=0, *, max_depth=_MAX_LUABINS_DEPTH):
    if not isinstance(node, dict) or depth > max_depth:
        raise AdvancedMutationError("Save Editor typed Lua node is invalid or too deeply nested.")
    kind = node.get("luaType")
    if kind == "table":
        entries = node.get("entries")
        if not isinstance(entries, list):
            raise AdvancedMutationError("Save Editor typed table requires ordered entries.")
        decoded = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"key", "value"}:
                raise AdvancedMutationError("Save Editor typed table entry is invalid.")
            key = value_from_typed(entry["key"], depth + 1, max_depth=max_depth)
            validate_key(key)
            decoded.append((key, value_from_typed(entry["value"], depth + 1, max_depth=max_depth)))
        array = node.get("arraySize", 0)
        hashed = node.get("hashSize", len(decoded) - array if type(array) is int else -1)
        if type(array) is not int or type(hashed) is not int or min(array, hashed) < 0 or array + hashed != len(decoded):
            raise AdvancedMutationError("Save Editor typed table allocation sizes do not match its entries.")
        return LuaTable(array, hashed, decoded)
    value = node.get("value")
    if kind == "string" and node.get("encoding") == "base64":
        try:
            value = base64.b64decode(value, validate=True).decode("utf-8", errors="surrogateescape")
        except (ValueError, TypeError, UnicodeError) as error:
            raise AdvancedMutationError("Save Editor Lua byte string is invalid base64.") from error
    elif kind == "number" and node.get("encoding") == "nonfinite":
        choices = {"nan": float("nan"), "inf": float("inf"), "-inf": -float("inf")}
        if not isinstance(value, str) or value not in choices:
            raise AdvancedMutationError("Save Editor nonfinite number must be nan, inf or -inf.")
        return choices[value]
    elif node.get("encoding") is not None:
        raise AdvancedMutationError("Save Editor typed scalar encoding is unsupported.")
    return validate_scalar(value, kind)


def validate_key(key):
    if type(key) not in (str, int, float, bool):
        raise AdvancedMutationError("Save Editor Lua keys must be strings, numbers other than NaN, or booleans.")
    if type(key) is float and math.isinf(key):
        return key
    validate_scalar(key, value_type(key))
    return key


def resolve_path(root, path):
    if not isinstance(path, (list, tuple)) or len(path) > _MAX_LUABINS_DEPTH + 2:
        raise AdvancedMutationError("Save Editor Lua path is invalid.")
    current = root
    for key in path:
        validate_key(key)
        if not isinstance(current, LuaTable):
            raise AdvancedMutationError("Save Editor Lua path crosses a non-table value.")
        current = current[key]  # LuaTable rejects physical duplicate identities.
    return current


def entry_id(path, index):
    encoded = [typed_value(key) if type(key) is float and math.isinf(key) else key for key in path]
    return "advanced:" + json.dumps(encoded, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + ":" + str(index)


def parse_id(identifier):
    if not isinstance(identifier, str) or not identifier.startswith("advanced:"):
        raise AdvancedMutationError("Save Editor Advanced identity is invalid.")
    try:
        text, suffix = identifier[len("advanced:"):].rsplit(":", 1)
        # Bare JSON Infinity/NaN has no supported wire representation. Only
        # the explicit tagged encoding can identify an infinite Lua key.
        path = json.loads(text, parse_constant=lambda _value: None)
        if not isinstance(path, list) or not path or len(path) > _MAX_LUABINS_DEPTH + 2:
            raise AdvancedMutationError()
        path = decode_path(path)
        if suffix != "new" and (not suffix.isdigit()):
            raise AdvancedMutationError()
    except (ValueError, TypeError) as error:
        raise AdvancedMutationError("Save Editor Advanced identity is invalid.") from error
    return path, suffix


def descriptor(root, identifier, *, include_value=True):
    path, suffix = parse_id(identifier)
    owner = resolve_path(root, path[:-1])
    if not isinstance(owner, LuaTable):
        raise AdvancedMutationError("Save Editor Advanced field owner is not a table.")
    matches = [(index, value) for index, key, value, _ in owner.physical_entries()
               if _same_lua_key(key, path[-1])]
    if len(matches) > 1:
        raise AmbiguousLuaKeyError("Save Editor Advanced path has duplicate physical keys.")
    if suffix == "new":
        if matches:
            raise AdvancedMutationError("Save Editor new Lua key already exists; edit its existing field.")
        present, value = False, None
    else:
        if not matches or int(suffix) != matches[0][0]:
            raise AdvancedMutationError("Save Editor Advanced field identity is stale.")
        present, value = True, matches[0][1]
    kind = value_type(value)
    if present and kind != "table" and not (kind == "number" and not math.isfinite(value)):
        validate_scalar(value, kind)
    result = {"id": identifier, "domain": "advanced", "rawId": display_key(path[-1]),
            "path": path, "beforePresent": present, "valueType": kind,
            "mutationKinds": (["set", "unset", "addMembership", "removeMembership"]
                              if kind == "table" else ["set", "unset"]), "constraints": {}}
    if include_value:
        result.update(before=json_value(value), typedBefore=typed_value(value))
    return result


def json_value(value):
    node = typed_value(value)
    return node if node["luaType"] == "table" or node.get("encoding") else node.get("value")


def display_key(key):
    if isinstance(key, str):
        try:
            key.encode("utf-8")
        except UnicodeError:
            return "base64:" + typed_value(key)["value"]
    return str(key)


def decode_path(path):
    if not isinstance(path, (list, tuple)):
        raise AdvancedMutationError("Save Editor Lua path is invalid.")
    return [validate_key(value_from_typed(key) if isinstance(key, dict) else key) for key in path]


def wire_path(path):
    return [typed_value(key) if ((isinstance(key, str) and typed_value(key).get("encoding"))
            or (type(key) is float and math.isinf(key))) else key for key in path]


def row(root, identifier, language):
    path, suffix = parse_id(identifier)
    result = {"id": identifier, "domain": "advanced", "rawId": display_key(path[-1]),
              "name": display_key(path[-1]), "englishName": display_key(path[-1]),
              "path": wire_path(path), "editable": False, "mutationKinds": [],
              "warning": warning(language), "reason": warning(language)}
    try:
        info = descriptor(root, identifier, include_value=False)
    except (ValueError, KeyError, TypeError) as error:
        ambiguous = isinstance(error, AmbiguousLuaKeyError)
        reason = (("此路径包含重复的物理 Lua 键，无法唯一确定写入目标。" if ambiguous else
                   "此值或路径不能按当前有限 Lua 类型可靠写回；请查看技术原因。")
                  if language == "zh-CN" else
                  ("This path contains duplicate physical Lua keys, so its write target is ambiguous." if ambiguous else
                   "This value or path cannot be written reliably using the supported finite Lua types; inspect the technical reason."))
        result.update(pathAmbiguous=isinstance(error, AmbiguousLuaKeyError),
                      readOnlyReason=reason, readOnlyReasonDiagnostic=str(error), value=None, valueType="unknown")
        # Inspection retains the physical occurrence even when key lookup is
        # ambiguous. It never turns that index into mutation authority.
        owner = resolve_path(root, path[:-1])
        if suffix.isdigit() and isinstance(owner, LuaTable):
            occurrence = owner.physical_entries()[int(suffix)]
            item = occurrence[2]
            result["valueType"] = value_type(item)
            if isinstance(item, LuaTable):
                result["childCount"] = len(item)
            if not isinstance(item, LuaTable) and result["valueType"] != "number":
                result["value"] = json_value(item)
        return result
    value = resolve_path(root, path) if info["beforePresent"] else None
    result.update(valueType=info["valueType"], editable=True,
                  mutationKinds=info["mutationKinds"], pathAmbiguous=False)
    if isinstance(value, LuaTable):
        result.update(value=None, childCount=len(value))
    else:
        encoded = typed_value(value)
        result["value"] = None if encoded.get("encoding") else value
        if encoded.get("encoding") == "base64":
            result["valueType"] = "binary"
        elif encoded.get("encoding") == "nonfinite":
            result["typedValue"] = encoded
    return result


def normalize_set(info, value, *, container=False):
    if isinstance(value, dict) and "luaType" in value:
        decoded = value_from_typed(value, max_depth=_MAX_LUABINS_DEPTH + (2 if container else 0))
    else:
        decoded = validate_scalar(value, info["valueType"])
    # Synthetic container views add up to two transport layers. Their actual
    # unwrapped document passes the same codec before Stage is acknowledged.
    if not container:
        _encode_luabins([decoded])
    return json_value(decoded), typed_value(decoded)


def member_descriptor(root, info, operation, value):
    if info["valueType"] != "table" or not isinstance(value, dict) or "key" not in value:
        raise AdvancedMutationError("Save Editor table membership requires a typed key.")
    key = value_from_typed(value["key"])
    validate_key(key)
    table = resolve_path(root, info["path"])
    matches = [(index, item) for index, candidate, item, _ in table.physical_entries()
               if _same_lua_key(candidate, key)]
    if len(matches) > 1:
        raise AmbiguousLuaKeyError("Save Editor member has duplicate physical keys.")
    if operation == "addMembership":
        if matches or "value" not in value:
            raise AdvancedMutationError("Save Editor added Lua member must have a new key and typed value.")
        return descriptor(root, entry_id([*info["path"], key], "new")), "set", value["value"]
    if not matches:
        raise AdvancedMutationError("Save Editor Lua member to remove is missing.")
    return descriptor(root, entry_id([*info["path"], key], matches[0][0])), "unset", None


def apply_intent(root, intent):
    owner = resolve_path(root, intent["path"][:-1])
    key = intent["path"][-1]
    if intent["operation"] == "unset":
        del owner[key]
    else:
        owner[key] = value_from_typed(intent["typedAfter"])


def paths_overlap(left, right):
    return all(_same_lua_key(a, b) for a, b in zip(left, right))


def changed_paths(before, after, path=()):
    if isinstance(before, LuaTable) and isinstance(after, LuaTable):
        if len(before) == len(after) and all(_same_lua_key(a[0], b[0])
                for a, b in zip(before.entries(), after.entries())):
            paths = []
            for (key, left), (_, right) in zip(before.entries(), after.entries()):
                paths.extend(changed_paths(left, right, (*path, key)))
            return paths
        keys = [key for key, _ in before.entries()]
        keys.extend(key for key, _ in after.entries() if not any(_same_lua_key(key, old) for old in keys))
        paths = []
        for key in keys:
            try:
                left, right = before[key], after[key]
            except KeyError:
                paths.append((*path, key))
            except AmbiguousLuaKeyError:
                paths.append(path)
            else:
                paths.extend(changed_paths(left, right, (*path, key)))
        return paths
    if type(before) in (int, float) and type(after) in (int, float):
        same = struct.pack("<d", before) == struct.pack("<d", after)
    else:
        same = type(before) is type(after) and before == after
    return [] if same else [path]


def warning(language):
    return ("这是按实际 Lua 类型和路径编辑的原始数据；用途或游戏内影响可能未知。请检查修改和关联效果。"
            if language == "zh-CN" else
            "This edits raw data by its actual Lua type and path. Its purpose or in-game effects may be unknown; inspect the changes and linked effects.")
