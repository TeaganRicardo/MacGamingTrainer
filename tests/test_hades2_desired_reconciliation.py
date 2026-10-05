import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.desired_reconciliation import Hades2DesiredStateReconciler
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.resident_session import ResidentMetrics, ResidentReply
from games.hades2.schema import MULTIPLIERS, TOGGLES


def matching_observation(desired):
    observation = {
        "status": "ready",
        "scene": "run",
        "desiredFeatures": {key: bool(desired[key]) for key in TOGGLES},
        "activeFeatures": {},
        "dormantFeatures": {},
        "featureErrors": {},
        "boonRarity": copy.deepcopy(desired["boonRarity"]),
        "gatheringProbabilities": copy.deepcopy(desired["gatheringProbabilities"]),
        "chaosGateProbability": desired["chaosGateProbability"],
        "stats": {},
        "healthLocked": False,
        "health": 100.0,
        "maxHealth": 100.0,
        "manaLocked": False,
        "mana": 50.0,
        "maxMana": 50.0,
        "armorLocked": False,
        "armor": 0.0,
        "moneyLocked": False,
        "money": 0,
        "resources": [],
        "rerollsLocked": False,
        "rerolls": 0,
        "elements": [],
        "nextRoomReward": desired["nextRoomReward"],
        "runtimeDiagnostics": {},
    }
    for key in MULTIPLIERS:
        if key != "gameSpeed":
            observation[key] = desired[key]

    for stat, value in desired["statLocks"].items():
        observation["stats"][stat] = {
            "locked": True,
            "target": value,
            "value": value,
        }

    for vital, row in desired["vitalLocks"].items():
        observation[vital + "Locked"] = True
        observation[vital] = row["current"]
        if vital != "armor":
            observation["max" + vital.capitalize()] = row["max"]

    for resource, amount in desired["resourceLocks"].items():
        if resource == "Money":
            observation["moneyLocked"] = True
            observation["money"] = amount
        else:
            observation["resources"].append(
                {"id": resource, "locked": True, "count": amount}
            )

    if desired["rerollsLock"] is not None:
        observation["rerollsLocked"] = True
        observation["rerolls"] = desired["rerollsLock"]

    for element, amount in desired["elementLocks"].items():
        observation["elements"].append(
            {"id": element, "locked": True, "count": amount}
        )

    if desired["nextRoomReward"] is not None:
        observation["runtimeDiagnostics"]["nextRoomRewardToken"] = desired[
            "nextRoomRewardToken"
        ]
    return observation


