"""Deep Host -> Hades backend module-protocol command contract.

The public seam is Hades2CommandContract.dispatch(command, params, request_id).
Command identity, Host timeout metadata, validation, request-id policy, routing
and the Hades presentation-error exit live together here.

Resident Lua commands are a separate internal interface behind
Hades2ResidentSession and intentionally do not consume this registry.
"""
from dataclasses import dataclass
import copy
import math
import subprocess

from core.errors import PresentableError

from . import preparation, save_advanced, save_container
from .diagnostics import build_diagnostics, export_diagnostics
from .error_presentation import Hades2PresentationError, presentation_for
from .operation_budgets import (
    CONNECT_ATTACH_HEADROOM_SECONDS,
    CONNECT_OPERATION_BUDGET_SECONDS,
    DEFAULT_COMMAND_TIMEOUT_SECONDS,
    DIAGNOSTICS_OPERATION_BUDGET_SECONDS,
    DISABLE_ALL_OPERATION_BUDGET_SECONDS,
    DISCONNECT_OPERATION_BUDGET_SECONDS,
    EXPORT_DIAGNOSTICS_OPERATION_BUDGET_SECONDS,
    EXPORT_REVEAL_TIMEOUT_SECONDS,
    LAUNCH_OPERATION_BUDGET_SECONDS,
    LAUNCH_TIMEOUT_SECONDS,
    MAILBOX_COMMAND_BUDGET_SECONDS,
    POST_PREPARATION_SCAN_BUDGET_SECONDS,
    PREPARATION_OPERATION_BUDGET_SECONDS,
    RESTORE_OPERATION_BUDGET_SECONDS,
    SAVE_EDITOR_OPERATION_BUDGET_SECONDS,
    STATUS_COMMAND_BUDGET_SECONDS,
)
from .runtime_error_presentation import present_runtime_error
from .save_workspace import (
    SAVE_EDITOR_DOMAINS,
    SAVE_EDITOR_SCOPES,
    SAVE_EDITOR_MUTATION_KINDS,
    SAVE_EDITOR_STATE_FILTERS,
)
from .schema import (
    BOON_RARITY_TARGETS,
    MAX_AMOUNT,
    MAX_TRAIT_LEVEL,
    STAT_RULES,
    VITALS,
    is_known_element,
    is_valid_next_occurrence_target,
    validate_desired_feature_value,
    validate_gathering_desired,
    validate_chaos_gate_probability,
)


def _params(raw):
    return copy.deepcopy(dict(raw or {}))


def _identity(raw):
    return _params(raw)


def _connect(raw):
    params = _params(raw)
    probe_runtime = params.get("probeRuntime", True)
    if type(probe_runtime) is not bool:
        raise ValueError("probeRuntime 必须为布尔值。")
    recover_lost_attach = params.get("recoverLostAttach", False)
    if type(recover_lost_attach) is not bool:
        raise ValueError("recoverLostAttach 必须为布尔值。")
    return {"probeRuntime": probe_runtime, "recoverLostAttach": recover_lost_attach}


def _set_desired(raw):
    params = _params(raw)
    feature = params.get("feature")
    value = validate_desired_feature_value(feature, params.get("value"))
    return {"feature": feature, "value": value}


def _set_gathering_desired(raw):
    params = _params(raw)
    if "probability" not in params:
        raise ValueError("概率必须为 0–100。")
    probability = validate_gathering_desired(params.get("family"), params["probability"])
    return {"family": params["family"], "probability": probability}


def _set_chaos_gate_desired(raw):
    params = _params(raw)
    if "probability" not in params:
        raise ValueError("概率必须为 0–100。")
    return {"probability": validate_chaos_gate_probability(params["probability"])}


def _generate_gathering(raw):
    params = _params(raw)
    validate_gathering_desired(params.get("family"), None)
    token = params.get("scopeToken")
    if not isinstance(token, str) or not 1 <= len(token) <= 128:
        raise ValueError("请刷新当前房间后再生成采集点。")
    return {"family": params["family"], "scopeToken": token}


def _generate_chaos_gate(raw):
    token = _params(raw).get("scopeToken")
    if not isinstance(token, str) or not 1 <= len(token) <= 128:
        raise ValueError("请刷新当前房间后再生成混沌之门。")
    return {"scopeToken": token}


