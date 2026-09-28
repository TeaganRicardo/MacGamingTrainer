import logging
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapter, GameAdapterContext
from core.protocol import JsonlRequestRouter
from games.hades2 import error_presentation
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
        "hades2.error.unknownFeature",
    ),
    (
        {"id": "feature-object", "command": "set_desired", "params": {"feature": {}, "value": True}},
        "hades2.error.unknownFeature",
    ),
    (
        {"id": "element-list", "command": "set_element", "params": {"element": [], "amount": 1}},
        "hades2.error.unknownElement",
    ),
    (
        {"id": "element-object", "command": "set_element", "params": {"element": {}, "amount": 1}},
        "hades2.error.unknownElement",
    ),
)

logging.disable(logging.CRITICAL)
try:
    for request, message in cases:
        reply = router.handle(request)
        assert reply["ok"] is False, request["id"]
        error = reply["error"]
        # Player-facing copy is a language-neutral key; the readable text stays
        # on the diagnostic so the operator trace is unchanged.
        assert error["code"] == "invalid_request", request["id"]
        assert error["presentation"] == message, request["id"]
        assert error["diagnostic"], request["id"]
        assert not any("一" <= character <= "鿿" for character in error["presentation"]), (
            request["id"]
        )
finally:
    logging.disable(logging.NOTSET)
    router.close()
    temporary_root.cleanup()

assert adapter.mutation_called is False

# A key that needs values must carry them to the Host. Producing arguments in
# the module is not enough: if the envelope drops them, the shipped template
# renders with holes, which is worse than the text it replaced. So assert both
# halves — the envelope carries a list, and the mapper supplies exactly as many
# values as the templates have placeholders.
import json as _json
import re as _re

_TABLES = {
    language: _json.loads(
        (ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json").read_text(encoding="utf-8")
    )["entries"]
    for language in ("zh-CN", "en")
}
_PROBES = {
    "hades2.error.gameNotRunning": "请先启动 Hades II 并进入存档。",
    "hades2.error.processQueryFailed": "查询 Hades II 进程失败（-9）：boom",
}
for _key, _message in _PROBES.items():
    _mapped, _arguments = error_presentation.presentation_for(_message)
    assert _mapped == _key, (_message, _mapped)
    for _language, _entries in _TABLES.items():
        _needed = max(int(index) for index in _re.findall(r"\{(\d+)\}", _entries[_key])) + 1
        assert len(_arguments) == _needed, (_key, _language, _needed, _arguments)
        # Every placeholder must be consumed, or the UI shows a literal {n}.
        _rendered = _entries[_key]
        for _index, _value in enumerate(_arguments):
            _rendered = _rendered.replace("{%d}" % _index, _value)
        assert not _re.search(r"\{\d+\}", _rendered), (_key, _language, _rendered)

# The envelope field is Core-owned and optional: an error without arguments must
# not gain an empty list on the wire, and one with arguments must keep them.
_json_router = JsonlRequestRouter(adapter, save_data_root=Path(temporary_root.name))
_carries = _json_router.error_reply("probe", "invalid_request", "hades2.error.gameNotRunning",
                                    arguments=["Hades II"])
assert _carries["error"]["arguments"] == ["Hades II"], _carries["error"]
_bare = _json_router.error_reply("probe", "invalid_request", "hades2.error.unknownFeature")
assert "arguments" not in _bare["error"], _bare["error"]

print("hades2_host_error_semantics_ok")
