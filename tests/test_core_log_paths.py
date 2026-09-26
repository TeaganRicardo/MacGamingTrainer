import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.log_paths import trainer_log_path


def test_valid_game_id_is_scoped_under_configured_home():
    with tempfile.TemporaryDirectory(prefix="mgt-log-path-valid-") as directory:
        home = Path(directory)
        expected = (
            home
            / "Library/Application Support/MacGamingTrainer"
            / "hades2"
            / "trainer.log"
        )
        assert trainer_log_path("hades2", home=home) == expected.resolve()


def test_game_id_rejects_empty_and_absolute_paths():
    for game_id in ("", "/tmp/escape", "\\\\server\\share", "C:\\escape", "bad\x00id"):
        try:
            trainer_log_path(game_id, home="/tmp/mgt-log-path-home")
        except ValueError:
            continue
        raise AssertionError(f"unsafe game_id accepted: {game_id!r}")


def test_game_id_rejects_dot_and_traversal_components():
    for game_id in (".", "..", "../outside", "..\\outside", "hades2/../../outside", "hades2\\..\\outside"):
        try:
            trainer_log_path(game_id, home="/tmp/mgt-log-path-home")
        except ValueError:
            continue
        raise AssertionError(f"unsafe game_id accepted: {game_id!r}")


def test_game_directory_symlink_cannot_escape_log_root():
    with tempfile.TemporaryDirectory(prefix="mgt-log-path-symlink-") as directory:
        home = Path(directory)
        log_root = home / "Library/Application Support/MacGamingTrainer"
        outside = home / "outside"
        log_root.mkdir(parents=True)
        outside.mkdir()
        (log_root / "hades2").symlink_to(outside, target_is_directory=True)
        try:
            trainer_log_path("hades2", home=home)
        except ValueError:
            pass
        else:
            raise AssertionError("symlinked game log directory escaped its root")


def test_log_root_symlink_cannot_redirect_logs_outside_home():
    with tempfile.TemporaryDirectory(prefix="mgt-log-path-root-symlink-") as directory:
        home = Path(directory)
        library = home / "Library" / "Application Support"
        library.mkdir(parents=True)
        outside = home.parent / (home.name + "-outside")
        outside.mkdir()
        try:
            (library / "MacGamingTrainer").symlink_to(outside, target_is_directory=True)
            try:
                trainer_log_path("hades2", home=home)
            except ValueError:
                pass
            else:
                raise AssertionError("symlinked log root escaped its home")
        finally:
            outside.rmdir()


def test_log_file_symlink_cannot_escape_log_root():
    with tempfile.TemporaryDirectory(prefix="mgt-log-path-file-symlink-") as directory:
        home = Path(directory)
        log_root = home / "Library/Application Support/MacGamingTrainer"
        game_dir = log_root / "hades2"
        game_dir.mkdir(parents=True)
        outside = home / "outside.log"
        outside.write_text("outside", encoding="utf-8")
        (game_dir / "trainer.log").symlink_to(outside)
        try:
            trainer_log_path("hades2", home=home)
        except ValueError:
            pass
        else:
            raise AssertionError("symlinked trainer.log escaped its root")


if __name__ == "__main__":
    test_valid_game_id_is_scoped_under_configured_home()
    test_game_id_rejects_empty_and_absolute_paths()
    test_game_id_rejects_dot_and_traversal_components()
    test_game_directory_symlink_cannot_escape_log_root()
    test_log_root_symlink_cannot_redirect_logs_outside_home()
    test_log_file_symlink_cannot_escape_log_root()
    print("core_log_paths_ok")
