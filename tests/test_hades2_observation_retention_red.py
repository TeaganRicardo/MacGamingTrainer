"""Temporary #470 RED: expose post-cross observation reconstruction cause."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "Backend"), str(ROOT / "tests"), str(ROOT / "Tools/fixtures")]

from games.hades2.resident_session import Hades2ResidentSession

with tempfile.TemporaryDirectory(prefix="mgt-470-red-") as temporary, patch.dict(os.environ, {
    "MGT_PROFILE_EVENTS": str(Path(temporary) / "events.log"),
    "MGT_PROFILE_TRAITS": "8",
    "MGT_PROFILE_CATALOG": "16",
    "MGT_PROFILE_RESOURCES": "8",
    "MGT_PROFILE_OPERATIONS": "0",
}):
    from hades2_profile_backend import OfflineLuaTransport

    transport = OfflineLuaTransport()
    session = Hades2ResidentSession(transport)
    try:
        session.status()
        for _ in range(3):
            session.status()
        reply = session.mutate("set_resource", {
            "resource": "MetaCurrency",
            "amount": 101,
            "requestId": "profile-resource-red",
        })
        row = next(item for item in reply.payload["resources"] if item["id"] == "MetaCurrency")
        assert row["count"] == 101 and not transport.tainted
    finally:
        session.close()

print("hades2_observation_retention_red_ok")
