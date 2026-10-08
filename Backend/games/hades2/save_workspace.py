"""Structured Hades II save-editor workspace.

The workspace owns Hades profile/target selection and the scalable semantic
query/mutation seam over one lossless Hades save document. Callers never need
to receive the complete Lua tree just to browse or search it.
"""

import math

from . import save_long_term, save_narrative
from .localization import official_display_names
from .save_document import Hades2SaveDocument, LuaTable
from .save_edit import Hades2SaveEditSession
from .save_provider import _active_profile
from .schema import MAX_AMOUNT


_MAX_EXACT_LUA_INTEGER = 9_007_199_254_740_991
_PLAYER_STAT_FIELDS = (
    {
        "id": "GameplayTime",
        "names": {
            "en": "Gameplay Time (seconds)",
            "zh-CN": "有效游戏时间（秒）",
        },
        "valueType": "number",
        "constraints": {"min": 0, "integer": False},
    },
    {
        "id": "TotalTime",
        "names": {
            "en": "Total Run Time (seconds)",
            "zh-CN": "累计运行时间（秒）",
        },
        "valueType": "number",
        "constraints": {"min": 0, "integer": False},
    },
    {
        "id": "TotalRequiredEnemyKills",
        "names": {
            "en": "Required Enemy Kills",
            "zh-CN": "关卡必要敌人击杀数",
        },
        "valueType": "integer",
        "constraints": {
            "min": 0,
            "max": _MAX_EXACT_LUA_INTEGER,
            "integer": True,
        },
    },
)


