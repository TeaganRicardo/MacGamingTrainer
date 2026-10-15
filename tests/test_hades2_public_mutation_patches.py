"""Runtime wire replies preserve all changes while omitting untouched domains."""
import copy
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests")]

from core.adapter import AdapterError
from core.protocol import JsonlRequestRouter
from games.hades2 import preparation
from games.hades2.adapter import Hades2Adapter
from games.hades2.schema import MULTIPLIERS, TOGGLES
from hades2_resident_session_fakes import FakeResidentSession, FakeTimeWarpController


with tempfile.TemporaryDirectory(prefix="mgt-public-mutations-") as temporary, patch.object(
    preparation, "DATA", Path(temporary) / "preferences",
):
    resident = FakeResidentSession()
    adapter = Hades2Adapter(resident_session=resident, time_warp_controller=FakeTimeWarpController())
    resident.payload.update(
        capabilities={"setFeature": True},
        desiredFeatures={key: False for key in TOGGLES},
        activeFeatures={key: False for key in TOGGLES},
        boonRarity=copy.deepcopy(adapter.preferences["boonRarity"]),
        **{key: adapter.preferences[key] for key in MULTIPLIERS},
        health=100, money=10, spellChargeCost=20,
        boons=[{"id": "ZeusUpgrade", "name": "Synthetic Zeus"}],
        rewards=[{"id": "MetaCurrencyDrop", "name": "Synthetic Reward"}],
        resources=[{"id": "MetaCurrency", "name": "Synthetic Resource", "count": 10, "locked": False}],
        currentRunTraits=[{"instanceId": "1", "name": "Synthetic Boon", "level": 1}],
        lastAction=None,
    )
    adapter.preference_initialized = True
    adapter.preference_dirty = False
    router = JsonlRequestRouter(adapter, save_data_root=Path(temporary) / "saves")
    host = {}
    sequence = 0

    def send(command, params=None):
        global sequence
        sequence += 1
        reply = router.handle({"id": str(sequence), "command": command, "params": params or {}})
        host.update(reply.get("result", reply.get("state", {})))
        return reply

    def mutation(session, call):
        command, params = call["command"], call["params"]
        if command == "set_resource":
            session.payload["resources"][0]["count"] = params["amount"]
            # Changes from synchronize/native owners must travel even when a
            # different initiating command happens to discover them.
            session.payload["spellChargeCost"] = None
            session.payload["capabilities"]["traitMutation"] = True
        elif command == "set_vital":
            session.payload["health"] = params["value"]
        elif command == "set_feature":
            session.payload["desiredFeatures"][params["feature"]] = params["value"]
            session.payload["activeFeatures"][params["feature"]] = params["value"]
        elif command == "set_trait_level":
            session.payload["currentRunTraits"][0]["level"] = params["targetLevel"]
            session.payload["lastAction"] = {"command": command, "requestId": params["requestId"], "outcome": "completed"}
        elif command == "spawn_reward":
            session.payload.update(requestId=params["requestId"], applied=True, lootObjectId=321)
        return session.payload

    resident.handler = mutation
    first = send("status")["result"]
    assert {"boons", "rewards", "resources", "currentRunTraits", "connected"} <= first.keys()
    resource = send("set_resource", {"resource": "MetaCurrency", "amount": 50})["result"]
    assert not {"boons", "rewards", "currentRunTraits"} & resource.keys(), resource.keys()
    assert resource["spellChargeCost"] is None and resource["capabilities"]["traitMutation"]
    assert host["resources"][0]["count"] == 50 and host["boons"] == first["boons"]
    vital = send("set_vital", {"vital": "health", "field": "current", "value": 75})["result"]
    assert vital == {"health": 75}, vital
    feature = send("set_desired", {"feature": "invincibility", "value": True})["result"]
    assert feature["desiredFeatures"]["invincibility"] and feature["activeFeatures"]["invincibility"]
    assert "resources" not in feature and "boons" not in feature
    trait = send("set_trait_level", {"generationId": "g", "runId": "r", "instanceId": "1",
        "trait": "SyntheticBoon", "family": "olympianHermes", "expectedLevel": 1,
        "expectedRarity": "Common", "expectedSameNameCount": 1, "targetLevel": 2})["result"]
    assert trait["currentRunTraits"][0]["level"] == 2 and trait["lastAction"]["outcome"] == "completed"
    assert "resources" not in trait and "boons" not in trait
    reward = send("spawn_reward", {"reward": "MetaCurrencyDrop"})["result"]
    assert reward["applied"] is True and reward["lootObjectId"] == 321
    assert "boons" not in reward and "currentRunTraits" not in reward
    repeated = send("spawn_reward", {"reward": "MetaCurrencyDrop"})["result"]
    assert repeated["applied"] is True and repeated["lootObjectId"] == 321
    assert repeated["requestId"] != reward["requestId"]
    # Reconstructing the Host from all incremental replies equals a later full
    # authoritative status, including receipts and explicit-null observations.
    reconstructed = copy.deepcopy(host)
    complete = send("status")["result"]
    assert reconstructed == complete
    assert {"boons", "rewards", "resources", "currentRunTraits"} <= complete.keys()

    # An error exposes Core's complete error-state projection. The next reply
    # must establish a fresh snapshot, even when a value returns to its older
    # published value rather than changing relative to that older baseline.
    def failure(session, call):
        adapter.state["money"] = 999
        return AdapterError("lua_error", "fixture failure")
    resident.handler = failure
    failed = send("set_resource", {"resource": "MetaCurrency", "amount": 51})
    assert not failed["ok"] and host["money"] == 999
    resident.handler = mutation
    recovered = send("set_vital", {"vital": "health", "field": "current", "value": 80})["result"]
    assert recovered["money"] == 10 and "boons" in recovered

    # A profile/diagnostic/Save reply is an independent projection. It cannot
    # silently become the baseline for later ordinary runtime patches.
    send("list_profiles")
    after_independent = send("set_vital", {"vital": "health", "field": "current", "value": 81})["result"]
    assert "boons" in after_independent and after_independent["health"] == 81

print("hades2_public_mutation_patches_ok")
