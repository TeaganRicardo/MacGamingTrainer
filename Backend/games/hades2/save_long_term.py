"""Source-verified relationship and long-term progression save descriptors.

Gift quantities delegate to their own stored-count/aggregate transaction owner;
ordered gift events and dialogue history remain separate.
Arcana loadout and automatic-card semantics belong to save_arcana.
"""

from . import save_advanced, save_arcana, save_relationships
from .save_mutation_utils import owner as lua_owner
from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_native_ids import (NPC_INTERACTION_IDS, OBJECTIVE_IDS,
                             SPECIAL_INTERACTION_FUNCTIONS, OBJECTIVE_LOCALIZATION_IDS)

_MAX = 9_007_199_254_740_991

# Labels describe the handlers reached after GiftLogic records the action.
# Several actions can share a counter (Dora's salute/decorating, for example).
_SPECIAL_ACTIONS = {
    "SpecialInteractSalute": ("NPCUseTextSpecial", "致意", "Salute"),
    "SpecialInteractSaluteInterrupt": ("NPCUseTextSpecial", "致意", "Salute"),
    "SpecialInteractSaluteBroker": ("SpecialInteractShade", "致意", "Salute"),
    "SpecialInteractShade": ("SpecialInteractShade", "致意", "Salute"),
    "SpecialInteractThreatenChronos": ("ChronosUseTextSpecial", "警告", "Warn"),
    "HugPersephone": ("PersephoneUseTextSpecial", "问候", "Greet"),
    "HugZagreus": ("ZagreusUseTextSpecial", "问候", "Greet"),
    "AttemptPetCerberusThread": ("UseCerberusSpecial_True", "爱抚", "Pet"),
    "UseArtemisJoinSong": ("ArtemisSingingUseTextSpecial", "合唱", "Join In"),
    "UseCosmeticsShop": ("DoraUseTextSpecial", "装饰", "Decorate"),
    "PlantAdmirePresentation": ("GardenPlotSpecial", "欣赏", "Admire"),
    "UseGhostEavesdropper": ("UseGhostEavesdropper", "致意", "Salute"),
    "UseExorcisedGhostsPreRun": ("UseExorcisedGhostsPreRun", "致意", "Salute"),
    "UseGhostInspectPoint": ("UseGhostInspectPoint", "致意", "Salute"),
    "SpecialInteractChangeNextRunRNG": ("WorldUpgradeChangeNextRunRNG", "命运无常", "Acceptance of Another Fate"),
    "UseHadesFountain": (None, "饮用喷泉", "Drink from the fountain"),
    "SpecialInteractDieHardFanShade": ("SpecialInteractShade", "致意", "Salute"),
    "SpecialInteractDieHardFanShadeSendToElysium": (None, "送别", "Send-off"),
    "PetFamiliarFrog": (None, "爱抚", "Pet"),
    "FrogFamiliarSpecialInteractUnlockedInHub": ("FamiliarUseTextSpecial", "倾诉", "Confide"),
}

