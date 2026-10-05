"""Deep Hades durable-desired reconciliation over the resident-session seam.

The caller supplies canonical durable desired state and a real pre-projection
runtime observation. This module owns the resident-backed diff policy, one-batch
execution and post-batch confirmation. It never mutates or persists desired state.
"""
from dataclasses import dataclass
import copy
import logging
import uuid

from .resident_session import ResidentReply
from .schema import MULTIPLIERS, TOGGLES, VITALS


@dataclass(frozen=True)
class DesiredReconciliationOutcome:
    reply: ResidentReply | None
    confirmed: bool
    mismatches: tuple[str, ...]


@dataclass(frozen=True)
class _Action:
    command: str
    params: dict
    mismatch: str
    request_id: bool = False


def _number_equal(left, right):
    if type(left) not in (int, float) or isinstance(left, bool):
        return False
    if type(right) not in (int, float) or isinstance(right, bool):
        return False
    return abs(float(left) - float(right)) <= 1e-6


def _boon_rarity_equal(observed, desired):
    if not isinstance(observed, dict) or not isinstance(desired, dict):
        return False
    if observed.get("target") != desired.get("target"):
        return False
    if not _number_equal(observed.get("multiplier"), desired.get("multiplier")):
        return False
    return (
        observed.get("forceLegendary") is desired.get("forceLegendary")
        and observed.get("forceDuo") is desired.get("forceDuo")
    )


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _rows_by_id(value):
    if not isinstance(value, list):
        return {}
    return {
        row["id"]: row
        for row in value
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }


