"""Retained collection transport preserves complete, fresh resident observations."""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests"), str(ROOT / "Tools/fixtures")]

from games.hades2 import localization, resident_session
from games.hades2.resident_session import Hades2ResidentSession, ResidentSessionError, lua_value


with tempfile.TemporaryDirectory(prefix="mgt-observation-") as temporary, patch.dict(os.environ, {
    "MGT_PROFILE_EVENTS": str(Path(temporary) / "events.log"),
    "MGT_PROFILE_TRAITS": "4", "MGT_PROFILE_CATALOG": "8", "MGT_PROFILE_RESOURCES": "4",
    "MGT_PROFILE_OPERATIONS": "0",
}):
    from hades2_profile_backend import OfflineLuaTransport

    class RecordingTransport(OfflineLuaTransport):
        def execute(self, source, **kwargs):
            result = super().execute(source, **kwargs)
            self.wire = json.loads(result)
            return result

    inputs = []
    original = resident_session.localize_catalog

    def localize(value):
        inputs.append(set(value))
        return original(value)

    game = Path(temporary) / "Game.app"
    identifiers = {"MetaCurrency", "Money", "ZeusUpgrade", "Boon"}
    identifiers.update("ProfileBoon%04d" % i for i in range(1, 9))
    identifiers.update("ProfileResource%04d" % i for i in range(1, 4))

    def text_generation(version):
        for language in ("zh-CN", "en"):
            path = game / "Contents/Resources/Content/Game/Text" / language / "fixture.sjson"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join('X={ Id="%s" DisplayName="%s %s v%d" }'
                % (key, language, key, version) for key in sorted(identifiers)))

    text_generation(1)
    issued = []

    def install_nonce():
        value = "%032x" % (len(issued) + 1)
        issued.append(value)
        return SimpleNamespace(hex=value)

    transport = RecordingTransport()
    session = Hades2ResidentSession(transport)
    try:
        with patch.object(resident_session, "localize_catalog", side_effect=localize), patch.object(
            localization, "GAME_SPEC", replace(localization.GAME_SPEC, app_bundle_path=game),
        ), patch.object(resident_session.uuid, "uuid4", side_effect=install_nonce):
            # Count the expensive whole-inventory eligibility pass without
            # replacing its native owner after the retained-domain baseline.
            transport.execute("""
            __mgtUpgradeQueries = 0
            __mgtUpgradeable = GetAllUpgradeableGodTraits
            GetAllUpgradeableGodTraits = function(...)
              __mgtUpgradeQueries = __mgtUpgradeQueries + 1
              return __mgtUpgradeable(...)
            end
            return '{}'
            """)
            first = session.status().payload
            assert transport.wire["__trainerObservation"]["retained"] == []
            assert transport.wire["__trainerObservation"]["generation"] == issued[0]
            assert transport.wire["__trainerObservation"]["revision"] == 1
            expected = copy.deepcopy(first)
            transport.execute("__mgtUpgradeQueries = 0; return '{}'")
            # Public replies may be mutated by their consumer; that cannot
            # rewrite the private localized baseline used on the next call.
            first["resources"][0]["count"] = 99999
            first["currentRunTraits"][0]["level"] = 99999
            first["currentRunTraits"][0]["availableRarities"].append("consumer-only")
            next_reply = session.mutate("set_vital", {"vital": "health", "field": "current", "value": 75}).payload
            assert next_reply["resources"] == expected["resources"]
            assert next_reply["currentRunTraits"] == expected["currentRunTraits"]
            assert next_reply["health"] == 75
            assert transport.wire["__trainerObservation"]["generation"] == issued[0] != issued[-1]
            assert set(transport.wire["__trainerObservation"]["retained"]) == {
                "resources", "elements", "currentRunTraits",
            }
            assert not {"resources", "elements", "currentRunTraits"} & inputs[-1]
            assert "__trainerObservation" not in next_reply
            assert transport.wire["__trainerObservation"]["revision"] == 2
            assert json.loads(transport.execute(
                "return '{\\\"count\\\":' .. tostring(__mgtUpgradeQueries) .. '}'"
            ))["count"] == 0

            # A Lua observation can complete after Python loses its reply. The
            # next acknowledged request must notice the revision gap and send a
            # fresh collection baseline instead of retaining unseen state.
            discarded = json.loads(transport.execute(
                "return __MacGamingTrainerV1.json(__MacGamingTrainerV1.observe("
                "'set_vital',{vital='health',field='current',value=76,includeCatalogs=false},"
                "'discarded',2))"
            ))
            assert discarded["__trainerObservation"]["revision"] == 3
            assert set(discarded["__trainerObservation"]["retained"]) == {
                "resources", "elements", "currentRunTraits",
            }
            recovered = session.mutate(
                "set_vital", {"vital": "health", "field": "current", "value": 77}
            ).payload
            assert recovered["health"] == 77
            assert transport.wire["__trainerObservation"]["revision"] == 4
            assert transport.wire["__trainerObservation"]["retained"] == []
            assert json.loads(transport.execute(
                "return '{\\\"count\\\":' .. tostring(__mgtUpgradeQueries) .. '}'"
            ))["count"] == 1
            transport.execute("__mgtUpgradeQueries = 0; return '{}'")

            # Native changes between requests remain observable even when an
            # unrelated command discovers them. Mutable values and bilingual
            # presentation are carried together for changed collections.
            transport.execute("CurrentRun.Hero.Traits[1].StackNum=7; CurrentRun.Hero.Traits[1].Rarity='Epic'; CurrentRun.Hero.Elements.Fire=9; GameState.Resources.MetaCurrency=555; return '{}'")
            changed = session.mutate("set_vital", {"vital": "health", "field": "current", "value": 80}).payload
            assert changed["currentRunTraits"][0]["level"] == 7
            assert changed["currentRunTraits"][0]["rarity"] == "Epic"
            assert changed["currentRunTraits"][0]["displayName"].startswith("zh-CN ")
            assert changed["currentRunTraits"][0]["englishName"].startswith("en ")
            assert next(row for row in changed["resources"] if row["id"] == "MetaCurrency")["count"] == 555
            assert next(row for row in changed["elements"] if row["id"] == "Fire")["count"] == 9
            assert {"resources", "elements", "currentRunTraits"} <= inputs[-1]
            assert json.loads(transport.execute(
                "return '{\\\"count\\\":' .. tostring(__mgtUpgradeQueries) .. '}'"
            ))["count"] == 1

            transport.execute("savedHero=CurrentRun.Hero; CurrentRun.Hero=nil; return '{}'")
            absent = session.mutate("set_resource", {"resource": "MetaCurrency", "amount": 556,
                "requestId": "absent-resource"}).payload
            assert absent["currentRunTraits"] == [] and not absent["capabilities"]["traitInventory"]
            assert transport.wire["__trainerObservation"]["retained"] == []
            transport.execute("CurrentRun.Hero=savedHero; savedHero.ObjectId=2; return '{}'")
            restored = session.mutate("set_vital", {"vital": "health", "field": "current", "value": 81}).payload
            assert len(restored["currentRunTraits"]) == 4
            assert transport.wire["__trainerObservation"]["retained"] == []
            # Status always reconstructs all dynamic collections, regardless
            # of an earlier patch sequence. Re-bootstrap creates a new epoch.
            session.status()
            assert transport.wire["__trainerObservation"]["retained"] == []
            old_generation = transport.wire["__trainerObservation"]["generation"]
            runtime = lua_value(str(ROOT / "Backend/games/hades2/runtime/hades.lua"))
            transport.execute("__MacGamingTrainerV1.dispatch('cleanup'); __MacGamingTrainerV1=nil; dofile("
                              + runtime + "); return '{}'")
            text_generation(2)
            replacement = session.status()
            assert replacement.generation_reset
            assert "boons" in replacement.payload and "rewards" in replacement.payload
            assert replacement.payload["currentRunTraits"][0]["displayName"].endswith("v2")
            session.invalidate_generation()
            fresh = session.status().payload
            assert len(fresh["currentRunTraits"]) == 4
            assert fresh["currentRunTraits"][0]["displayName"].endswith("v2")
            assert fresh["currentRunTraits"][0]["englishName"].endswith("v2")
            assert transport.wire["__trainerObservation"]["retained"] == []
            assert transport.wire["__trainerObservation"]["generation"] != old_generation
            # Force the allocator to reuse temporary addresses across repeated
            # installs. Each actual observed incarnation still owns a new UUID,
            # which is also the stale-selection identity of its returned rows.
            seen = {transport.wire["__trainerObservation"]["generation"]}
            for _ in range(30):
                transport.execute("__MacGamingTrainerV1.dispatch('cleanup'); __MacGamingTrainerV1=nil; "
                                  + "collectgarbage('collect'); dofile(" + runtime + "); return '{}'")
                replacement = session.status()
                token = transport.wire["__trainerObservation"]["generation"]
                assert replacement.generation_reset and token not in seen and token == issued[-1]
                assert replacement.payload["currentRunTraits"][0]["generationId"] == token
                seen.add(token)
    finally:
        session.close()

    # Missing retained-domain evidence after native execution cannot authorize
    # an automatic replay or a guessed result, even for an otherwise valid id.
    class MissingBaseline:
        pid, tainted, last_duration = 4242, False, 0.001
        calls = 0
        def execute(self, source, **kwargs):
            self.calls += 1
            return json.dumps({"__trainerObservation": {"generation": "new", "retained": ["resources"]}})

    missing = MissingBaseline()
    try:
        Hades2ResidentSession(missing).mutate("set_resource", {"resource": "MetaCurrency", "amount": 1})
    except ResidentSessionError as error:
        assert error.code == "outcome_unknown" and missing.tainted and missing.calls == 1
    else:
        raise AssertionError("missing collection evidence was accepted")

print("hades2_resident_observation_collections_ok")