SAVE_EDITOR_DOMAINS = (
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
SAVE_EDITOR_MUTATION_KINDS = (
    "set",
    "unset",
    "addMembership",
    "removeMembership",
    "setEnum",
    "setCounter",
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

    __slots__ = ("_session", "_game_path", "_pending", "profile")

    def __init__(self, session, profile, game_path=None):
        self._session = session
        self._game_path = game_path
        self._pending = {}
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
            Hades2SaveEditSession.open(
                save_service,
                relative_path,
                version_pinned=True,
            ),
            profile,
            game_path=game_path,
        )

    def _game_state(self):
        try:
            game_state = self.document.lua_state["GameState"]
        except KeyError as error:
            raise ValueError("Save Editor GameState is unavailable.") from error
        if not isinstance(game_state, LuaTable):
            raise ValueError("Save Editor GameState is malformed.")
        return game_state

    def _resources(self):
        try:
            game_state = self._game_state()
            resources = game_state["Resources"]
        except KeyError as error:
            raise ValueError("Save Editor resource inventory is unavailable.") from error
        if not isinstance(resources, LuaTable):
            raise ValueError("Save Editor resource inventory is malformed.")
        return resources

    def _resource_descriptor(self, identifier):
        if not isinstance(identifier, str) or not identifier:
            raise ValueError("Save Editor resource identity is invalid.")
        resources = self._resources()
        try:
            value = resources[identifier]
        except KeyError as error:
            raise ValueError("Save Editor resource is unavailable.") from error
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not float(value).is_integer()
        ):
            raise ValueError("Save Editor resource is not an editable integer.")
        return {
            "id": "resource:{}".format(identifier),
            "domain": "resources",
            "rawId": identifier,
            "path": ["GameState", "Resources", identifier],
            "before": int(value),
            "mutationKinds": ("set",),
        }

    def _resource_rows(self, language):
        resources = self._resources()
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
        for key, _value in resources.entries():
            if not isinstance(key, str):
                continue
            try:
                descriptor = self._resource_descriptor(key)
            except ValueError:
                continue
            rows.append({
                "id": descriptor["id"],
                "domain": descriptor["domain"],
                "rawId": key,
                "path": descriptor["path"],
                "name": names.get(key) or key,
                "englishName": english.get(key) or key,
                "value": descriptor["before"],
                "valueType": "integer",
                "editable": True,
                "mutationKinds": list(descriptor["mutationKinds"]),
                "constraints": {
                    "min": 0,
                    "max": MAX_AMOUNT,
                    "integer": True,
                },
            })
        return rows

    def _player_stat_descriptor(self, identifier):
        field = next(
            (field for field in _PLAYER_STAT_FIELDS if field["id"] == identifier),
            None,
        )
        if field is None:
            raise ValueError("Save Editor player statistic is not writable.")

        game_state = self._game_state()
        try:
            value = game_state[identifier]
        except KeyError:
            value = 0

        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise ValueError("Save Editor player statistic is malformed.")

        if field["valueType"] == "integer":
            if not float(value).is_integer():
                raise ValueError("Save Editor player statistic must be integral.")
            value = int(value)
        else:
            value = float(value)

        return {
            "id": "playerStat:{}".format(identifier),
            "domain": "playerStats",
            "rawId": identifier,
            "path": ["GameState", identifier],
            "before": value,
            "mutationKinds": ("set",),
            "valueType": field["valueType"],
            "constraints": dict(field["constraints"]),
            "names": field["names"],
        }

    def _player_stat_rows(self, language):
        rows = []
        for field in _PLAYER_STAT_FIELDS:
            descriptor = self._player_stat_descriptor(field["id"])
            rows.append({
                "id": descriptor["id"],
                "domain": descriptor["domain"],
                "rawId": descriptor["rawId"],
                "path": descriptor["path"],
                "name": descriptor["names"][language],
                "englishName": descriptor["names"]["en"],
                "value": descriptor["before"],
                "valueType": descriptor["valueType"],
                "editable": True,
                "mutationKinds": list(descriptor["mutationKinds"]),
                "constraints": descriptor["constraints"],
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
        if domain not in SAVE_EDITOR_DOMAINS:
            raise ValueError("Save Editor domain is unknown.")
        if not isinstance(search, str) or len(search) > 256:
            raise ValueError("Save Editor search must be at most 256 characters.")
        if language not in ("zh-CN", "en"):
            raise ValueError("Save Editor language is unsupported.")
        offset, limit = _page(offset, limit)

        if domain == "resources":
            rows = self._resource_rows(language)
        elif domain == "playerStats":
            rows = self._player_stat_rows(language)
        elif domain in ("flags", "dialogue", "progression"):
            rows = save_narrative.rows(
                self.document.lua_state, domain, language, game_path=self._game_path
            )
            if domain == "progression":
                rows.extend(save_long_term.rows(
                    self.document.lua_state, domain, language, game_path=self._game_path
                ))
        elif domain == "relationships":
            rows = save_long_term.rows(
                self.document.lua_state, domain, language, game_path=self._game_path
            )
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

    def summary(self):
        return {
            "profile": self.profile,
            "relativePath": self.relative_path,
            "domains": list(SAVE_EDITOR_DOMAINS),
            "pendingCount": len(self._pending),
        }

    def _descriptor(self, entry_id):
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("Save Editor entry identity is invalid.")
        prefix, separator, identifier = entry_id.partition(":")
        if separator and prefix == "resource":
            return self._resource_descriptor(identifier)
        if separator and prefix == "playerStat":
            return self._player_stat_descriptor(identifier)
        semantic = save_narrative.descriptor(
            self.document.lua_state, entry_id, game_path=self._game_path
        )
        if semantic is not None:
            return semantic
        semantic = save_long_term.descriptor(
            self.document.lua_state, entry_id, game_path=self._game_path
        )
        if semantic is not None:
            return semantic
        raise ValueError("Save Editor entry is not writable.")

    def stage(self, entry_id, operation, value=None):
        descriptor = self._descriptor(entry_id)
        if operation not in descriptor["mutationKinds"]:
            raise ValueError("Save Editor mutation is not allowed for this entry.")
        if entry_id.startswith(("gift:", "interaction:", "card:", "objective:")):
            save_long_term.validate(descriptor, operation, value)
        elif descriptor["domain"] in ("flags", "dialogue", "progression"):
            save_narrative.validate(descriptor, operation, value)
        if operation == "set":
            if descriptor["domain"] == "resources":
                if (
                    type(value) is not int
                    or isinstance(value, bool)
                    or not 0 <= value <= MAX_AMOUNT
                ):
                    raise ValueError(
                        "Save Editor resource value must be an integer 0..999999."
                    )
            elif descriptor["domain"] == "playerStats":
                constraints = descriptor["constraints"]
                if descriptor["valueType"] == "integer":
                    maximum = constraints.get("max", _MAX_EXACT_LUA_INTEGER)
                    if (
                        type(value) is not int
                        or isinstance(value, bool)
                        or not constraints["min"] <= value <= maximum
                    ):
                        raise ValueError(
                            "Save Editor player statistic must be an in-range integer."
                        )
                else:
                    if (
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not math.isfinite(float(value))
                        or float(value) < constraints["min"]
                    ):
                        raise ValueError(
                            "Save Editor player statistic must be a finite non-negative number."
                        )
                    value = float(value)
        before = descriptor["before"]
        if value == before:
            self._pending.pop(entry_id, None)
            return self.review()

        self._pending[entry_id] = {
            "id": descriptor["id"],
            "domain": descriptor["domain"],
            "rawId": descriptor["rawId"],
            "path": descriptor["path"],
            "operation": operation,
            "before": before,
            "after": value,
        }
        return self.review()

    def review(self):
        changes = []
        for intent in self._pending.values():
            changes.append({
                key: intent[key]
                for key in ("id", "domain", "rawId", "operation", "before", "after")
            })
        changes.extend(
            save_narrative.linked_changes(self.document.lua_state, self._pending.values())
        )
        changes.extend(
            save_long_term.linked_changes(self.document.lua_state, self._pending.values())
        )
        return {"count": len(changes), "changes": changes}

    def cancel(self):
        self._pending.clear()
        return self.review()

    @staticmethod
    def _apply_intent(document, intent):
        if intent["id"].startswith(("gift:", "interaction:", "card:", "objective:")):
            save_long_term.apply_intent(document.lua_state, intent)
            return
        if intent["domain"] in ("flags", "dialogue", "progression"):
            save_narrative.apply_intent(document.lua_state, intent)
            return
        path = intent["path"]
        owner = _lua_path(document.lua_state, path[:-1])
        if not isinstance(owner, LuaTable):
            raise ValueError("Save Editor mutation owner is not a table.")
        key = path[-1]
        operation = intent["operation"]
        if operation in ("set", "setEnum", "setCounter"):
            owner[key] = intent["after"]
            return
        if operation == "unset":
            del owner[key]
            return
        if operation in ("addMembership", "removeMembership"):
            try:
                collection = owner[key]
            except KeyError as error:
                raise ValueError("Save Editor membership target is missing.") from error
            if not isinstance(collection, LuaTable):
                raise ValueError("Save Editor membership target is not a table.")
            member = intent["after"]
            if operation == "addMembership":
                collection[member] = True
            else:
                try:
                    del collection[member]
                except KeyError:
                    pass
            return
        raise ValueError("Save Editor mutation operation is unsupported.")

    def apply(self):
        if not self._pending:
            raise ValueError("Save Editor has no changes to apply.")

        source_document = self._session.document
        candidate = Hades2SaveDocument.from_bytes(source_document.to_bytes())
        for intent in self._pending.values():
            # Re-resolve the descriptor against the pinned source before
            # applying its typed intent. This keeps mutation authority in the
            # semantic workspace rather than in caller-supplied Lua paths.
            descriptor = self._descriptor(intent["id"])
            if intent["operation"] not in descriptor["mutationKinds"]:
                raise ValueError("Save Editor mutation is no longer allowed.")
            self._apply_intent(candidate, intent)

        save_long_term.validate_batch(candidate.lua_state, self._pending.values())
        self._session.document = candidate
        try:
            result = self._session.apply()
        except BaseException:
            self._session.document = source_document
            raise

        change_count = len(self._pending)
        self._pending.clear()
        return {
            **result,
            "changeCount": change_count,
        }
