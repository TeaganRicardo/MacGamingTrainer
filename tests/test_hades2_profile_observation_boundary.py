"""Temporary #470 RED: expose the retained resource mutation decode cause."""
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
        first = session.status().payload
        assert len(first["resources"]) >= 2
        for _ in range(3):
            session.status()
        edited = session.mutate(
            "set_resource", {"resource": "MetaCurrency", "amount": 101,
                             "requestId": "resource-retention-boundary"}
        ).payload
        assert next(row for row in edited["resources"]
                    if row["id"] == "MetaCurrency")["count"] == 101
        assert not transport.tainted
    finally:
        session.close()

print("hades2_profile_observation_boundary_ok")
