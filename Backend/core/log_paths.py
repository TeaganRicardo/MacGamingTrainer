from pathlib import Path


def trainer_log_path(game_id, home=None):
    """Return the module-scoped trainer log path for one installed game."""
    root = Path.home() if home is None else Path(home)
    return root / 'Library/Application Support/MacGamingTrainer' / game_id / 'trainer.log'
