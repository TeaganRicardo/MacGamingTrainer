from pathlib import Path
import contextlib
import io
import json
import logging
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapter, GameAdapterContext
from core import server
from games.hades2.preferences import Hades2PreferenceStore


class StartupAdapter(GameAdapter):
    def __init__(self, data_dir: Path):
        super().__init__(GameAdapterContext(
            game_id="startup_fixture",
            display_name="Startup Fixture",
            module_protocol_version=1,
            module_dir=ROOT,
            public_metadata={
                "id": "startup_fixture",
                "displayName": "Startup Fixture",
                "protocolVersion": 1,
            },
        ))
        self.data_dir = data_dir
        self.state = {"connected": False}
        self.closed = False

    def dispatch(self, command, params, request_id):
        return {"command": command, "requestId": request_id}

    def close(self):
        self.closed = True


root_logger = logging.getLogger()
original_handlers = list(root_logger.handlers)
original_level = root_logger.level
original_factory = server.create_adapter
original_available_games = server.available_games
original_stdin = sys.stdin

with tempfile.TemporaryDirectory(prefix="mgt-backend-startup-log-") as td:
    temp_root = Path(td)
    data_dir = temp_root / "data"
    data_dir.mkdir()
    desired = temp_root / "desired-state.json"
    desired.write_text("{ definitely not valid json", encoding="utf-8")

    unrelated_output = io.StringIO()
    unrelated_handler = logging.StreamHandler(unrelated_output)
    unrelated_handler.setFormatter(logging.Formatter("UNRELATED %(levelname)s %(message)s"))
    root_logger.addHandler(unrelated_handler)
    root_logger.setLevel(logging.WARNING)

    created = []

    def create_startup_adapter(game_id):
        assert game_id == "startup_fixture"
        logging.warning("startup fixture constructor warning")
        Hades2PreferenceStore(desired).load()
        adapter = StartupAdapter(data_dir)
        created.append(adapter)
        return adapter

    server.available_games = lambda: [{"id": "startup_fixture"}]
    server.create_adapter = create_startup_adapter
    sys.stdin = io.StringIO(json.dumps({
        "id": "ping-1",
        "command": "ping",
        "params": {},
    }) + "\n")

    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            server.main(["--game", "startup_fixture"])
    finally:
        server.create_adapter = original_factory
        server.available_games = original_available_games
        sys.stdin = original_stdin

    log_path = data_dir / "trainer.log"
    assert log_path.is_file(), "server startup must create its own trainer.log even when root already has a handler"
    log_text = log_path.read_text(encoding="utf-8")
    assert "startup fixture constructor warning" in log_text
    assert "Quarantined invalid desired-state profile" in log_text
    assert "request ping-1 ping success game=startup_fixture" in log_text
    assert log_text.count("startup fixture constructor warning") == 1

    reply = json.loads(stdout.getvalue().strip())
    assert reply["ok"] is True
    assert reply["id"] == "ping-1"
    assert created and created[0].closed is True

    assert unrelated_handler in root_logger.handlers, "worker logging must preserve unrelated handlers"
    assert unrelated_output.getvalue().count("startup fixture constructor warning") == 1

# Restore the process-global logger after the test even if the server owns its
# own handler during main().
for handler in list(root_logger.handlers):
    if handler not in original_handlers:
        root_logger.removeHandler(handler)
        if handler is not unrelated_handler:
            handler.close()
root_logger.handlers[:] = original_handlers
root_logger.setLevel(original_level)

print("backend_startup_logging_ok")
