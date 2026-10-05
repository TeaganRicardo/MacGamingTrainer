"""Deep Hades resident-session seam over the LLDB/Lua transport.

Callers express semantic resident operations here. Raw Lua construction, bootstrap
state, debugger budgets, transaction ledger, Trait Tray handoff, decode trust and
resident-generation recovery stay behind this interface.
"""
from dataclasses import dataclass
import json
import logging
import math
import time
from pathlib import Path

from core.adapter import AdapterError

from .catalog import localize_catalog


TransportError = AdapterError

_TRAIT_TRAY_HANDOFF_KEY = "__trainerTraitTrayHandoff"
_TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS = 0.75
_TRAIT_TRAY_HANDOFF_POLL_SECONDS = 0.05
_REPLAY_EXPRESSION_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class ResidentMetrics:
    boundary_duration: float = 0.0
    json_duration: float = 0.0
    localize_duration: float = 0.0
    expression_duration: float = 0.0


@dataclass(frozen=True)
class ResidentReply:
    payload: dict
    metrics: ResidentMetrics
    generation_reset: bool = False
    outcome_unknown: bool = False


class ResidentGenerationInvalidated(Exception):
    """A non-status call discovered that the resident generation disappeared."""

    def __init__(self, original):
        super().__init__(str(original))
        self.original = original


def lua_value(value):
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("必须输入有限数值。")
        return str(value)
    if isinstance(value, str):
        return '"' + "".join(
            ("\\%03d" % ord(char)) if ord(char) < 32 or char in ('"', "\\") else char
            for char in value
        ) + '"'
    if isinstance(value, dict):
        return "{" + ",".join(
            "[" + lua_value(key) + "]=" + lua_value(item)
            for key, item in value.items()
        ) + "}"
    raise ValueError("参数类型不支持。")


