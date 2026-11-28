"""The native action ledger and the mailbox preserve outcomes without optional state."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests/fixtures/hades2")]

from core.adapter import AdapterError
from games.hades2.adapter import Hades2Adapter
from games.hades2.mailbox import ERROR, OK, SUCCESS, Hades2CommandMailbox
from hades2_resident_session_fakes import FakeTimeWarpController, hades2_adapter_context
from offline_lua_transport import OfflineLuaTransport


class MailboxTransport:
    def __init__(self, resident):
        self.resident = resident
        self.pid = resident.pid
        self.tainted = False
        self.calls = 0
        self.mailbox = Hades2CommandMailbox.__new__(Hades2CommandMailbox)
        self.mailbox._clock = lambda: 0.0
        self.mailbox._mapping = None
        self.mailbox._pending_sequence = None
        self.mailbox._call = lambda *_args: OK
        self.mailbox.tainted = False

    def alive(self):
        return self.resident.alive()

    def execute(self, source, **kwargs):
        self.calls += 1
        reply = json.loads(self.resident.execute(source, **kwargs))
        result = reply["text"]
        receipt = SimpleNamespace(outcome=SUCCESS if reply["ok"] else ERROR,
                                  status=0 if reply["ok"] else 2,
                                  execution_ns=0, queue_ns=0, length=len(result.encode()))
        try:
            return self.mailbox._finish(self.calls, (receipt, result), 0.0, len(source.encode()))
        finally:
            self.tainted |= self.mailbox.tainted

    def acknowledge_result(self):
        self.mailbox.acknowledge()


class ActionObservationTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory(prefix="mgt-action-observation-"))
        self.context = hades2_adapter_context(temporary)
        self.enterContext(patch.dict(os.environ, {
            "MGT_PROFILE_EVENTS": str(Path(temporary) / "resident.log"),
            "MGT_PROFILE_TRAITS": "1", "MGT_PROFILE_CATALOG": "2", "MGT_PROFILE_RESOURCES": "2",
            "MGT_PROFILE_OPERATIONS": "0",
        }))

    def resident(self):
        fixture = OfflineLuaTransport(mailbox_receipts=True)
        self.addCleanup(fixture.close)
        self.lua(fixture, """
            local spawn = SpawnObstacle
            fixtureEffects = 0
            SpawnObstacle = function(...)
              fixtureEffects = fixtureEffects + 1
              CurrentRun.Hero.Health = CurrentRun.Hero.Health - 10
              return spawn(...)
            end
            return '{}'
        """)
        return fixture

    @staticmethod
    def lua(fixture, source):
        reply = json.loads(fixture.execute(source))
        assert reply["ok"], reply["text"]
        return json.loads(reply["text"])

    def adapter(self, transport, identity="fixture-game"):
        return Hades2Adapter(context=self.context, transport=transport,
                             time_warp_controller=FakeTimeWarpController(), identity=lambda _pid: identity)

    @staticmethod
    def reward(adapter, request_id="first", reward="MetaCurrencyDrop"):
        return adapter.execute("spawn_reward", {"reward": reward, "requestId": request_id})

    def test_preflight_refusal_and_normal_action(self):
        fixture = self.resident()
        transport = MailboxTransport(fixture)
        adapter = self.adapter(transport)
        with self.assertRaises(AdapterError) as raised:
            self.reward(adapter, reward="not-a-reward")
        self.assertEqual(raised.exception.code, "lua_error")
        self.assertIsNone(adapter.recovery.read())
        self.assertIsNone(transport.mailbox._pending_sequence)
        self.assertEqual(self.lua(fixture, "return tostring(fixtureEffects)"), 0)

        reply = self.reward(adapter)
        self.assertEqual(reply["lastAction"]["outcome"], "completed")
        self.assertEqual(reply["health"], 90)
        self.assertEqual(self.lua(fixture, "return tostring(fixtureEffects)"), 1)

    def test_receipt_survives_state_build_and_serialization_errors(self):
        for fault in ("state", "json"):
            with self.subTest(fault=fault):
                fixture = self.resident()
                transport = MailboxTransport(fixture)
                adapter = self.adapter(transport)
                self.assertEqual(adapter.observe_runtime()["health"], 100)
                self.lua(fixture, """
                    local M = __MacGamingTrainerV1
                    local fingerprint, json = M.observationRetention.resourceFingerprint, M.json
                    M.observationRetention.resourceFingerprint = function(...)
                      if fixtureEffects > 0 and "%s" == "state" then
                        M.observationRetention.resourceFingerprint = fingerprint
                        error("instrumented post-action state failure")
                      end
                      return fingerprint(...)
                    end
                    M.json = function(value)
                      if value.requestId and value.__trainerObservation and "%s" == "json" then
                        error("instrumented action observation encode failure")
                      end
                      return json(value)
                    end
                    return '{}'
                """ % (fault, fault))
                with self.assertRaises(AdapterError) as raised:
                    self.reward(adapter)
                self.assertEqual(raised.exception.code, "action_observation_failed")
                self.assertIn("instrumented", raised.exception.diagnostic)
                state = adapter.state_for_error()
                self.assertEqual(state["lastAction"]["outcome"], "completed")
                self.assertEqual(state["lastAction"]["requestId"], "first")
                self.assertEqual(state["health"], 100, "partial reply was treated as a full observation")
                self.assertFalse(transport.tainted)
                self.assertIsNone(transport.mailbox._pending_sequence)
                self.assertIsNone(adapter.recovery.read())

                restarted = self.adapter(MailboxTransport(fixture))
                self.assertEqual(restarted.observe_runtime()["health"], 90)
                try:
                    duplicate = self.reward(restarted)
                except AdapterError as error:
                    self.assertEqual(error.code, "action_observation_failed")
                    duplicate = restarted.state_for_error()
                self.assertTrue(duplicate["duplicate"])
                self.assertEqual(duplicate["actionOutcome"], "completed")
                self.assertEqual(self.lua(fixture, "return tostring(fixtureEffects)"), 1)

    def test_unencodable_receipt_blocks_same_lifetime_after_backend_restart(self):
        fixture = self.resident()
        transport = MailboxTransport(fixture)
        adapter = self.adapter(transport)
        adapter.observe_runtime()
        self.lua(fixture, """
            local M = __MacGamingTrainerV1
            local json = M.json
            M.json = function(value)
              if value.requestId then error("instrumented action receipt encode failure") end
              return json(value)
            end
            return '{}'
        """)
        with self.assertRaises(AdapterError) as raised:
            self.reward(adapter)
        self.assertEqual(raised.exception.code, "outcome_unknown")
        self.assertTrue(transport.tainted)
        self.assertIsNotNone(transport.mailbox._pending_sequence)
        self.assertEqual(self.lua(fixture, "return tostring(fixtureEffects)"), 1)
        self.assertTrue(self.lua(fixture, "return tostring(__MacGamingTrainerV1.terminalActionUnknown)"))
        pending = adapter.recovery.read()["requests"][0]
        self.assertEqual((pending["requestId"], pending["outcome"]), ("first", "unknown"))

        same_lifetime = MailboxTransport(fixture)
        with self.assertRaises(AdapterError) as restarted:
            self.reward(self.adapter(same_lifetime), request_id="second")
        self.assertEqual(restarted.exception.code, "outcome_unknown")
        self.assertEqual(same_lifetime.calls, 0)
        self.assertEqual(self.lua(fixture, "return tostring(fixtureEffects)"), 1)

        new_resident = self.resident()
        fresh = self.adapter(MailboxTransport(new_resident), identity="new-game-with-same-pid")
        self.assertEqual(self.reward(fresh, request_id="fresh")["actionOutcome"], "completed")
        self.assertEqual(self.lua(new_resident, "return tostring(fixtureEffects)"), 1)
        self.assertIsNone(fresh.recovery.read())


if __name__ == "__main__":
    unittest.main()
