from pathlib import Path
import logging
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from games.hades2.command_router import Hades2CommandRouter


class RouterHarnessAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id="hades2",
            display_name="Hades II",
            module_protocol_version=5,
            module_dir=ROOT / "Backend/games/hades2",
            public_metadata={},
        ))
        self.state = {"connected": False, "scene": "test"}
        self.command_router = Hades2CommandRouter(self)
        self.mutation_called = False

    def dispatch(self, command, params, request_id):
        return self.command_router.dispatch(command, params, request_id)

    def set_desired(self, feature, value):
        self.mutation_called = True
        raise AssertionError("invalid desired feature reached mutation")

    def execute(self, command, params):
        self.mutation_called = True
        raise AssertionError("invalid element reached mutation")

    def close(self):
        pass


temporary_root = tempfile.TemporaryDirectory(prefix="mgt-hades2-host-errors-")
adapter = RouterHarnessAdapter()
router = JsonlRequestRouter(adapter, save_data_root=Path(temporary_root.name))

cases = (
    (
        {"id": "feature-list", "command": "set_desired", "params": {"feature": [], "value": True}},
        "未知功能。",
    ),
    (
        {"id": "feature-object", "command": "set_desired", "params": {"feature": {}, "value": True}},
        "未知功能。",
    ),
    (
        {"id": "element-list", "command": "set_element", "params": {"element": [], "amount": 1}},
        "未知元素。",
    ),
    (
        {"id": "element-object", "command": "set_element", "params": {"element": {}, "amount": 1}},
        "未知元素。",
    ),
)

logging.disable(logging.CRITICAL)
try:
    for request, message in cases:
        reply = router.handle(request)
        assert reply["ok"] is False, request["id"]
        assert reply["error"] == {"code": "invalid_request", "message": message}, request["id"]
finally:
    logging.disable(logging.NOTSET)
    router.close()
    temporary_root.cleanup()

assert adapter.mutation_called is False

print("hades2_host_error_semantics_ok")
