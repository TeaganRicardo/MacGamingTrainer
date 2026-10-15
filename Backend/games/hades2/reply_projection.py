"""Public reply snapshots and change-aware mutation patches for Hades."""
import copy
import time

from core.operation_profile import record

ACTION_RESULT_FIELDS = (
    "requestId", "duplicate", "applied", "actionOutcome", "actionError", "lootObjectId",
)


class Hades2ReplyProjection:
    def __init__(self):
        self._previous = None

    def invalidate(self):
        self._previous = None

    def publish(self, reply, kind):
        started = time.perf_counter()
        if kind == "independent":
            # Profile, Save and diagnostics replies have independent shapes;
            # none can establish the ordinary runtime's complete baseline.
            self.invalidate()
            return reply

        previous = self._previous
        changes = {}
        retained = {}
        for key, value in reply.items():
            if previous is None or key not in previous or previous[key] != value:
                changes[key] = value
                # Keep our baseline independent of the Adapter's mutable state
                # and of objects returned to in-process callers. Untouched
                # domains reuse their already isolated baseline values.
                retained[key] = copy.deepcopy(value)
            else:
                retained[key] = previous[key]
            # These are per-operation receipts, not retained state. A repeated
            # `applied=true` still belongs to this operation's actual reply.
            if key in ACTION_RESULT_FIELDS or (key == "lastAction" and isinstance(value, dict)):
                changes[key] = value
        if previous is not None:
            for key in previous.keys() - reply.keys():
                changes[key] = None
        self._previous = retained
        full = kind == "snapshot" or previous is None
        result = reply if full else changes
        record("backend.public_projection", time.perf_counter() - started,
               response_kind="full" if full else "patch", field_count=len(result))
        return result
