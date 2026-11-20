from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from core.errors import PresentableError
from core.log_paths import trainer_data_root, trainer_log_directory
from core.module_manifest import GameModuleManifest, SaveManagementSpec
from core.save_resolution import SaveProviderContext


class AdapterError(PresentableError, RuntimeError):
    """Module-raised failure with a stable presentation identity.

    `presentation` is a stable key or a message the Host resolves; `arguments`
    are the values for its placeholders. The host envelope carries both, and
    `diagnostic` is technical detail that never reaches the player.
    """


class HostPresentationError(AdapterError):
    """Core-owned failure whose player-facing identity resolves in Host.strings."""

    PRESENTATION_PREFIX = "host."

    def __init__(
        self, code: str, presentation: str, *, diagnostic: Optional[str] = None, arguments: Sequence[Any] = ()
    ):
        if not isinstance(presentation, str) or not presentation.startswith(self.PRESENTATION_PREFIX):
            raise ValueError("Core presentation errors must use a host.* key.")
        super().__init__(
            code,
            presentation,
            diagnostic=diagnostic,
            arguments=arguments,
        )


@dataclass(frozen=True)
class GameAdapterContext:
    game_id: str
    display_name: str
    module_protocol_version: int
    module_dir: Path
    public_metadata: Mapping[str, Any]
    process_name: str = ''
    save_management: Optional[SaveManagementSpec] = None
    executable_path_suffix: str = ''
    steam_launch_url: Optional[str] = None
    home: Path = field(default_factory=Path.home)

    @classmethod
    def from_manifest(cls, manifest: GameModuleManifest, *, home: Optional[Path] = None) -> 'GameAdapterContext':
        return cls(
            game_id=manifest.id,
            display_name=manifest.display_name,
            module_protocol_version=manifest.module_protocol_version,
            module_dir=manifest.source_path.parent,
            public_metadata=manifest.public_metadata(),
            process_name=manifest.process_name,
            save_management=manifest.save_management,
            executable_path_suffix=manifest.executable_path_suffix,
            steam_launch_url=manifest.steam_launch_url,
            home=Path.home() if home is None else home,
        )

    @property
    def data_dir(self) -> Path:
        """Directory for this game's Trainer-owned data."""
        return trainer_data_root(self.home) / self.game_id

    @property
    def log_dir(self) -> Path:
        """Resolve the Host's contained session log directory at time of use."""
        return trainer_log_directory(self.game_id, home=self.home)


class GameAdapter(ABC):
    """Per-game backend contract.

    The host owns framing, idempotency and lifecycle. A game adapter owns its
    commands/state and may use any implementation strategy (files, native
    helpers, memory access, optional runtime adapters, etc.).
    """

    def __init__(self, context: GameAdapterContext):
        self.context = context
        self.save_service = None

    def bind_save_service(self, save_service):
        """Bind the Host-owned generic Save service for optional game semantics."""
        self.save_service = save_service

    def save_provider_context(self) -> SaveProviderContext:
        """Supply the declared module directory and any module-owned install path."""
        return SaveProviderContext(self.context.module_dir)

    def state_for_error(self) -> Optional[dict[str, Any]]:
        """Return an already-observed public state for error replies, if available."""
        return None

    def reply_replayed(self):
        """Observe delivery of a historical cached reply without re-execution.

        Adapters retaining a public projection baseline must invalidate it:
        the receiver may now hold the historical observation instead. Stateless
        reply producers need no action and keep this default implementation.
        """
        pass

    @property
    def game_id(self):
        return self.context.game_id

    @property
    def display_name(self):
        return self.context.display_name

    @property
    def module_protocol_version(self):
        return self.context.module_protocol_version

    @abstractmethod
    def dispatch(self, command: str, params: dict, request_id: str):
        raise NotImplementedError

    @abstractmethod
    def close(self):
        raise NotImplementedError

    def metadata(self):
        metadata = dict(self.context.public_metadata)
        metadata.update(
            {
                'id': self.game_id,
                'displayName': self.display_name,
                'protocolVersion': self.module_protocol_version,
            }
        )
        return metadata
