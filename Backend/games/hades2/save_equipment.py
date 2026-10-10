"""Hades II durable weapon, aspect, tool, and familiar Save Editor ownership.

Shop purchases write WeaponsUnlocked plus WorldUpgrades/WorldUpgradesAdded.
An aspect level is the contiguous purchased shop tier sequence, not a runtime
trait stack. Changing a durable selector never edits CurrentRun mounts.
"""
import copy

from .localization import official_display_names
from .save_document import AmbiguousLuaKeyError, LuaTable


_WEAPONS = {
    "WeaponStaffSwing": ("BaseStaffAspect", "StaffClearCastAspect", "StaffSelfHitAspect", "StaffRaiseDeadAspect"),
    "WeaponDagger": ("DaggerBackstabAspect", "DaggerBlockAspect", "DaggerHomingThrowAspect", "DaggerTripleAspect"),
    "WeaponTorch": ("TorchSpecialDurationAspect", "TorchDetonateAspect", "TorchSprintRecallAspect", "TorchAutofireAspect"),
    "WeaponAxe": ("AxeRecoveryAspect", "AxeArmCastAspect", "AxePerfectCriticalAspect", "AxeRallyAspect"),
    "WeaponLob": ("LobAmmoBoostAspect", "LobCloseAttackAspect", "LobImpulseAspect", "LobGunAspect"),
    "WeaponSuit": ("BaseSuitAspect", "SuitHexAspect", "SuitMarkCritAspect", "SuitComboAspect"),
}
_TOOLS = ("ToolExorcismBook", "ToolFishingRod", "ToolPickaxe", "ToolShovel")
_FAMILIARS = ("CatFamiliar", "FrogFamiliar", "RavenFamiliar", "HoundFamiliar", "PolecatFamiliar")
_ASPECT_PARENT = {aspect: weapon for weapon, aspects in _WEAPONS.items() for aspect in aspects}
_DEFAULT_ASPECTS = {aspects[0] for aspects in _WEAPONS.values()}
_MARKER_FIELDS = ("WeaponsUnlocked", "WorldUpgrades", "WorldUpgradesAdded")


def _state(root):
    state = root["GameState"]
    if not isinstance(state, LuaTable):
        raise ValueError("Save Editor GameState is malformed.")
    return state


def _table(state, name):
    value = state.get(name)
    if not isinstance(value, LuaTable):
        raise ValueError("Save Editor {} is unavailable or malformed.".format(name))
    return value


def _flag(table, key):
    value = table.get(key)
    if value is not None and type(value) is not bool:
        raise ValueError("Save Editor equipment ownership is not boolean.")
    return value is True


def _markers(state):
    return tuple(_table(state, field) for field in _MARKER_FIELDS)


def _merge_owner_state(*states):
    if "ambiguous" in states:
        return "ambiguous"
    if "unsupported" in states:
        return "unsupported"
    return None


def _marker_write_state(state, keys):
    try:
        markers = _markers(state)
    except AmbiguousLuaKeyError:
        return "ambiguous"
    except ValueError:
        return "unsupported"
    for table in markers:
        for key in keys:
            try:
                _flag(table, key)
            except AmbiguousLuaKeyError:
                return "ambiguous"
            except ValueError:
                return "unsupported"
    return None


def _selection_write_state(state, weapon):
    try:
        _selection(state, weapon)
    except AmbiguousLuaKeyError:
        return "ambiguous"
    except ValueError:
        return "unsupported"
    return None


def _aspect_tier_keys(aspect):
    return (aspect, *("{}{}".format(aspect, tier) for tier in range(2, 6)))


def _owned(state, key):
    # The actual game gives the starter weapon through WeaponsUnlocked
    # without a corresponding WorldUpgrade purchase. Purchase mirrors are
    # intentionally not equal to ownership for every key.
    return _flag(_table(state, "WeaponsUnlocked"), key)


