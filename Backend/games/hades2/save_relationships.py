"""Edit stored gift quantities and their proven aggregate, without replaying gifts."""
import copy

from . import save_advanced
from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable
from .save_mutation_utils import MAX_INTEGER, add, effect, integer, owner, read


def _identity(person, resource):
    # Existing native identifiers use this form. Reject unroundtrippable names
    # at this semantic seam; their actual paths remain writable in Advanced.
    return "gift:" + person + ":" + resource


def _parts(entry_id):
    parts = entry_id.split(":")
    if len(parts) != 3 or parts[0] != "gift" or not all(parts[1:]):
        raise save_advanced.AdvancedMutationError("Save Editor gift identity is invalid; use its typed Advanced path.")
    return parts[1:]


def _reconstructed_total(root, resource):
    gifts = owner(root, ["GameState", "GiftRecord"])
    if gifts is None:
        raise save_advanced.AdvancedMutationError("Save Editor gift quantities are unavailable for aggregate reconstruction.")
    total = 0
    multiplicity = {}
    for person, _ in gifts.entries():
        if type(person) is str:
            multiplicity[person] = multiplicity.get(person, 0) + 1
    for person, record in gifts.entries():
        if type(person) is not str:
            continue
        if not isinstance(record, LuaTable):
            raise save_advanced.AdvancedMutationError("Save Editor gift aggregate cannot be reconstructed from a malformed person owner.")
        # Only a person contributing this resource needs an unambiguous owner.
        amount = record.get(resource)
        if amount is None:
            continue
        if multiplicity[person] != 1:
            raise AmbiguousLuaKeyError("Save Editor gift aggregate contains duplicate contributing people.")
        total = integer(total + integer(amount))
    return total


def descriptor(root, entry_id):
    if not isinstance(entry_id, str) or not entry_id.startswith("gift:"):
        return None
    person, resource = _parts(entry_id)
    path = ["GameState", "GiftRecord", person, resource]
    before = integer(save_advanced.resolve_path(root, path))
    total = read(root, ["GameState", "GiftResourceRecord", resource])
    if total is None:
        _reconstructed_total(root, resource)
    else:
        integer(total)
    return {"id": entry_id, "domain": "relationships", "rawId": person + " / " + resource,
            "path": path, "before": before, "valueType": "integer",
            "mutationKinds": ("set",), "constraints": {"min": 0, "max": MAX_INTEGER, "integer": True}}


def rows(root, language="zh-CN", game_path=None):
    zh = language == "zh-CN"
    try:
        gifts = owner(root, ["GameState", "GiftRecord"])
    except ValueError:
        return []  # Other relationship owners and Advanced remain available.
    if gifts is None:
        return []
    identities = []
    for person, record in gifts.entries():
        if type(person) is str and isinstance(record, LuaTable):
            identities.extend((person, resource) for resource, _ in record.entries() if type(resource) is str)
    names = {item for pair in identities for item in pair}
    native = official_display_names(names, language, game_path=game_path)
    english = native if not zh else official_display_names(names, "en", game_path=game_path)
    result = []
    for person, resource in sorted(set(identities)):
        identity = _identity(person, resource)
        label = (native.get(person) or person) + " · " + (native.get(resource) or resource)
        en = (english.get(person) or person) + " · " + (english.get(resource) or resource)
        row = {"id": identity, "domain": "relationships", "rawId": person + " / " + resource,
            "path": ["GameState", "GiftRecord", person, resource], "name": label, "englishName": en,
            "entityId": "person:" + person, "entityName": native.get(person) or person,
            "valueType": "integer", "choices": [], "group": "赠礼数量" if zh else "Gift quantities"}
        try:
            info = descriptor(root, identity)
        except (ValueError, KeyError) as error:
            row.update(value=None, editable=False, mutationKinds=[],
                ownerState="ambiguous" if isinstance(error, AmbiguousLuaKeyError) else "unsupported",
                blockReasonCode="ambiguousOwner" if isinstance(error, AmbiguousLuaKeyError) else "unsupportedOwner",
                reason=("数量或所需资源总计的路径有歧义或类型不符；请检查具体原始记录。" if zh else
                        "The quantity or its required aggregate has an ambiguous path or incompatible type; inspect that record."),
                blockReasonDiagnostic=str(error))
        else:
            row.update(value=info["before"], editable=True, mutationKinds=["set"], constraints=info["constraints"],
                reason=("修改已存储的赠礼数量及资源总计；保留赠礼顺序、剧情与当前挑战，不执行赠礼事件。" if zh else
                        "Edit the stored quantity and resource total; preserve gift order, narrative and CurrentRun without replaying a gift."))
        result.append(row)
    return result


