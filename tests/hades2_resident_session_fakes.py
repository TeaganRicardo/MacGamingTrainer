import copy

from games.hades2.resident_session import ResidentMetrics, ResidentReply


class FakeResidentSession:
    """Semantic test adapter for the Hades resident-session seam."""

    def __init__(self, payload=None, handler=None, pid=4242):
        self.payload = copy.deepcopy(payload or {
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
        })
        self.handler = handler
        self.pid = pid
        self.live = True
        self.calls = []
        self.invalidations = 0
        self.last_attach_profile = {}

    def alive(self):
        return self.live

    def attach(self, pid):
        self.pid = pid
        self.live = True
        self.invalidations += 1

    def detach(self):
        self.live = False

    def close(self):
        self.live = False

    def invalidate_generation(self):
        self.invalidations += 1

    def status(self, params=None):
        return self._reply("status", "status", params or {}, None)

    def observe_status(self, params=None):
        return self._reply("observe", "status", params or {}, None)

    def mutate(self, command, params=None):
        return self._reply("mutate", command, params or {}, None)

    def reconcile(self, calls):
        return self._reply("reconcile", "replay_preferences", {}, list(calls))

    def _reply(self, kind, command, params, batch):
        record = {
            "kind": kind,
            "command": command,
            "params": copy.deepcopy(params),
            "batch": copy.deepcopy(batch),
        }
        self.calls.append(record)
        result = None
        if self.handler is not None:
            result = self.handler(self, record)
        if isinstance(result, BaseException):
            raise result
        if isinstance(result, ResidentReply):
            return result
        payload = copy.deepcopy(self.payload if result is None else result)
        return ResidentReply(
            payload=payload,
            metrics=ResidentMetrics(boundary_duration=0.001),
        )


class FakeTimeWarpController:
    def __init__(self):
        self.speed = 1.0
        self.calls = []
        self.error = None

    def set_speed(self, value):
        self.calls.append(("set", float(value)))
        if self.error is not None:
            raise self.error
        self.speed = float(value)
        return self.speed

    def reset(self):
        self.calls.append(("reset", 1.0))
        if self.error is not None:
            raise self.error
        self.speed = 1.0
        return self.speed
