"""Explicit offline quest reward grants, separate from direct status editing.

Literal native rewards are read from the shared installed-source capture. This
plans the proven saved AddResource writes; it never executes installed Lua,
evaluates future quest eligibility or pretends to show a game presentation.
"""
import copy
import hashlib
import json
import re

from . import save_advanced
from .localization import official_display_names
from .save_document import LuaTable
from .save_investigation import _parse_lua_table, _scalar
from .save_mutation_utils import add, effect, integer, owner, read
from .save_native_ids import QUEST_IDS, RESOURCE_IDS, QUEST_REWARD_OWNER_SHA256


def _fields(definitions, name, active=()):
    if type(name) is not str:
        raise save_advanced.AdvancedMutationError("Save Editor reward inheritance is not a literal named definition.")
    if name in active or len(definitions.get(name, ())) != 1:
        raise save_advanced.AdvancedMutationError("Save Editor reward source is missing, duplicated or cyclic: " + name)
    try:
        parsed = _parse_lua_table(definitions[name][0]["script"], reject_duplicate_fields=(
            "RewardResourceName", "RewardResourceAmount", "OnAddedFunctionName", "IgnoreAsLastResourceGained", "InheritFrom"))
    except ValueError as error:
        raise save_advanced.AdvancedMutationError(str(error)) from error
    if not isinstance(parsed, dict):
        raise save_advanced.AdvancedMutationError("Save Editor reward source is not a literal native table.")
    fields = parsed["fields"]
    inheritance = fields.get("InheritFrom")
    inherited = {}
    if inheritance is not None:
        if not isinstance(inheritance, dict):
            raise save_advanced.AdvancedMutationError("Save Editor reward inheritance is dynamic.")
        for parent in inheritance["members"]:
            parent_fields = _fields(definitions, _scalar(parent), (*active, name))
            for key, value in parent_fields.items():
                if key in inherited and inherited[key] != value and key not in fields:
                    raise save_advanced.AdvancedMutationError("Save Editor inherited reward field has ambiguous values: " + key)
                inherited[key] = value
    inherited.update({key: value for key, value in fields.items() if key in (
        "RewardResourceName", "RewardResourceAmount", "OnAddedFunctionName", "IgnoreAsLastResourceGained")})
    return inherited


def _gift_callback(root):
    # Supported OnGiftPointsAdded has no saved effect when this actual trait
    # sum is zero. Current TraitData defines no producer of this legacy field.
    # A custom/legacy positive field would invoke processed health-trait setup,
    # which this offline action must not silently omit or synthesize.
    traits = read(root, ["CurrentRun", "Hero", "Traits"])
    if traits is None:
        return
    if not isinstance(traits, LuaTable):
        raise save_advanced.AdvancedMutationError("Save Editor cannot inspect the reward's GiftPointHealthMultiplier owner.")
    total = 0
    index = 1
    while True:
        trait = traits.get(index)
        if trait is None:
            break
        if not isinstance(trait, LuaTable):
            raise save_advanced.AdvancedMutationError("Save Editor reward trait array contains a non-table value.")
        value = trait.get("GiftPointHealthMultiplier")
        if value is not None:
            total += save_advanced.validate_scalar(value, "number")
        index += 1
    if total > 0:
        raise save_advanced.AdvancedMutationError("This reward invokes a saved positive GiftPointHealthMultiplier and processed native health-trait setup; use direct resource/status editing until that specific callback owner is supported.")


