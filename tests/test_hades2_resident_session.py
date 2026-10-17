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
        self.pending_receipt = False
        self.acknowledged = []

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
        if not self.tainted:
            assert not self.pending_receipt, "A new command crossed before the resident accepted its previous receipt"
        self.calls.append({
            "source": source,
            "expression_timeout_seconds": expression_timeout_seconds,
        })
        if self.tainted:
            raise AdapterError("restart_required", "tainted transport")
        outcome = self.outcomes.pop(0) if self.outcomes else payload()
        if isinstance(outcome, BaseException):
            raise outcome
        self.pending_receipt = True
        if isinstance(outcome, str):
            return outcome
        return json.dumps(outcome)

    def acknowledge_result(self):
        assert self.pending_receipt and not self.tainted
        self.pending_receipt = False
        self.acknowledged.append(self.calls[-1]["source"])


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
    assert len(status_transport.acknowledged) == 2
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
    assert not decode_transport.acknowledged and decode_transport.pending_receipt

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
    assert not async_transport.acknowledged and async_transport.pending_receipt
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
    assert len(known_transport.acknowledged) == 1

    # A game-thread VM lease mismatch is a known pre-execution rejection.
    # Status may bootstrap a fresh VM; a submitted mutation is never replayed.
    native_missing = AdapterError("resident_generation_missing", "fixture VM reset")
    lease_transport = FakeTransport([payload(), native_missing, payload()])
    lease_session = Hades2ResidentSession(lease_transport, bootstrap="BOOTSTRAP")
    lease_session.status()
    assert lease_session.status().generation_reset is True
    assert len(lease_transport.calls) == 3 and len(lease_transport.acknowledged) == 2
    lease_transport.outcomes = [native_missing]
    before = len(lease_transport.calls)
    try:
        lease_session.mutate("spawn_reward", {"requestId": "never-replay"})
    except ResidentGenerationInvalidated:
        pass
    else:
        raise AssertionError("A mutation crossed a replacement VM lease")
    assert len(lease_transport.calls) == before + 1

    # Native menu-close handoff is an ordinary accepted control receipt.
    # It must release its slot before the next observation/actual mutation.
    handoff_transport = FakeTransport([
        {"__trainerTraitTrayHandoff": "closing"}, payload(),
    ])
    handoff_session = Hades2ResidentSession(handoff_transport, bootstrap="")
    handoff_session.mutate("set_resource", {"resource": "MetaCurrency", "amount": 10})
    assert len(handoff_transport.calls) == len(handoff_transport.acknowledged) == 2

    class LostAcknowledgementTransport(FakeTransport):
        def acknowledge_result(self):
            assert self.pending_receipt
            raise AdapterError("restart_required", "hades2.error.debuggerExited",
                               diagnostic="ACK reply lost")

    # A decoded receipt remains authoritative when only its release fails. The
    # session returns both pieces of evidence and closes every later boundary,
    # even for a transport double that does not enforce sticky terminal state.
    for action_outcome in ("completed", "accepted", "failed"):
        action = {"requestId": "known-ack-loss", "command": "open_special_choice",
                  "outcome": action_outcome}
        accepted_payload = payload(lastAction=action, requestId="known-ack-loss",
                                   actionOutcome=action_outcome, applied=action_outcome == "completed")
        ack_transport = LostAcknowledgementTransport([accepted_payload])
        ack_session = Hades2ResidentSession(ack_transport, bootstrap="")
        ack_reply = ack_session.mutate("open_special_choice", {"source": "Artemis"})
        assert ack_reply.payload == accepted_payload
        assert ack_reply.outcome_unknown is False
        assert ack_reply.connection_error.code == "restart_required"
        assert ack_reply.connection_error.presentation == "hades2.error.commandResultConnectionLost"
        assert ack_reply.connection_error.metrics == ack_reply.metrics
        assert not ack_session.allows_process_time_warp() and not ack_session.alive()
        assert ack_transport.pending_receipt and not ack_transport.acknowledged
        ack_session.invalidate_generation()  # a log notification cannot restore trust
        for operation in (ack_session.status, lambda: ack_session.reconcile([]),
                          lambda: ack_session.mutate("spawn_reward", {"reward": "Money"})):
            try:
                operation()
            except AdapterError as error:
                assert error.code == "restart_required"
            else:
                raise AssertionError("ACK loss admitted another resident command")
        assert len(ack_transport.calls) == 1

    # The accepted menu-close control action is not the requested mutation.
    # A lost ACK must end the handoff before another dispatch and say the
    # original change has not executed, without making the control result unknown.
    handoff_loss = LostAcknowledgementTransport([
        {"__trainerTraitTrayHandoff": "closing"}, payload(applied=True),
    ])
    handoff_loss_session = Hades2ResidentSession(handoff_loss, bootstrap="")
    try:
        handoff_loss_session.mutate("set_resource", {"resource": "MetaCurrency", "amount": 10})
    except AdapterError as error:
        assert error.code == "restart_required"
        assert error.presentation == "hades2.error.commandNotExecutedConnectionLost"
    else:
        raise AssertionError("menu-close ACK loss continued into the original mutation")
    assert len(handoff_loss.calls) == 1 and handoff_loss.pending_receipt
    assert not handoff_loss_session.allows_process_time_warp()

    # Status recovery carries both its generation reset and the accepted
    # replacement-generation receipt when ACK is the step that fails.
    recovering_transport = FakeTransport([payload()])
    recovering_session = Hades2ResidentSession(recovering_transport, bootstrap="BOOTSTRAP")
    recovering_session.status()
    recovering_transport.outcomes = [native_missing, payload(money=99)]
    recovering_transport.acknowledge_result = lambda: (_ for _ in ()).throw(
        AdapterError("restart_required", "ACK reply lost")
    )
    recovered = recovering_session.status()
    assert recovered.generation_reset is True and recovered.payload["money"] == 99
    assert recovered.connection_error.code == "restart_required"
    assert len(recovering_transport.calls) == 3

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
