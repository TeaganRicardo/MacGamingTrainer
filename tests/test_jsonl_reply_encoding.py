"""The wire boundary encodes one immutable reply for delivery and replay."""
import json
import logging
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapter, GameAdapterContext
from core.protocol import HOST_PROTOCOL_VERSION, JsonlRequestRouter
from core.server import process_line


class PayloadAdapter(GameAdapter):
    def __init__(self, size):
        super().__init__(GameAdapterContext(
            game_id="encoding_fixture", display_name="Encoding Fixture",
            module_protocol_version=3, module_dir=ROOT, public_metadata={},
        ))
        self.result = {"text": "雪 λ", "values": list(range(size))}
        self.calls = 0

    def dispatch(self, command, params, request_id):
        self.calls += 1
        if command == "nonfinite":
            return {"value": float("nan")}
        return self.result

    def close(self):
        pass


with tempfile.TemporaryDirectory(prefix="mgt-reply-encoding-") as temporary:
    for size in (2, 50000):
        adapter = PayloadAdapter(size)
        router = JsonlRequestRouter(adapter, save_data_root=Path(temporary) / str(size))
        request = json.dumps({"id": "one-shot", "command": "payload", "params": {}})
        original_dumps = json.dumps
        response_encodes = []

        def count_response_encodes(value, *args, **kwargs):
            # The request fingerprint is separate. Count every traversal of
            # the successful response body, including pre-validation copies.
            if value is adapter.result or (isinstance(value, dict) and "result" in value):
                response_encodes.append(value)
            return original_dumps(value, *args, **kwargs)

        with patch("json.dumps", side_effect=count_response_encodes):
            first = process_line(router, request)
            assert len(response_encodes) == 1, len(response_encodes)
            decoded = json.loads(first)
            assert decoded["result"] == adapter.result
            assert decoded["protocolVersion"] == HOST_PROTOCOL_VERSION
            assert decoded["gameID"] == "encoding_fixture" and decoded["moduleProtocolVersion"] == 3
            decoded["result"]["values"].append(-1)
            adapter.result["values"].append(-2)
            assert process_line(router, request) == first
            assert adapter.calls == 1 and len(response_encodes) == 1

        conflict = json.loads(process_line(router, json.dumps({
            "id": "one-shot", "command": "payload", "params": {"different": True},
        })))
        assert conflict["error"]["code"] == "duplicate_conflict" and adapter.calls == 1
        invalid = json.dumps({"id": "bad-result", "command": "nonfinite", "params": {}})
        logging.disable(logging.CRITICAL)
        try:
            error = process_line(router, invalid)
            assert process_line(router, invalid) == error
        finally:
            logging.disable(logging.NOTSET)
        failure = json.loads(error)
        assert failure["id"] == "bad-result" and failure["error"]["code"] == "operation_failed"
        assert "non-JSON-safe" in failure["error"]["diagnostic"]
        assert adapter.calls == 2

print("jsonl_reply_encoding_ok")
