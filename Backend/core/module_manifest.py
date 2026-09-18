from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Union

_ID_RE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
_PY_TARGET_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$')


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class GameModuleManifest:
    """Runtime-only view of module.json.

    Backend core intentionally knows nothing about Swift source layout, app
    bundle metadata, architectures, entitlements, or presentation. Those fields
    are build-tool concerns and are validated under Tools/.
    """

    id: str
    display_name: str
    module_protocol_version: int
    adapter: str
    process_name: str
    bundle_identifier: str
    source_path: Path

    @classmethod
    def load(cls, path: Union[str, Path]) -> 'GameModuleManifest':
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ManifestError(f'Cannot read game module manifest: {source}') from error
        if not isinstance(data, dict):
            raise ManifestError('Game module manifest must be a JSON object.')

        game_id = data.get('id')
        if not isinstance(game_id, str) or not _ID_RE.fullmatch(game_id):
            raise ManifestError('id must be a lowercase Python-package-safe identifier.')
        display_name = data.get('displayName')
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 120:
            raise ManifestError('displayName must be a non-empty string.')
        protocol_version = data.get('protocolVersion')
        if type(protocol_version) is not int or not 1 <= protocol_version <= 1_000_000:
            raise ManifestError('protocolVersion must be a positive integer.')
        backend = data.get('backend')
        adapter = backend.get('adapter') if isinstance(backend, dict) else None
        if not isinstance(adapter, str) or not _PY_TARGET_RE.fullmatch(adapter):
            raise ManifestError('backend.adapter must be module.path:ClassName.')

        target_application = data.get('targetApplication')
        if not isinstance(target_application, dict):
            raise ManifestError('targetApplication must be an object.')
        process_name = target_application.get('processName')
        if not isinstance(process_name, str) or not process_name.strip() or len(process_name) > 120:
            raise ManifestError('targetApplication.processName must be a non-empty string.')
        bundle_identifier = target_application.get('bundleIdentifier')
        if not isinstance(bundle_identifier, str) or not bundle_identifier.strip() or len(bundle_identifier) > 255:
            raise ManifestError('targetApplication.bundleIdentifier must be a non-empty string.')

        return cls(
            id=game_id,
            display_name=display_name.strip(),
            module_protocol_version=protocol_version,
            adapter=adapter,
            process_name=process_name.strip(),
            bundle_identifier=bundle_identifier.strip(),
            source_path=source,
        )

    def public_metadata(self) -> dict:
        return {
            'id': self.id,
            'displayName': self.display_name,
            'protocolVersion': self.module_protocol_version,
            'targetApplication': {
                'processName': self.process_name,
                'bundleIdentifier': self.bundle_identifier,
            },
        }

    def validate_backend_layout(self, backend_root: Union[str, Path]) -> None:
        backend_root = Path(backend_root).resolve()
        expected_module_dir = (backend_root / 'games' / self.id).resolve()
        if self.source_path.parent.resolve() != expected_module_dir:
            raise ManifestError(
                f'Game module {self.id!r} must live at Backend/games/{self.id}/module.json.'
            )
        required_adapter_prefix = f'games.{self.id}.'
        if not self.adapter.startswith(required_adapter_prefix):
            raise ManifestError(
                f'backend.adapter must stay inside the game package ({required_adapter_prefix}...).'
            )
