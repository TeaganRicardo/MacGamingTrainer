"""Structured Hades II save-editor workspace.

The workspace owns Hades profile/target selection and the scalable semantic
query/mutation seam over one lossless Hades save document. Callers never need
to receive the complete Lua tree just to browse or search it.
"""

from .localization import official_display_names
from .save_document import LuaTable
from .save_edit import Hades2SaveEditSession
from .save_provider import _active_profile
from .schema import MAX_AMOUNT


_DOMAINS = (
    "overview",
    "resources",
    "playerStats",
    "progression",
    "dialogue",
    "flags",
    "relationships",
    "weapons",
    "advanced",
)


def _page(offset, limit):
    if type(offset) is not int or offset < 0:
        raise ValueError("Save Editor query offset must be a non-negative integer.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Save Editor query limit must be 1..200.")
    return offset, limit


def _lua_path(root, path):
    current = root
    for key in path:
        if not isinstance(current, LuaTable):
            raise ValueError("Save Editor path does not identify a table.")
        try:
            current = current[key]
        except KeyError as error:
            raise ValueError("Save Editor path is missing.") from error
    return current


def _value_type(value):
    if isinstance(value, LuaTable):
        return "table"
    if type(value) is bool:
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if value is None:
        return "nil"
    return "unknown"


def _json_scalar(value):
    if isinstance(value, LuaTable):
        return None
    if type(value) is bool or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


class Hades2SaveWorkspace:
    """One editor workspace pinned to the active Hades profile save."""

    __slots__ = ("_session", "_game_path", "profile")

    def __init__(self, session, profile, game_path=None):
        self._session = session
        self._game_path = game_path
        self.profile = profile

    @property
    def relative_path(self):
        return self._session.relative_path

    @property
    def document(self):
        return self._session.document

    @classmethod
    def open(cls, save_service):
        files = tuple(save_service.resolved_files())
        by_path = {row.relative_path: row for row in files}
        active = by_path.get("activeProfile")
        profile = _active_profile(active.source_path) if active is not None else None
        if profile is None:
            raise ValueError("Save Editor could not resolve the active Hades profile.")

        temporary = "{}_Temp.sav".format(profile)
        persistent = "{}.sav".format(profile)
        relative_path = temporary if temporary in by_path else persistent
        if relative_path not in by_path:
            raise ValueError("Save Editor active profile save is missing.")

        provider = getattr(save_service, "provider", None)
        game_path = getattr(provider, "game_path", None)
        return cls(
            Hades2SaveEditSession.open(save_service, relative_path),
            profile,
            game_path=game_path,
        )

    def _resource_rows(self, language):
        try:
            game_state = self.document.lua_state["GameState"]
            resources = game_state["Resources"]
        except KeyError as error:
            raise ValueError("Save Editor resource inventory is unavailable.") from error
        if not isinstance(resources, LuaTable):
            raise ValueError("Save Editor resource inventory is malformed.")

        identifiers = {
            key for key, _value in resources.entries()
            if isinstance(key, str)
        }
        names = official_display_names(
            identifiers,
            language,
            game_path=self._game_path,
        )
        english = (
            names if language == "en"
            else official_display_names(identifiers, "en", game_path=self._game_path)
        )

        rows = []
        for key, value in resources.entries():
            if not isinstance(key, str):
                continue
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not float(value).is_integer()
            ):
                # A primitive-looking value is not silently writable unless the
                # resource descriptor can prove the supported integer contract.
                continue
            amount = int(value)
            rows.append({
                "id": "resource:{}".format(key),
                "domain": "resources",
                "rawId": key,
                "path": ["GameState", "Resources", key],
                "name": names.get(key) or key,
                "englishName": english.get(key) or key,
                "value": amount,
                "valueType": "integer",
                "editable": True,
                "mutationKinds": ["set"],
                "constraints": {
                    "min": 0,
                    "max": MAX_AMOUNT,
                    "integer": True,
                },
            })
        return rows

    def _advanced_rows(self, path):
        target = _lua_path(self.document.lua_state, path)
        if not isinstance(target, LuaTable):
            raise ValueError("Save Editor Advanced path must identify a table.")
        rows = []
        for key, value in target.entries():
            item_path = [*path, key]
            kind = _value_type(value)
            row = {
                "id": "advanced:" + "/".join(str(part) for part in item_path),
                "domain": "advanced",
                "rawId": str(key),
                "path": item_path,
                "name": str(key),
                "englishName": str(key),
                "value": _json_scalar(value),
                "valueType": kind,
                "editable": False,
                "mutationKinds": [],
            }
            if isinstance(value, LuaTable):
                row["childCount"] = len(value)
            rows.append(row)
        return rows

    def query(
        self,
        *,
        domain,
        search="",
        offset=0,
        limit=100,
        path=None,
        language="zh-CN",
    ):
        if domain not in _DOMAINS:
            raise ValueError("Unknown Save Editor domain.")
        if not isinstance(search, str) or len(search) > 256:
            raise ValueError("Save Editor search must be at most 256 characters.")
        if language not in ("zh-CN", "en"):
            raise ValueError("Save Editor language is unsupported.")
        offset, limit = _page(offset, limit)

        if domain == "resources":
            rows = self._resource_rows(language)
        elif domain == "advanced":
            if path is None:
                path = []
            if not isinstance(path, (list, tuple)) or len(path) > 64:
                raise ValueError("Save Editor Advanced path is invalid.")
            rows = self._advanced_rows(list(path))
        else:
            rows = []

        needle = search.casefold().strip()
        if needle:
            rows = [
                row for row in rows
                if needle in row["rawId"].casefold()
                or needle in row["name"].casefold()
                or needle in row["englishName"].casefold()
            ]
        total = len(rows)
        return {
            "profile": self.profile,
            "relativePath": self.relative_path,
            "domain": domain,
            "offset": offset,
            "limit": limit,
            "total": total,
            "items": rows[offset:offset + limit],
        }
