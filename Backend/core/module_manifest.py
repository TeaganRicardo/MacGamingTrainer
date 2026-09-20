from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Optional, Tuple, Union

_ID_RE = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
_PY_TARGET_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$')
_RESTORE_POLICIES = frozenset({'hotPreferred', 'stoppedOnly'})


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class SaveRootSpec:
    id: str
    path: str
    include: Tuple[str, ...]


@dataclass(frozen=True)
class SaveManagementSpec:
    roots: Tuple[SaveRootSpec, ...]
    provider: Optional[str]
    hot_backup: bool
    restore_policy: str
    staged_restore: bool


def _parse_save_management(data, game_id):
    raw = data.get('saveManagement')
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ManifestError('saveManagement must be an object.')

    roots = raw.get('roots')
    if not isinstance(roots, list) or not roots:
        raise ManifestError('saveManagement.roots must be a non-empty array.')
    parsed_roots = []
    seen_root_ids = set()
    for root in roots:
        if not isinstance(root, dict):
            raise ManifestError('saveManagement.roots entries must be objects.')
        root_id = root.get('id')
        if not isinstance(root_id, str) or not _ID_RE.fullmatch(root_id):
            raise ManifestError('saveManagement root id must be a lowercase safe identifier.')
        if root_id in seen_root_ids:
            raise ManifestError('saveManagement root ids must be unique.')
        seen_root_ids.add(root_id)

        root_path = root.get('path')
        if not isinstance(root_path, str) or not root_path.strip():
            raise ManifestError('saveManagement root path must be non-empty.')
        root_path = root_path.strip()
        expanded = Path(root_path).expanduser()
        if not (root_path.startswith('~/') or expanded.is_absolute()):
            raise ManifestError('saveManagement root path must be absolute or ~-relative.')

        includes = root.get('include')
        if not isinstance(includes, list) or not includes:
            raise ManifestError('saveManagement root include must be a non-empty array.')
        parsed_includes = []
        for pattern in includes:
            if not isinstance(pattern, str) or not pattern.strip():
                raise ManifestError('saveManagement include patterns must be non-empty strings.')
            pattern = pattern.strip()
            path = Path(pattern)
            if path.is_absolute() or '..' in path.parts or '\\' in pattern:
                raise ManifestError('saveManagement include patterns must stay inside their root.')
            parsed_includes.append(pattern)
        parsed_roots.append(SaveRootSpec(root_id, root_path, tuple(parsed_includes)))

    provider = raw.get('provider')
    if provider is not None:
        if not isinstance(provider, str) or not _PY_TARGET_RE.fullmatch(provider):
            raise ManifestError('saveManagement.provider must be module.path:ClassName or null.')
        if not provider.startswith('games.{}.'.format(game_id)):
            raise ManifestError('saveManagement.provider must stay inside the game package.')

    hot_backup = raw.get('hotBackup', False)
    staged_restore = raw.get('stagedRestore', False)
    restore_policy = raw.get('restorePolicy', 'stoppedOnly')
    if type(hot_backup) is not bool:
        raise ManifestError('saveManagement.hotBackup must be boolean.')
    if type(staged_restore) is not bool:
        raise ManifestError('saveManagement.stagedRestore must be boolean.')
    if restore_policy not in _RESTORE_POLICIES:
        raise ManifestError('saveManagement.restorePolicy must be hotPreferred or stoppedOnly.')

    return SaveManagementSpec(
        roots=tuple(parsed_roots),
        provider=provider,
        hot_backup=hot_backup,
        restore_policy=restore_policy,
        staged_restore=staged_restore,
    )


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
    save_management: Optional[SaveManagementSpec] = None

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
            save_management=_parse_save_management(data, game_id),
        )

    def public_metadata(self) -> dict:
        metadata = {
            'id': self.id,
            'displayName': self.display_name,
            'protocolVersion': self.module_protocol_version,
            'targetApplication': {
                'processName': self.process_name,
                'bundleIdentifier': self.bundle_identifier,
            },
        }
        if self.save_management is not None:
            metadata['saveManagement'] = {
                'supported': True,
                'hotBackup': self.save_management.hot_backup,
                'restorePolicy': self.save_management.restore_policy,
                'stagedRestore': self.save_management.staged_restore,
            }
        return metadata

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
