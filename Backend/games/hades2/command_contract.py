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

from . import preparation
from .config import STEAM_SPEC
from .diagnostics import build_diagnostics, export_diagnostics
from .error_presentation import Hades2PresentationError, presentation_for
from .operation_budgets import EXPORT_REVEAL_TIMEOUT_SECONDS
from .runtime_error_presentation import present_runtime_error
from .save_workspace import SAVE_EDITOR_DOMAINS, SAVE_EDITOR_MUTATION_KINDS
from .schema import (
    BOON_RARITY_TARGETS,
    MAX_AMOUNT,
    STAT_RULES,
    VITALS,
    is_known_element,
    is_valid_next_room_reward,
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
    return {"probeRuntime": probe_runtime}


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
    if params.get("counter") != "spellCharge":
        raise ValueError("未知局内计数器。")
    value = params.get("value")
    if (
        type(value) not in (int, float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or not 0 <= value <= MAX_AMOUNT
    ):
        raise ValueError(f"巫咒充能必须为 0–{MAX_AMOUNT}。")
    return params


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


def _spawn_reward(raw):
    params = _params(raw)
    if not isinstance(params.get("reward"), str) or not params["reward"]:
        raise ValueError("请选择掉落物或祝福。")
    return params


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
    return params


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
                or target_level > 999999
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
    config = {
        "target": params.get("target"),
        "multiplier": params.get("multiplier"),
        "forceLegendary": params.get("forceLegendary"),
        "forceDuo": params.get("forceDuo"),
    }
    if config["target"] not in BOON_RARITY_TARGETS:
        raise ValueError("最低稀有度无效。")
    if (
        type(config["multiplier"]) not in (int, float)
        or isinstance(config["multiplier"], bool)
        or not math.isfinite(config["multiplier"])
        or not 0 <= config["multiplier"] <= 1000
    ):
        raise ValueError("稀有度倍率必须为 0–1000%。")
    if (
        type(config["forceLegendary"]) is not bool
        or type(config["forceDuo"]) is not bool
    ):
        raise ValueError("Legendary / Duo 设置无效。")
    return config


def _next_room_reward(raw):
    params = _params(raw)
    reward = params.get("reward")
    if not is_valid_next_room_reward(reward):
        raise ValueError("下一房奖励无效。")
    return {"reward": reward}


def _save_editor_query(raw):
    params = _params(raw)
    domain = params.get("domain")
    search = params.get("search", "")
    offset = params.get("offset", 0)
    limit = params.get("limit", 100)
    path = params.get("path", [])
    language = params.get("language", "zh-CN")
    if domain not in SAVE_EDITOR_DOMAINS:
        raise ValueError("Save Editor query domain is invalid.")
    if not isinstance(search, str) or len(search) > 256:
        raise ValueError("Save Editor query search is too long.")
    if type(offset) is not int or offset < 0:
        raise ValueError("Save Editor query offset is invalid.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("Save Editor query limit must be 1..200.")
    if (
        not isinstance(path, list)
        or len(path) > 64
        or any(
            part is None
            or isinstance(part, (list, dict))
            or type(part) not in (str, int, float, bool)
            for part in path
        )
    ):
        raise ValueError("Save Editor query path is invalid.")
    if language not in ("zh-CN", "en"):
        raise ValueError("Save Editor query language is invalid.")
    return {
        "domain": domain,
        "search": search,
        "offset": offset,
        "limit": limit,
        "path": path,
        "language": language,
    }


def _save_editor_stage(raw):
    params = _params(raw)
    entry_id = params.get("entryId")
    operation = params.get("operation")
    if not isinstance(entry_id, str) or not 1 <= len(entry_id) <= 512:
        raise ValueError("Save Editor mutation entry is invalid.")
    if operation not in SAVE_EDITOR_MUTATION_KINDS:
        raise ValueError("Save Editor mutation operation is invalid.")
    result = {"entryId": entry_id, "operation": operation}
    if "value" in params:
        result["value"] = params["value"]
    return result


def _direct(method):
    def invoke(adapter, params):
        return getattr(adapter, method)()

    return invoke


def _runtime(command):
    def invoke(adapter, params):
        return adapter.execute(command, params)

    return invoke


def _connect_invoke(adapter, params):
    return adapter.connect(probe_runtime=params["probeRuntime"])


def _set_desired_invoke(adapter, params):
    return adapter.set_desired(params["feature"], params["value"])


def _boon_rarity_invoke(adapter, params):
    return adapter.set_boon_rarity_desired(params)


def _gathering_invoke(adapter, params):
    return adapter.set_gathering_desired(params["family"], params["probability"])


def _chaos_gate_invoke(adapter, params):
    return adapter.set_chaos_gate_desired(params["probability"])


def _next_room_invoke(adapter, params):
    return adapter.set_next_room_reward_desired(params["reward"])


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
    subprocess.run(
        ["/usr/bin/open", STEAM_SPEC.launch_url],
        check=True,
        timeout=10,
        shell=False,
    )
    return adapter.scan()


def _stopped_operation(name):
    def invoke(adapter, params):
        if adapter.runtime.alive():
            raise ValueError("请断开连接并退出游戏后操作。")
        info = {"prepare": preparation.prepare, "restore": preparation.restore}[name]()
        return dict(adapter.scan(), operation=info)

    return invoke


@dataclass(frozen=True)
class CommandSpec:
    name: str
    timeout_seconds: float
    requires_request_id: bool
    validate: object
    invoke: object


def _spec(
    name,
    *,
    timeout=6.0,
    request_id=False,
    validate=_identity,
    invoke=None,
):
    return CommandSpec(
        name=name,
        timeout_seconds=float(timeout),
        requires_request_id=bool(request_id),
        validate=validate,
        invoke=invoke or _runtime(name),
    )


_COMMAND_SPECS = (
    _spec("scan", timeout=15.0, invoke=_direct("scan")),
    _spec("status", timeout=15.0),
    _spec("connect", timeout=90.0, validate=_connect, invoke=_connect_invoke),
    _spec("disconnect", timeout=12.0, invoke=_direct("disconnect")),
    _spec("launch", timeout=10.0, invoke=_launch),
    _spec("disable_all"),
    _spec("runtime_reset", invoke=_direct("runtime_reset")),
    _spec("reset_desired", invoke=_direct("reset_desired")),
    _spec("set_desired", validate=_set_desired, invoke=_set_desired_invoke),
    _spec("set_vital", validate=_set_vital),
    _spec("set_counter", validate=_set_counter),
    _spec("lock_vital", validate=_lock_vital),
    _spec("set_resource", request_id=True, validate=_set_resource),
    _spec("lock_resource", request_id=True, validate=_lock_resource),
    _spec("set_rerolls", request_id=True, validate=_set_rerolls),
    _spec("lock_rerolls", request_id=True, validate=_lock_rerolls),
    _spec(
        "set_gathering_desired",
        validate=_set_gathering_desired,
        invoke=_gathering_invoke,
    ),
    _spec(
        "set_chaos_gate_desired",
        validate=_set_chaos_gate_desired,
        invoke=_chaos_gate_invoke,
    ),
    _spec("generate_gathering", request_id=True, validate=_generate_gathering),
    _spec("set_stat", validate=_set_stat),
    _spec("set_element", validate=_set_element),
    _spec("lock_element", validate=_lock_element),
    _spec(
        "set_boon_rarity_desired",
        validate=_boon_rarity,
        invoke=_boon_rarity_invoke,
    ),
    _spec(
        "set_next_room_reward_desired",
        validate=_next_room_reward,
        invoke=_next_room_invoke,
    ),
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
    _spec("save_editor_open", invoke=_direct("open_save_editor")),
    _spec(
        "save_editor_query",
        validate=_save_editor_query,
        invoke=_save_editor_query_invoke,
    ),
    _spec(
        "save_editor_stage",
        validate=_save_editor_stage,
        invoke=_save_editor_stage_invoke,
    ),
    _spec("save_editor_review", invoke=_direct("review_save_editor")),
    _spec("save_editor_cancel", invoke=_direct("cancel_save_editor")),
    _spec("save_editor_apply", timeout=30.0, invoke=_direct("apply_save_editor")),
    _spec("list_profiles", invoke=_list_profiles),
    _spec("save_profile", invoke=_save_profile),
    _spec("load_profile", invoke=_load_profile),
    _spec("delete_profile", invoke=_delete_profile),
    _spec("diagnostics", timeout=70.0, invoke=_diagnostics),
    _spec("export_diagnostics", timeout=85.0, invoke=_export_diagnostics),
    _spec("prepare", timeout=560.0, invoke=_stopped_operation("prepare")),
    _spec("restore", timeout=240.0, invoke=_stopped_operation("restore")),
)

COMMAND_SPECS = {spec.name: spec for spec in _COMMAND_SPECS}


def command_metadata():
    """Stable build metadata for the Swift caller adapter."""
    return tuple(
        {
            "name": spec.name,
            "timeoutSeconds": spec.timeout_seconds,
        }
        for spec in _COMMAND_SPECS
    )


class Hades2CommandContract:
    def __init__(self, adapter):
        self.adapter = adapter

    def dispatch(self, command, params, request_id):
        try:
            spec = COMMAND_SPECS.get(command)
            if spec is None:
                raise ValueError("未知命令。")
            validated = spec.validate(params)
            if spec.requires_request_id:
                validated = dict(validated, requestId=request_id)
            return spec.invoke(self.adapter, validated)
        except Exception as error:
            raise self._as_presentation_key(
                present_runtime_error(command, error)
            ) from error

    @staticmethod
    def _as_presentation_key(error):
        key, arguments = presentation_for(str(error))
        if key is None:
            return error
        return Hades2PresentationError(
            getattr(error, "code", "invalid_request"),
            key,
            arguments,
            diagnostic=str(error),
        )