def _set_owned(state, key, owned):
    for table in _markers(state):
        _flag(table, key)  # Never overwrite unknown non-boolean data.
        if owned:
            table[key] = True
        else:
            table.pop(key, None)


def _rank(state, aspect):
    weapon = _ASPECT_PARENT[aspect]
    parent = _owned(state, weapon)
    default = aspect in _DEFAULT_ASPECTS
    owned = parent if default else _owned(state, aspect)
    if owned and not parent:
        raise ValueError("Save Editor owned aspect lacks its base weapon.")
    level = 1 if owned else 0
    gap = False
    for rank in range(2, 6):
        purchased = _owned(state, "{}{}".format(aspect, rank))
        if purchased and (gap or not owned):
            raise ValueError("Save Editor aspect upgrade tiers are not contiguous.")
        if purchased:
            level = rank
        else:
            gap = True
    return level


def _tool_level(state, tool):
    first = _owned(state, tool)
    second = _owned(state, tool + "2")
    if second and not first:
        raise ValueError("Save Editor tool upgrade lacks the initial tool.")
    return 2 if second else (1 if first else 0)


def _set_rank(state, aspect, level):
    for tier in range(1, 6):
        if tier == 1 and aspect in _DEFAULT_ASPECTS:
            # The free aspect has a separate native unlock bit after the shop
            # is opened. Its absence is valid until then, but revocation cannot
            # leave the bit behind.
            if level == 0:
                _set_owned(state, aspect, False)
            elif level > 1:
                owner = _table(state, "WeaponsUnlocked")
                _flag(owner, aspect)
                owner[aspect] = True
            continue
        name = aspect if tier == 1 else "{}{}".format(aspect, tier)
        _set_owned(state, name, tier <= level)


def _selection(state, weapon):
    selections = _table(state, "LastWeaponUpgradeName")
    value = selections.get(weapon)
    if value is None:
        return ""
    if not isinstance(value, str) or value not in _WEAPONS[weapon]:
        raise ValueError("Save Editor weapon selection is unknown.")
    return value


def _names(ids, language, game_path):
    native = official_display_names(ids, language, game_path=game_path)
    en = native if language == "en" else official_display_names(ids, "en", game_path=game_path)
    return native, en


def _row(entry_id, key, path, name, english, value, kind, group,
         *, editable=True, maximum=None, choices=(), choice_names=None,
         block_reason_code=None, owner_state=None):
    row = {
        "id": entry_id, "domain": "weapons", "rawId": key,
        "path": path, "name": name, "englishName": english,
        "value": value, "valueType": kind, "editable": editable,
        "mutationKinds": ["setEnum"] if kind == "enum" and editable else
                         ["set"] if editable else [],
        "group": group, "choices": list(choices),
    }
    if maximum is not None:
        row["constraints"] = {"min": 1 if entry_id.startswith("aspect:") and
                             key in _DEFAULT_ASPECTS else 0,
                             "max": maximum, "integer": True}
    if choice_names is not None:
        row["choiceNames"] = choice_names
    if block_reason_code:
        row["blockReasonCode"] = block_reason_code
    if owner_state:
        row["ownerState"] = owner_state
    return row


