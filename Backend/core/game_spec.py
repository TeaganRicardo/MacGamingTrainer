from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class GameSpec:
    """Distribution-agnostic local identity for one game.

    Core does not assume a particular distribution service, a macOS .app
    bundle, or a CPU architecture. Game modules opt into those concepts explicitly.
    """

    id: str
    display_name: str
    process_name: str
    executable_path: Path
    bundle_identifier: Optional[str] = None
    app_bundle_path: Optional[Path] = None
    save_path: Optional[Path] = None
    minimum_architecture: Optional[str] = None

    @classmethod
    def macos_app_bundle(
        cls,
        *,
        id: str,
        display_name: str,
        process_name: str,
        app_path: Path,
        executable_name: str,
        bundle_identifier: Optional[str] = None,
        save_path: Optional[Path] = None,
        minimum_architecture: Optional[str] = None,
    ) -> 'GameSpec':
        app_path = Path(app_path)
        return cls(
            id=id,
            display_name=display_name,
            process_name=process_name,
            executable_path=app_path / 'Contents' / 'MacOS' / executable_name,
            bundle_identifier=bundle_identifier,
            app_bundle_path=app_path,
            save_path=save_path,
            minimum_architecture=minimum_architecture,
        )

    @property
    def app_path(self) -> Path:
        """Compatibility alias for modules that require a macOS app bundle."""
        if self.app_bundle_path is None:
            raise RuntimeError(f'{self.display_name} does not declare a macOS app bundle path.')
        return self.app_bundle_path

    @property
    def executable_name(self) -> str:
        return self.executable_path.name