class Hades2DesiredStateReconciler:
    """Plan, execute and confirm replay-safe resident-backed desired state."""

    def __init__(self, resident_session, request_id_factory=None):
        self._resident_session = resident_session
        self._request_id_factory = request_id_factory or (
            lambda: f"replay-{uuid.uuid4().hex}"
        )

    def reconcile(self, desired, observed, *, force_full=False):
        desired_snapshot = copy.deepcopy(desired) if isinstance(desired, dict) else {}
        observed_snapshot = copy.deepcopy(observed) if isinstance(observed, dict) else {}

        actions = self._diff(
            desired_snapshot,
            observed_snapshot,
            force_full=bool(force_full),
        )
        reply = None
        after = observed_snapshot
        if actions:
            calls = self._materialize(actions)
            logging.info("ReplayPreferences count=%d", len(calls))
            reply = self._resident_session.reconcile(calls)
            after = reply.payload if isinstance(reply.payload, dict) else {}

        remaining = self._diff(desired_snapshot, after, force_full=False)
        mismatches = tuple(dict.fromkeys(action.mismatch for action in remaining))
        return DesiredReconciliationOutcome(
            reply=reply,
            confirmed=not mismatches,
            mismatches=mismatches,
        )

    def _materialize(self, actions):
        calls = []
        for action in actions:
            params = copy.deepcopy(action.params)
            if action.request_id:
                params["requestId"] = str(self._request_id_factory())
            calls.append((action.command, params))
        return calls

    def _diff(self, desired, observed, *, force_full):
        actions = []
        lock_releases = []
        lock_updates = []
        desired_features = _mapping(observed.get("desiredFeatures"))

        for key in TOGGLES:
            wanted = bool(desired.get(key, False))
            if force_full or desired_features.get(key) is not wanted:
                actions.append(
                    _Action(
                        "set_feature",
                        {"feature": key, "value": wanted},
                        f"feature:{key}",
                    )
                )

        for key in MULTIPLIERS:
            if key == "gameSpeed":
                continue
            wanted = desired.get(key)
            if force_full or not _number_equal(observed.get(key), wanted):
                actions.append(
                    _Action(
                        "set_feature",
                        {"feature": key, "value": wanted},
                        f"feature:{key}",
                    )
                )

        wanted_rarity = _mapping(desired.get("boonRarity"))
        if force_full or not _boon_rarity_equal(
            observed.get("boonRarity"), wanted_rarity
        ):
            actions.append(
                _Action(
                    "set_boon_rarity",
                    dict(wanted_rarity),
                    "boonRarity",
                )
            )

        wanted_gathering = _mapping(desired.get("gatheringProbabilities"))
        observed_gathering = _mapping(observed.get("gatheringProbabilities"))
        if force_full or observed_gathering != wanted_gathering:
            actions.append(
                _Action(
                    "set_gathering_probabilities",
                    {"probabilities": dict(wanted_gathering)},
                    "gatheringProbabilities",
                )
            )

        wanted_chaos = desired.get("chaosGateProbability")
        observed_chaos = observed.get("chaosGateProbability")
        chaos_matches = (
            observed_chaos is None
            if wanted_chaos is None
            else _number_equal(observed_chaos, wanted_chaos)
        )
        if force_full or not chaos_matches:
            actions.append(
                _Action(
                    "set_chaos_gate_probability",
                    {"probability": wanted_chaos},
                    "chaosGateProbability",
                )
            )

        observed_stats = _mapping(observed.get("stats"))
        wanted_stats = _mapping(desired.get("statLocks"))
        locked_stats = {
            key
            for key, row in observed_stats.items()
            if isinstance(row, dict) and row.get("locked")
        }
        for stat in sorted(locked_stats - set(wanted_stats)):
            lock_releases.append(
                _Action(
                    "set_stat",
                    {"stat": stat, "locked": False},
                    f"stat:{stat}",
                )
            )
        for stat, value in wanted_stats.items():
            row = observed_stats.get(stat)
            matches = (
                isinstance(row, dict)
                and bool(row.get("locked"))
                and _number_equal(row.get("target"), value)
            )
            if force_full or not matches:
                lock_updates.append(
                    _Action(
                        "set_stat",
                        {"stat": stat, "locked": True, "value": value},
                        f"stat:{stat}",
                    )
                )

        wanted_vitals = _mapping(desired.get("vitalLocks"))
        for vital in VITALS:
            if bool(observed.get(vital + "Locked")) and vital not in wanted_vitals:
                lock_releases.append(
                    _Action(
                        "lock_vital",
                        {"vital": vital, "locked": False},
                        f"vital:{vital}",
                    )
                )
        for vital, row in wanted_vitals.items():
            if not isinstance(row, dict):
                continue
            for field in ("max", "current"):
                if field == "max" and vital == "armor":
                    continue
                value = row.get(field)
                state_key = vital if field == "current" else "max" + vital.capitalize()
                if force_full or not _number_equal(observed.get(state_key), value):
                    lock_updates.append(
                        _Action(
                            "set_vital",
                            {"vital": vital, "field": field, "value": value},
                            f"vital:{vital}",
                        )
                    )
            if force_full or not bool(observed.get(vital + "Locked")):
                lock_updates.append(
                    _Action(
                        "lock_vital",
                        {"vital": vital, "locked": True},
                        f"vital:{vital}",
                    )
                )

        resource_rows = _rows_by_id(observed.get("resources"))
        wanted_resources = _mapping(desired.get("resourceLocks"))
        locked_resources = {
            key
            for key, row in resource_rows.items()
            if bool(row.get("locked"))
        }
        if observed.get("moneyLocked"):
            locked_resources.add("Money")
        for resource in sorted(locked_resources - set(wanted_resources)):
            lock_releases.append(
                _Action(
                    "lock_resource",
                    {"resource": resource, "locked": False},
                    f"resource:{resource}",
                    request_id=True,
                )
            )
        for resource, amount in wanted_resources.items():
            observed_amount = (
                observed.get("money")
                if resource == "Money"
                else _mapping(resource_rows.get(resource)).get("count")
            )
            observed_locked = (
                bool(observed.get("moneyLocked"))
                if resource == "Money"
                else bool(_mapping(resource_rows.get(resource)).get("locked"))
            )
            if force_full or not _number_equal(observed_amount, amount):
                lock_updates.append(
                    _Action(
                        "set_resource",
                        {"resource": resource, "amount": int(amount)},
                        f"resource:{resource}",
                        request_id=True,
                    )
                )
            if force_full or not observed_locked:
                lock_updates.append(
                    _Action(
                        "lock_resource",
                        {"resource": resource, "locked": True},
                        f"resource:{resource}",
                        request_id=True,
                    )
                )

        wanted_rerolls = desired.get("rerollsLock")
        observed_rerolls_locked = bool(observed.get("rerollsLocked"))
        if wanted_rerolls is None:
            if observed_rerolls_locked:
                lock_releases.append(
                    _Action(
                        "lock_rerolls",
                        {"locked": False},
                        "rerolls",
                        request_id=True,
                    )
                )
        else:
            if force_full or not _number_equal(
                observed.get("rerolls"), wanted_rerolls
            ):
                lock_updates.append(
                    _Action(
                        "set_rerolls",
                        {"amount": int(wanted_rerolls)},
                        "rerolls",
                        request_id=True,
                    )
                )
            if force_full or not observed_rerolls_locked:
                lock_updates.append(
                    _Action(
                        "lock_rerolls",
                        {"locked": True},
                        "rerolls",
                        request_id=True,
                    )
                )

        element_rows = _rows_by_id(observed.get("elements"))
        wanted_elements = _mapping(desired.get("elementLocks"))
        locked_elements = {
            key
            for key, row in element_rows.items()
            if bool(row.get("locked"))
        }
        for element in sorted(locked_elements - set(wanted_elements)):
            lock_releases.append(
                _Action(
                    "lock_element",
                    {"element": element, "locked": False},
                    f"element:{element}",
                )
            )
        for element, amount in wanted_elements.items():
            row = _mapping(element_rows.get(element))
            if force_full or not _number_equal(row.get("count"), amount):
                lock_updates.append(
                    _Action(
                        "set_element",
                        {"element": element, "amount": int(amount)},
                        f"element:{element}",
                    )
                )
            if force_full or not bool(row.get("locked")):
                lock_updates.append(
                    _Action(
                        "lock_element",
                        {"element": element, "locked": True},
                        f"element:{element}",
                    )
                )

        # Lock reconciliation is deliberately two-phase across all lock families:
        # first release every stale owner, then apply desired values/locks.
        actions.extend(lock_releases)
        actions.extend(lock_updates)

        wanted_reward = desired.get("nextRoomReward")
        wanted_token = desired.get("nextRoomRewardToken")
        observed_reward = observed.get("nextRoomReward")
        diagnostics = _mapping(observed.get("runtimeDiagnostics"))
        reward_matches = observed_reward == wanted_reward
        if wanted_reward is not None:
            reward_matches = (
                reward_matches
                and diagnostics.get("nextRoomRewardToken") == wanted_token
            )
        if force_full or not reward_matches:
            actions.append(
                _Action(
                    "set_next_room_reward",
                    {"reward": wanted_reward, "token": wanted_token},
                    "nextRoomReward",
                )
            )

        return actions