def rows(root, language="zh-CN", game_path=None):
    state = _state(root)
    zh = language == "zh-CN"
    native, en = _names(
        set(_WEAPONS) | set(_ASPECT_PARENT) | set(_TOOLS) | set(_FAMILIARS),
        language, game_path,
    )
    result = []
    world_group = "武器解锁" if zh else "Weapon unlocks"
    aspect_group = "武器形态" if zh else "Weapon aspects"
    tool_group = "采集工具" if zh else "Gathering tools"
    familiar_group = "魔宠" if zh else "Familiars"

    for weapon, aspects in _WEAPONS.items():
        title = native.get(weapon) or weapon
        english = en.get(weapon) or weapon
        weapon_owner_state = None
        owned = None
        try:
            owned = _owned(state, weapon)
        except AmbiguousLuaKeyError:
            weapon_owner_state = "ambiguous"
        except ValueError:
            weapon_owner_state = "unsupported"
        if weapon_owner_state is None and weapon != "WeaponStaffSwing":
            marker_keys = [weapon]
            selection_state = None
            if owned is True:
                for aspect in aspects:
                    marker_keys.extend(_aspect_tier_keys(aspect))
                selection_state = _selection_write_state(state, weapon)
            weapon_owner_state = _merge_owner_state(
                _marker_write_state(state, marker_keys),
                selection_state,
            )
        weapon_editable = (
            weapon_owner_state is None and weapon != "WeaponStaffSwing"
        )
        result.append(_row(
            "weapon:" + weapon, weapon, ["GameState", "WeaponsUnlocked", weapon],
            title, english, owned, "boolean", world_group,
            editable=weapon_editable,
            choices=(False, True),
            block_reason_code=(
                "ambiguousOwner" if weapon_owner_state == "ambiguous"
                else "unsupportedOwner" if weapon_owner_state == "unsupported"
                else "starterWeapon" if weapon == "WeaponStaffSwing"
                else None
            ),
            owner_state=weapon_owner_state,
        ))

        for aspect in aspects:
            aspect_owner_state = None
            level = None
            try:
                level = _rank(state, aspect)
            except AmbiguousLuaKeyError:
                aspect_owner_state = "ambiguous"
            except ValueError:
                aspect_owner_state = "unsupported"
            name = native.get(aspect) or aspect
            english_name = en.get(aspect) or aspect
            if aspect_owner_state is None:
                marker_keys = list(_aspect_tier_keys(aspect))
                if owned is False:
                    marker_keys.append(weapon)
                selection_state = (
                    _selection_write_state(state, weapon)
                    if aspect not in _DEFAULT_ASPECTS else None
                )
                aspect_owner_state = _merge_owner_state(
                    _marker_write_state(state, marker_keys),
                    selection_state,
                )
            aspect_editable = (
                aspect_owner_state is None
                and (owned is True or aspect not in _DEFAULT_ASPECTS)
            )
            result.append(_row(
                "aspect:" + aspect, aspect, ["GameState", "WeaponsUnlocked", aspect],
                title + " · " + name + (" · 等级" if zh else " · Rank"),
                english + " · " + english_name + " · Rank", level, "integer", aspect_group,
                editable=aspect_editable, maximum=5,
                block_reason_code=(
                    "ambiguousOwner" if aspect_owner_state == "ambiguous"
                    else "unsupportedOwner" if aspect_owner_state == "unsupported"
                    else None if aspect_editable
                    else "baseWeaponRequired"
                ),
                owner_state=aspect_owner_state,
            ))

        if owned is True:
            selection_owner_state = None
            chosen = None
            try:
                chosen = _selection(state, weapon)
            except AmbiguousLuaKeyError:
                selection_owner_state = "ambiguous"
            except ValueError:
                selection_owner_state = "unsupported"
            choices = ("", *aspects)
            choice_names = {"": "默认形态" if zh else "Default aspect"}
            choice_names.update({
                aspect: native.get(aspect) or aspect
                for aspect in aspects
            })
            result.append(_row(
                "aspectSelection:" + weapon, weapon,
                ["GameState", "LastWeaponUpgradeName", weapon],
                title + (" · 装备形态" if zh else " · Selected aspect"),
                english + " · Selected aspect", chosen, "enum", aspect_group,
                editable=selection_owner_state is None,
                choices=choices, choice_names=choice_names,
                block_reason_code=(
                    "ambiguousOwner" if selection_owner_state == "ambiguous"
                    else "unsupportedOwner" if selection_owner_state == "unsupported"
                    else None
                ),
                owner_state=selection_owner_state,
            ))

    for tool in _TOOLS:
        tool_owner_state = None
        level = None
        try:
            level = _tool_level(state, tool)
        except AmbiguousLuaKeyError:
            tool_owner_state = "ambiguous"
        except ValueError:
            tool_owner_state = "unsupported"
        if tool_owner_state is None:
            tool_owner_state = _marker_write_state(
                state, (tool, tool + "2")
            )
        name = native.get(tool) or tool
        english = en.get(tool) or tool
        result.append(_row(
            "tool:" + tool, tool, ["GameState", "WeaponsUnlocked", tool],
            name + (" · 等级" if zh else " · Level"),
            english + " · Level", level, "integer", tool_group, maximum=2,
            editable=tool_owner_state is None,
            block_reason_code=(
                "ambiguousOwner" if tool_owner_state == "ambiguous"
                else "unsupportedOwner" if tool_owner_state == "unsupported"
                else None
            ),
            owner_state=tool_owner_state,
        ))

    try:
        familiar_unlocks = state.get("FamiliarsUnlocked")
    except AmbiguousLuaKeyError:
        familiar_unlocks = None
        familiar_owner_state = "ambiguous"
    else:
        familiar_owner_state = (
            None if familiar_unlocks is None or isinstance(familiar_unlocks, LuaTable)
            else "unsupported"
        )

    if isinstance(familiar_unlocks, LuaTable) or familiar_owner_state is not None:
        for familiar in _FAMILIARS:
            owner_state = familiar_owner_state
            owned = None
            if isinstance(familiar_unlocks, LuaTable):
                try:
                    owned = _flag(familiar_unlocks, familiar)
                except AmbiguousLuaKeyError:
                    owner_state = "ambiguous"
                except ValueError:
                    owner_state = "unsupported"
            name = native.get(familiar) or familiar
            english = en.get(familiar) or familiar
            result.append(_row(
                "familiar:" + familiar, familiar,
                ["GameState", "FamiliarsUnlocked", familiar],
                name, english, owned, "boolean", familiar_group,
                editable=owner_state is None,
                choices=(False, True),
                block_reason_code=(
                    "ambiguousOwner" if owner_state == "ambiguous"
                    else "unsupportedOwner" if owner_state == "unsupported"
                    else None
                ),
                owner_state=owner_state,
            ))

        selection_owner_state = familiar_owner_state
        chosen = None
        if selection_owner_state is None:
            try:
                chosen = state.get("EquippedFamiliar")
            except AmbiguousLuaKeyError:
                selection_owner_state = "ambiguous"
            else:
                if chosen is not None and (
                    not isinstance(chosen, str) or chosen not in _FAMILIARS
                ):
                    selection_owner_state = "unsupported"
        choices = ("", *_FAMILIARS)
        choice_names = {"": "不携带" if zh else "None"}
        choice_names.update({f: native.get(f) or f for f in _FAMILIARS})
        result.append(_row(
            "familiarSelection", "EquippedFamiliar",
            ["GameState", "EquippedFamiliar"],
            "当前魔宠" if zh else "Equipped Familiar",
            "Equipped Familiar", chosen or "", "enum", familiar_group,
            editable=selection_owner_state is None,
            choices=choices, choice_names=choice_names,
            block_reason_code=(
                "ambiguousOwner" if selection_owner_state == "ambiguous"
                else "unsupportedOwner" if selection_owner_state == "unsupported"
                else None
            ),
            owner_state=selection_owner_state,
        ))
    return result


