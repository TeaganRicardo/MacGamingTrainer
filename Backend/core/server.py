#!/usr/bin/env python3
"""Game-agnostic JSONL host. Game behavior lives under Backend/games/<game_id>."""
from pathlib import Path
import argparse
import json
import logging
import os
import signal
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.protocol import JsonlRequestRouter
from core.registry import available_games, create_adapter


_LOG_FORMAT = '%(asctime)s %(levelname)s %(message)s'


class _StartupLogBuffer(logging.Handler):
    """Hold worker records until the selected adapter reveals its log location."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _BackendLoggingSession:
    """Own exactly one backend file handler without replacing embedder handlers."""

    def __init__(self):
        self.root = logging.getLogger()
        self.original_level = self.root.level
        self.buffer = _StartupLogBuffer()
        self.file_handler = None
        self.root.addHandler(self.buffer)
        if self.root.level > logging.INFO:
            self.root.setLevel(logging.INFO)

    def configure_file(self, log_path):
        if self.file_handler is not None:
            return
        log_path = Path(log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding='utf-8')
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        self.file_handler = handler
        self.root.addHandler(handler)
        for record in self.buffer.records:
            handler.handle(record)
        self.root.removeHandler(self.buffer)
        self.buffer.records.clear()

    def close(self):
        if self.buffer in self.root.handlers:
            self.root.removeHandler(self.buffer)
        if self.file_handler is not None:
            self.root.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = None
        self.root.setLevel(self.original_level)


def _fallback_log_path(game_id):
    return Path.home() / 'Library/Application Support/MacGamingTrainer' / game_id / 'trainer.log'


def _adapter_log_path(adapter):
    data_dir = getattr(adapter, 'data_dir', None)
    if data_dir is not None:
        return Path(data_dir) / 'trainer.log'
    return _fallback_log_path(adapter.game_id)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--game', default=os.environ.get('MGT_GAME_ID'))
    return parser.parse_args(argv)


def encode_reply(router, reply):
    """Serialize one response without allowing a bad module result to kill the host."""
    try:
        return json.dumps(reply, ensure_ascii=False, allow_nan=False)
    except Exception:
        logging.exception('Backend reply serialization failed')
        fallback = router.error_reply(None, 'protocol_error', '后端响应无法安全序列化。')
        return json.dumps(fallback, ensure_ascii=False, allow_nan=False)


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
            logging_session.configure_file(_fallback_log_path(game_id))
            logging.exception('Backend adapter initialization failed game=%s', game_id)
            raise

        logging_session.configure_file(_adapter_log_path(adapter))
        router = JsonlRequestRouter(adapter)

        def interrupt(signum, frame):
            raise KeyboardInterrupt()

        signal.signal(signal.SIGTERM, interrupt)
        signal.signal(signal.SIGINT, interrupt)
        try:
            for line in sys.stdin:
                try:
                    if len(line) > 65536:
                        raise ValueError('请求过长。')
                    request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('非有限 JSON 数值：' + value)))
                    reply = router.handle(request)
                except Exception as error:
                    reply = router.error_reply(None, 'invalid_request', str(error))
                print(encode_reply(router, reply), flush=True)
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
