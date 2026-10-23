"""Read projections of native run/lifetime/harvest owners, without write authority.

RunLogic.UpdateLifetimeTraitRecords derives aggregates from completed runs;
editing one history scalar cannot truthfully update all those owners. Unknown
fields remain in the lossless document/Advanced tree and gain no semantics here.
"""
import math

from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable


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


def _get(owner, key):
    return owner.get(key) if isinstance(owner, LuaTable) else None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _row(entity, title, key, label, value, path, language, *, kind="number", terms=()):
    zh = language == "zh-CN"
    return {
        "id": entity + ":" + key, "entityId": entity, "entityName": title,
        "domain": "history", "rawId": key, "path": path,
        "name": label[0 if zh else 1], "englishName": label[1],
        "value": value, "valueType": kind, "editable": False,
        "mutationKinds": [], "choices": [],
        "group": "历史与统计" if zh else "History and statistics",
        "reasonCode": "historyReadOnly",
        "reason": ("历史与累计统计由游戏结束流程共同维护，单项修改无法同步关联记录；此处仅供查看。"
                   if zh else "Run completion maintains history and cumulative statistics together; a single-field edit cannot update the linked records. This view is read-only."),
        # History is a deliberate read-only player task, unlike absent writable
        # progression entries. Its populated entities belong in normal browse.
        "_browseReadOnly": True, "_search": tuple(terms),
    }


def _unavailable(owner, path, language):
    label = ("历史来源不可用", "History source unavailable")
    return _row("history:unavailable:" + owner, label[language != "zh-CN"],
                owner, label, "记录存在歧义或格式不受支持" if language == "zh-CN" else
                "Ambiguous or unsupported record; preserved in Advanced", path,
                language, kind="string", terms=(owner,))


def rows(root, language="zh-CN", game_path=None):
    """Project only observed source-identified measures; never infer missing zeros."""
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
        except (AmbiguousLuaKeyError, ValueError):
            result.append(_unavailable(name, ["GameState", name], language))
        else:
            result.extend(projected)

    def runs(history):
        projected, seen = [], set()
        for index, run in history.entries():
            if not _number(index) or index < 1 or int(index) != index or index in seen or not isinstance(run, LuaTable):
                raise ValueError("malformed run history")
            seen.add(index)
            index = int(index)
            entity = "history:run:" + str(index)
            title = ("第 {} 次挑战" if zh else "Run {}").format(index)
            path = ["GameState", "RunHistory", index]
            def add(key, label, value, kind="number", terms=(), field_path=None):
                projected.append(_row(entity, title, key, label, value, field_path or path + [key],
                                      language, kind=kind, terms=terms))
            outcome = _get(run, "RunResult")
            labels = _RESULTS.get(outcome) if type(outcome) in (int, float) else None
            add("RunResult", ("结果", "Result"),
                labels[0 if zh else 1] if labels else ("未识别结果" if zh else "Unidentified result"), "string")
            for key, label in (
                ("GameplayTime", ("挑战时间（秒）", "Run time (seconds)")),
                ("ShrinePointsCache", ("恐惧值", "Fear")),
            ):
                value = _get(run, key)
                if _number(value):
                    add(key, label, value)
            for key, label in (("EndingRoomName", ("终点", "Destination")),
                               ("ActiveBounty", ("试炼", "Bounty"))):
                identity = _get(run, key)
                if isinstance(identity, str):
                    names = official_display_names((identity,), language, game_path=game_path)
                    add(key, label, names.get(identity) or ("未识别地点" if zh else "Unidentified destination"),
                        "string", (identity,))
            traits = _get(run, "TraitCache")
            if isinstance(traits, LuaTable):
                seen_traits = set()
                identifiers = [key for key, _ in traits.entries() if isinstance(key, str)]
                names = official_display_names(identifiers, language, game_path=game_path)
                english = names if not zh else official_display_names(identifiers, "en", game_path=game_path)
                for position, (identifier, count) in enumerate(traits.entries(), 1):
                    if identifier in seen_traits:
                        raise ValueError("ambiguous run trait history")
                    seen_traits.add(identifier)
                    if not isinstance(identifier, str) or not _number(count):
                        continue
                    name = names.get(identifier) or ("未识别祝福 {}" if zh else "Unidentified trait {}").format(position)
                    en = english.get(identifier) or "Unidentified trait {}".format(position)
                    add("trait:" + identifier, ("祝福 · " + name, "Trait · " + en), count,
                        terms=(identifier, name, en), field_path=path + ["TraitCache", identifier])
        return projected

    def lifetime(stats):
        projected, seen = [], set()
        identities = [key for key, _ in stats.entries() if isinstance(key, str)]
        names = official_display_names(identities, language, game_path=game_path)
        for position, (identity, record) in enumerate(stats.entries(), 1):
            if not isinstance(identity, str) or identity in seen or not isinstance(record, LuaTable):
                raise ValueError("malformed lifetime history")
            seen.add(identity)
            title = names.get(identity) or ("未识别祝福 {}" if zh else "Unidentified trait {}").format(position)
            title = ("累计 · " if zh else "Lifetime · ") + title
            for key, label in _TRAIT_MEASURES.items():
                value = record.get(key)
                if _number(value):
                    projected.append(_row("history:trait:" + identity, title, key, label, value,
                        ["GameState", "LifetimeTraitStats", identity, key], language,
                        terms=(identity, names.get(identity))))
        return projected

    owner("RunHistory", runs)
    owner("LifetimeTraitStats", lifetime)
    for family, (titles, measures) in _GATHERING.items():
        for key, label in measures.items():
            try:
                value = state.get(key)
            except AmbiguousLuaKeyError:
                result.append(_unavailable(key, ["GameState", key], language))
                continue
            if _number(value):
                result.append(_row("history:gathering:" + family, titles[0 if zh else 1],
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
                    raise ValueError("ambiguous gathering history")
                seen.add(key)
                if isinstance(key, str) and _number(count):
                    name = names.get(key) or ("未识别对象 {}" if zh else "Unidentified entity {}").format(position)
                    en = english.get(key) or "Unidentified entity {}".format(position)
                    projected.append(_row("history:collection:" + owner_name, titles[0 if zh else 1],
                        key, (name, en), count, ["GameState", owner_name, key], language, terms=(key,)))
            return projected
        owner(owner_name, counts)
    return result