class ApplyingSession:
    def __init__(self, observation, ignore=None):
        self.observation = copy.deepcopy(observation)
        self.ignore = set(ignore or ())
        self.calls = []

    def reconcile(self, calls):
        calls = copy.deepcopy(list(calls))
        self.calls.append(calls)
        for command, params in calls:
            key = self._key(command, params)
            if key in self.ignore:
                continue
            self._apply(command, params)
        return ResidentReply(
            payload=copy.deepcopy(self.observation),
            metrics=ResidentMetrics(boundary_duration=0.005),
        )

    @staticmethod
    def _key(command, params):
        if command == "set_feature":
            return "feature:" + str(params.get("feature"))
        if command in ("set_stat",):
            return "stat:" + str(params.get("stat"))
        if command in ("set_vital", "lock_vital"):
            return "vital:" + str(params.get("vital"))
        if command in ("set_resource", "lock_resource"):
            return "resource:" + str(params.get("resource"))
        if command in ("set_element", "lock_element"):
            return "element:" + str(params.get("element"))
        if command in ("set_rerolls", "lock_rerolls"):
            return "rerolls"
        if command == "set_boon_rarity":
            return "boonRarity"
        if command == "set_gathering_probabilities":
            return "gatheringProbabilities"
        if command == "set_chaos_gate_probability":
            return "chaosGateProbability"
        if command == "set_next_room_reward":
            return "nextRoomReward"
        return command

    def _apply(self, command, params):
        if command == "set_feature":
            feature = params["feature"]
            if feature in TOGGLES:
                self.observation["desiredFeatures"][feature] = bool(params["value"])
            else:
                self.observation[feature] = float(params["value"])
            return
        if command == "set_boon_rarity":
            self.observation["boonRarity"] = {
                "target": params["target"],
                "multiplier": float(params["multiplier"]),
                "forceLegendary": bool(params["forceLegendary"]),
                "forceDuo": bool(params["forceDuo"]),
            }
            return
        if command == "set_gathering_probabilities":
            self.observation["gatheringProbabilities"] = copy.deepcopy(
                params["probabilities"]
            )
            return
        if command == "set_chaos_gate_probability":
            self.observation["chaosGateProbability"] = params["probability"]
            return
        if command == "set_stat":
            stat = params["stat"]
            row = self.observation["stats"].setdefault(
                stat, {"locked": False, "target": None, "value": 0}
            )
            row["locked"] = bool(params["locked"])
            row["target"] = params.get("value") if params["locked"] else None
            if "value" in params:
                row["value"] = params["value"]
            return
        if command == "set_vital":
            vital = params["vital"]
            field = params["field"]
            state_key = vital if field == "current" else "max" + vital.capitalize()
            self.observation[state_key] = params["value"]
            return
        if command == "lock_vital":
            self.observation[params["vital"] + "Locked"] = bool(params["locked"])
            return
        if command == "set_resource":
            resource = params["resource"]
            amount = int(params["amount"])
            if resource == "Money":
                self.observation["money"] = amount
            else:
                row = next(
                    (
                        item
                        for item in self.observation["resources"]
                        if item.get("id") == resource
                    ),
                    None,
                )
                if row is None:
                    row = {"id": resource, "locked": False, "count": 0}
                    self.observation["resources"].append(row)
                row["count"] = amount
            return
        if command == "lock_resource":
            resource = params["resource"]
            locked = bool(params["locked"])
            if resource == "Money":
                self.observation["moneyLocked"] = locked
            else:
                row = next(
                    (
                        item
                        for item in self.observation["resources"]
                        if item.get("id") == resource
                    ),
                    None,
                )
                if row is None:
                    row = {"id": resource, "locked": False, "count": 0}
                    self.observation["resources"].append(row)
                row["locked"] = locked
            return
        if command == "set_rerolls":
            self.observation["rerolls"] = int(params["amount"])
            return
        if command == "lock_rerolls":
            self.observation["rerollsLocked"] = bool(params["locked"])
            return
        if command == "set_element":
            element = params["element"]
            row = next(
                (
                    item
                    for item in self.observation["elements"]
                    if item.get("id") == element
                ),
                None,
            )
            if row is None:
                row = {"id": element, "locked": False, "count": 0}
                self.observation["elements"].append(row)
            row["count"] = int(params["amount"])
            return
        if command == "lock_element":
            element = params["element"]
            row = next(
                (
                    item
                    for item in self.observation["elements"]
                    if item.get("id") == element
                ),
                None,
            )
            if row is None:
                row = {"id": element, "locked": False, "count": 0}
                self.observation["elements"].append(row)
            row["locked"] = bool(params["locked"])
            return
        if command == "set_next_room_reward":
            self.observation["nextRoomReward"] = params["reward"]
            diagnostics = self.observation.setdefault("runtimeDiagnostics", {})
            if params["reward"] is None:
                diagnostics.pop("nextRoomRewardToken", None)
            else:
                diagnostics["nextRoomRewardToken"] = params.get("token")
            return
        raise AssertionError("unexpected command: " + command)


def deterministic_ids():
    value = 0

    def next_id():
        nonlocal value
        value += 1
        return f"replay-test-{value}"

    return next_id


# A fully converged desired/runtime pair is a true no-op: no resident boundary.
desired = Hades2PreferenceStore.defaults()
desired.update(
    statLocks={"enemyHealth": 175},
    vitalLocks={"mana": {"current": 40, "max": 90}},
    resourceLocks={"Money": 500, "MetaCurrency": 12},
    rerollsLock=3,
    elementLocks={"Fire": 7},
    nextRoomReward="WeaponUpgrade",
    nextRoomRewardToken="reward-token",
    gatheringProbabilities={"flora": 25.0},
    chaosGateProbability=75.0,
)
desired["invincibility"] = True
desired["damageMultiplier"] = 3.0
desired["boonRarity"] = {
    "target": "Heroic",
    "multiplier": 250.0,
    "forceLegendary": True,
    "forceDuo": False,
}
observed = matching_observation(desired)
session = ApplyingSession(observed)
reconciler = Hades2DesiredStateReconciler(
    session, request_id_factory=deterministic_ids()
)
outcome = reconciler.reconcile(desired, observed)
assert outcome.confirmed is True
assert outcome.mismatches == ()
assert outcome.reply is None
assert session.calls == []