def descriptor(root, entry_id, game_path=None):
    if not isinstance(entry_id, str) or not (
        entry_id.startswith(("weapon:", "aspect:", "aspectSelection:", "tool:", "familiar:"))
        or entry_id == "familiarSelection"
    ):
        return None
    for row in rows(root, "en", game_path=game_path):
        if row["id"] == entry_id:
            if row.get("ownerState") == "ambiguous":
                raise AmbiguousLuaKeyError(
                    "Save Editor semantic owner is ambiguous."
                )
            if row.get("ownerState") == "unsupported":
                raise ValueError("Save Editor semantic owner is unsupported.")
            return {
                "id": entry_id, "domain": "weapons", "rawId": row["rawId"],
                "path": row["path"], "before": row["value"],
                "valueType": row["valueType"], "mutationKinds": tuple(row["mutationKinds"]),
                "constraints": row.get("constraints", {}),
                "choices": row["choices"],
            }
    return None


def validate(descriptor_value, operation, value):
    if operation not in descriptor_value["mutationKinds"]:
        raise ValueError("Save Editor equipment mutation is not authorized.")
    kind = descriptor_value["valueType"]
    if kind == "boolean":
        if operation != "set" or type(value) is not bool:
            raise ValueError("Save Editor equipment unlock must be boolean.")
    elif kind == "integer":
        limits = descriptor_value["constraints"]
        if (operation != "set" or type(value) is not int or
                not limits["min"] <= value <= limits["max"]):
            raise ValueError("Save Editor equipment rank is out of range.")
    elif kind == "enum":
        if operation != "setEnum" or type(value) is not str or value not in descriptor_value["choices"]:
            raise ValueError("Save Editor equipment selection is invalid.")
    else:
        raise ValueError("Save Editor equipment mutation type is unsupported.")


