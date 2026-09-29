from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


class AdapterError(RuntimeError):
    """Module-raised failure with a stable presentation identity.

    `presentation` is a stable key or a message the Host resolves; `arguments`
    are the values for its placeholders. The host envelope carries both, and
    `diagnostic` is technical detail that never reaches the player.
    """

    def __init__(self, code: str, presentation: str, *, diagnostic: Optional[str] = None,
                 arguments: Sequence[Any] = ()):
        super().__init__(presentation)
        self.code = code
        self.presentation = presentation
        self.diagnostic = diagnostic
        self.arguments = list(arguments)


class HostPresentationError(AdapterError):
    """Core-owned failure whose player-facing identity resolves in Host.strings."""

    PRESENTATION_PREFIX = "host."

    def __init__(self, code: str, presentation: str, *, diagnostic: Optional[str] = None,
                 arguments: Sequence[Any] = ()):
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
    save_management: Any = None


class GameAdapter(ABC):
    """Per-game backend contract.

    The host owns framing, idempotency and lifecycle. A game adapter owns its
    commands/state and may use any implementation strategy (files, native
    helper, memory access, LLDB, Lua, etc.).
    """

    def __init__(self, context: GameAdapterContext):
        self.context = context

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
        metadata.update({
            'id': self.game_id,
            'displayName': self.display_name,
            'protocolVersion': self.module_protocol_version,
        })
        return metadata