# A cross-family mismatch is planned as one resident batch and confirmed against
# the returned observation. gameSpeed remains outside the resident reconciler.
mismatch = matching_observation(desired)
mismatch["desiredFeatures"]["invincibility"] = False
mismatch["damageMultiplier"] = 2.0
mismatch["boonRarity"]["target"] = "Epic"
mismatch["gatheringProbabilities"] = {}
mismatch["chaosGateProbability"] = None
mismatch["stats"]["enemyHealth"] = {
    "locked": False,
    "target": None,
    "value": 100,
}
mismatch["manaLocked"] = False
mismatch["mana"] = 20
mismatch["maxMana"] = 50
mismatch["moneyLocked"] = False
mismatch["money"] = 100
for row in mismatch["resources"]:
    if row["id"] == "MetaCurrency":
        row.update(locked=False, count=1)
mismatch["rerollsLocked"] = False
mismatch["rerolls"] = 0
for row in mismatch["elements"]:
    if row["id"] == "Fire":
        row.update(locked=False, count=1)
mismatch["nextRoomReward"] = None
mismatch["runtimeDiagnostics"] = {}

session = ApplyingSession(mismatch)
reconciler = Hades2DesiredStateReconciler(
    session, request_id_factory=deterministic_ids()
)
before = copy.deepcopy(desired)
outcome = reconciler.reconcile(desired, mismatch)
assert outcome.confirmed is True
assert outcome.mismatches == ()
assert outcome.reply is not None
assert len(session.calls) == 1
batch = session.calls[0]
assert any(
    command == "set_feature"
    and params == {"feature": "invincibility", "value": True}
    for command, params in batch
)
assert any(
    command == "set_feature"
    and params == {"feature": "damageMultiplier", "value": 3.0}
    for command, params in batch
)
assert any(command == "set_boon_rarity" for command, _ in batch)
assert any(command == "set_gathering_probabilities" for command, _ in batch)
assert any(command == "set_chaos_gate_probability" for command, _ in batch)
assert any(command == "set_stat" for command, _ in batch)
assert any(command == "set_vital" for command, _ in batch)
assert any(command == "lock_vital" for command, _ in batch)
assert any(command == "set_resource" for command, _ in batch)
assert any(command == "lock_resource" for command, _ in batch)
assert any(command == "set_rerolls" for command, _ in batch)
assert any(command == "lock_rerolls" for command, _ in batch)
assert any(command == "set_element" for command, _ in batch)
assert any(command == "lock_element" for command, _ in batch)
assert any(command == "set_next_room_reward" for command, _ in batch)
assert all(
    not (command == "set_feature" and params.get("feature") == "gameSpeed")
    for command, params in batch
)
assert desired == before, "reconciliation mutated durable desired state"


# Stale locks are released before desired locks/values are applied.
release_desired = Hades2PreferenceStore.defaults()
release_desired.update(
    statLocks={"enemyHealth": 200},
    vitalLocks={"mana": {"current": 45, "max": 95}},
    resourceLocks={"Money": 600},
    rerollsLock=4,
    elementLocks={"Fire": 8},
)
stale = matching_observation(Hades2PreferenceStore.defaults())
stale["stats"]["grasp"] = {"locked": True, "target": 30, "value": 30}
stale["healthLocked"] = True
stale["health"] = 120
stale["maxHealth"] = 160
stale["resources"] = [{"id": "Bones", "locked": True, "count": 9}]
stale["rerollsLocked"] = True
stale["rerolls"] = 1
stale["elements"] = [{"id": "Water", "locked": True, "count": 2}]
session = ApplyingSession(stale)
reconciler = Hades2DesiredStateReconciler(
    session, request_id_factory=deterministic_ids()
)
outcome = reconciler.reconcile(release_desired, stale)
assert outcome.confirmed is True
batch = session.calls[0]


