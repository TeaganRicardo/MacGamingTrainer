import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core import server
from core.adapter import GameAdapter, GameAdapterContext

MAX_LINE_BYTES = 65536
OVERSIZED_LINE_BYTES = 8 * 1024 * 1024


class NoNewlineReader:
    """Generate a huge unterminated line without storing it in the test."""

    def __init__(self):
        self.buffer = self
        self.bytes_read = 0
        self.read_sizes = []

    def readline(self, size=-1):
        self.read_sizes.append(size)
        if self.bytes_read >= OVERSIZED_LINE_BYTES:
            return b""
        amount = OVERSIZED_LINE_BYTES - self.bytes_read
        if size >= 0:
            amount = min(amount, size)
        self.bytes_read += amount
        return b"x" * amount

    def __iter__(self):
        return self

    def __next__(self):
        line = self.readline()
        if not line:
            raise StopIteration
        return line.decode("ascii")


class RecordedBytesReader:
    def __init__(self, payload):
        self.stream = io.BytesIO(payload)
        self.buffer = self
        self.read_sizes = []

    def readline(self, size=-1):
        self.read_sizes.append(size)
        return self.stream.readline(size)


class InputAdapter(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext(
            game_id="bounded_input_fixture",
            display_name="Bounded Input Fixture",
            module_protocol_version=1,
            module_dir=ROOT,
            public_metadata={"id": "bounded_input_fixture", "protocolVersion": 1},
        ))
        self.closed = False

    def dispatch(self, command, params, request_id):
        raise AssertionError("oversized input must never reach command dispatch")

    def close(self):
        self.closed = True


old_stdin = sys.stdin
old_home = os.environ.get("HOME")
old_create_adapter = server.create_adapter
old_available_games = server.available_games
root_logger = server.logging.getLogger()
old_handlers = list(root_logger.handlers)
old_level = root_logger.level

with tempfile.TemporaryDirectory(prefix="mgt-bounded-jsonl-input-") as td:
    home = Path(td) / "home"
    home.mkdir()
    os.environ["HOME"] = str(home)
    reader = NoNewlineReader()
    adapter = InputAdapter()
    server.available_games = lambda: [{"id": "bounded_input_fixture"}]
    server.create_adapter = lambda game_id: adapter
    sys.stdin = reader
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            server.main(["--game", "bounded_input_fixture"])

        def run_bytes(payload):
            next_reader = RecordedBytesReader(payload)
            sys.stdin = next_reader
            next_adapter = InputAdapter()
            server.create_adapter = lambda game_id: next_adapter
            next_stdout = io.StringIO()
            with contextlib.redirect_stdout(next_stdout):
                server.main(["--game", "bounded_input_fixture"])
            assert next_adapter.closed
            assert all(0 < size <= MAX_LINE_BYTES + 1 for size in next_reader.read_sizes)
            return [json.loads(line) for line in next_stdout.getvalue().splitlines()]

        # Discard an oversized record in bounded chunks, then parse the next
        # record on the same stream rather than treating its tail as JSON.
        valid_request = b'{"id":"after","command":"hello"}\n'
        next_replies = run_bytes(b"x" * (MAX_LINE_BYTES + 100) + b"\n" + valid_request)
        assert len(next_replies) == 2, next_replies
        assert next_replies[0]["error"]["code"] == "invalid_request"
        assert next_replies[1]["ok"] is True and next_replies[1]["id"] == "after"

        # EOF does not produce a phantom reply; a valid final record without a
        # newline still receives one, as does a truncated invalid record.
        assert run_bytes(b"") == []
        assert [reply["id"] for reply in run_bytes(valid_request[:-1])] == ["after"]
        truncated = run_bytes(b'{"id":')
        assert len(truncated) == 1 and truncated[0]["error"]["code"] == "invalid_request"

        # The newline counts toward the 65536-byte limit, not just JSON text.
        base = b'{"id":"exact","command":"hello"}'
        exact = base + b" " * (MAX_LINE_BYTES - len(base) - 1) + b"\n"
        assert len(exact) == MAX_LINE_BYTES
        exact_replies = run_bytes(exact + valid_request)
        assert [reply["id"] for reply in exact_replies] == ["exact", "after"]
        assert all(reply["ok"] for reply in exact_replies)
        too_long = run_bytes(exact[:-1] + b" \n" + valid_request)
        assert len(too_long) == 2 and too_long[0]["error"]["code"] == "invalid_request"
        assert too_long[1]["id"] == "after" and too_long[1]["ok"] is True

        unicode_record = b'{"id":"unicode","command":"hello","params":{"pad":"' + "汉".encode() * 21845 + b'"}}\n'
        assert len(unicode_record) > MAX_LINE_BYTES
        unicode_replies = run_bytes(unicode_record + valid_request)
        assert len(unicode_replies) == 2 and unicode_replies[0]["error"]["code"] == "invalid_request"
        assert unicode_replies[1]["id"] == "after" and unicode_replies[1]["ok"] is True

        malformed_replies = run_bytes(b'{not json}\n' + valid_request)
        assert len(malformed_replies) == 2 and malformed_replies[0]["error"]["code"] == "invalid_request"
        assert malformed_replies[1]["id"] == "after" and malformed_replies[1]["ok"] is True
    finally:
        sys.stdin = old_stdin
        server.create_adapter = old_create_adapter
        server.available_games = old_available_games
        root_logger.handlers[:] = old_handlers
        root_logger.setLevel(old_level)
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home

    assert reader.bytes_read == OVERSIZED_LINE_BYTES
    assert reader.read_sizes and all(0 < size <= MAX_LINE_BYTES + 1 for size in reader.read_sizes), (
        f"server must drain an unterminated record using bounded reads, got {reader.read_sizes}"
    )
    replies = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert len(replies) == 1 and replies[0]["ok"] is False
    assert replies[0]["error"]["code"] == "invalid_request"
    assert adapter.closed

print("server_bounded_jsonl_input_ok")
