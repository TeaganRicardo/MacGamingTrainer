"""Structured Hades II save-editor workspace.

The workspace owns Hades profile/target selection and the scalable semantic
query/mutation seam over one lossless Hades save document. Callers never need
to receive the complete Lua tree just to browse or search it.
"""

import json
import math

from . import save_equipment, save_long_term, save_narrative
from .save_investigation import NativeDialogueInvestigation
from .localization import official_display_names
from .save_native_ids import QUEST_IDS, RESOURCE_IDS
from .save_document import AmbiguousLuaKeyError, Hades2SaveDocument, LuaTable
from .save_edit import Hades2SaveEditSession
from .save_provider import resolve_active_profile_save
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
    "discover",
    "resources",
    "playerStats",
    "progression",
    "investigate",
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

SAVE_EDITOR_INVESTIGATION_FILTERS = (
    "all", "recorded", "notRecorded", "ambiguous", "unknown",
)
SAVE_EDITOR_DISCOVERY_FILTERS = (
    "all", "observed", "absent", "editable", "readOnly",
    "ambiguous", "unsupported", "unknown",
)
SAVE_EDITOR_STATE_FILTERS = tuple(dict.fromkeys(
    (*SAVE_EDITOR_INVESTIGATION_FILTERS, *SAVE_EDITOR_DISCOVERY_FILTERS)
))


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

    __slots__ = ("_session", "_game_path", "_pending", "_investigation", "profile")

    def __init__(self, session, profile, game_path=None):
        self._session = session
        self._game_path = game_path
        self._pending = {}
        self._investigation = None
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
        profile, relative_path = resolve_active_profile_save(files)

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
        if not isinstance(identifier, str) or identifier not in RESOURCE_IDS:
            raise ValueError("Save Editor resource identity is not supported by the native catalog.")
        resources = self._resources()
        # Native ResourceData declares the identity; absence from the save
        # represents a zero balance, not an unknown resource.
        value = resources.get(identifier, 0)
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
        identifiers = RESOURCE_IDS
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
        for key in sorted(RESOURCE_IDS):
            row = {
                "id": "resource:" + key,
                "domain": "resources",
                "rawId": key,
                "path": ["GameState", "Resources", key],
                "name": names.get(key) or key,
                "englishName": english.get(key) or key,
                "value": None,
                "valueType": "integer",
                "editable": False,
                "mutationKinds": [],
                "constraints": {
                    "min": 0,
                    "max": MAX_AMOUNT,
                    "integer": True,
                },
            }
            try:
                descriptor = self._resource_descriptor(key)
            except AmbiguousLuaKeyError:
                row["ownerState"] = "ambiguous"
                row["blockReasonCode"] = "ambiguousOwner"
            except ValueError:
                row["ownerState"] = "unsupported"
                row["blockReasonCode"] = "unsupportedOwner"
            else:
                row["value"] = descriptor["before"]
                row["editable"] = True
                row["mutationKinds"] = list(descriptor["mutationKinds"])
            rows.append(row)
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
            row = {
                "id": "playerStat:" + field["id"],
                "domain": "playerStats",
                "rawId": field["id"],
                "path": ["GameState", field["id"]],
                "name": field["names"][language],
                "englishName": field["names"]["en"],
                "value": None,
                "valueType": field["valueType"],
                "editable": False,
                "mutationKinds": [],
                "constraints": dict(field["constraints"]),
            }
            try:
                descriptor = self._player_stat_descriptor(field["id"])
            except AmbiguousLuaKeyError:
                row["ownerState"] = "ambiguous"
                row["blockReasonCode"] = "ambiguousOwner"
            except ValueError:
                row["ownerState"] = "unsupported"
                row["blockReasonCode"] = "unsupportedOwner"
            else:
                row["value"] = descriptor["before"]
                row["editable"] = True
                row["mutationKinds"] = list(descriptor["mutationKinds"])
            rows.append(row)
        return rows

    def _overview_rows(self, language):
        state = self._game_state()
        resources = state.get("Resources")
        resource_count = 0
        if isinstance(resources, LuaTable):
            resource_count = sum(
                1 for key, value in resources.entries()
                if isinstance(key, str) and key in RESOURCE_IDS
                and type(value) in (float, int) and math.isfinite(float(value))
                and float(value).is_integer()
            )
        line_history = state.get("TextLinesRecord")
        flags = state.get("Flags")
        measurements = (
            ("resources", "已记录资源种类", "Recorded resource types", resource_count, ["GameState", "Resources"]),
            ("dialogue", "已记录对话", "Recorded dialogue entries",
             sum(1 for _, value in line_history.entries() if value is True)
             if isinstance(line_history, LuaTable) else 0, ["GameState", "TextLinesRecord"]),
            ("flags", "已存储标志", "Stored flags",
             len(flags) if isinstance(flags, LuaTable) else 0, ["GameState", "Flags"]),
            ("pending", "待提交修改", "Staged changes", len(self._pending), []),
        )
        return [
            {
                "id": "overview:" + key,
                "domain": "overview",
                "rawId": key,
                "path": path,
                "name": zh if language == "zh-CN" else en,
                "englishName": en,
                "value": value,
                "valueType": "integer",
                "editable": False,
                "mutationKinds": [],
            }
            for key, zh, en, value, path in measurements
        ]

    def _advanced_rows(self, path):
        target = _lua_path(self.document.lua_state, path)
        if not isinstance(target, LuaTable):
            raise ValueError("Save Editor Advanced path must identify a table.")
        rows = []
        for physical_index, key, value, ambiguous in target.physical_entries():
            item_path = [*path, key]
            kind = _value_type(value)
            row = {
                # Preserve Lua key type and path boundaries in opaque Swift IDs.
                # Numbers, booleans and strings can share the same printed key.
                "id": "advanced:" + json.dumps(
                    item_path, ensure_ascii=True, separators=(",", ":")
                ) + ":" + str(physical_index),
                "pathAmbiguous": ambiguous,
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

    @staticmethod
    def _discovery_reason(code, language):
        zh = language == "zh-CN"
        messages = {
            "editable": (
                "已记录，并且原生所有权已验证，可安全编辑。",
                "Observed with verified native ownership; supported for editing.",
            ),
            "editableAbsent": (
                "原生已知项目当前未记录；其所有权已验证，可通过受支持操作写入。",
                "Native-known state is absent; its verified owner supports the advertised edit.",
            ),
            "readOnly": (
                "当前可识别，但尚无经过验证的独立写入所有权。",
                "Recognized state is read-only because independent write ownership is not verified.",
            ),
            "knownAbsent": (
                "原生已知项目当前未记录；其完整写入生命周期尚未验证，因此保持只读。",
                "Native-known state is absent; its complete write lifecycle is not yet verified, so it remains read-only.",
            ),
            "unknownRaw": (
                "修改器尚不了解此存档数据；保留原值，仅可在“高级”中只读查看。",
                "Unknown save data is preserved and available read-only in Advanced.",
            ),
            "ambiguousOwner": (
                "存档中存在重复或歧义所有权；仅允许只读检查。",
                "Duplicate or ambiguous save ownership is read-only.",
            ),
            "unsupportedOwner": (
                "原生身份已知，但当前存档中的所有者或值不符合受支持结构；仅允许只读检查。",
                "The native identity is known, but its saved owner or value is outside the supported structure; it remains read-only.",
            ),
            "ambiguousRaw": (
                "此原始路径存在重复键或路径歧义；仅允许只读检查。",
                "This raw path contains duplicate keys or ambiguous ownership and is read-only.",
            ),
        }
        pair = messages.get(code, messages["readOnly"])
        return pair[0] if zh else pair[1]

    def _path_state(self, path):
        current = self.document.lua_state
        for key in path:
            if not isinstance(current, LuaTable):
                return "unknown"
            try:
                current = current[key]
            except KeyError:
                return "absent"
            except AmbiguousLuaKeyError:
                return "ambiguous"
        return "observed"

    def _semantic_state(self, row):
        owner_state = row.get("ownerState")
        if owner_state in ("ambiguous", "unsupported"):
            return owner_state
        state = self._path_state(row["path"])
        if state != "absent":
            return state
        # Some semantic descriptors are owned by a linked native record rather
        # than the presentation path carried by the row. A meaningful non-
        # default value proves that the semantic owner was observed even when
        # this particular physical key is absent (for example a default weapon
        # aspect owned by its base weapon).
        value = row.get("value")
        if value is True:
            return "observed"
        if (
            type(value) in (int, float)
            and not isinstance(value, bool)
            and value != 0
        ):
            return "observed"
        if isinstance(value, str) and value:
            return "observed"
        return "absent"

    def _semantic_discovery_rows(self, language):
        domains = (
            "resources", "playerStats", "progression",
            "flags", "relationships", "weapons",
        )
        other_language = "en" if language == "zh-CN" else "zh-CN"
        result = []
        for domain in domains:
            if domain == "resources":
                rows = self._resource_rows(language)
                aliases = self._resource_rows(other_language)
            elif domain == "playerStats":
                rows = self._player_stat_rows(language)
                aliases = self._player_stat_rows(other_language)
            elif domain in ("flags", "progression"):
                rows = save_narrative.rows(
                    self.document.lua_state, domain, language,
                    game_path=self._game_path,
                )
                aliases = save_narrative.rows(
                    self.document.lua_state, domain, other_language,
                    game_path=self._game_path,
                )
                if domain == "progression":
                    rows.extend(save_long_term.rows(
                        self.document.lua_state, domain, language,
                        game_path=self._game_path,
                    ))
                    aliases.extend(save_long_term.rows(
                        self.document.lua_state, domain, other_language,
                        game_path=self._game_path,
                    ))
            elif domain == "relationships":
                rows = save_long_term.rows(
                    self.document.lua_state, domain, language,
                    game_path=self._game_path,
                )
                aliases = save_long_term.rows(
                    self.document.lua_state, domain, other_language,
                    game_path=self._game_path,
                )
            else:
                rows = save_equipment.rows(
                    self.document.lua_state, language,
                    game_path=self._game_path,
                )
                aliases = save_equipment.rows(
                    self.document.lua_state, other_language,
                    game_path=self._game_path,
                )

            alias_by_id = {row["id"]: row for row in aliases}
            for source in rows:
                row = dict(source)
                state = self._semantic_state(row)
                if state == "ambiguous":
                    row["editable"] = False
                    row["mutationKinds"] = []
                    reason_code = row.get("blockReasonCode") or "ambiguousOwner"
                elif state == "unsupported":
                    row["editable"] = False
                    row["mutationKinds"] = []
                    reason_code = row.get("blockReasonCode") or "unsupportedOwner"
                elif row.get("editable"):
                    reason_code = "editable" if state == "observed" else "editableAbsent"
                else:
                    reason_code = row.get("blockReasonCode") or "readOnly"
                alias = alias_by_id.get(row["id"], {})
                row["state"] = state
                row["reasonCode"] = reason_code
                row["reason"] = (
                    row.get("blockReasonDiagnostic")
                    if reason_code not in (
                        "editable", "editableAbsent", "readOnly",
                        "ambiguousOwner", "unsupportedOwner",
                    )
                    and row.get("blockReasonDiagnostic")
                    else self._discovery_reason(reason_code, language)
                )
                row["_search"] = tuple({
                    str(value) for value in (
                        row.get("rawId"), row.get("name"), row.get("englishName"),
                        row.get("group"), alias.get("name"), alias.get("englishName"),
                        alias.get("group"),
                    ) if value
                })
                result.append(row)
        return result

    def _known_absent_quest_rows(self, language):
        state = self._game_state()
        try:
            statuses = state.get("QuestStatus")
        except AmbiguousLuaKeyError:
            # save_narrative.rows owns the explicit ambiguous identities when
            # the QuestStatus container itself is duplicated.
            return []
        if not isinstance(statuses, LuaTable):
            return []
        observed = {
            key for key, _ in statuses.entries()
            if isinstance(key, str)
        }
        missing = sorted(QUEST_IDS - observed)
        if not missing:
            return []
        current = official_display_names(
            missing, language, game_path=self._game_path
        )
        english = (
            current if language == "en"
            else official_display_names(missing, "en", game_path=self._game_path)
        )
        chinese = (
            current if language == "zh-CN"
            else official_display_names(missing, "zh-CN", game_path=self._game_path)
        )
        zh = language == "zh-CN"
        rows = []
        for name in missing:
            localized = current.get(name) or (("任务 · " if zh else "Quest · ") + name)
            english_name = english.get(name) or ("Quest · " + name)
            row = {
                "id": "quest:" + name,
                "domain": "progression",
                "rawId": name,
                "path": ["GameState", "QuestStatus", name],
                "name": localized,
                "englishName": english_name,
                "value": None,
                "valueType": "enum",
                "editable": False,
                "mutationKinds": [],
                "group": "命运清单" if zh else "Fated List quests",
                "choices": [],
                "state": "absent",
                "reasonCode": "knownAbsent",
                "reason": self._discovery_reason("knownAbsent", language),
                "_search": tuple({
                    token for token in (
                        name,
                        localized,
                        english_name,
                        chinese.get(name),
                    ) if token
                }),
            }
            rows.append(row)
        return rows

    def _raw_discovery_rows(self, needle, semantic_paths, language):
        if not needle:
            return []
        rows = []

        def visit(table, path):
            if not isinstance(table, LuaTable):
                return
            for physical_index, key, value, ambiguous in table.physical_entries():
                item_path = [*path, key]
                kind = _value_type(value)
                key_text = str(key)
                scalar = _json_scalar(value)
                value_text = "" if scalar is None else str(scalar)
                if (
                    tuple(item_path) not in semantic_paths
                    and (needle in key_text.casefold() or needle in value_text.casefold())
                ):
                    reason_code = "ambiguousRaw" if ambiguous else "unknownRaw"
                    row = {
                        "id": "advanced:" + json.dumps(
                            item_path, ensure_ascii=True, separators=(",", ":")
                        ) + ":" + str(physical_index),
                        "domain": "advanced",
                        "rawId": key_text,
                        "path": item_path,
                        "name": key_text,
                        "englishName": key_text,
                        "value": scalar,
                        "valueType": kind,
                        "editable": False,
                        "mutationKinds": [],
                        "pathAmbiguous": ambiguous,
                        "state": "ambiguous" if ambiguous else "unknown",
                        "reasonCode": reason_code,
                        "reason": self._discovery_reason(reason_code, language),
                    }
                    if isinstance(value, LuaTable):
                        row["childCount"] = len(value)
                    rows.append(row)
                if isinstance(value, LuaTable):
                    visit(value, item_path)

        visit(self.document.lua_state, [])
        return rows

    def _discovery_rows(self, search, language, state_filter):
        semantic = self._semantic_discovery_rows(language)
        semantic.extend(self._known_absent_quest_rows(language))

        investigation = self._narrative_investigation().query(
            self.document.lua_state,
            search=search,
            offset=0,
            limit=100_000,
            language=language,
            permissions=self._dialogue_write_decisions(),
            state_filter="all",
        )
        investigation_state = {
            "recorded": "observed",
            "notRecorded": "absent",
            "ambiguous": "ambiguous",
            "unknown": "unknown",
        }
        for source in investigation["items"]:
            row = dict(source)
            row["state"] = investigation_state.get(row.get("status"), "unknown")
            row["editable"] = bool(row.get("canStage"))
            # Investigation owns the safe stage identity. Discovery reports
            # editability but sends the user through the detailed owner flow.
            row["mutationKinds"] = []
            row["reasonCode"] = (
                "editable" if row["editable"]
                else row.get("blockReasonCode") or "readOnly"
            )
            row["_search"] = (row["rawId"], row["name"], row["englishName"])
            semantic.append(row)

        semantic_paths = {
            tuple(row["path"]) for row in semantic
            if isinstance(row.get("path"), list)
        }
        needle = search.casefold().strip()
        rows = []
        for row in semantic:
            if not needle:
                if row["state"] != "observed":
                    continue
            elif row.get("domain") != "investigate" and not any(
                needle in token.casefold() for token in row["_search"]
            ):
                continue
            item = dict(row)
            item.pop("_search", None)
            rows.append(item)
        rows.extend(self._raw_discovery_rows(needle, semantic_paths, language))

        if state_filter == "editable":
            rows = [row for row in rows if row.get("editable") is True]
        elif state_filter == "readOnly":
            rows = [row for row in rows if row.get("editable") is not True]
        elif state_filter != "all":
            rows = [row for row in rows if row.get("state") == state_filter]

        rank = {"observed": 0, "absent": 1, "ambiguous": 2, "unknown": 3}
        rows.sort(key=lambda row: (
            rank.get(row.get("state"), 4),
            not row.get("editable", False),
            str(row.get("group") or "").casefold(),
            row["name"].casefold(),
            row["rawId"].casefold(),
        ))
        return rows

    def _narrative_investigation(self):
        if self._investigation is None:
            self._investigation = NativeDialogueInvestigation(self._game_path)
        return self._investigation

    def _dialogue_write_decisions(self):
        # Reuse the actual descriptor/companion validator, including its
        # precise block reason. Do not make investigation its own write policy.
        try:
            observed = save_narrative.rows(
                self.document.lua_state, "dialogue", "en", game_path=self._game_path
            )
        except (ValueError, AmbiguousLuaKeyError, KeyError):
            return {}
        return {
            row["rawId"]: {
                "allowed": row["editable"],
                "code": row.get("blockReasonCode"),
                "diagnostic": row.get("blockReasonDiagnostic"),
            }
            for row in observed
        }

    def investigate(self, entry_id, language="zh-CN"):
        if language not in ("en", "zh-CN") or not isinstance(entry_id, str) or not entry_id.startswith("investigate:") or len(entry_id) > 512:
            raise ValueError("Save Editor investigation identity is invalid.")
        return self._narrative_investigation().detail(
            self.document.lua_state, entry_id[len("investigate:"):],
            language, self._dialogue_write_decisions()
        )

    def query(
        self,
        *,
        domain,
        search="",
        offset=0,
        limit=100,
        path=None,
        language="zh-CN",
        stateFilter="all",
    ):
        if domain not in SAVE_EDITOR_DOMAINS:
            raise ValueError("Save Editor domain is unknown.")
        if not isinstance(search, str) or len(search) > 256:
            raise ValueError("Save Editor search must be at most 256 characters.")
        if language not in ("zh-CN", "en"):
            raise ValueError("Save Editor language is unsupported.")
        offset, limit = _page(offset, limit)
        if domain == "investigate":
            if stateFilter not in SAVE_EDITOR_INVESTIGATION_FILTERS:
                raise ValueError("Save Editor investigation filter is invalid.")
        elif domain == "discover":
            if stateFilter not in SAVE_EDITOR_DISCOVERY_FILTERS:
                raise ValueError("Save Editor discovery filter is invalid.")
        elif stateFilter != "all":
            raise ValueError("Save Editor state filter is not supported for this domain.")
        if domain == "discover":
            rows = self._discovery_rows(search, language, stateFilter)
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
        if domain == "investigate":
            results = self._narrative_investigation().query(
                self.document.lua_state,
                search=search, offset=offset, limit=limit, language=language,
                permissions=self._dialogue_write_decisions(), state_filter=stateFilter,
            )
            return {
                "profile": self.profile, "relativePath": self.relative_path,
                "domain": domain, "offset": offset, "limit": limit, **results,
            }

        if domain == "overview":
            rows = self._overview_rows(language)
        elif domain == "resources":
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
        elif domain == "weapons":
            rows = save_equipment.rows(
                self.document.lua_state, language, game_path=self._game_path
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
            "coverage": [
                {
                    "id": "resources",
                    "discoverability": "supported",
                    "understanding": "supported",
                    "write": "supported",
                    "reasonCode": "verifiedDescriptors",
                },
                {
                    "id": "playerHistory",
                    "discoverability": "partial",
                    "understanding": "partial",
                    "write": "partial",
                    "reasonCode": "playerHistoryPartial",
                },
                {
                    "id": "narrative",
                    "discoverability": "supported",
                    "understanding": "partial",
                    "write": "partial",
                    "reasonCode": "narrativePartial",
                },
                {
                    "id": "relationships",
                    "discoverability": "supported",
                    "understanding": "partial",
                    "write": "partial",
                    "reasonCode": "relationshipsPartial",
                },
                {
                    "id": "progression",
                    "discoverability": "supported",
                    "understanding": "partial",
                    "write": "partial",
                    "reasonCode": "progressionPartial",
                },
                {
                    "id": "equipment",
                    "discoverability": "supported",
                    "understanding": "partial",
                    "write": "partial",
                    "reasonCode": "equipmentPartial",
                },
                {
                    "id": "unknown",
                    "discoverability": "supported",
                    "understanding": "readOnly",
                    "write": "readOnly",
                    "reasonCode": "unknownReadOnly",
                },
            ],
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
        semantic = save_equipment.descriptor(
            self.document.lua_state, entry_id, game_path=self._game_path
        )
        if semantic is not None:
            return semantic
        raise ValueError("Save Editor entry is not writable.")

    def stage(self, entry_id, operation, value=None):
        descriptor = self._descriptor(entry_id)
        if operation not in descriptor["mutationKinds"]:
            raise ValueError("Save Editor mutation is not allowed for this entry.")
        if descriptor["domain"] == "weapons":
            save_equipment.validate(descriptor, operation, value)
        elif entry_id.startswith(("interaction:", "specialInteraction:", "card:", "objective:")):
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
        previous = self._pending.get(entry_id)
        if value == before:
            self._pending.pop(entry_id, None)
        else:
            self._pending[entry_id] = {
                "id": descriptor["id"],
                "domain": descriptor["domain"],
                "rawId": descriptor["rawId"],
                "path": descriptor["path"],
                "operation": operation,
                "before": before,
                "after": value,
            }
        try:
            return self.review()
        except Exception:
            # A rejected preview must not leave an invisible pending mutation.
            if previous is None:
                self._pending.pop(entry_id, None)
            else:
                self._pending[entry_id] = previous
            raise

    def review(self):
        changes = []
        for intent in self._pending.values():
            # A staged identity must still resolve uniquely on the pinned source.
            # Reject a stale or ambiguous preview before linked effects are shown.
            descriptor = self._descriptor(intent["id"])
            if (intent["operation"] not in descriptor["mutationKinds"]
                    or intent["before"] != descriptor["before"]):
                raise ValueError("Save Editor staged owner is ambiguous or has changed.")
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
        changes.extend(
            save_equipment.linked_changes(self.document.lua_state, self._pending.values())
        )
        return {"count": len(changes), "changes": changes}

    def cancel(self):
        self._pending.clear()
        return self.review()

    @staticmethod
    def _apply_intent(document, intent):
        if intent["domain"] == "weapons":
            save_equipment.apply_intent(document.lua_state, intent)
            return
        if intent["id"].startswith(("interaction:", "specialInteraction:", "card:", "objective:")):
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
        save_equipment.validate_batch(candidate.lua_state, self._pending.values())
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