_INTERACTION_OWNERS = {
    "BartenderShade01": ("Bartender", "灵魂调配师", "Spirit Mixer"),
    "CrossroadsFountainWall01": ("Fountain", "泉水", "Fountain"),
    "DieHardFanShade": (None, "忠实观众阴魂", "Devoted fan shade"),
    "GameStatsScreen": ("GameStatsScreen_Title", "归档轶事", "Archived Trivia"),
    "GhostInspectPoint": (None, "阴魂", "Shades"),
    "HubGardenPlot": ("GardenPlots", "土壤", "Soil Plots"),
    "Market": ("Broker", "残魂商人", "Wretched Broker"),
    "MusicPlayerScreen": (None, "乐师阴魂", "Musician shade"),
    "RunHistoryScreen": ("RunHistoryScreen_Title", "过往成果", "Past Deeds"),
    "NPC_Cerberus_Story_01": ("NPC_Cerberus_Field_01", "刻耳柏洛斯", "Cerberus"),
    "NPC_Melinoe_Story_01": ("PlayerUnit", "墨利诺厄", "Melinoë"),
}
# These neutral scenery actors have no native dialogue sets. Existing physical
# values stay typed-editable in Advanced rather than gaining invented counters.
_CONVERSATION_HOSTS = NPC_INTERACTION_IDS - {"NPC_HorseAndChariot_01", "NPC_LeopardGuest"}
# These native hosts share a person but own different saved counters. Contexts
# cover every use of the host, including actors reused in memories and endings.
_INTERACTION_CONTEXTS = {
    "NPC_Arachne_01": ("BiomeF", "厄瑞玻斯", "Erebus"),
    "NPC_Arachne_Home_01": ("Crossroads", "三岔路口", "Crossroads"),
    "NPC_Artemis_01": ("Crossroads", "三岔路口", "Crossroads"),
    "NPC_Artemis_Field_01": (None, "途中授予祝福", "Boon encounter"),
    "NPC_Cerberus_Field_01": ("BiomeI", "塔耳塔罗斯", "Tartarus"),
    "NPC_Cerberus_Story_01": (None, "冥府重逢", "House reunion"),
    "NPC_Chronos_01": (None, "早期邂逅与时间异象", "Earlier encounters & time anomalies"),
    "NPC_Chronos_Story_01": (None, "往事与终局", "Memories & finale"),
    "NPC_Chronos_02": (None, "结局后的邂逅", "Encounters after the ending"),
    "NPC_Hades_Field_01": ("BiomeI", "塔耳塔罗斯", "Tartarus"),
    "NPC_Hades_Story_01": (None, "终局剧情", "Finale scene"),
    "NPC_Hades_02": (None, "回忆与重逢", "Memories & reunion"),
    "NPC_Hecate_01": (None, "三岔路口与往事", "Crossroads & memories"),
    "NPC_Hecate_Story_01": (None, "捉迷藏与终局", "Hide-and-seek & finale"),
    "HermesUpgrade": (None, "祝福选择", "Boon selection"),
    "NPC_Hermes_01": (None, "当面会面", "In-person encounter"),
    "NPC_Hypnos_01": ("Crossroads", "三岔路口", "Crossroads"),
    "NPC_Hypnos_02": (None, "梦境第一层", "First dream layer"),
    "NPC_Hypnos_03": (None, "梦境第二层", "Second dream layer"),
    "NPC_Hypnos_04": (None, "最终梦境与苏醒", "Final dream & awakening"),
    "NPC_Hypnos_DreamRun": (None, "梦境挑战", "Dream runs"),
    "NPC_Narcissus_01": ("BiomeG", "俄刻阿诺斯", "Oceanus"),
    "NPC_Narcissus_Field_01": (None, "与回声相会", "Visiting Echo"),
    "NPC_Melinoe_Story_01": (None, "童年", "Childhood"),
    "NPC_Nyx_01": (None, "往事中的噩梦", "Nightmare memory"),
    "NPC_Nyx_Story_01": (None, "重逢与混沌邂逅", "Reunion & Chaos visits"),
    "SpellDrop": ("SpellScreenMenu_Title", "月之礼赠", "Gifts of the Moon"),
    "NPC_Selene_01": ("Crossroads", "三岔路口", "Crossroads"),
    "NPC_Zagreus_Past_01": (None, "跨越时间的梦中会面", "Dreams across time"),
    "NPC_Zagreus_01": (None, "终局重逢", "Reunion in the ending"),
    "NPC_Zeus_01": (None, "对战堤丰", "Typhon battle"),
    "NPC_Zeus_Story_01": ("BiomePalace", "宙斯圣殿", "The Palace of Zeus"),
}
for _familiar in ("Cat", "Raven", "Hound", "Polecat"):
    for _context in ("LockedInRun", "UnlockedInHub"):
        _SPECIAL_ACTIONS[_familiar + "FamiliarSpecialInteract" + _context] = (None, "爱抚", "Pet")


