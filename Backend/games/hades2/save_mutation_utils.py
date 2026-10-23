"""Physical Lua owners shared by Hades Save transaction planners."""
from .save_advanced import AdvancedMutationError, resolve_path, validate_scalar
from .save_document import LuaTable

MAX_INTEGER = 9_007_199_254_740_991


def read(root, path, default=None):
    try:
        return resolve_path(root, path)
    except KeyError:
        return default


def owner(root, path, *, create=False):
    current = root
    for key in path:
        if not isinstance(current, LuaTable):
            raise AdvancedMutationError("Save Editor transaction path crosses a non-table owner.")
        child = current.get(key)
        if child is None and create:
            child = LuaTable()
            current[key] = child
        if child is None:
            return None
        if not isinstance(child, LuaTable):
            raise AdvancedMutationError("Save Editor transaction owner is not a Lua table.")
        current = child
    return current


def integer(value):
    validate_scalar(value, "integer")
    if not 0 <= value <= MAX_INTEGER:
        raise AdvancedMutationError("Save Editor transaction counter is outside the exact non-negative Lua integer range.")
    return int(value)


def add(root, path, delta):
    previous = integer(read(root, path, 0))
    after = integer(previous + delta)
    owner(root, path[:-1], create=True)[path[-1]] = after
    return after


def effect(identity, domain, name, path, before, after):
    return {"id": identity, "domain": domain, "rawId": str(path[-1]), "name": name,
            "path": path, "operation": "set", "before": before, "after": after}
