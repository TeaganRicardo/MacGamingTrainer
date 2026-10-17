#!/usr/bin/env python3
"""Game-agnostic JSONL host. Game behavior lives under Backend/games/<game_id>."""
import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.operation_profile import correlation, operation, record
from core.protocol import JsonlRequestRouter
from core.registry import available_games, create_adapter

_LOG_FORMAT = '%(levelname)s %(message)s'


class _BackendLoggingSession:
    """Forward backend diagnostics through stderr; Host owns persistence/retention."""

    def __init__(self):
        self.root = logging.getLogger()
        self.original_level = self.root.level
        self.handler = logging.StreamHandler(sys.stderr)
        self.handler.setLevel(logging.INFO)
        self.handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        self.root.addHandler(self.handler)
        if self.root.level > logging.INFO:
            self.root.setLevel(logging.INFO)

    def close(self):
        if self.handler in self.root.handlers:
            self.root.removeHandler(self.handler)
        self.handler.close()
        self.root.setLevel(self.original_level)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--game', default=os.environ.get('MGT_GAME_ID'))
    return parser.parse_args(argv)


def encode_reply(router, reply):
    """Serialize one response without allowing a bad module result to kill the host."""
    try:
        return router.encode_reply(reply)
    except Exception:
        logging.exception('Backend reply serialization failed')
        fallback = router.core_error_reply(
            None,
            'protocol_error',
            'backend reply could not be serialized as strict JSON',
        )
        return router.encode_reply(fallback)


def process_line(router, line):
    """One ordinary JSONL record, shared by the server and offline probes."""
    started = time.perf_counter()
    request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('非有限 JSON 数值：' + value)))
    decode = time.perf_counter() - started
    identity = request.get('id') if isinstance(request, dict) else None
    command = request.get('command', '') if isinstance(request, dict) else ''
    with operation(identity, command):
        if correlation() is not None:
            record('backend.request_decode', decode,
                   request_bytes=len(line.encode('utf-8')) if isinstance(line, str) else len(line))
        encoded = router.handle_encoded(request)
        if correlation() is not None:
            record('backend.reply_ready', 0.0,
                   reply_bytes=len(encoded.encode('utf-8')) + 1)
        return encoded


def main(argv=None):
    args = parse_args(argv)
    games = available_games()
    if args.game:
        game_id = args.game
    elif len(games) == 1:
        game_id = games[0]['id']
    elif not games:
        raise RuntimeError('没有安装任何游戏模块。')
    else:
        raise RuntimeError('检测到多个游戏模块；必须使用 --game 明确选择。')

    logging_session = _BackendLoggingSession()
    router = None
    try:
        try:
            adapter = create_adapter(game_id)
        except Exception:
            logging.exception('Backend adapter initialization failed game=%s', game_id)
            raise

        router = JsonlRequestRouter(adapter)

        def interrupt(signum, frame):
            raise KeyboardInterrupt()

        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        try:
            input_stream = getattr(sys.stdin, 'buffer', sys.stdin)
            while True:
                line = input_stream.readline(65537)
                if not line:
                    break
                line_bytes = 0
                try:
                    line_bytes = len(line.encode('utf-8')) if isinstance(line, str) else len(line)
                    if line_bytes > 65536:
                        raise ValueError('请求过长。')
                    encoded = process_line(router, line)
                except Exception as error:
                    reply = router.core_error_reply(None, 'invalid_request', str(error))
                    encoded = encode_reply(router, reply)
                print(encoded, flush=True)
                if line_bytes > 65536:
                    # Stay in sync with the next JSONL record without holding
                    # the rest of this untrusted line in memory.
                    while line and line[-1:] not in ('\n', b'\n'):
                        line = input_stream.readline(65537)
        except KeyboardInterrupt:
            pass
    finally:
        if router is not None:
            try:
                router.close()
            except Exception:
                logging.exception('Backend close failed')
        logging_session.close()


if __name__ == '__main__':
    main()
