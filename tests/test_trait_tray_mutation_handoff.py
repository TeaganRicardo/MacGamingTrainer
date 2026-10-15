"""Actual resident handoff closes a synthetic Trait Tray before one mutation."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests"), str(ROOT / "Tools/fixtures")]
from games.hades2 import resident_session
from games.hades2.resident_session import Hades2ResidentSession, TransportError, lua_value


@contextmanager
def fixture(active, close_after=1):
    with tempfile.TemporaryDirectory(prefix="mgt-trait-tray-") as temporary, patch.dict(os.environ, {
        "MGT_PROFILE_EVENTS": str(Path(temporary) / "events.log"),
        "MGT_PROFILE_TRAITS": "2", "MGT_PROFILE_CATALOG": "4", "MGT_PROFILE_RESOURCES": "4",
        "MGT_PROFILE_OPERATIONS": "0",
    }), patch.object(resident_session, "localize_catalog", side_effect=lambda value: value):
        from hades2_profile_backend import OfflineLuaTransport

        class Transport(OfflineLuaTransport):
            def __init__(self):
                super().__init__()
                self.sources = []
            def execute(self, source, **kwargs):
                self.sources.append(source)
                # One explicit synthetic engine boundary advances native close.
                source = """if fixtureCloseRequested then
                  fixturePostClose = fixturePostClose + 1
                  if fixtureCloseAfter and fixturePostClose >= fixtureCloseAfter then
                    ActiveScreens.TraitTrayScreen = nil
                  end
                end;
                """ + source
                return super().execute(source, **kwargs)

        transport = Transport()
        session = Hades2ResidentSession(transport)
        transport.execute("""
          fixtureMutations, fixtureBatches, fixtureCloseRequests, fixturePostClose = 0,0,0,0
          fixtureCloseRequested = false
          fixtureCloseAfter = """ + lua_value(close_after) + ";" + """
          local dispatch, batch = __MacGamingTrainerV1.dispatch, __MacGamingTrainerV1.dispatchBatch
          __MacGamingTrainerV1.dispatch = function(command, params)
            if command ~= 'status' then fixtureMutations = fixtureMutations + 1 end
            return dispatch(command, params)
          end
          __MacGamingTrainerV1.dispatchBatch = function(calls, catalogs)
            fixtureBatches = fixtureBatches + 1
            return batch(calls, catalogs)
          end
          thread = function(work, screen) work(screen) end
          TraitTrayScreenClose = function(screen)
            fixtureCloseRequests = fixtureCloseRequests + 1
            fixtureCloseRequested, screen.Closing = true, true
          end
          ActiveScreens.TraitTrayScreen = """ + ("{}" if active else "nil") + "; return '{}'")
        transport.sources.clear()
        try:
            yield session, transport
        finally:
            session.close()


def stats(transport):
    return json.loads(transport.execute("""return __MacGamingTrainerV1.json({
      mutations=fixtureMutations, batches=fixtureBatches, closes=fixtureCloseRequests,
      active=ActiveScreens.TraitTrayScreen~=nil,
      health=CurrentRun.Hero.Health, mana=CurrentRun.Hero.Mana })"""))


def edit(session, value=42):
    return session.mutate("set_vital", {"vital": "health", "field": "current", "value": value})


with fixture(False) as (session, transport):
    edit(session)
    assert len(transport.sources) == 1
    observed = stats(transport)
    assert observed['mutations'] == 1 and observed['health'] == 42 and observed['closes'] == 0

with fixture(True) as (session, transport):
    reply = edit(session)
    assert reply.payload['health'] == 42 and len(transport.sources) == 2
    observed = stats(transport)
    assert observed['mutations'] == 1 and observed['closes'] == 1 and not observed['active']

with fixture(True) as (session, transport):
    session.observe_status()
    assert len(transport.sources) == 1
    observed = stats(transport)
    assert observed['active'] and observed['closes'] == 0 and observed['mutations'] == 0

with fixture(True) as (session, transport):
    reply = session.reconcile([
        ('set_vital', {'vital': 'health', 'field': 'current', 'value': 80}),
        ('set_vital', {'vital': 'mana', 'field': 'current', 'value': 40}),
    ])
    assert len(transport.sources) == 2 and reply.payload['health'] == 80
    observed = stats(transport)
    assert observed['batches'] == 1 and observed['mutations'] == 2 and observed['closes'] == 1
    assert observed['health'] == 80 and observed['mana'] == 40

with fixture(True, None) as (session, transport), patch.object(
    resident_session, '_TRAIT_TRAY_HANDOFF_TIMEOUT_SECONDS', 0.02,
), patch.object(resident_session, '_TRAIT_TRAY_HANDOFF_POLL_SECONDS', 0.005):
    try:
        edit(session)
    except TransportError as error:
        assert error.code == 'waiting'
    else:
        raise AssertionError('stale Trait Tray ownership was allowed to mutate')
    observed = stats(transport)
    assert observed['active'] and observed['closes'] == 1 and observed['mutations'] == 0

print('trait_tray_mutation_handoff_ok')
