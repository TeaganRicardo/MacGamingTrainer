"""Editable stored history/statistics without replaying historical game events.

Each semantic scalar owns its exact unique Lua path. Changing one statistic does
not fabricate a completed run, alter another aggregate or mutate CurrentRun.
Unknown records remain lossless and technically editable through Advanced.
"""
from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable
from . import save_advanced


# Supported-build RunHistoryData.RunResultData, consumed by Was*Run helpers.
_RESULTS = {
    1: ("冥界 · 通关", "Underworld · Cleared"),
    2: ("冥界 · 未通关", "Underworld · Failed"),
    3: ("地表 · 通关", "Surface · Cleared"),
    4: ("地表 · 未通关", "Surface · Failed"),
    5: ("试炼 · 完成", "Bounty · Cleared"),
    6: ("试炼 · 未完成", "Bounty · Failed"),
    7: ("冥界试炼 · 完成", "Underworld bounty · Cleared"),
    8: ("地表试炼 · 完成", "Surface bounty · Cleared"),
    9: ("梦境 · 完成", "Dream · Cleared"),
    10: ("梦境 · 未完成", "Dream · Failed"),
}
_TRAIT_MEASURES = {
    "UseCount": ("使用次数", "Runs used"),
    "ClearCount": ("通关次数", "Clears"),
    "ClearCountUnderworld": ("冥界通关次数", "Underworld clears"),
    "ClearCountSurface": ("地表通关次数", "Surface clears"),
    "FastestTimeUnderworld": ("冥界最快时间（秒）", "Fastest Underworld time (seconds)"),
    "FastestTimeSurface": ("地表最快时间（秒）", "Fastest Surface time (seconds)"),
    "HighestShrinePointsUnderworld": ("冥界最高恐惧值", "Highest Underworld Fear"),
    "HighestShrinePointsSurface": ("地表最高恐惧值", "Highest Surface Fear"),
}
_GATHERING = {
    "fishing": (("垂钓记录", "Fishing history"), {
        "FishingSuccesses": ("成功次数", "Successes"),
        "FishingSuccessesManual": ("亲自成功次数", "Manual successes"),
        "FishingSuccessesFamiliar": ("魔宠成功次数", "Familiar successes"),
        "FishingFails": ("失败次数", "Failures"),
    }),
    "exorcism": (("引魂记录", "Shade pacification history"), {
        "ExorcismSuccesses": ("成功次数", "Successes"),
        "ExorcismSuccessesManual": ("亲自成功次数", "Manual successes"),
        "ExorcismSuccessesFamiliar": ("魔宠成功次数", "Familiar successes"),
        "ExorcismFails": ("失败次数", "Failures"),
    }),
    "harvest": (("采集记录", "Harvest history"), {
        "HarvestSuccesses": ("成功次数", "Successes"),
        "HarvestSuccessesManual": ("亲自成功次数", "Manual successes"),
        "HarvestSuccessesFamiliar": ("魔宠成功次数", "Familiar successes"),
    }),
}


_AMBIGUOUS = object()


def _get(owner, key):
    try:
        return owner.get(key) if isinstance(owner, LuaTable) else None
    except AmbiguousLuaKeyError:
        # Projection retains the field so its own unique-path check can expose
        # the duplicate without hiding other valid fields in the same run.
        return _AMBIGUOUS


def _number(value):
    try:
        save_advanced.validate_scalar(value, "number")
        return True
    except ValueError:
        return False