def apply_intent(root, intent):
    state = _state(root)
    entry_id = intent["id"]
    after = intent["after"]
    if entry_id.startswith("weapon:"):
        weapon = entry_id[len("weapon:"):]
        if weapon not in _WEAPONS:
            raise ValueError("Save Editor weapon is unknown.")
        _set_owned(state, weapon, after)
        if not after:
            for aspect in _WEAPONS[weapon]:
                _set_rank(state, aspect, 0)
            _table(state, "LastWeaponUpgradeName").pop(weapon, None)
        return
    if entry_id.startswith("aspect:"):
        aspect = entry_id[len("aspect:"):]
        if aspect not in _ASPECT_PARENT:
            raise ValueError("Save Editor aspect is unknown.")
        # A starter weapon may already be owned without purchase markers.
        # Only create linked parent purchase records if ownership changes.
        if after and not _owned(state, _ASPECT_PARENT[aspect]):
            _set_owned(state, _ASPECT_PARENT[aspect], True)
        _set_rank(state, aspect, after)
        if not after:
            selected = _table(state, "LastWeaponUpgradeName")
            if selected.get(_ASPECT_PARENT[aspect]) == aspect:
                selected.pop(_ASPECT_PARENT[aspect], None)
        return
    if entry_id.startswith("aspectSelection:"):
        weapon = entry_id[len("aspectSelection:"):]
        if weapon not in _WEAPONS or (after and after not in _WEAPONS[weapon]):
            raise ValueError("Save Editor selected aspect is unknown.")
        owner = _table(state, "LastWeaponUpgradeName")
        if after:
            owner[weapon] = after
        else:
            owner.pop(weapon, None)
        return
    if entry_id.startswith("tool:"):
        tool = entry_id[len("tool:"):]
        if tool not in _TOOLS:
            raise ValueError("Save Editor tool is unknown.")
        _set_owned(state, tool, after >= 1)
        _set_owned(state, tool + "2", after == 2)
        return
    if entry_id.startswith("familiar:"):
        familiar = entry_id[len("familiar:"):]
        if familiar not in _FAMILIARS:
            raise ValueError("Save Editor familiar is unknown.")
        table = _table(state, "FamiliarsUnlocked")
        if after:
            table[familiar] = True
        else:
            table.pop(familiar, None)
            if state.get("EquippedFamiliar") == familiar:
                state.pop("EquippedFamiliar", None)
        return
    if entry_id == "familiarSelection":
        if after:
            if after not in _FAMILIARS:
                raise ValueError("Save Editor familiar selection is unknown.")
            state["EquippedFamiliar"] = after
        else:
            state.pop("EquippedFamiliar", None)
        return
    raise ValueError("Save Editor equipment mutation is unknown.")


