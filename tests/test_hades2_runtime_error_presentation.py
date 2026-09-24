import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from games.hades2.command_router import Hades2CommandRouter


class RuntimeErrorHarnessAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id="hades2",
            display_name="Hades II",
            module_protocol_version=5,
            module_dir=ROOT / "Backend/games/hades2",
            public_metadata={},
        ))
        self.state = {"connected": True, "scene": "run"}
        self.command_router = Hades2CommandRouter(self)

    def dispatch(self, command, params, request_id):
        return self.command_router.dispatch(command, params, request_id)

    def set_desired(self, feature, value):
        raise AdapterError(
            "lua_error",
            '[string "MacGamingTrainer"]:2999: Feature unavailable: synthetic runtime failure',
        )

    def execute(self, command, params):
        messages = {
            "open_sell_traits": '[string "MacGamingTrainer"]:3086: Cannot open boon sell screen while another screen is active',
            "open_special_choice": '[string "MacGamingTrainer"]:3131: Cannot open special blessing choice while another screen is active',
        }
        raise AdapterError("lua_error", messages[command])

    def close(self):
        pass


temporary_root = tempfile.TemporaryDirectory(prefix="mgt-hades2-runtime-error-presentation-")
adapter = RuntimeErrorHarnessAdapter()
router = JsonlRequestRouter(adapter, save_data_root=Path(temporary_root.name))

cases = (
    (
        {"id": "sell-screen-active", "command": "open_sell_traits", "params": {}},
        "已有游戏界面打开，请先关闭当前界面后再打开净化之池。",
    ),
    (
        {"id": "special-screen-active", "command": "open_special_choice", "params": {"source": "Artemis"}},
        "已有游戏界面打开，请先关闭当前界面后再打开奖励选择界面。",
    ),
    (
        {"id": "generic-lua-error", "command": "set_desired", "params": {"feature": "godMode", "value": True}},
        "游戏内操作失败，请查看日志。",
    ),
)

logging.disable(logging.CRITICAL)
try:
    for request, expected in cases:
        reply = router.handle(request)
        assert reply["ok"] is False, request["id"]
        assert reply["error"] == {"code": "lua_error", "message": expected}, reply["error"]
        assert "[string " not in reply["error"]["message"]
        assert "Cannot open" not in reply["error"]["message"]
finally:
    logging.disable(logging.NOTSET)
    router.close()
    temporary_root.cleanup()

print("hades2_runtime_error_presentation_ok")