def _row(root, entity, title, key, label, value, path, language, *, kind="integer", terms=()):
    zh = language == "zh-CN"
    row = {
        "id": entity + ":" + key, "entityId": entity, "entityName": title,
        "domain": "history", "rawId": key, "path": path,
        "name": label[0 if zh else 1], "englishName": label[1],
        "value": value, "valueType": kind, "editable": False,
        "mutationKinds": [], "choices": [],
        "group": "历史与统计" if zh else "History and statistics",
        # Keep complete history entities visible, including an observed zero.
        "_browseReadOnly": True, "_search": tuple(terms),
    }
    try:
        owner = save_advanced.resolve_path(root, path[:-1])
        if not isinstance(owner, LuaTable):
            raise ValueError("history scalar owner is not a Lua table")
        try:
            actual = save_advanced.resolve_path(root, path)
            present = True
        except KeyError:
            if path != ["GameState", "FishingFails"]:
                raise
            actual, present = 0, False
        actual_kind = save_advanced.value_type(actual)
        save_advanced.validate_scalar(actual, actual_kind)
        if actual_kind not in ("number", "boolean", "string"):
            raise ValueError("history measure is not a scalar")
        if actual_kind != "number" or kind not in ("integer", "number", "enum"):
            kind = actual_kind
        row.update(value=save_advanced.json_value(actual), valueType=kind,
                   editable=True, mutationKinds=["setEnum" if kind == "enum" else "set"],
                   beforePresent=present, ownerState="observed" if present else "absent",
                   reasonCode="editable" if present else "editableAbsent")
        if kind in ("number", "integer"):
            row["constraints"] = {"min": 0, "integer": kind == "integer"}
        if kind == "enum":
            choices = list(_RESULTS)
            if actual not in choices:
                choices.append(actual)
            row["choices"] = [str(int(item)) for item in choices]
            row["choiceNames"] = {str(int(item)): (_RESULTS[item][0 if zh else 1]
                if item in _RESULTS else ("未识别结果 · " if zh else "Unidentified result · ") + str(item))
                for item in choices}
        row["reason"] = (("只修改此已存储统计，不重放挑战或生成其他历史事件。" if zh else
                         "Edit this stored statistic only; no run or historical event is replayed.") if present else
                         ("尚未记录；原生缺省值为 0，设置数值会创建此统计。" if zh else
                          "Not recorded; its native default is zero. Setting a value creates this statistic."))
    except (ValueError, KeyError, TypeError) as error:
        ambiguous = isinstance(error, AmbiguousLuaKeyError)
        row.update(value=None, reasonCode="ambiguousHistoryPath" if ambiguous else "unsupportedHistoryValue",
                   reason=("此 Lua 路径含重复键，不能唯一确定写入目标。" if zh else
                           "This Lua path contains duplicate keys and has no unique write target.") if ambiguous else
                          ("此来源不是支持的有限 Lua 标量；可在高级视图检查保留的原始记录。" if zh else
                           "This source is not a supported finite Lua scalar; inspect its preserved record in Advanced."),
                   reasonDiagnostic=str(error))
    return row


def _unavailable(owner, path, language, error):
    zh = language == "zh-CN"
    label = ("历史来源不可用", "History source unavailable")
    ambiguous = isinstance(error, AmbiguousLuaKeyError)
    return {"id": "history:unavailable:" + owner, "entityId": "history:unavailable:" + owner,
            "entityName": label[0 if zh else 1], "domain": "history", "rawId": owner, "path": path,
            "name": label[0 if zh else 1], "englishName": label[1], "value": None,
            "valueType": "string", "editable": False, "mutationKinds": [], "choices": [],
            "reasonCode": "ambiguousHistoryPath" if ambiguous else "unsupportedHistoryOwner",
            "reasonDiagnostic": str(error),
            "reason": (("此历史来源含重复 Lua 键，无法唯一定位；原始内容保留在高级视图。" if zh else
                        "This history source contains duplicate Lua keys and cannot be uniquely addressed; its content remains in Advanced.") if ambiguous else
                       ("此来源不是预期的历史表；原始内容保留在高级视图。" if zh else
                        "This source is not the expected history table; its original content remains in Advanced.")),
            "_browseReadOnly": True, "_search": (owner,)}