def validate(info, operation, value):
    if operation != "set":
        raise save_advanced.AdvancedMutationError("Save Editor gift quantity requires a set operation.")
    return integer(value)


def apply_intent(root, intent):
    apply_batch(root, (intent,))


def apply_batch(root, intents):
    deltas = {}
    for intent in intents:
        if not intent["id"].startswith("gift:"):
            continue
        person, resource = _parts(intent["id"])
        count_owner = owner(root, ["GameState", "GiftRecord", person])
        if count_owner is None:
            raise save_advanced.AdvancedMutationError("Save Editor gift person owner is missing.")
        count_owner[resource] = integer(intent["after"])
        deltas[resource] = deltas.get(resource, 0) + integer(intent["after"]) - integer(intent["before"])
    if not deltas:
        return
    aggregate = owner(root, ["GameState", "GiftResourceRecord"], create=True)
    for resource, delta in deltas.items():
        if aggregate.get(resource) is None:
            aggregate[resource] = _reconstructed_total(root, resource)
        else:
            add(root, ["GameState", "GiftResourceRecord", resource], delta)


def linked_changes(root, intents):
    own = [intent for intent in intents if intent["id"].startswith("gift:")]
    if not own:
        return []
    candidate = copy.deepcopy(root)
    apply_batch(candidate, own)
    result = []
    for resource in sorted({_parts(intent["id"])[1] for intent in own}):
        path = ["GameState", "GiftResourceRecord", resource]
        before, after = read(root, path), read(candidate, path)
        if before != after:
            result.append(effect("linked:giftTotal:" + resource, "relationships", "Gift resource total · " + resource, path, before, after))
    return result


def validate_batch(root, intents):
    for intent in intents:
        if intent["id"].startswith("gift:"):
            if read(root, intent["path"]) != intent["after"]:
                raise save_advanced.AdvancedMutationError("Save Editor gift quantity conflicts with another action.", conflict=True)


def _owned_paths(intents):
    for intent in intents:
        if intent["id"].startswith("gift:"):
            yield intent["path"]
            yield ["GameState", "GiftResourceRecord", _parts(intent["id"])[1]]


def overlaps_pending_gift(intents, info):
    others = (intent for intent in intents if intent["id"] != info["id"])
    return any(save_advanced.paths_overlap(path, info["path"]) for path in _owned_paths(others))


def validate_transaction_owners(source, intents, apply_other):
    paths = tuple(_owned_paths(intents))
    if not paths:
        return
    others = [intent for intent in intents if not intent["id"].startswith("gift:")]
    candidate = copy.deepcopy(source)
    apply_other(candidate, others)
    for resource in {_parts(intent["id"])[1] for intent in intents if intent["id"].startswith("gift:")}:
        if (read(source, ["GameState", "GiftResourceRecord", resource]) is None
                and _reconstructed_total(source, resource) != _reconstructed_total(candidate, resource)):
            raise save_advanced.AdvancedMutationError("Save Editor another action changes the gift aggregate's reconstruction inputs; revise or remove one intent.", conflict=True)
    other_paths = [intent["path"] for intent in others]
    other_paths.extend(save_advanced.changed_paths(source, candidate))
    if any(save_advanced.paths_overlap(left, right) for left in paths for right in other_paths):
        raise save_advanced.AdvancedMutationError("Save Editor gift quantities/aggregate and another action affect the same owner; revise or remove one intent.", conflict=True)