def _reward(root, name, investigation, *, native=None):
    if native is None:
        investigation._refresh()
        native = investigation.native
    expected = getattr(investigation, "reward_owner_hashes", QUEST_REWARD_OWNER_SHA256)
    if any(native.get("scriptHashes", {}).get(key) != digest for key, digest in expected.items()):
        raise save_advanced.AdvancedMutationError("Save Editor quest reward mutation owners do not match their verified source capture.")
    fields = _fields(native.get("quests", {}), name)
    resource = _scalar(fields.get("RewardResourceName"))
    amount = fields.get("RewardResourceAmount")
    if type(resource) is not str or resource not in RESOURCE_IDS or not isinstance(amount, str) or not re.fullmatch(r"\d+", amount):
        raise save_advanced.AdvancedMutationError("Save Editor quest reward is not an exact supported resource/integer literal.")
    amount = integer(int(amount))
    if amount == 0:
        raise save_advanced.AdvancedMutationError("Save Editor quest has no positive resource reward to grant.")
    policy = _fields(native.get("resources", {}), resource)
    callback = _scalar(policy.get("OnAddedFunctionName"))
    if callback == "OnGiftPointsAdded":
        _gift_callback(root)
    elif callback is not None:
        raise save_advanced.AdvancedMutationError("Save Editor reward has a different native callback owner: " + str(callback))
    ignore_last = _scalar(policy.get("IgnoreAsLastResourceGained"))
    if ignore_last not in (None, "true", "false"):
        raise save_advanced.AdvancedMutationError("Save Editor reward's last-resource policy is dynamic.")
    policy_identity = hashlib.sha256(json.dumps({"reward": fields, "resource": policy,
        "owners": {key: native.get("scriptHashes", {}).get(key) for key in expected}},
        sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    return {"resource": resource, "amount": amount, "ignoreLast": ignore_last == "true",
            "callbackPaths": [["CurrentRun", "Hero", "Traits"]] if callback == "OnGiftPointsAdded" else [],
            "mutationIdentity": policy_identity}


def descriptor(root, entry_id, investigation, *, native=None):
    if not isinstance(entry_id, str) or not entry_id.startswith("questClaim:"):
        return None
    name = entry_id[len("questClaim:"):]
    if name not in QUEST_IDS:
        return None
    status = read(root, ["GameState", "QuestStatus", name])
    if status is not None and type(status) is not str:
        raise save_advanced.AdvancedMutationError("Save Editor quest reward status has an incompatible type.")
    evidence = _reward(root, name, investigation, native=native)
    for path in _counter_paths(evidence["resource"]):
        integer(read(root, path, 0))
    completion = read(root, ["GameState", "QuestsCompleted", name])
    if completion is not None:
        save_advanced.validate_scalar(completion, "boolean")
    return {"id": entry_id, "domain": "questRewards", "rawId": name,
            "path": ["GameState", "QuestStatus", name], "before": status == "CashedOut",
            "valueType": "boolean", "mutationKinds": ("set",), "choices": (False, True),
            "ownerEvidence": evidence, "constraints": {}}


def rows(root, language, investigation, game_path=None, *, include_absent=False):
    zh = language == "zh-CN"
    # One browse is one captured source observation. Independent descriptors
    # used by Stage/review/Apply still refresh before granting authority.
    investigation._refresh()
    native = investigation.native
    try:
        statuses = owner(root, ["GameState", "QuestStatus"])
    except ValueError:
        statuses = None
    names = ({name for name, _ in statuses.entries() if type(name) is str and name in QUEST_IDS}
             if statuses is not None else set())
    if include_absent:
        names.update(set(native.get("quests", {})) & QUEST_IDS)
    localized = official_display_names(names, language, game_path=game_path)
    english = localized if not zh else official_display_names(names, "en", game_path=game_path)
    result = []
    for name in sorted(names):
        title = localized.get(name) or name
        row = {"id": "questClaim:" + name, "entityId": "quest:" + name, "entityName": title,
               "domain": "questRewards", "rawId": name, "path": ["GameState", "QuestStatus", name],
               "name": "发放奖励并标记已领取" if zh else "Grant reward and mark claimed",
               "englishName": "Grant reward and mark claimed", "valueType": "boolean", "choices": [False, True],
               "group": "命运清单奖励" if zh else "Fated List rewards"}
        try:
            info = descriptor(root, row["id"], investigation, native=native)
        except (ValueError, KeyError) as error:
            row.update(value=None, editable=False, mutationKinds=[], reasonDiagnostic=str(error),
                       reason=(("此离线发放动作无法完整确定：{}；普通任务与资源字段仍可直接编辑。" if zh else
                                "This offline grant cannot be resolved: {}. Ordinary quest and resource fields remain editable.").format(error)))
        else:
            evidence = info["ownerEvidence"]
            resource_name = official_display_names((evidence["resource"],), language, game_path=game_path).get(evidence["resource"], evidence["resource"])
            row.update(value=info["before"], editable=not info["before"], mutationKinds=[] if info["before"] else ["set"],
                rewardResource=evidence["resource"], rewardAmount=evidence["amount"],
                reason=(("已领取；不会再次发放奖励。" if zh else "Already claimed; no duplicate reward is granted.") if info["before"] else
                        (("离线发放 {} × {}，记录资源、累计与当前挑战获得量，并标记已领取；保留活动目标提示，不运行游戏表现或判断未来条件。" if zh else
                          "Offline grant: {} × {}; records inventory, lifetime and CurrentRun gains and marks claimed. Active objective prompts are preserved; no game presentation or future eligibility evaluation.").format(resource_name, evidence["amount"]))))
            if not info["before"]:
                row["warning"] = row["reason"]
        result.append(row)
    return result


def validate(info, operation, value):
    if operation != "set" or type(value) is not bool or info["before"] and value is False:
        raise save_advanced.AdvancedMutationError("Save Editor reward claim requires a grant intent; direct quest status edits do not refund rewards.")
    return value


def _counter_paths(resource):
    return (["GameState", "Resources", resource], ["GameState", "LifetimeResourcesGained", resource],
            ["CurrentRun", "ResourcesGained", resource])


def apply_batch(root, intents):
    claims = sorted((intent for intent in intents if intent["id"].startswith("questClaim:") and intent["after"]),
                    key=lambda item: item["id"])
    for intent in claims:
        name, evidence = intent["rawId"], intent["ownerEvidence"]
        if read(root, ["GameState", "QuestStatus", name]) == "CashedOut":
            raise save_advanced.AdvancedMutationError("Save Editor reward was already claimed by another action.", conflict=True)
        for path in _counter_paths(evidence["resource"]):
            add(root, path, evidence["amount"])
        if not evidence["ignoreLast"]:
            owner(root, ["GameState"], create=True)["UnviewedLastResourceGained"] = evidence["resource"]
        owner(root, ["GameState", "QuestStatus"], create=True)[name] = "CashedOut"
        owner(root, ["GameState", "QuestsCompleted"], create=True)[name] = True


def linked_changes(root, intents):
    own = [intent for intent in intents if intent["id"].startswith("questClaim:") and intent["after"]]
    if not own:
        return []
    candidate = copy.deepcopy(root)
    apply_batch(candidate, own)
    paths = set()
    for intent in own:
        paths.update(tuple(path) for path in _counter_paths(intent["ownerEvidence"]["resource"]))
        paths.add(("GameState", "QuestsCompleted", intent["rawId"]))
        if not intent["ownerEvidence"]["ignoreLast"]:
            paths.add(("GameState", "UnviewedLastResourceGained"))
    result = []
    for path in sorted(paths):
        before, after = read(root, path), read(candidate, path)
        if before != after:
            identity = "linked:questReward:" + "/".join(path)
            result.append(effect(identity, "questRewards", "Quest reward · " + " / ".join(path[1:]), list(path), before, after))
    return result


def validate_batch(source, intents, project_other):
    own = [intent for intent in intents if intent["id"].startswith("questClaim:") and intent["after"]]
    if not own:
        return
    claim_paths = [path for intent in own for path in _claim_paths(intent)]
    other_intents = [intent for intent in intents if not intent["id"].startswith("questClaim:")]
    others = project_other(other_intents)
    other_paths = [intent["path"] for intent in other_intents]
    other_paths.extend(save_advanced.changed_paths(source, others))
    if any(save_advanced.paths_overlap(left, right) for left in claim_paths
           for right in other_paths):
        raise save_advanced.AdvancedMutationError("Save Editor explicit reward and another action affect the same saved owner; revise or remove one intent.", conflict=True)


def _claim_paths(intent):
    paths = [*_counter_paths(intent["ownerEvidence"]["resource"]),
             ["GameState", "QuestStatus", intent["rawId"]],
             ["GameState", "QuestsCompleted", intent["rawId"]]]
    if not intent["ownerEvidence"]["ignoreLast"]:
        paths.append(["GameState", "UnviewedLastResourceGained"])
    paths.extend(intent["ownerEvidence"].get("callbackPaths", ()))
    return paths


def overlaps_pending_claim(intents, info):
    for intent in intents:
        if not intent["id"].startswith("questClaim:") or not intent["after"] or intent["id"] == info["id"]:
            continue
        if any(save_advanced.paths_overlap(path, info["path"]) for path in _claim_paths(intent)):
            return True
    return False
