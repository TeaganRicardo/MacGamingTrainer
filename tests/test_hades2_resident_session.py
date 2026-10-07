import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades2 import resident_session as session_module
from games.hades2.resident_session import (
    Hades2ResidentSession,
    ResidentGenerationInvalidated,
)


def payload(**extra):
    result = {
        "status": "ready",
        "scene": "run",
        "capabilities": {},
        "desiredFeatures": {},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureSupport": {},
        "featureErrors": {},
        "resources": [],
        "elements": [],
        "stats": {},
        "boonRarity": {},
        "gatheringProbabilities": {},
        "chaosGateProbability": None,
    }
    result.update(extra)
    return result


class FakeTransport:
    def __init__(self, outcomes=None):
        self.pid = 4242
        self.live = True
        self.tainted = False
        self.last_duration = 0.125
        self.last_expression_duration = 0.025
        self.last_attach_profile = {}
        self.outcomes = list(outcomes or [])
        self.calls = []

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True

    def detach(self):
        self.live = False

    def close(self):
        self.live = False

    def execute(self, source, *, expression_timeout_seconds=None):
        self.calls.append({
            "source": source,
            "expression_timeout_seconds": expression_timeout_seconds,
        })
        if self.tainted:
            raise AdapterError("restart_required", "tainted transport")
        outcome = self.outcomes.pop(0) if self.outcomes else payload()
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, str):
            return outcome
        return json.dumps(outcome)


old_localize = session_module.localize_catalog
session_module.localize_catalog = lambda value: value
try:
    # Status owns bootstrap/catalog generation state. Once initialized, callers
    # do not carry those flags or raw source policy.
    status_transport = FakeTransport([
        payload(boons=[{"id": "A"}], rewards=[{"id": "B"}]),
        payload(),
    ])
    status_session = Hades2ResidentSession(status_transport, bootstrap="BOOTSTRAP")
    first = status_session.status()
    second = status_session.status()
    assert first.payload["status"] == "ready"
    assert second.payload["status"] == "ready"
    assert len(status_transport.calls) == 2
    assert status_transport.calls[0]["source"].startswith("BOOTSTRAP\n")
    assert not status_transport.calls[1]["source"].startswith("BOOTSTRAP\n")

    # Ordinary mutation uses the transport default expression budget. Durable
    # reconciliation is one boundary with the session-owned 5 second budget.
    operation_transport = FakeTransport([payload(), payload()])
    operation_session = Hades2ResidentSession(operation_transport, bootstrap="")
    operation_session.mutate("set_health", {"amount": 42, "requestId": "one"})
    assert operation_transport.calls[-1]["expression_timeout_seconds"] is None
    operation_session.reconcile([
        ("set_feature", {"feature": "invincibility", "value": True}),
        ("set_boon_rarity", {"target": "Heroic"}),
    ])
    assert len(operation_transport.calls) == 2
    assert operation_transport.calls[-1]["expression_timeout_seconds"] == 5.0

    # A missing resident generation on status is recovered exactly once in the
    # same attachment and reported as lifecycle evidence to Adapter.
    missing = AdapterError(
        "lua_error",
        "[string \"MacGamingTrainer\"]:1: attempt to index global '__MacGamingTrainerV1' (a nil value)",
    )
    reset_transport = FakeTransport([
        payload(boons=[], rewards=[]),
        missing,
        payload(),
    ])
    reset_session = Hades2ResidentSession(reset_transport, bootstrap="BOOTSTRAP")
    reset_session.status()  # establish the first generation through the public seam
    reset_reply = reset_session.status()
    assert reset_reply.generation_reset is True
    assert len(reset_transport.calls) == 3
    assert not reset_transport.calls[1]["source"].startswith("BOOTSTRAP\n")
    assert reset_transport.calls[2]["source"].startswith("BOOTSTRAP\n")

    # The same evidence during a mutation is never replayed automatically.
    mutation_reset_transport = FakeTransport([payload(), missing])
    mutation_reset_session = Hades2ResidentSession(
        mutation_reset_transport, bootstrap="BOOTSTRAP"
    )
    mutation_reset_session.status()  # establish the first generation publicly
    try:
        mutation_reset_session.mutate(
            "set_resource", {"resource": "Money", "amount": 10, "requestId": "unsafe"}
        )
    except ResidentGenerationInvalidated as error:
        assert error.original.code == "lua_error"
    else:
        raise AssertionError("mutation was replayed across a missing resident generation")
    assert len(mutation_reset_transport.calls) == 2

    # Host decode failure happens after the transport boundary and therefore
    # terminal-taints trust.
    decode_transport = FakeTransport(["{broken"])
    decode_session = Hades2ResidentSession(decode_transport, bootstrap="")
    try:
        decode_session.status()
    except AdapterError as error:
        assert error.code == "outcome_unknown"
    else:
        raise AssertionError("malformed resident payload did not become outcome_unknown")
    assert decode_transport.tainted is True

    null_transport = FakeTransport(["null"])
    null_session = Hades2ResidentSession(null_transport, bootstrap="")
    try:
        null_session.mutate("lock_vital", {"vital": "health", "locked": True})
    except AdapterError as error:
        assert error.code == "outcome_unknown"
    else:
        raise AssertionError("a missing resident observation was accepted as success")
    assert null_transport.tainted is True

    # A valid resident reply can itself report an asynchronous unknown outcome.
    # Session taints trust before returning the evidence to Adapter.
    async_transport = FakeTransport([
        payload(lastAction={
            "requestId": "special-choice-1",
            "command": "open_special_choice",
            "outcome": "outcome_unknown",
        }),
    ])
    async_session = Hades2ResidentSession(async_transport, bootstrap="")
    async_reply = async_session.status()
    assert async_reply.outcome_unknown is True
    assert async_transport.tainted is True
    try:
        async_session.status()
    except AdapterError as error:
        assert error.code == "restart_required"
    else:
        raise AssertionError("tainted session admitted another resident boundary")

    # In-game native rerolls have no Trainer request receipt. Their resident
    # trust observation must independently close the same session boundary.
    native_transport = FakeTransport([payload(runtimeOutcomeUnknown=True)])
    native_session = Hades2ResidentSession(native_transport, bootstrap="")
    assert native_session.status().outcome_unknown is True
    assert native_transport.tainted is True

    # Known resident failures remain known and do not poison session trust.
    known_transport = FakeTransport([
        payload(lastAction={
            "requestId": "known-1",
            "command": "open_special_choice",
            "outcome": "failed",
            "error": "native refusal",
        }),
    ])
    known_session = Hades2ResidentSession(known_transport, bootstrap="")
    known_reply = known_session.status()
    assert known_reply.outcome_unknown is False
    assert known_transport.tainted is False

    cleanup_transport = FakeTransport([
        AdapterError("lua_error", "MGT_RESIDENT_RESTART_REQUIRED: cleanup failed"),
    ])
    cleanup_session = Hades2ResidentSession(cleanup_transport, bootstrap="")
    try:
        cleanup_session.mutate("cleanup", {})
    except AdapterError as error:
        assert error.code == "restart_required"
    else:
        raise AssertionError("resident cleanup failure did not require restart")
finally:
    session_module.localize_catalog = old_localize

print("hades2_resident_session_ok")