def _semantic_values(root):
    """Compact owned-state projection for meaningful automatic effects."""
    state = _state(root)
    values = {}
    for weapon, aspects in _WEAPONS.items():
        try:
            values["weapon:" + weapon] = _owned(state, weapon)
        except (AmbiguousLuaKeyError, ValueError):
            continue
        for aspect in aspects:
            try:
                values["aspect:" + aspect] = _rank(state, aspect)
            except (AmbiguousLuaKeyError, ValueError):
                pass
        try:
            values["aspectSelection:" + weapon] = _selection(state, weapon)
        except (AmbiguousLuaKeyError, ValueError):
            pass
    for tool in _TOOLS:
        try:
            values["tool:" + tool] = _tool_level(state, tool)
        except (AmbiguousLuaKeyError, ValueError):
            pass
    try:
        familiars = state.get("FamiliarsUnlocked")
    except AmbiguousLuaKeyError:
        familiars = None
    if isinstance(familiars, LuaTable):
        for familiar in _FAMILIARS:
            try:
                values["familiar:" + familiar] = _flag(familiars, familiar)
            except (AmbiguousLuaKeyError, ValueError):
                pass
        try:
            value = state.get("EquippedFamiliar")
        except AmbiguousLuaKeyError:
            value = object()
        if value is None or (isinstance(value, str) and value in _FAMILIARS):
            values["familiarSelection"] = value or ""
    return values


def linked_changes(root, intents):
    own = [intent for intent in intents if intent["domain"] == "weapons"]
    if not own:
        return []
    before = _semantic_values(root)
    english_labels = {row["id"]: row["name"] for row in rows(root, "en")}
    candidate = copy.deepcopy(root)
    for intent in own:
        apply_intent(candidate, intent)
    after = _semantic_values(candidate)
    edited = {intent["id"] for intent in own}
    changes = []
    for key in sorted(set(before) & set(after)):
        if key not in edited and before[key] != after[key]:
            changes.append({
                "id": "linked:" + key, "domain": "weapons", "rawId": key,
                "name": english_labels.get(key, key), "operation": "set",
                "before": before[key], "after": after[key],
            })
    return changes


def validate_batch(root, intents):
    """Reject contradictory staged intents and impossible final ownership."""
    own = [intent for intent in intents if intent["domain"] == "weapons"]
    if not own:
        return
    current = _semantic_values(root)
    affected_weapons = set()
    familiars_changed = False
    for intent in own:
        entry = intent["id"]
        if current.get(entry) != intent["after"]:
            raise ValueError("Save Editor equipment changes conflict.")
        if entry.startswith("weapon:"):
            affected_weapons.add(entry[len("weapon:"):])
        elif entry.startswith("aspect:"):
            affected_weapons.add(_ASPECT_PARENT[entry[len("aspect:"):]])
        elif entry.startswith("aspectSelection:"):
            affected_weapons.add(entry[len("aspectSelection:"):])
        elif entry.startswith("familiar:") or entry == "familiarSelection":
            familiars_changed = True

    for weapon in affected_weapons:
        aspects = _WEAPONS[weapon]
        if "weapon:" + weapon not in current:
            continue
        owned = current["weapon:" + weapon]
        for aspect in aspects:
            key = "aspect:" + aspect
            if key in current:
                if not owned and current[key] > 0:
                    raise ValueError("Save Editor locked weapon has acquired aspects.")
                if owned and aspect in _DEFAULT_ASPECTS and current[key] < 1:
                    raise ValueError("Save Editor unlocked weapon lacks default aspect.")
        selected = current.get("aspectSelection:" + weapon)
        if selected and (not owned or current.get("aspect:" + selected, 0) == 0):
            raise ValueError("Save Editor selected aspect is not purchased.")

    if familiars_changed:
        familiar = current.get("familiarSelection")
        if familiar and current.get("familiar:" + familiar) is not True:
            raise ValueError("Save Editor equipped familiar must be unlocked.")
