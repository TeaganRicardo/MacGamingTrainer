"""Authoritative Host -> Hades backend command contract.

This module owns the public Hades module-protocol command interface. Resident
Lua commands remain a separate interface behind Hades2ResidentSession.
"""
from dataclasses import dataclass
import copy


def _identity(params):
    return copy.deepcopy(dict(params or {}))


def _validate_chaos_pair(params):
    params = _identity(params)
    blessing = params.get("blessing")
    curse = params.get("curse")
    if (
        not isinstance(blessing, str)
        or not blessing
        or not isinstance(curse, str)
        or not curse
    ):
        raise ValueError("请选择掉落物或祝福。")
    return {"blessing": blessing, "curse": curse}


def _scan(adapter, params):
    return adapter.scan()


def _runtime(command):
    def invoke(adapter, params):
        return adapter.execute(command, params)

    return invoke


@dataclass(frozen=True)
class CommandSpec:
    name: str
    timeout_seconds: float = 6.0
    requires_request_id: bool = False
    validate: object = _identity
    invoke: object = None


COMMAND_SPECS = {
    "scan": CommandSpec(
        name="scan",
        timeout_seconds=15.0,
        invoke=_scan,
    ),
    "acquire_chaos_pair": CommandSpec(
        name="acquire_chaos_pair",
        requires_request_id=True,
        validate=_validate_chaos_pair,
        invoke=_runtime("acquire_chaos_pair"),
    ),
}


class Hades2CommandContract:
    def __init__(self, adapter):
        self.adapter = adapter

    def dispatch(self, command, params, request_id):
        spec = COMMAND_SPECS.get(command)
        if spec is None:
            raise ValueError("未知命令。")
        validated = spec.validate(params)
        if spec.requires_request_id:
            validated = dict(validated, requestId=request_id)
        return spec.invoke(self.adapter, validated)
