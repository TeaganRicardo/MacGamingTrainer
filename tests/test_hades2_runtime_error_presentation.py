import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError, GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from games.hades2.command_contract import Hades2CommandContract


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
        self.command_contract = Hades2CommandContract(self)

    def dispatch(self, command, params, request_id):
        return self.command_contract.dispatch(command, params, request_id)

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

# Player-facing copy is a language-neutral key; the Lua source text stays on the
# diagnostic, so the operator trace is unchanged and the wire is not localized.
cases = (
    (
        {"id": "sell-screen-active", "command": "open_sell_traits", "params": {}},
        "hades2.error.sellScreenBusy",
        '[string "MacGamingTrainer"]:3086: Cannot open boon sell screen while another screen is active',
    ),
    (
        {"id": "special-screen-active", "command": "open_special_choice", "params": {"source": "Artemis"}},
        "hades2.error.choiceScreenBusy",
        '[string "MacGamingTrainer"]:3131: Cannot open special blessing choice while another screen is active',
    ),
    (
        {"id": "generic-lua-error", "command": "set_desired", "params": {"feature": "invincibility", "value": True}},
        "hades2.error.runtimeActionFailed",
        '[string "MacGamingTrainer"]:2999: Feature unavailable: synthetic runtime failure',
    ),
)

logging.disable(logging.CRITICAL)
try:
    for request, expected, diagnostic in cases:
        reply = router.handle(request)
        assert reply["ok"] is False, request["id"]
        assert reply["error"] == {
            "code": "lua_error",
            "presentation": expected,
            "diagnostic": diagnostic,
        }, reply["error"]
        assert "message" not in reply["error"]
        # Lua source locations and English runtime text must never reach the UI.
        assert "[string " not in reply["error"]["presentation"]
        assert "Cannot open" not in reply["error"]["presentation"]
        assert not any("一" <= character <= "鿿" for character in reply["error"]["presentation"])
finally:
    logging.disable(logging.NOTSET)
    router.close()
    temporary_root.cleanup()

print("hades2_runtime_error_presentation_ok")
