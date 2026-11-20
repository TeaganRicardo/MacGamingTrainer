from pathlib import Path
import re
from typing import Optional, Union


def trainer_data_root(home: Optional[Union[Path, str]] = None) -> Path:
    """Return the Trainer Application Support directory."""
    home_directory = Path.home() if home is None else Path(home)
    return home_directory / 'Library/Application Support/MacGamingTrainer'


def trainer_data_directory(game_id: str, home: Optional[Union[Path, str]] = None) -> Path:
    """Scope Trainer data to one safe game directory."""
    if not isinstance(game_id, str) or not game_id or game_id in ('.', '..') or '\x00' in game_id:
        raise ValueError('game_id must be one non-empty safe path component')
    if '/' in game_id or '\\' in game_id or Path(game_id).is_absolute() or re.match(r'^[A-Za-z]:', game_id):
        raise ValueError('game_id must be one non-empty safe path component')
    return trainer_data_root(home) / game_id


def trainer_log_directory(game_id: str, home: Optional[Union[Path, str]] = None) -> Path:
    """Return the contained game-scoped root for Host-owned session logs."""
    root = Path.home() if home is None else Path(home)
    game_directory = trainer_data_directory(game_id, root)
    log_root = game_directory.parent
    expected_log_root = trainer_data_root(root.resolve())
    resolved_root = log_root.resolve()
    if resolved_root != expected_log_root:
        raise ValueError('trainer log root must not resolve through symlinks')

    resolved_game = game_directory.resolve()
    if game_directory.is_symlink() or resolved_game.parent != resolved_root:
        raise ValueError('trainer log directory escapes its root')
    return resolved_game
