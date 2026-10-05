import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import resident_session as session_module
from games.hades2.resident_session import Hades2ResidentSession, TransportError


def runtime_payload():
    return {
        "status": "ready",
        "scene": "run",
        "capabilities": {},
        "desiredFeatures": {},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureSupport": {},
        "featureErrors": {},
        "boonRarity": {
            "target": "Epic",
            "multiplier": 100.0,
            "forceLegendary": False,
            "forceDuo": False,
        },
        "resources": [],
        "elements": [],
        "stats": {},
    }


class TraitTrayTransport:
    def __init__(self, tray_active, close_after_boundaries=1):
        self.pid = 4242
        self.last_duration = 0.001
        self.last_expression_duration = 0.0
        self.sources = []
        self.tray_active = tray_active
        self.close_requested = False
        self.close_after_boundaries = close_after_boundaries
        self.post_close_boundaries = 0
        self.mutation_applications = 0
        self.tainted = False

    def alive(self):
        return True

    def execute(self, source, *, expression_timeout_seconds=None):
        self.sources.append(source)
        dispatch_count = source.count("__MacGamingTrainerV1.dispatch(")
        has_batch_dispatch = "__MacGamingTrainerV1.dispatchBatch(" in source
        has_status_dispatch = 'dispatch("status"' in source
        is_mutation = (
            has_batch_dispatch
            or dispatch_count > 1
            or (dispatch_count == 1 and not has_status_dispatch)
        )

        if self.close_requested and self.tray_active:
            self.post_close_boundaries += 1
            if (
                self.close_after_boundaries is not None
                and self.post_close_boundaries >= self.close_after_boundaries
            ):
                self.tray_active = False

        if self.tray_active and is_mutation:
            if "TraitTrayScreenClose" not in source:
                raise AssertionError("mutation crossed resident dispatch while Trait Tray owned the UI")
            self.close_requested = True
            return json.dumps({"__trainerTraitTrayHandoff": "closing"})

        if is_mutation:
            self.mutation_applications += 1
        return json.dumps(runtime_payload())


# Closed tray: common mutations remain one LLDB boundary.
closed_transport = TraitTrayTransport(tray_active=False)
closed_session = Hades2ResidentSession(closed_transport, bootstrap="")
closed_session.mutate("set_health", {"amount": 42, "requestId": "closed-path"})
assert len(closed_transport.sources) == 1
assert closed_transport.mutation_applications == 1


# Open tray: session owns native close/yield/retry and applies the mutation once.
open_transport = TraitTrayTransport(tray_active=True)
open_session = Hades2ResidentSession(open_transport, bootstrap="")
reply = open_session.mutate("set_health", {"amount": 42, "requestId": "open-path"})
assert reply.payload["status"] == "ready"
assert open_transport.close_requested is True
assert open_transport.tray_active is False
assert len(open_transport.sources) == 2
assert open_transport.mutation_applications == 1
assert all("TraitTrayScreenClose" in source for source in open_transport.sources)


# Observation never enters the mutation handoff.
status_transport = TraitTrayTransport(tray_active=True)
status_session = Hades2ResidentSession(status_transport, bootstrap="")
status_session.observe_status()
assert status_transport.tray_active is True
assert status_transport.close_requested is False
assert len(status_transport.sources) == 1
assert "TraitTrayScreenClose" not in status_transport.sources[0]


# Durable replay remains one batch mutation after the same handoff.
batch_transport = TraitTrayTransport(tray_active=True)
batch_session = Hades2ResidentSession(batch_transport, bootstrap="")
batch_session.reconcile([
    ("set_feature", {"feature": "invincibility", "enabled": True, "requestId": "batch-a"}),
    ("set_health", {"amount": 80, "requestId": "batch-b"}),
])
assert batch_transport.close_requested is True
assert batch_transport.tray_active is False
assert batch_transport.mutation_applications == 1
assert len(batch_transport.sources) == 2


# Broken native close lifecycle stays bounded and never falls through to mutation.
timeout_transport = TraitTrayTransport(tray_active=True, close_after_boundaries=None)
timeout_session = Hades2ResidentSession(timeout_transport, bootstrap="")
old_timeout = session_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS
old_poll = session_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS
session_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS = 0.02
session_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS = 0.005
try:
    try:
        timeout_session.mutate("set_health", {"amount": 42, "requestId": "timeout-path"})
    except TransportError as error:
        assert error.code == "waiting"
    else:
        raise AssertionError("stale Trait Tray ownership was allowed to dispatch")
finally:
    session_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS = old_timeout
    session_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS = old_poll
assert timeout_transport.mutation_applications == 0


print("trait_tray_mutation_handoff_ok")
