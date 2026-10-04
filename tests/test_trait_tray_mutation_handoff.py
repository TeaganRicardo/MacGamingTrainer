import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import adapter as adapter_module
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter


base = Path(tempfile.mkdtemp(prefix="mgt-trait-tray-handoff-"))
preparation.DATA = base
adapter_module.localize_catalog = lambda payload: payload


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
        self.sources = []
        self.tray_active = tray_active
        self.close_requested = False
        self.close_after_boundaries = close_after_boundaries
        self.post_close_boundaries = 0
        self.mutation_applications = 0
        self.tainted = False

    def alive(self):
        return True

    def attach(self, pid):
        self.pid = pid

    def detach(self):
        pass

    def close(self):
        pass

    def execute(self, source):
        self.sources.append(source)
        dispatch_count = source.count("__MacGamingTrainerV1.dispatch(")
        has_status_dispatch = 'dispatch("status"' in source or "dispatch(\"status\"" in source
        is_mutation = dispatch_count > 1 or (dispatch_count == 1 and not has_status_dispatch)

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


# Closed tray: the existing mutation remains one transport boundary. The handoff
# must not add a separate probe/wait to the common path.
closed_transport = TraitTrayTransport(tray_active=False)
closed_adapter = Hades2Adapter(transport=closed_transport)
closed_adapter.execute("set_health", {"amount": 42, "requestId": "closed-path"})
assert len(closed_transport.sources) == 1
assert closed_transport.mutation_applications == 1


# Open tray: the first boundary requests game-owned closure without dispatching
# the mutation. A later boundary executes the original request after ownership
# is gone, so the request is neither rejected nor duplicated.
open_transport = TraitTrayTransport(tray_active=True)
open_adapter = Hades2Adapter(transport=open_transport)
result = open_adapter.execute("set_health", {"amount": 42, "requestId": "open-path"})
assert result["status"] == "ready"
assert open_transport.close_requested is True
assert open_transport.tray_active is False
assert len(open_transport.sources) == 2
assert open_transport.mutation_applications == 1
assert sum('dispatch("set_health"' in source or 'dispatch(\"set_health\"' in source for source in open_transport.sources) == 2
assert all("TraitTrayScreenClose" in source for source in open_transport.sources)


# Read-only status is observational: it neither closes the screen nor enters the
# mutation handoff.
status_transport = TraitTrayTransport(tray_active=True)
status_adapter = Hades2Adapter(transport=status_transport)
status_adapter.observe_runtime()
assert status_transport.tray_active is True
assert status_transport.close_requested is False
assert len(status_transport.sources) == 1
assert "TraitTrayScreenClose" not in status_transport.sources[0]


# Replay/batch is one atomic mutation boundary: the entire batch waits behind
# the same handoff and applies once only after Trait Tray ownership is released.
batch_transport = TraitTrayTransport(tray_active=True)
batch_adapter = Hades2Adapter(transport=batch_transport)
batch_adapter.execute(
    "replay_preferences",
    {},
    replay=True,
    batch=[
        ("set_feature", {"feature": "invincibility", "enabled": True, "requestId": "batch-a"}),
        ("set_health", {"amount": 80, "requestId": "batch-b"}),
    ],
)
assert batch_transport.close_requested is True
assert batch_transport.tray_active is False
assert batch_transport.mutation_applications == 1
assert len(batch_transport.sources) == 2


# A broken native close lifecycle is bounded and must never fall through into
# resident mutation while stale Trait Tray ownership remains.
timeout_transport = TraitTrayTransport(tray_active=True, close_after_boundaries=None)
timeout_adapter = Hades2Adapter(transport=timeout_transport)
old_timeout = adapter_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS
old_poll = adapter_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS
adapter_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS = 0.02
adapter_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS = 0.005
try:
    try:
        timeout_adapter.execute("set_health", {"amount": 42, "requestId": "timeout-path"})
    except adapter_module.TransportError as error:
        assert error.code == "waiting"
    else:
        raise AssertionError("stale Trait Tray ownership was allowed to dispatch")
finally:
    adapter_module._TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS = old_timeout
    adapter_module._TRAIT_TRAY_HANDOFF_POLL_SECONDS = old_poll
assert timeout_transport.mutation_applications == 0


print("trait_tray_mutation_handoff_ok")