def _special_label(name, language, game_path):
    labels = []
    for handler in SPECIAL_INTERACTION_FUNCTIONS.get(name, ()):
        identity, chinese, english = _SPECIAL_ACTIONS[handler]
        native = official_display_names((identity,), language, game_path=game_path) if identity else {}
        label = native.get(identity) or (chinese if language == "zh-CN" else english)
        if label not in labels:
            labels.append(label)
    if not labels:
        return "SpecialInteractRecord"
    return " / ".join(labels) + ("次数" if language == "zh-CN" else " count")


def linked_cache_label(raw_id, language, game_path=None):
    return save_arcana.cache_label(raw_id, language, game_path=game_path)


def _state(root):
    state = root["GameState"]
    if not isinstance(state, LuaTable):
        raise ValueError("Save Editor GameState is malformed.")
    return state


def _table(state, field):
    value = state.get(field)
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor {} is unavailable or malformed.".format(field))
    return value


def _integer(value):
    return (type(value) in (float, int) and
            0 <= value <= _MAX and
            float(value).is_integer())


def _display(ids, language, game_path):
    native = official_display_names(ids, language, game_path=game_path)
    en = native if language == "en" else official_display_names(ids, "en", game_path=game_path)
    return native, en


def _npc_person(native_id):
    if native_id in ("HermesUpgrade", "SpellDrop", "TrialUpgrade"):
        return {"HermesUpgrade": "Hermes", "SpellDrop": "Selene", "TrialUpgrade": "Chaos"}[native_id]
    if not native_id.startswith("NPC_"):
        return native_id
    name = native_id[len("NPC_"):]
    for variant in (
        "_Story_01", "_Field_01", "_Home_01", "_Past_01",
        "_DreamRun", "_01", "_02", "_03", "_04",
    ):
        if name.endswith(variant):
            return name[:-len(variant)]
    return name


def _row(entry_id, domain, raw_id, path, label, en, value, value_type,
         *, group, editable=True, maximum=_MAX,
         block_reason_code=None, owner_state=None,
         entity_id=None, entity_name=None):
    result = {
        "id": entry_id, "domain": domain, "rawId": raw_id, "path": path,
        "name": label, "englishName": en, "value": value,
        "valueType": value_type, "editable": editable,
        "mutationKinds": ["set"] if editable else [],
        "group": group,
        "choices": [False, True] if value_type == "boolean" else [],
    }
    if entity_id is not None:
        result["entityId"] = entity_id
        result["entityName"] = entity_name
    if value_type == "integer":
        result["constraints"] = {"min": 0 if not entry_id.startswith("card:") else 1,
                                 "max": maximum, "integer": True}
    if block_reason_code:
        result["blockReasonCode"] = block_reason_code
    if owner_state:
        result["ownerState"] = owner_state
    return result