def rows(root, language="zh-CN", game_path=None):
    """Project stored measures plus the explicit, creatable FishingFails default."""
    zh = language == "zh-CN"
    state = root.get("GameState")
    if not isinstance(state, LuaTable):
        return []
    result = []

    def owner(name, build):
        try:
            value = state.get(name)
            if value is None:
                return
            if not isinstance(value, LuaTable):
                raise ValueError("malformed history owner")
            projected = build(value)
        except (AmbiguousLuaKeyError, ValueError) as error:
            result.append(_unavailable(name, ["GameState", name], language, error))
        else:
            result.extend(projected)

    def runs(history):
        projected, seen = [], set()
        for index, run in history.entries():
            if not _number(index) or index < 1 or int(index) != index or not isinstance(run, LuaTable):
                raise ValueError("malformed run history")
            if index in seen:
                continue
            seen.add(index)
            index = int(index)
            entity = "history:run:" + str(index)
            title = ("第 {} 次挑战" if zh else "Run {}").format(index)
            path = ["GameState", "RunHistory", index]
            def add(key, label, value, kind="integer", terms=(), field_path=None):
                projected.append(_row(root, entity, title, key, label, value, field_path or path + [key],
                                      language, kind=kind, terms=terms))
            outcome = _get(run, "RunResult")
            labels = _RESULTS.get(outcome) if type(outcome) in (int, float) else None
            if outcome is not None:
                add("RunResult", ("结果", "Result"), outcome,
                    "enum" if _number(outcome) and float(outcome).is_integer() else "number",
                    (str(outcome), *(labels or ())))
            for key, label in (
                ("GameplayTime", ("挑战时间（秒）", "Run time (seconds)")),
                ("ShrinePointsCache", ("恐惧值", "Fear")),
            ):
                value = _get(run, key)
                if value is not None:
                    add(key, label, value, "number" if key == "GameplayTime" else "integer")
            for key, label in (("EndingRoomName", ("终点", "Destination")),
                               ("ActiveBounty", ("试炼", "Bounty"))):
                identity = _get(run, key)
                if isinstance(identity, str):
                    names = official_display_names((identity,), language, game_path=game_path)
                    add(key, label, identity, "string", (identity, names.get(identity)))
            traits = _get(run, "TraitCache")
            if isinstance(traits, LuaTable):
                seen_traits = set()
                identifiers = [key for key, _ in traits.entries() if isinstance(key, str)]
                names = official_display_names(identifiers, language, game_path=game_path)
                english = names if not zh else official_display_names(identifiers, "en", game_path=game_path)
                for position, (identifier, count) in enumerate(traits.entries(), 1):
                    if identifier in seen_traits:
                        continue
                    seen_traits.add(identifier)
                    if not isinstance(identifier, str) or count is None:
                        continue
                    name = names.get(identifier) or identifier
                    en = english.get(identifier) or identifier
                    add("trait:" + identifier, ("祝福 · " + name, "Trait · " + en), count,
                        terms=(identifier, name, en), field_path=path + ["TraitCache", identifier])
                    if identifier not in names:
                        projected[-1]["rawTyped"] = True
        return projected

    def lifetime(stats):
        projected, seen = [], set()
        identities = [key for key, _ in stats.entries() if isinstance(key, str)]
        names = official_display_names(identities, language, game_path=game_path)
        for position, (identity, record) in enumerate(stats.entries(), 1):
            if not isinstance(identity, str) or not isinstance(record, LuaTable):
                raise ValueError("malformed lifetime history")
            if identity in seen:
                continue
            seen.add(identity)
            title = names.get(identity) or identity
            title = ("累计 · " if zh else "Lifetime · ") + title
            for key, label in _TRAIT_MEASURES.items():
                value = _get(record, key)
                if value is not None:
                    projected.append(_row(root, "history:trait:" + identity, title, key, label, value,
                        ["GameState", "LifetimeTraitStats", identity, key], language,
                        kind="number" if key.startswith("FastestTime") else "integer", terms=(identity, names.get(identity))))
                    if identity not in names:
                        projected[-1]["rawTyped"] = True
        return projected

    owner("RunHistory", runs)
    owner("LifetimeTraitStats", lifetime)
    for family, (titles, measures) in _GATHERING.items():
        for key, label in measures.items():
            try:
                value = state.get(key)
            except AmbiguousLuaKeyError as error:
                result.append(_unavailable(key, ["GameState", key], language, error))
                continue
            if value is not None or key == "FishingFails":
                result.append(_row(root, "history:gathering:" + family, titles[0 if zh else 1],
                    key, label, value, ["GameState", key], language))
    for owner_name, titles in (("FishCaught", ("鱼类记录", "Fish caught")),
                              ("ExorcisedNames", ("引魂对象记录", "Pacified shades"))):
        def counts(records):
            projected, seen = [], set()
            identities = [key for key, _ in records.entries() if isinstance(key, str)]
            names = official_display_names(identities, language, game_path=game_path)
            english = names if not zh else official_display_names(identities, "en", game_path=game_path)
            for position, (key, count) in enumerate(records.entries(), 1):
                if key in seen:
                    continue
                seen.add(key)
                if isinstance(key, str) and count is not None:
                    name = names.get(key) or key
                    en = english.get(key) or key
                    projected.append(_row(root, "history:collection:" + owner_name, titles[0 if zh else 1],
                        key, (name, en), count, ["GameState", owner_name, key], language, terms=(key,)))
                    if key not in names:
                        projected[-1]["rawTyped"] = True
            return projected
        owner(owner_name, counts)
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str) or not entry_id.startswith("history:"):
        return None
    for row in rows(root, "en", game_path=game_path):
        if row["id"] == entry_id:
            if not row["editable"]:
                raise ValueError(row.get("reasonDiagnostic") or row["reason"])
            # The same unique-path resolver is used for projection, review and
            # application; absence is permitted only for the named native default.
            return {"id": entry_id, "domain": "history", "rawId": row["rawId"],
                    "path": row["path"], "before": row["value"],
                    "beforePresent": row["beforePresent"], "valueType": row["valueType"],
                    "mutationKinds": tuple(row["mutationKinds"]),
                    "constraints": row.get("constraints", {}), "choices": row["choices"]}
    return None


def validate(info, operation, value):
    kind = info["valueType"]
    if operation not in info["mutationKinds"]:
        raise ValueError("Save Editor history operation is not supported.")
    if kind == "enum":
        if isinstance(value, str) and value in info["choices"]:
            value = int(value)
        save_advanced.validate_scalar(value, "integer")
        if str(int(value)) not in info["choices"]:
            raise ValueError("Save Editor RunResult is not a listed native choice; use typed Advanced for an unknown value.")
    else:
        save_advanced.validate_scalar(value, kind)
        if kind in ("integer", "number") and value < info["constraints"]["min"]:
            raise ValueError("Save Editor history statistic must be non-negative.")
    return value


def apply_intent(root, intent):
    owner = save_advanced.resolve_path(root, intent["path"][:-1])
    if not isinstance(owner, LuaTable):
        raise ValueError("Save Editor history owner is not a table.")
    owner[intent["path"][-1]] = intent["after"]