def first_index(command, **expected):
    return next(
        index
        for index, (name, params) in enumerate(batch)
        if name == command
        and all(params.get(key) == value for key, value in expected.items())
    )


assert first_index("set_stat", stat="grasp", locked=False) < first_index(
    "set_stat", stat="enemyHealth", locked=True
)
assert first_index("lock_vital", vital="health", locked=False) < first_index(
    "set_vital", vital="mana", field="max"
)
assert first_index("lock_resource", resource="Bones", locked=False) < first_index(
    "set_resource", resource="Money", amount=600
)
assert first_index("lock_element", element="Water", locked=False) < first_index(
    "set_element", element="Fire", amount=8
)

release_indexes = [
    index
    for index, (command, params) in enumerate(batch)
    if (
        command == "set_stat" and params.get("locked") is False
    ) or (
        command in ("lock_vital", "lock_resource", "lock_rerolls", "lock_element")
        and params.get("locked") is False
    )
]
apply_indexes = [
    index
    for index, (command, params) in enumerate(batch)
    if (
        command == "set_stat" and params.get("locked") is True
    ) or command in (
        "set_vital", "set_resource", "set_rerolls", "set_element"
    ) or (
        command in ("lock_vital", "lock_resource", "lock_rerolls", "lock_element")
        and params.get("locked") is True
    )
]
assert release_indexes and apply_indexes
assert max(release_indexes) < min(apply_indexes), (
    "all stale locks must release before any desired lock/value is applied"
)


# Request IDs are reconciler-owned and present only on the replay-safe command
# families that require them.
request_ids = [
    params["requestId"]
    for command, params in batch
    if command in ("set_resource", "lock_resource", "set_rerolls", "lock_rerolls")
]
assert request_ids
assert len(request_ids) == len(set(request_ids))
assert all(value.startswith("replay-test-") for value in request_ids)


# Force-full deliberately sends resident-backed desired state even when the
# observation already matches. Confirmation still uses the normal minimum diff.
full_session = ApplyingSession(matching_observation(desired))
full = Hades2DesiredStateReconciler(
    full_session, request_id_factory=deterministic_ids()
).reconcile(desired, matching_observation(desired), force_full=True)
assert full.confirmed is True
assert len(full_session.calls) == 1
full_batch = full_session.calls[0]
for key in TOGGLES:
    assert any(
        command == "set_feature" and params.get("feature") == key
        for command, params in full_batch
    )
for key in MULTIPLIERS:
    if key != "gameSpeed":
        assert any(
            command == "set_feature" and params.get("feature") == key
            for command, params in full_batch
        )
assert any(command == "set_boon_rarity" for command, _ in full_batch)
assert any(command == "set_next_room_reward" for command, _ in full_batch)


# A semantically successful batch that does not converge is not confirmation.
# Desired state remains unchanged and the mismatch is explicit for Adapter.
partial_observed = matching_observation(desired)
partial_observed["desiredFeatures"]["invincibility"] = False
partial_session = ApplyingSession(
    partial_observed,
    ignore={"feature:invincibility"},
)
partial_reconciler = Hades2DesiredStateReconciler(
    partial_session, request_id_factory=deterministic_ids()
)
before = copy.deepcopy(desired)
partial = partial_reconciler.reconcile(desired, partial_observed)
assert partial.confirmed is False
assert "feature:invincibility" in partial.mismatches
assert len(partial_session.calls) == 1
assert desired == before


# Equal reward text with a different token is not equivalent durable one-shot
# identity; reconciliation must re-arm the requested token.
token_observed = matching_observation(desired)
token_observed["runtimeDiagnostics"]["nextRoomRewardToken"] = "stale-token"
token_session = ApplyingSession(token_observed)
token_outcome = Hades2DesiredStateReconciler(
    token_session, request_id_factory=deterministic_ids()
).reconcile(desired, token_observed)
assert token_outcome.confirmed is True
assert any(
    command == "set_next_room_reward"
    and params.get("token") == "reward-token"
    for command, params in token_session.calls[0]
)

print("hades2_desired_reconciliation_ok")