def _counter_rows(state, field, prefix, known, domain, language, game_path, chinese, english, *, person=False):
    owner_state = None
    try:
        collection = state.get(field)
    except AmbiguousLuaKeyError:
        collection, owner_state = None, "ambiguous"
    else:
        if collection is not None and not isinstance(collection, LuaTable):
            owner_state = "unsupported"
    names = set(known)
    if isinstance(collection, LuaTable):
        names.update(name for name, _ in collection.entries() if type(name) is str)
    native, en = _display(names, language, game_path)
    for name in names & _INTERACTION_OWNERS.keys():
        identity, owner_chinese, owner_english = _INTERACTION_OWNERS[name]
        labels, english_labels = _display((identity,) if identity else (), language, game_path)
        native[name] = labels.get(identity) or (owner_chinese if language == "zh-CN" else owner_english)
        en[name] = english_labels.get(identity) or owner_english
    if prefix == "objective":
        ids = tuple(OBJECTIVE_LOCALIZATION_IDS.get(name, "Objective_" + name) for name in names)
        labels, english_labels = _display(ids, language, game_path)
        for name in names:
            identity = OBJECTIVE_LOCALIZATION_IDS.get(name, "Objective_" + name)
            if identity in labels:
                native[name] = labels[identity]
            if identity in english_labels:
                en[name] = english_labels[identity]
        if "TimeChallengeValue" in names:
            if native.get("TimeChallengeValue") in (None, "", "TimeChallengeValue"):
                native["TimeChallengeValue"] = "限时挑战倒计时" if language == "zh-CN" else "Timed challenge countdown"
            if en.get("TimeChallengeValue") in (None, "", "TimeChallengeValue"):
                en["TimeChallengeValue"] = "Timed challenge countdown"
    result = []
    for name in sorted(names):
        issue, value, kind = owner_state, 0, "integer"
        if isinstance(collection, LuaTable):
            try:
                raw_value = collection.get(name, 0)
            except AmbiguousLuaKeyError:
                issue, value = "ambiguous", None
            else:
                if name not in known and save_advanced.value_type(raw_value) in ("boolean", "number", "string"):
                    kind = save_advanced.value_type(raw_value)
                    try:
                        value = save_advanced.validate_scalar(raw_value, kind)
                    except ValueError:
                        issue, value = "unsupported", None
                elif _integer(raw_value):
                    value = int(raw_value)
                else:
                    issue, value = "unsupported", None
        title = native.get(name) or name
        chinese_label, english_label = chinese, english
        if prefix == "specialInteraction":
            chinese_label = _special_label(name, language, game_path)
            english_label = _special_label(name, "en", game_path)
        entity = "person:" + _npc_person(name) if person and (name.startswith("NPC_") or name in ("HermesUpgrade", "SpellDrop", "TrialUpgrade")) else (
            "familiar:" + name if person and name.endswith("Familiar") else
            "object:" + name if person else None)
        row = _row(prefix + ":" + name, domain, name, ["GameState", field, name],
            (chinese_label if language == "zh-CN" else english_label) + " · " + title,
            english_label + " · " + (en.get(name) or name), value, kind,
            group=("角色互动" if language == "zh-CN" else "Character interactions") if person else
                  ("目标统计" if language == "zh-CN" else "Objective counters"),
            editable=issue is None, owner_state=issue,
            block_reason_code="ambiguousOwner" if issue == "ambiguous" else "unsupportedOwner" if issue else None,
            entity_id=entity,
            entity_name=(title if title != name else _npc_person(name)) if person else None)
        if person and name in _INTERACTION_CONTEXTS:
            identity, chinese_context, english_context = _INTERACTION_CONTEXTS[name]
            labels = official_display_names((identity,), language, game_path=game_path) if identity else {}
            row["hostId"] = name
            row["hostName"] = labels.get(identity) or (chinese_context if language == "zh-CN" else english_context)
        if name not in known:
            row["rawTyped"] = True
            row["reason"] = ("此已保存字段用途未编目；按实际类型修改，不重放互动事件。" if language == "zh-CN" else
                             "This saved field is not catalogued; edit its actual type without replaying interaction events.")
            if issue is None:
                row["warning"] = row["reason"]
        result.append(row)
    return result