def _generate_chamber_facility(raw):
    params = _params(raw)
    facility = params.get("facility")
    token = params.get("scopeToken")
    if (type(facility) is not str or not 1 <= len(facility) <= 48
            or not facility.isascii() or not facility.isidentifier()
            or type(token) is not str or not 1 <= len(token) <= 128):
        raise ValueError("请刷新当前房间后再生成房间设施。")
    return {"facility": facility, "scopeToken": token}


def _mature_garden(raw):
    token = _params(raw).get("scopeToken")
    if not isinstance(token, str) or not 1 <= len(token) <= 128:
        raise ValueError("hades2.garden.unavailable")
    return {"scopeToken": token}


def _set_vital(raw):
    params = _params(raw)
    vital = params.get("vital")
    field = params.get("field")
    value = params.get("value")
    if vital not in VITALS or field not in ("current", "max"):
        raise ValueError("局内数值字段无效。")
    if vital == "armor" and field != "current":
        raise ValueError("护甲仅提供当前值，不存在可编辑上限。")
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= MAX_AMOUNT
    ):
        raise ValueError(f"局内数值必须为 0–{MAX_AMOUNT}。")
    if vital == "health" and value < 1:
        raise ValueError("生命值必须至少为 1。")
    return params


def _set_counter(raw):
    params = _params(raw)
    if params.get("counter") not in ("spellCharge", "biomeTime"):
        raise ValueError("未知局内计数器。")
    value = params.get("value")
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= MAX_AMOUNT
    ):
        if params["counter"] == "biomeTime":
            raise ValueError("区域限时必须为 0–999999 秒。")
        raise ValueError(f"巫咒充能必须为 0–{MAX_AMOUNT}。")
    if params["counter"] == "biomeTime" and value % 1 != 0:
        raise ValueError("区域限时必须使用整数秒。")
    return params


def _lock_biome_time(raw):
    params = _params(raw)
    if type(params.get("locked")) is not bool:
        raise ValueError("区域限时锁定状态必须为布尔值。")
    return {"locked": params["locked"]}


def _lock_vital(raw):
    params = _params(raw)
    if params.get("vital") not in VITALS:
        raise ValueError("未知局内数值。")
    if type(params.get("locked")) is not bool:
        raise ValueError("锁定值必须为布尔值。")
    return params


