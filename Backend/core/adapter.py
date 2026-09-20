from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


class AdapterError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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
