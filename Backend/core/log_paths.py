from pathlib import Path
import re


def trainer_log_directory(game_id, home=None):
    """Return the contained game-scoped root for Host-owned session logs."""
    if not isinstance(game_id, str) or not game_id or game_id in ('.', '..') or '\x00' in game_id:
        raise ValueError('game_id must be one non-empty safe path component')
    if '/' in game_id or '\\' in game_id or Path(game_id).is_absolute() or re.match(r'^[A-Za-z]:', game_id):
        raise ValueError('game_id must be one non-empty safe path component')

    root = Path.home() if home is None else Path(home)
    resolved_home = root.resolve()
    log_root = root / 'Library/Application Support/MacGamingTrainer'
    expected_log_root = resolved_home / 'Library/Application Support/MacGamingTrainer'
    resolved_root = log_root.resolve()
    if resolved_root != expected_log_root:
        raise ValueError('trainer log root must not resolve through symlinks')

    game_directory = log_root / game_id
    resolved_game = game_directory.resolve()
    if game_directory.is_symlink() or resolved_game.parent != resolved_root:
        raise ValueError('trainer log directory escapes its root')
    return resolved_game


def trainer_log_path(game_id, home=None):
    """Return the contained legacy flat log path when that file is safe."""
    path = trainer_log_directory(game_id, home=home) / 'trainer.log'
    if path.is_symlink():
        raise ValueError('trainer log path must not contain symlinks')
    return path.resolve()
