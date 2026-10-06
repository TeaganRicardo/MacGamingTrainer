import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "Backend"

original_home = os.environ.get("HOME")
with tempfile.TemporaryDirectory(prefix="mgt-backend-runtime-isolation-") as temporary:
    os.environ["HOME"] = temporary
    sys.path.insert(0, str(BACKEND))
    try:
        from core.registry import create_adapter

        adapter = create_adapter("hades2")
        try:
            metadata = adapter.metadata()
            assert metadata["id"] == "hades2"
            assert metadata["displayName"] == "Hades II"
        finally:
            adapter.close()
    finally:
        if original_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = original_home

print("hades2_backend_runtime_isolation_ok")