def _set_stat(raw):
    params = _params(raw)
    stat = params.get("stat")
    locked = params.get("locked")
    value = params.get("value")
    rule = STAT_RULES.get(stat)
    if rule is None:
        raise ValueError("未知属性。")
    if type(locked) is not bool:
        raise ValueError("锁定值必须为布尔值。")
    if locked:
        if (
            type(value) not in (int, float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise ValueError("属性值必须为有限数值。")
        if rule.get("integer") and type(value) is not int:
            raise ValueError(rule["error"])
        if not rule["min"] <= value <= rule["max"]:
            raise ValueError(rule["error"])
    return params


def _set_element(raw):
    params = _params(raw)
    if not is_known_element(params.get("element")):
        raise ValueError("未知元素。")
    amount = params.get("amount")
    if type(amount) is not int or not 0 <= amount <= MAX_AMOUNT:
        raise ValueError(f"元素数量必须为 0–{MAX_AMOUNT} 的整数。")
    return params


def _lock_element(raw):
    params = _params(raw)
    if not is_known_element(params.get("element")):
        raise ValueError("未知元素。")
    if type(params.get("locked")) is not bool:
        raise ValueError("锁定值必须为布尔值。")
    return params


def _set_resource(raw):
    params = _params(raw)
    if type(params.get("amount")) is not int or not 0 <= params["amount"] <= MAX_AMOUNT:
        raise ValueError(f"数量必须是 0–{MAX_AMOUNT} 的整数。")
    if not isinstance(params.get("resource"), str) or not params["resource"]:
        raise ValueError("请选择资源。")
    return params


def _lock_resource(raw):
    params = _params(raw)
    if not isinstance(params.get("resource"), str) or not params["resource"]:
        raise ValueError("请选择资源。")
    if type(params.get("locked")) is not bool:
        raise ValueError("锁定值必须为布尔值。")
    return params


def _set_rerolls(raw):
    params = _params(raw)
    if type(params.get("amount")) is not int or not 0 <= params["amount"] <= MAX_AMOUNT:
        raise ValueError(f"数量必须是 0–{MAX_AMOUNT} 的整数。")
    return params


def _lock_rerolls(raw):
    params = _params(raw)
    if type(params.get("locked")) is not bool:
        raise ValueError("锁定值必须为布尔值。")
    return params


def _acquisition(params):
    # Exact acquisition takes rarity and level from the caller, never from the
    # Boon Rarity panel. Which values the selected target accepts is resident
    # catalog data (`rarities`, `supportsLevel`); the resident enforces it. An
    # absent rarity means the target takes none; an absent level is one stack.
    if "rarity" in params:
        rarity = params["rarity"]
        if not isinstance(rarity, str) or not rarity:
            raise ValueError("获取稀有度无效。")
    if "level" in params:
        level = params["level"]
        if type(level) is not int or not 1 <= level <= MAX_TRAIT_LEVEL:
            raise ValueError("获取等级无效。")
    return params


def _spawn_reward(raw):
    params = _params(raw)
    if not isinstance(params.get("reward"), str) or not params["reward"]:
        raise ValueError("请选择掉落物或祝福。")
    return _acquisition(params)


def _chaos_pair(raw):
    params = _params(raw)
    blessing = params.get("blessing")
    curse = params.get("curse")
    if (
        not isinstance(blessing, str)
        or not blessing
        or not isinstance(curse, str)
        or not curse
    ):
        raise ValueError("请选择掉落物或祝福。")
    return _acquisition(params)


def _special_choice(raw):
    params = _params(raw)
    source = params.get("source")
    if not isinstance(source, str) or not source:
        raise ValueError("请选择支持原生奖励选择界面的角色。")
    return params


def _trait_mutation(command):
    def validate(raw):
        params = _params(raw)
        required_strings = ("generationId", "runId", "instanceId", "trait", "family")
        if any(
            not isinstance(params.get(key), str) or not params[key]
            for key in required_strings
        ):
            raise ValueError("请选择当前局祝福。")
        level = params.get("expectedLevel")
        if type(level) is not int or level < 1:
            raise ValueError("请选择当前局祝福。")
        same_count = params.get("expectedSameNameCount")
        if type(same_count) is not int or same_count < 1:
            raise ValueError("请选择当前局祝福。")
        rarity = params.get("expectedRarity")
        if not isinstance(rarity, str):
            raise ValueError("请选择当前局祝福。")
        remaining = params.get("expectedRemainingUses")
        if remaining is not None and (
            type(remaining) not in (int, float)
            or isinstance(remaining, bool)
            or not math.isfinite(remaining)
            or remaining < 0
        ):
            raise ValueError("请选择当前局效果。")
        if command in ("set_trait_remaining_uses", "expire_trait") and remaining is None:
            raise ValueError("请选择当前局效果。")
        if command == "set_trait_level":
            target_level = params.get("targetLevel")
            if (
                type(target_level) is not int
                or target_level <= level
                or target_level > MAX_TRAIT_LEVEL
            ):
                raise ValueError("目标等级必须高于当前等级。")
        if command == "set_trait_rarity":
            if params.get("rarity") not in BOON_RARITY_TARGETS:
                raise ValueError("最低稀有度无效。")
        if command == "set_trait_remaining_uses":
            target_uses = params.get("targetRemainingUses")
            if type(target_uses) is not int or not 1 <= target_uses <= 999999:
                raise ValueError("剩余次数必须为 1–999999 的整数。")
        return params

    return validate


def _boon_rarity(raw):
    params = _params(raw)
    if "multiplier" in params:
        raise ValueError("稀有度倍率参数已弃用。")
    config = {
        "target": params.get("target"),
        "forceLegendary": params.get("forceLegendary"),
        "forceDuo": params.get("forceDuo"),
    }
    if config["target"] not in BOON_RARITY_TARGETS:
        raise ValueError("最低稀有度无效。")
    if (
        type(config["forceLegendary"]) is not bool
        or type(config["forceDuo"]) is not bool
    ):
        raise ValueError("Legendary / Duo 设置无效。")
    return config


def _world_occurrence_apply(raw):
    params = _params(raw)
    target = params.get("target")
    if not isinstance(target, str) or not target or not is_valid_next_occurrence_target(target):
        raise ValueError("下一次遭遇目标无效。")
    return {"target": target}


def _world_occurrence_cancel(raw):
    params = _params(raw)
    token = params.get("leaseToken")
    if not isinstance(token, str) or not token or len(token) > 768:
        raise ValueError("World occurrence lease is invalid or stale")
    return {"leaseToken": token}


def _world_exit_apply(raw):
    params = _params(raw)
    door_token = params.get("doorToken")
    kind = params.get("kind")
    target = params.get("target")
    if not isinstance(door_token, str) or not door_token or len(door_token) > 512:
        raise ValueError("World exit token is invalid or stale")
    if kind not in ("reward", "roomCategory"):
        raise ValueError("World exit target kind is invalid")
    if not isinstance(target, str) or not target or len(target) > 256:
        raise ValueError("World exit target is invalid")
    return {"doorToken": door_token, "kind": kind, "target": target}


def _world_exit_cancel(raw):
    params = _params(raw)
    door_token = params.get("doorToken")
    lease_token = params.get("leaseToken")
    if not isinstance(door_token, str) or not door_token or len(door_token) > 512:
        raise ValueError("World exit token is invalid or stale")
    if not isinstance(lease_token, str) or not lease_token or len(lease_token) > 768:
        raise ValueError("World exit lease is invalid or stale")
    return {"doorToken": door_token, "leaseToken": lease_token}


def _save_editor_selection(raw):
    params = _params(raw)
    result = {}
    if "snapshotId" in params:
        snapshot = params["snapshotId"]
        if not isinstance(snapshot, str) or not snapshot or len(snapshot) > 128:
            raise ValueError("Save Editor snapshot identity is invalid.")
        result["snapshotId"] = snapshot
    for name in ("source", "target"):
        if name not in params:
            continue
        value = params[name]
        if not isinstance(value, dict) or set(value) != {"rootId", "relativePath"}:
            raise ValueError("Save Editor file identity is invalid.")
        if any(not isinstance(part, str) or not part or len(part) > 1024 for part in value.values()):
            raise ValueError("Save Editor file identity is invalid.")
        result[name] = value
    return result


def _save_editor_target(raw):
    result = _save_editor_selection(raw)
    if set(result) != {"target"}:
        raise ValueError("Save Editor target selection requires one declared file identity.")
    return result


def _save_editor_query(raw):
    params = _params(raw)
    domain = params.get("domain")
    search = params.get("search", "")
    offset = params.get("offset", 0)
    limit = params.get("limit", 100)
    path = params.get("path", [])
    language = params.get("language", "zh-CN")
    state_filter = params.get("stateFilter", "all")
    if state_filter not in SAVE_EDITOR_STATE_FILTERS:
        raise ValueError("Save Editor state filter is invalid.")
    if domain not in SAVE_EDITOR_DOMAINS:
        raise ValueError("Save Editor query domain is invalid.")
    if not isinstance(search, str) or len(search) > 256:
        raise ValueError("Save Editor query search is too long.")
    if type(offset) is not int or offset < 0:
        raise ValueError("Save Editor query offset is invalid.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Save Editor query limit must be 1..200.")
    if not isinstance(path, list) or len(path) > save_advanced._MAX_LUABINS_DEPTH + 2:
        raise ValueError("Save Editor query path is invalid.")
    if save_container.namespace(path) is not None:
        if domain != "advanced":
            raise save_advanced.AdvancedMutationError("Save Editor container paths require Advanced.")
        save_advanced.decode_path(path[1:])
    else:
        save_advanced.decode_path(path)
    if language not in ("zh-CN", "en"):
        raise ValueError("Save Editor query language is invalid.")
    result = {
        "domain": domain,
        "search": search,
        "offset": offset,
        "limit": limit,
        "path": path,
        "language": language,
    }
    if "stateFilter" in params:
        result["stateFilter"] = state_filter
    if "scope" in params:
        if params["scope"] not in SAVE_EDITOR_SCOPES:
            raise ValueError("Save Editor browse scope is invalid.")
        result["scope"] = params["scope"]
    return result


def _save_editor_detail(raw):
    params = _params(raw)
    entry_id = params.get("entryId")
    language = params.get("language", "zh-CN")
    if (not isinstance(entry_id, str) or not entry_id.startswith(("investigate:", "advanced:", "save-container:"))
            or len(entry_id) <= 9 or language not in ("en", "zh-CN")):
        raise ValueError("Save Editor investigation identity is invalid.")
    return {"entryId": entry_id, "language": language}


def _save_editor_language(raw):
    params = _params(raw)
    language = params.get("language", "zh-CN")
    if language not in ("en", "zh-CN"):
        raise ValueError("Save Editor language is unsupported.")
    return {"language": language}


def _save_editor_apply(raw):
    entries = _params(raw).get("draftEntryIds", [])
    if not isinstance(entries, list) or any(
            not isinstance(entry, str) or not entry for entry in entries):
        raise ValueError("Save Editor draft identities are invalid.")
    return {"draftEntryIds": list(dict.fromkeys(entries))}


def _save_editor_stage(raw):
    params = _params(raw)
    entry_id = params.get("entryId")
    operation = params.get("operation")
    language = params.get("language", "zh-CN")
    if not isinstance(entry_id, str) or not entry_id or (len(entry_id) > 512 and not entry_id.startswith(("advanced:", "save-container:"))):
        raise ValueError("Save Editor mutation entry is invalid.")
    if operation not in SAVE_EDITOR_MUTATION_KINDS:
        raise ValueError("Save Editor mutation operation is invalid.")
    if language not in ("en", "zh-CN"):
        raise ValueError("Save Editor language is unsupported.")
    result = {"entryId": entry_id, "operation": operation, "language": language}
    if "value" in params:
        result["value"] = params["value"]
    return result


def _save_editor_unstage(raw):
    params = _params(raw)
    entry_id = params.get("entryId")
    language = params.get("language", "zh-CN")
    if not isinstance(entry_id, str) or not entry_id or (len(entry_id) > 512 and not entry_id.startswith(("advanced:", "save-container:"))):
        raise ValueError("Save Editor staged action identity is invalid.")
    if language not in ("en", "zh-CN"):
        raise ValueError("Save Editor language is unsupported.")
    return {"entryId": entry_id, "language": language}


def _direct(method):
    def invoke(adapter, params):
        return getattr(adapter, method)()

    return invoke


def _runtime(command):
    def invoke(adapter, params):
        return adapter.execute(command, params)

    return invoke


def _connect_invoke(adapter, params):
    return adapter.connect(
        probe_runtime=params["probeRuntime"],
        recover_lost_attach=params["recoverLostAttach"],
    )


def _set_desired_invoke(adapter, params):
    return adapter.set_desired(params["feature"], params["value"])


def _boon_rarity_invoke(adapter, params):
    return adapter.set_boon_rarity_desired(params)


def _gathering_invoke(adapter, params):
    return adapter.set_gathering_desired(params["family"], params["probability"])


def _chaos_gate_invoke(adapter, params):
    return adapter.set_chaos_gate_desired(params["probability"])


def _list_profiles(adapter, params):
    return {"profiles": adapter.list_profiles()}


def _save_profile(adapter, params):
    return adapter.save_profile(params.get("name"), params.get("shortcuts"))


def _load_profile(adapter, params):
    return adapter.load_profile(params.get("name"))


def _delete_profile(adapter, params):
    return adapter.delete_profile(params.get("name"))


def _save_editor_query_invoke(adapter, params):
    return adapter.query_save_editor(params)


def _save_editor_stage_invoke(adapter, params):
    return adapter.stage_save_editor(params)


def _diagnostics(adapter, params):
    return build_diagnostics(adapter)


def _export_diagnostics(adapter, params):
    result = export_diagnostics(adapter)
    subprocess.run(
        ["/usr/bin/open", "-R", result["diagnosticBundle"]],
        check=True,
        timeout=EXPORT_REVEAL_TIMEOUT_SECONDS,
        shell=False,
    )
    return result


def _launch(adapter, params):
    url = adapter.context.steam_launch_url
    if url is None:
        raise RuntimeError("Hades II module manifest is missing a valid steamAppId.")
    subprocess.run(
        ["/usr/bin/open", url],
        check=True,
        timeout=LAUNCH_TIMEOUT_SECONDS,
        shell=False,
    )
    return adapter.scan()


def _stopped_operation(name):
    def invoke(adapter, params):
        if adapter.runtime.alive():
            raise ValueError("请断开连接并退出游戏后操作。")
        info = {"prepare": preparation.prepare, "restore": preparation.restore}[name](adapter.legacy_data_dir)
        return dict(adapter.scan(), operation=info)

    return invoke


@dataclass(frozen=True)
class CommandSpec:
    name: str
    timeout_seconds: float
    worst_case_inner_seconds: float
    requires_request_id: bool
    validate: object
    invoke: object
    reply_kind: str
    requires_trusted_target: bool = True
    supports_offline_intent: bool = False


def _spec(
    name,
    *,
    timeout=DEFAULT_COMMAND_TIMEOUT_SECONDS,
    inner=None,
    request_id=False,
    validate=_identity,
    invoke=None,
    reply_kind=None,
    trusted=True,
    offline=False,
):
    if inner is None:
        inner = MAILBOX_COMMAND_BUDGET_SECONDS if invoke is None else 0.0
    return CommandSpec(
        name=name,
        timeout_seconds=float(timeout),
        worst_case_inner_seconds=float(inner),
        requires_request_id=bool(request_id),
        validate=validate,
        invoke=invoke or _runtime(name),
        reply_kind=reply_kind or ("patch" if invoke is None else "independent"),
        requires_trusted_target=bool(trusted),
        supports_offline_intent=bool(offline),
    )


_COMMAND_SPECS = (
    _spec(
        "scan",
        timeout=POST_PREPARATION_SCAN_BUDGET_SECONDS + 5.0,
        inner=POST_PREPARATION_SCAN_BUDGET_SECONDS,
        invoke=_direct("scan"),
        reply_kind="snapshot",
        trusted=False,
    ),
    _spec(
        "status",
        timeout=STATUS_COMMAND_BUDGET_SECONDS + 3.0,
        inner=STATUS_COMMAND_BUDGET_SECONDS,
        reply_kind="snapshot",
    ),
    _spec(
        "connect",
        timeout=CONNECT_OPERATION_BUDGET_SECONDS + CONNECT_ATTACH_HEADROOM_SECONDS,
        inner=CONNECT_OPERATION_BUDGET_SECONDS,
        validate=_connect,
        invoke=_connect_invoke,
        reply_kind="snapshot",
    ),
    _spec(
        "disconnect",
        timeout=DISCONNECT_OPERATION_BUDGET_SECONDS + 4.0,
        inner=DISCONNECT_OPERATION_BUDGET_SECONDS,
        invoke=_direct("disconnect"),
        reply_kind="snapshot",
    ),
    _spec(
        "launch",
        timeout=LAUNCH_OPERATION_BUDGET_SECONDS + 5.0,
        inner=LAUNCH_OPERATION_BUDGET_SECONDS,
        invoke=_launch,
        trusted=False,
    ),
    _spec(
        "disable_all",
        timeout=DISABLE_ALL_OPERATION_BUDGET_SECONDS + 8.0,
        inner=DISABLE_ALL_OPERATION_BUDGET_SECONDS,
        reply_kind="snapshot",
    ),
    _spec("runtime_reset", inner=0.0, invoke=_direct("runtime_reset"), reply_kind="snapshot"),
    _spec("reset_desired", inner=MAILBOX_COMMAND_BUDGET_SECONDS, invoke=_direct("reset_desired"), reply_kind="snapshot", offline=True),
    _spec("set_desired", inner=MAILBOX_COMMAND_BUDGET_SECONDS, validate=_set_desired, invoke=_set_desired_invoke, reply_kind="patch", offline=True),
    _spec("set_vital", validate=_set_vital),
    _spec("set_counter", validate=_set_counter),
    _spec("lock_vital", validate=_lock_vital),
    _spec("lock_biome_time", validate=_lock_biome_time),
    _spec("set_resource", request_id=True, validate=_set_resource),
    _spec("lock_resource", request_id=True, validate=_lock_resource),
    _spec("set_rerolls", request_id=True, validate=_set_rerolls),
    _spec("lock_rerolls", request_id=True, validate=_lock_rerolls),
    _spec(
        "set_gathering_desired",
        inner=MAILBOX_COMMAND_BUDGET_SECONDS,
        validate=_set_gathering_desired,
        invoke=_gathering_invoke,
        reply_kind="patch",
        offline=True,
    ),
    _spec(
        "set_chaos_gate_desired",
        inner=MAILBOX_COMMAND_BUDGET_SECONDS,
        validate=_set_chaos_gate_desired,
        invoke=_chaos_gate_invoke,
        reply_kind="patch",
        offline=True,
    ),
    _spec("generate_gathering", request_id=True, validate=_generate_gathering),
    _spec("generate_chaos_gate", request_id=True, validate=_generate_chaos_gate),
    _spec("generate_chamber_facility", request_id=True, validate=_generate_chamber_facility),
    _spec("mature_garden", request_id=True, validate=_mature_garden),
    _spec("set_stat", validate=_set_stat),
    _spec("set_element", validate=_set_element),
    _spec("lock_element", validate=_lock_element),
    _spec(
        "set_boon_rarity_desired",
        inner=MAILBOX_COMMAND_BUDGET_SECONDS,
        validate=_boon_rarity,
        invoke=_boon_rarity_invoke,
        reply_kind="patch",
        offline=True,
    ),
    _spec("apply_world_occurrence", request_id=True, validate=_world_occurrence_apply),
    _spec("cancel_world_occurrence", request_id=True, validate=_world_occurrence_cancel),
    _spec("apply_world_exit", request_id=True, validate=_world_exit_apply),
    _spec("cancel_world_exit", request_id=True, validate=_world_exit_cancel),
    _spec("spawn_reward", request_id=True, validate=_spawn_reward),
    _spec("acquire_chaos_pair", request_id=True, validate=_chaos_pair),
    _spec("open_sell_traits", request_id=True),
    _spec(
        "set_trait_level",
        request_id=True,
        validate=_trait_mutation("set_trait_level"),
    ),
    _spec(
        "set_trait_rarity",
        request_id=True,
        validate=_trait_mutation("set_trait_rarity"),
    ),
    _spec(
        "set_trait_remaining_uses",
        request_id=True,
        validate=_trait_mutation("set_trait_remaining_uses"),
    ),
    _spec("expire_trait", request_id=True, validate=_trait_mutation("expire_trait")),
    _spec("remove_trait", request_id=True, validate=_trait_mutation("remove_trait")),
    _spec(
        "advance_trait_lifecycle",
        request_id=True,
        validate=_trait_mutation("advance_trait_lifecycle"),
    ),
    _spec("open_special_choice", request_id=True, validate=_special_choice),
    _spec("save_editor_inventory", validate=_save_editor_selection,
        invoke=lambda adapter, params: adapter.save_editor_inventory(params), trusted=False),
    _spec("save_editor_open", validate=_save_editor_selection,
        invoke=lambda adapter, params: adapter.open_save_editor(params), trusted=False),
    _spec("save_editor_target", validate=_save_editor_target,
        invoke=lambda adapter, params: adapter.set_save_editor_target(params), trusted=False),
    _spec(
        "save_editor_query",
        timeout=SAVE_EDITOR_OPERATION_BUDGET_SECONDS + 5.0,
        inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS,
        validate=_save_editor_query,
        invoke=_save_editor_query_invoke,
        trusted=False,
    ),
    _spec(
        "save_editor_detail",
        timeout=SAVE_EDITOR_OPERATION_BUDGET_SECONDS + 5.0,
        inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS,
        validate=_save_editor_detail,
        invoke=lambda adapter, params: adapter.detail_save_editor(params),
        trusted=False,
    ),
    _spec(
        "save_editor_stage",
        validate=_save_editor_stage,
        invoke=_save_editor_stage_invoke,
        trusted=False,
    ),
    _spec(
        "save_editor_unstage",
        validate=_save_editor_unstage,
        invoke=lambda adapter, params: adapter.unstage_save_editor(params),
        trusted=False,
    ),
    _spec(
        "save_editor_review",
        validate=_save_editor_language,
        invoke=lambda adapter, params: adapter.review_save_editor(params),
        trusted=False,
    ),
    _spec(
        "save_editor_cancel",
        validate=_save_editor_language,
        invoke=lambda adapter, params: adapter.cancel_save_editor(params),
        trusted=False,
    ),
    _spec("save_editor_apply", timeout=SAVE_EDITOR_OPERATION_BUDGET_SECONDS + 5.0,
        inner=SAVE_EDITOR_OPERATION_BUDGET_SECONDS,
        validate=_save_editor_apply,
        invoke=lambda adapter, params: adapter.apply_save_editor(params), trusted=False),
    _spec("save_editor_close", invoke=lambda adapter, params: adapter.close_save_editor(params), trusted=False),
    _spec("list_profiles", invoke=_list_profiles, trusted=False),
    _spec("save_profile", invoke=_save_profile, trusted=False),
    _spec("load_profile", inner=MAILBOX_COMMAND_BUDGET_SECONDS, invoke=_load_profile, offline=True),
    _spec("delete_profile", invoke=_delete_profile, trusted=False),
    _spec(
        "diagnostics",
        timeout=DIAGNOSTICS_OPERATION_BUDGET_SECONDS + 5.0,
        inner=DIAGNOSTICS_OPERATION_BUDGET_SECONDS,
        invoke=_diagnostics,
    ),
    _spec(
        "export_diagnostics",
        timeout=EXPORT_DIAGNOSTICS_OPERATION_BUDGET_SECONDS + 10.0,
        inner=EXPORT_DIAGNOSTICS_OPERATION_BUDGET_SECONDS,
        invoke=_export_diagnostics,
    ),
    _spec(
        "prepare",
        timeout=PREPARATION_OPERATION_BUDGET_SECONDS + 45.0,
        inner=PREPARATION_OPERATION_BUDGET_SECONDS,
        invoke=_stopped_operation("prepare"),
    ),
    _spec(
        "restore",
        timeout=RESTORE_OPERATION_BUDGET_SECONDS + 25.0,
        inner=RESTORE_OPERATION_BUDGET_SECONDS,
        invoke=_stopped_operation("restore"),
    ),
)

COMMAND_SPECS = {spec.name: spec for spec in _COMMAND_SPECS}


def command_metadata():
    """Stable build metadata for the Swift caller adapter."""
    return tuple(
        {
            "name": spec.name,
            "timeoutSeconds": spec.timeout_seconds,
            "requiresTrustedTarget": spec.requires_trusted_target,
            "supportsOfflineIntent": spec.supports_offline_intent,
        }
        for spec in _COMMAND_SPECS
    )


def command_budget_audit():
    """Per-command outer timeout vs worst-case inner budget table."""
    return tuple(
        {
            "name": spec.name,
            "timeoutSeconds": spec.timeout_seconds,
            "worstCaseInnerSeconds": spec.worst_case_inner_seconds,
        }
        for spec in _COMMAND_SPECS
    )


class Hades2CommandContract:
    def __init__(self, adapter):
        self.adapter = adapter

    @staticmethod
    def reply_kind(command):
        return COMMAND_SPECS[command].reply_kind

    def dispatch(self, command, params, request_id):
        try:
            spec = COMMAND_SPECS.get(command)
            if spec is None:
                raise ValueError("未知命令。")
            validated = spec.validate(params)
            workspace = None
            if command.startswith("save_editor_") and command not in ("save_editor_inventory", "save_editor_open"):
                identifier = _params(params).get("workspaceId")
                if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
                    raise ValueError("Save Editor workspace identity is invalid.")
                workspace = self.adapter.validate_save_workspace(identifier)
                if command != "save_editor_close":
                    workspace.require_baseline(_params(params).get("baselineGeneration"))
                validated = dict(validated, workspaceId=identifier)
            if spec.requires_request_id:
                validated = dict(validated, requestId=request_id)
            result = spec.invoke(self.adapter, validated)
            if workspace is not None and command != "save_editor_close":
                return dict(result, baselineGeneration=workspace.baseline_generation)
            return result
        except Exception as error:
            raise self._as_presentation_key(
                present_runtime_error(command, error)
            ) from error

    @staticmethod
    def _as_presentation_key(error):
        # Preserve resolved presentation and recovery data across the legacy text mapper.
        if isinstance(error, PresentableError) and error.presentation and error.presentation.startswith(("host.", "hades2.")):
            return error
        key, arguments = presentation_for(str(error))
        if key is None:
            return error
        return Hades2PresentationError(
            getattr(error, "code", "invalid_request"),
            key,
            arguments,
            diagnostic=getattr(error, "diagnostic", None) or str(error),
        )
