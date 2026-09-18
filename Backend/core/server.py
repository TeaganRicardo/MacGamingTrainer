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
    adapter = create_adapter(game_id)
    data_dir = getattr(adapter, 'data_dir', None)
    if data_dir is not None:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        log_path = Path(data_dir) / 'trainer.log'
    else:
        # Generic fallback is namespaced per game. Modules that preserve a
        # historical data location can still expose adapter.data_dir explicitly.
        log_path = Path.home() / 'Library/Application Support/MacGamingTrainer' / adapter.game_id / 'trainer.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(log_path), level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
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
        try:
            router.close()
        except Exception:
            logging.exception('Backend close failed')


if __name__ == '__main__':
    main()