def rows(root, domain, language="zh-CN", game_path=None, *, include_absent=False):
    state = _state(root)
    result = []
    zh = language == "zh-CN"
    if domain == "relationships":
        result.extend(_counter_rows(state, "NPCInteractions", "interaction", _CONVERSATION_HOSTS,
            domain, language, game_path, "对话次数", "Conversations", person=True))
        result.extend(_counter_rows(state, "SpecialInteractRecord", "specialInteraction", SPECIAL_INTERACTION_FUNCTIONS,
            domain, language, game_path, "SpecialInteractRecord", "SpecialInteractRecord", person=True))

        result.extend(save_relationships.rows(root, language, game_path))

    if domain == "progression":
        result.extend(save_arcana.rows(root, language, game_path=game_path, include_absent=include_absent))

        result.extend(_counter_rows(state, "ObjectivesCompleted", "objective", OBJECTIVE_IDS,
            domain, language, game_path, "目标完成次数", "Objective completions"))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str):
        return None
    if entry_id.startswith("gift:"):
        return save_relationships.descriptor(root, entry_id)
    domain = ("relationships" if entry_id.startswith(("interaction:", "specialInteraction:"))
              else "progression" if entry_id.startswith(("card:", "objective:")) else None)
    if domain is None:
        return None
    for row in rows(root, domain, "en", game_path=game_path, include_absent=entry_id.startswith("card:")):
        if row["id"] == entry_id:
            if row.get("ownerState") == "ambiguous":
                raise AmbiguousLuaKeyError(
                    "Save Editor semantic owner is ambiguous."
                )
            if row.get("ownerState") == "unsupported":
                raise ValueError("Save Editor semantic owner is unsupported.")
            return {
                "id": row["id"], "domain": domain, "rawId": row["rawId"],
                "path": row["path"], "before": row["value"],
                "valueType": row["valueType"],
                "mutationKinds": tuple(row["mutationKinds"]),
                "constraints": row.get("constraints", {}),
                "rawTyped": row.get("rawTyped", False),
            }
    return None


def validate(descriptor_value, operation, value):
    if descriptor_value["id"].startswith("gift:"):
        return save_relationships.validate(descriptor_value, operation, value)
    if operation not in descriptor_value["mutationKinds"] or operation != "set":
        raise ValueError("Save Editor long-term mutation is not authorized.")
    if descriptor_value.get("rawTyped"):
        save_advanced.validate_scalar(value, descriptor_value["valueType"])
        return
    if descriptor_value["valueType"] == "boolean":
        if type(value) is not bool:
            raise ValueError("Save Editor long-term flag must be boolean.")
    elif descriptor_value["valueType"] == "integer":
        limits = descriptor_value["constraints"]
        if type(value) is not int or not limits["min"] <= value <= limits["max"]:
            raise ValueError("Save Editor long-term counter is out of range.")
    else:
        raise ValueError("Save Editor long-term mutation type is unsupported.")


def apply_intent(root, intent):
    if intent["id"].startswith("gift:"):
        return save_relationships.apply_intent(root, intent)
    state = _state(root)
    entry_id = intent["id"]
    after = intent["after"]
    if entry_id.startswith(("interaction:", "specialInteraction:")):
        special = entry_id.startswith("specialInteraction:")
        name = entry_id[len("specialInteraction:"):] if special else entry_id[len("interaction:"):]
        owner = lua_owner(root, ["GameState", "SpecialInteractRecord" if special else "NPCInteractions"], create=True)
        if name not in (SPECIAL_INTERACTION_FUNCTIONS if special else NPC_INTERACTION_IDS):
            owner[name] = after
            return
        if after == 0:
            owner.pop(name, None)
        else:
            owner[name] = after
        return
    if entry_id.startswith("card:"):
        return save_arcana.apply_intent(root, intent)
    if entry_id.startswith("objective:"):
        name = entry_id[len("objective:"):]
        owner = lua_owner(root, ["GameState", "ObjectivesCompleted"], create=True)
        if name not in OBJECTIVE_IDS:
            owner[name] = after
            return
        if after:
            owner[name] = after
        else:
            owner.pop(name, None)
        return
    raise ValueError("Save Editor long-term mutation is unknown.")


def linked_changes(root, intents):
    return save_arcana.linked_changes(root, intents) + save_relationships.linked_changes(root, intents)


def finalize_batch(root, intents, source=None):
    save_arcana.finalize_batch(root, intents, source=source)


def validate_batch(root, intents):
    save_arcana.validate_batch(root, intents)