class Hades2ResidentSession:
    def __init__(self, transport, bootstrap=None):
        self._transport = transport
        if bootstrap is None:
            bootstrap = (Path(__file__).with_name("runtime") / "hades.lua").read_text()
        self._bootstrap = bootstrap
        self._generation_ready = False
        self._catalog_ready = False

    @property
    def pid(self):
        return self._transport.pid

    @property
    def last_attach_profile(self):
        return dict(getattr(self._transport, "last_attach_profile", {}) or {})

    def alive(self):
        return self._transport.alive()

    def allows_process_time_warp(self):
        """Whether the current resident generation makes Host Time Warp safe.

        This exposes the semantic capability, not bootstrap/catalog bookkeeping.
        """
        return self._generation_ready

    def attach(self, pid):
        self._transport.attach(pid)
        # A debugger reconnect is the synchronization seam for resident source.
        # Re-bootstrap once even when the same game process survived a manual detach.
        self.invalidate_generation()

    def detach(self):
        self._transport.detach()

    def close(self):
        self._transport.close()

    def invalidate_generation(self):
        self._generation_ready = False
        self._catalog_ready = False

    def status(self, params=None):
        return self._execute_status(params or {}, read_only=False)

    def observe_status(self, params=None):
        return self._execute_status(params or {}, read_only=True)

    def mutate(self, command, params=None):
        return self._execute(command, params or {}, replay=False, read_only=False, batch=None)

    def reconcile(self, calls):
        return self._execute(
            "replay_preferences", {}, replay=True, read_only=False, batch=list(calls)
        )

    @staticmethod
    def _runtime_generation_missing(error):
        message = str(error)
        return error.code == "lua_error" and "__MacGamingTrainerV1" in message and "nil value" in message

    @staticmethod
    def _resident_cleanup_failed(error):
        return error.code == "lua_error" and "MGT_RESIDENT_RESTART_REQUIRED:" in str(error)

    def _execute_status(self, params, read_only):
        runtime_params = dict(params)
        recovered_generation = False
        generation_reset = False
        while True:
            try:
                reply = self._execute(
                    "status", runtime_params, replay=False, read_only=read_only, batch=None
                )
                if generation_reset:
                    return ResidentReply(
                        payload=reply.payload,
                        metrics=reply.metrics,
                        generation_reset=True,
                        outcome_unknown=reply.outcome_unknown,
                    )
                return reply
            except TransportError as error:
                if self._resident_cleanup_failed(error):
                    raise TransportError(
                        "restart_required",
                        "hades2.error.residentCleanupFailed",
                        diagnostic=str(error),
                    ) from error
                if not self._runtime_generation_missing(error):
                    raise
                self.invalidate_generation()
                if recovered_generation:
                    raise
                recovered_generation = True
                generation_reset = True
                runtime_params["includeCatalogs"] = True
                logging.info(
                    "Lua runtime generation reset detected; re-bootstrap status in same debugger attachment"
                )

    def _execute(self, command, params, *, replay, read_only, batch):
        if not self.alive():
            raise TransportError("disconnected", "请先连接游戏。")

        runtime_params = dict(params)
        if "includeCatalogs" not in runtime_params:
            runtime_params["includeCatalogs"] = not self._catalog_ready

        trait_tray_started = None
        trait_tray_boundaries = 0
        while True:
            if (
                trait_tray_started is not None
                and time.monotonic() - trait_tray_started
                >= _TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS
            ):
                raise TransportError("waiting", "游戏内祝福菜单未能及时关闭，修改尚未执行。")

            dispatch = self._dispatch_source(command, runtime_params, batch)
            if command != "status":
                dispatch = self._mutation_handoff_source(dispatch)
            code = self._bootstrap + "\n" + dispatch if not self._generation_ready else dispatch

            boundary_started = time.monotonic()
            try:
                reply = self._cross(
                    command,
                    code,
                    replay=replay,
                    read_only=read_only,
                    expression_timeout_seconds=(
                        _REPLAY_EXPRESSION_TIMEOUT_SECONDS if batch is not None else None
                    ),
                )
            except TransportError as error:
                if self._resident_cleanup_failed(error):
                    raise TransportError(
                        "restart_required",
                        "hades2.error.residentCleanupFailed",
                        diagnostic=str(error),
                    ) from error
                if self._runtime_generation_missing(error):
                    if command == "status":
                        raise
                    self.invalidate_generation()
                    raise ResidentGenerationInvalidated(error) from error
                raise

            handoff = (
                reply.payload.get(_TRAIT_TRAY_HANDOFF_KEY)
                if isinstance(reply.payload, dict)
                else None
            )
            if handoff is None:
                break
            if handoff == "unsupported":
                raise TransportError(
                    "incompatible",
                    "游戏内祝福菜单缺少受支持的关闭流程，无法安全继续修改。",
                )
            if handoff != "closing":
                raise TransportError("lua_error", "游戏内祝福菜单未能及时关闭，修改尚未执行。")
            if trait_tray_started is None:
                trait_tray_started = boundary_started
            trait_tray_boundaries += 1
            elapsed = time.monotonic() - trait_tray_started
            if elapsed >= _TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS:
                raise TransportError("waiting", "游戏内祝福菜单未能及时关闭，修改尚未执行。")
            time.sleep(
                min(
                    _TRAIT_TRAY_HANDOFF_POLL_SECONDS,
                    max(0.0, _TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS - elapsed),
                )
            )

        if trait_tray_started is not None:
            logging.info(
                "TraitTrayHandoff command=%s duration=%.3fs boundaries=%d",
                command,
                time.monotonic() - trait_tray_started,
                trait_tray_boundaries + 1,
            )

        self._generation_ready = True
        if "boons" in reply.payload and "rewards" in reply.payload:
            self._catalog_ready = True

        last_action = reply.payload.get("lastAction") if isinstance(reply.payload, dict) else None
        outcome_unknown = (
            isinstance(last_action, dict)
            and last_action.get("outcome") == "outcome_unknown"
        )
        if outcome_unknown:
            self._transport.tainted = True
        if (
            isinstance(last_action, dict)
            and last_action.get("outcome") == "failed"
            and last_action.get("error")
        ):
            logging.warning(
                "LuaAction command=%s requestId=%s outcome=failed raw=%s",
                last_action.get("command"),
                last_action.get("requestId"),
                last_action.get("error"),
            )

        if outcome_unknown:
            return ResidentReply(
                payload=reply.payload,
                metrics=reply.metrics,
                outcome_unknown=True,
            )
        return reply

    def _dispatch_source(self, command, params, batch):
        if batch is None:
            dispatch_value = (
                "__MacGamingTrainerV1.dispatch("
                + lua_value(command)
                + ","
                + lua_value(params)
                + ")"
            )
        else:
            calls = []
            for batch_command, batch_params in batch:
                item_params = dict(batch_params or {})
                item_params["includeCatalogs"] = False
                calls.append(
                    '{["command"]='
                    + lua_value(batch_command)
                    + ',["params"]='
                    + lua_value(item_params)
                    + "}"
                )
            dispatch_value = "__MacGamingTrainerV1.dispatchBatch({" + ",".join(calls) + "})"
        return "return __MacGamingTrainerV1.json(" + dispatch_value + ")"

    @staticmethod
    def _mutation_handoff_source(dispatch):
        return (
            'return __MacGamingTrainerV1.json((function() '
            'local __mgtScreen=(type(ActiveScreens)=="table") and ActiveScreens.TraitTrayScreen or nil;'
            'if __mgtScreen~=nil then '
            'if type(thread)~="function" or type(TraitTrayScreenClose)~="function" then '
            'return {["'
            + _TRAIT_TRAY_HANDOFF_KEY
            + '"]="unsupported"} end;'
            'if not __mgtScreen.Closing then thread(TraitTrayScreenClose,__mgtScreen) end;'
            'return {["'
            + _TRAIT_TRAY_HANDOFF_KEY
            + '"]="closing"} end;'
            + dispatch[len("return __MacGamingTrainerV1.json("):-1]
            + " end)())"
        )

    def _cross(self, command, source, *, replay, read_only, expression_timeout_seconds):
        started = time.monotonic()
        crossed = False
        json_duration = 0.0
        localize_duration = 0.0
        try:
            if expression_timeout_seconds is None:
                raw = self._transport.execute(source)
            else:
                raw = self._transport.execute(
                    source,
                    expression_timeout_seconds=expression_timeout_seconds,
                )
            crossed = True
            boundary_duration = getattr(self._transport, "last_duration", 0.0)
            if type(boundary_duration) not in (int, float) or boundary_duration <= 0:
                boundary_duration = time.monotonic() - started

            phase = time.monotonic()
            payload = json.loads(raw)
            json_duration = time.monotonic() - phase
            phase = time.monotonic()
            payload = localize_catalog(payload)
            localize_duration = time.monotonic() - phase
        except Exception as error:
            boundary_duration = getattr(self._transport, "last_duration", 0.0)
            if type(boundary_duration) not in (int, float) or boundary_duration <= 0:
                boundary_duration = time.monotonic() - started
            metrics = ResidentMetrics(
                boundary_duration=boundary_duration,
                json_duration=json_duration,
                localize_duration=localize_duration,
                expression_duration=(
                    getattr(self._transport, "last_expression_duration", 0.0) or 0.0
                ),
            )
            if crossed:
                self._transport.tainted = True
            logging.info(
                "LuaBoundary command=%s duration=%.3fs outcome=%s crossed_transport=%s replay=%s readOnly=%s decodeError=%s expression=%.3fs",
                command,
                boundary_duration,
                "outcome_unknown" if crossed else getattr(error, "code", type(error).__name__),
                "yes" if crossed else "no",
                bool(replay),
                bool(read_only),
                type(error).__name__ if crossed else "none",
                metrics.expression_duration,
            )
            if crossed:
                unknown = AdapterError(
                    "outcome_unknown",
                    "游戏调用结果不明，未自动重试；请检查游戏并重启。",
                )
                unknown.resident_metrics = metrics
                raise unknown from error
            try:
                error.resident_metrics = metrics
            except Exception:
                pass
            raise

        metrics = ResidentMetrics(
            boundary_duration=boundary_duration,
            json_duration=json_duration,
            localize_duration=localize_duration,
            expression_duration=(
                getattr(self._transport, "last_expression_duration", 0.0) or 0.0
            ),
        )
        logging.info(
            "LuaBoundary command=%s duration=%.3fs outcome=ok crossed_transport=yes replay=%s readOnly=%s expression=%.3fs",
            command,
            metrics.boundary_duration,
            bool(replay),
            bool(read_only),
            metrics.expression_duration,
        )
        return ResidentReply(payload=payload, metrics=metrics)
