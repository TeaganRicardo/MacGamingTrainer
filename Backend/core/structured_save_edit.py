"""Generic recoverable lifecycle for game-owned structured save documents.

Core owns physical source/target identity, pinned digests, candidate staging,
verified replacement, baseline advancement and terminal recovery evidence.
Game adapters supply a structured codec and retain save eligibility and meaning.
There is deliberately no apply-bytes entrypoint.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Optional, Protocol, TypeVar

from .errors import PresentableError
from .save_resolution import ResolvedSaveFile

if TYPE_CHECKING:
    from .save_service import CoreSaveService

_Document = TypeVar("_Document")
_Workspace = TypeVar("_Workspace", bound="SaveEditorWorkspaceProtocol")


class StructuredSaveEligibilityProtocol(Protocol):
    """Protocol for game-owned save member eligibility predicates."""

    def editor_files(self, files: Sequence[ResolvedSaveFile]) -> Sequence[Mapping[str, Any]]: ...
    def is_source(self, relative_path: str) -> bool: ...


class SaveEditorWorkspaceProtocol(Protocol):
    """Minimum lifecycle surface managed by Core's workspace registry."""

    identifier: str
    baseline_generation: str

    def summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...
    def set_target(self, target: object) -> dict[str, Any]: ...


class StructuredSaveCodec(Protocol[_Document]):
    """Game-owned adapter for one structured save document format."""

    def decode(self, payload: bytes) -> _Document:
        """Decode bytes into the game's structured document type."""
        ...

    def encode(self, document: _Document) -> bytes:
        """Encode only the game's structured document type."""
        ...

    def load(self, path: Path) -> _Document:
        """Reload the installed physical document through the game codec."""
        ...


class StructuredSaveEditValidationError(PresentableError, ValueError):
    """A structured candidate did not survive the game's codec validation."""

    def __init__(self, message: str) -> None:
        super().__init__("invalid_request", "host.save.error.failed", diagnostic=message, message=message)


class StructuredSaveEditRecoveryError(PresentableError, ValueError):
    """A prior uncertain Apply locks this session until recovery is inspected."""

    code = "rollback_failed"

    def __init__(self, recovery_paths: Iterable[str]) -> None:
        self.recovery_paths = tuple(recovery_paths)
        if self.recovery_paths:
            display = "\n".join(self.recovery_paths)
            diagnostic = (
                "A previous structured Save Editor Apply could not be rolled back. "
                "Recovery evidence was preserved at: " + display
            )
            super().__init__(
                self.code,
                "host.save.error.rollbackFailed",
                diagnostic=diagnostic,
                arguments=(display,),
                recovery_path=display,
                message=diagnostic,
            )
        else:
            diagnostic = (
                "A previous structured Save Editor Apply has unresolved recovery evidence; "
                "the recovery location could not be inspected."
            )
            super().__init__(self.code, "host.save.error.recoveryUnresolved", diagnostic=diagnostic, message=diagnostic)


@dataclass(frozen=True)
class StructuredSaveEligibility:
    """Game-owned save file eligibility, source validation, and default-source selection."""

    editor_files: Callable[..., list[dict[str, Any]]]
    is_source: Callable[[str], bool]
    default_source: Optional[Callable[[Sequence[ResolvedSaveFile]], Optional[dict[str, str]]]] = None


class StructuredSaveEditSession(Generic[_Document]):
    """One pinned structured source and explicit physical replacement target."""

    __slots__ = (
        "_save_service",
        "_codec",
        "_source_file",
        "_source_identity",
        "_target",
        "_version_pinned",
        "_eligibility",
        "_source_metadata",
        "_source_sha256",
        "_original_sha256",
        "_document",
        "_recovery_paths",
        "_recovery_unresolved",
    )

    def __init__(
        self,
        save_service: CoreSaveService,
        codec: StructuredSaveCodec[_Document],
        source_file: ResolvedSaveFile,
        source_identity: dict[str, str],
        target: Optional[ResolvedSaveFile],
        original_sha256: str,
        document: _Document,
        *,
        version_pinned: bool = False,
        eligibility: Optional[Any] = None,
        source_metadata: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._save_service = save_service
        self._codec = codec
        self._source_file = source_file
        self._source_identity = dict(source_identity)
        self._target = target
        self._version_pinned = bool(version_pinned)
        self._eligibility = eligibility
        self._source_metadata = dict(source_metadata) if source_metadata is not None else dict(source_identity)
        self._source_sha256 = original_sha256
        self._original_sha256 = original_sha256
        self._document = document
        self._recovery_paths: tuple[str, ...] = ()
        self._recovery_unresolved = False

    @classmethod
    def open(
        cls,
        save_service: CoreSaveService,
        source_identity: object,
        codec: StructuredSaveCodec[_Document],
        *,
        snapshot_id: Optional[str] = None,
        target: object = None,
        version_pinned: bool = False,
        eligibility: Optional[Any] = None,
        source_metadata: Optional[Mapping[str, str]] = None,
    ) -> StructuredSaveEditSession[_Document]:
        identity = cls._identity(source_identity, "source")
        selected, raw = save_service.read_source_file(
            identity["rootId"],
            identity["relativePath"],
            snapshot_id,
        )
        document = codec.decode(raw)
        session = cls(
            save_service,
            codec,
            selected,
            identity,
            None,
            sha256(raw).hexdigest(),
            document,
            version_pinned=version_pinned,
            eligibility=eligibility,
            source_metadata=source_metadata,
        )
        if target is not None:
            session.set_target(target)
        return session

    @staticmethod
    def _eligible_target_identities(
        save_service: CoreSaveService, eligibility: StructuredSaveEligibilityProtocol
    ) -> list[dict[str, str]]:
        editor_files_fn = getattr(eligibility, "editor_files", None)
        if not callable(editor_files_fn):
            raise TypeError("Save eligibility must expose callable editor_files.")
        return [
            {"rootId": str(row["rootId"]), "relativePath": str(row["relativePath"])}
            for row in editor_files_fn(save_service.resolved_files())
        ]

    @classmethod
    def open_selected(
        cls,
        save_service: CoreSaveService,
        codec: StructuredSaveCodec[_Document],
        eligibility: StructuredSaveEligibilityProtocol,
        *,
        source: Optional[Mapping[str, Any]] = None,
        relative_path: Optional[str] = None,
        root_id: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        target: Optional[Mapping[str, Any]] = None,
        default_target: bool = False,
        version_pinned: bool = False,
    ) -> StructuredSaveEditSession[_Document]:
        is_source_fn = getattr(eligibility, "is_source", None)
        if not callable(is_source_fn):
            raise TypeError("Save eligibility must expose callable is_source.")

        if source is not None:
            checked_source = (
                cls._identity(dict(source), "source")
                if isinstance(source, Mapping)
                else cls._identity(source, "source")
            )
            selected_root: Optional[str] = checked_source["rootId"]
            selected_path = checked_source["relativePath"]
        elif relative_path is not None:
            if not isinstance(relative_path, str) or not relative_path:
                raise ValueError("Save Editor source must identify one save file.")
            selected_root = root_id
            selected_path = relative_path
        else:
            default_fn = getattr(eligibility, "default_source", None)
            default_choice: Optional[Mapping[str, str]] = (
                default_fn(save_service.source_files(snapshot_id)) if callable(default_fn) else None
            )
            if default_choice is None:
                raise ValueError("Save Editor requires an explicit supported source file.")
            checked_default = cls._identity(dict(default_choice), "source")
            selected_root = checked_default["rootId"]
            selected_path = checked_default["relativePath"]

        if not is_source_fn(selected_path):
            raise ValueError("Save Editor source is not a supported profile save.")

        matches = [
            row
            for row in save_service.source_files(snapshot_id)
            if row.relative_path == selected_path and (selected_root is None or row.root_id == selected_root)
        ]
        if len(matches) != 1:
            raise ValueError("Save Editor source is missing or ambiguous.")

        matched = matches[0]
        identity = {"rootId": matched.root_id, "relativePath": matched.relative_path}
        source_metadata: dict[str, str] = {"kind": "managedBackup" if snapshot_id is not None else "currentFile"}
        if snapshot_id is not None:
            source_metadata["snapshotId"] = snapshot_id
        source_metadata.update(identity)

        selected_target: Optional[dict[str, str]] = None
        if target is not None:
            selected_target = cls._identity(dict(target) if isinstance(target, Mapping) else target, "target")
            if selected_target not in cls._eligible_target_identities(save_service, eligibility):
                raise ValueError("Save Editor target is missing or unsupported.")
        elif default_target:
            if identity in cls._eligible_target_identities(save_service, eligibility):
                selected_target = dict(identity)

        return cls.open(
            save_service,
            identity,
            codec,
            snapshot_id=snapshot_id,
            target=selected_target,
            version_pinned=version_pinned,
            eligibility=eligibility,
            source_metadata=source_metadata,
        )

    @staticmethod
    def _identity(identity: object, role: str) -> dict[str, str]:
        if (
            not isinstance(identity, dict)
            or set(identity) != {"rootId", "relativePath"}
            or not isinstance(identity["rootId"], str)
            or not identity["rootId"]
            or not isinstance(identity["relativePath"], str)
            or not identity["relativePath"]
        ):
            raise ValueError("Structured Save Editor {} must identify one physical save file.".format(role))
        return {"rootId": identity["rootId"], "relativePath": identity["relativePath"]}

    def _resolve_target(self, identity: object) -> ResolvedSaveFile:
        selected = self._identity(identity, "target")
        if self._eligibility is not None:
            if selected not in self._eligible_target_identities(self._save_service, self._eligibility):
                raise ValueError("Save Editor target is missing or unsupported.")
        matches = [
            row
            for row in self._save_service.resolved_files()
            if (row.root_id, row.relative_path) == (selected["rootId"], selected["relativePath"])
        ]
        if len(matches) != 1:
            raise ValueError("Structured Save Editor target is missing or ambiguous.")
        row = matches[0]
        try:
            physical_path = row.source_path.resolve(strict=True)
        except OSError as error:
            raise ValueError("Structured Save Editor target is no longer available.") from error
        return ResolvedSaveFile(row.root_id, row.relative_path, physical_path)

    @property
    def document(self) -> _Document:
        return self._document

    @property
    def source(self) -> dict[str, str]:
        return dict(self._source_metadata)

    @property
    def source_identity(self) -> dict[str, str]:
        return dict(self._source_identity)

    @property
    def source_sha256(self) -> str:
        return self._source_sha256

    @property
    def original_sha256(self) -> str:
        return self._original_sha256

    @property
    def target(self) -> Optional[dict[str, str]]:
        if self._target is None:
            return None
        return {
            "rootId": self._target.root_id,
            "relativePath": self._target.relative_path,
        }

    @property
    def relative_path(self) -> str:
        return self._target.relative_path if self._target is not None else self._source_file.relative_path

    @property
    def recovery_path(self) -> Optional[str]:
        return self._recovery_paths[0] if len(self._recovery_paths) == 1 else None

    @property
    def recovery_paths(self) -> tuple[str, ...]:
        return self._recovery_paths

    @property
    def recovery_unresolved(self) -> bool:
        return self._recovery_unresolved

    def set_target(self, identity: object) -> Optional[dict[str, str]]:
        self._target = self._resolve_target(identity)
        return self.target

    def _encode(self, document: _Document) -> bytes:
        payload = self._codec.encode(document)
        if type(payload) is not bytes:
            raise TypeError("Structured save codec must return bytes.")
        return payload

    def _recovery_snapshot(self) -> frozenset[str]:
        paths = self._save_service.recovery_paths()
        if not isinstance(paths, (list, tuple)) or any(not isinstance(path, str) for path in paths):
            raise RuntimeError("Core Save returned invalid recovery evidence.")
        return frozenset(paths)

    def _record_recovery(self, paths: Iterable[str]) -> None:
        self._recovery_paths = tuple(sorted(set(paths)))
        self._recovery_unresolved = True

    def _capture_recovery_after_failure(self, error: BaseException, before: frozenset[str]) -> None:
        if isinstance(error, PresentableError) and error.recovery_path is not None:
            self._record_recovery((error.recovery_path,))
            return
        try:
            after = self._recovery_snapshot()
        except BaseException:
            # If terminal evidence cannot be inspected after a transaction
            # interruption, the session must not permit another Apply.
            self._record_recovery(())
            return
        added = after - before
        if added:
            self._record_recovery(added)

    def _require_resolved(self) -> None:
        if self._recovery_unresolved:
            raise StructuredSaveEditRecoveryError(self._recovery_paths)

    def apply(self, candidate: _Document) -> dict[str, object]:
        self._require_resolved()
        if self._target is None:
            raise ValueError("Save Editor requires an explicitly selected physical write target.")

        encoded = self._encode(candidate)
        # The game codec validates the entire candidate before Core begins a
        # filesystem transaction. No caller-supplied raw-byte write is exposed.
        self._codec.decode(encoded)
        encoded_sha256 = sha256(encoded).hexdigest()
        if encoded_sha256 == self._original_sha256:
            raise ValueError("Save Editor document has no changes to apply.")

        target_path = Path(self._target.source_path)
        key = (self._target.root_id, self._target.relative_path)
        recovery_before = self._recovery_snapshot()

        temporary = tempfile.TemporaryDirectory(prefix="mgt-structured-save-edit-")
        try:
            staged = Path(temporary.name) / target_path.name
            with staged.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            replacement = ResolvedSaveFile(
                self._target.root_id,
                self._target.relative_path,
                staged,
            )

            def verify_installed() -> None:
                installed = self._codec.load(target_path)
                if self._encode(installed) != encoded:
                    raise StructuredSaveEditValidationError(
                        "Installed structured save did not round-trip to the edited document."
                    )

            expected_hashes = None if self._version_pinned else {key: self._original_sha256}
            try:
                result = self._save_service.replace_files(
                    (replacement,),
                    expected_hashes,
                    post_install_verify=verify_installed,
                    expected_paths={key: target_path},
                    allow_running=True,
                )
            except BaseException as error:
                self._capture_recovery_after_failure(error, recovery_before)
                raise
            self._original_sha256 = encoded_sha256
            self._document = candidate
        except BaseException:
            try:
                temporary.cleanup()
            except OSError:
                logging.exception('Failed Save Editor staging cleanup: %s', temporary.name)
            raise
        try:
            temporary.cleanup()
        except OSError:
            logging.exception('Save Editor staging cleanup failed after a verified edit: %s', temporary.name)
            result['maintenanceWarning'] = 'staging_cleanup_failed'
        return {
            "applied": True,
            "relativePath": self._target.relative_path,
            "runtimeReloaded": False,
            **result,
        }


DEFAULT_MAX_OPEN_SAVE_WORKSPACES = 8
_UNSET = object()


class SaveEditorWorkspaceRegistry(Generic[_Workspace]):
    """Core registry owning open Save Editor workspaces, baselines, eviction, and standard routes."""

    STANDARD_COMMANDS = frozenset(
        {
            "inventory",
            "open",
            "close",
            "target",
            "save_editor_inventory",
            "save_editor_open",
            "save_editor_close",
            "save_editor_target",
        }
    )

    def __init__(
        self,
        get_save_service: Callable[[], Optional[CoreSaveService]],
        *,
        inventory: Callable[[CoreSaveService, Optional[str]], dict[str, Any]],
        open_workspace: Callable[..., _Workspace],
        max_open: int = DEFAULT_MAX_OPEN_SAVE_WORKSPACES,
        unavailable_error: Optional[Callable[[], Exception]] = None,
        not_open_error: Optional[Callable[[object], Exception]] = None,
        stale_baseline_error: Optional[Callable[[], Exception]] = None,
    ) -> None:
        if type(max_open) is not int or max_open < 1:
            raise ValueError("max_open must be a positive integer.")
        self._get_save_service = get_save_service
        self._inventory = inventory
        self._open_workspace = open_workspace
        self._max_open = max_open
        self._unavailable_error = unavailable_error or (
            lambda: ValueError("Save Editor save management is unavailable.")
        )
        self._not_open_error = not_open_error or (lambda _identifier: ValueError("Save Editor workspace is not open."))
        self._stale_baseline_error = stale_baseline_error or (
            lambda: ValueError("Save Editor document baseline is stale; refresh before editing.")
        )
        self._workspaces: OrderedDict[str, _Workspace] = OrderedDict()

    def _require_save_service(self) -> CoreSaveService:
        service = self._get_save_service()
        if service is None:
            raise self._unavailable_error()
        return service

    @staticmethod
    def _close_workspace(workspace: object) -> None:
        close_fn = getattr(workspace, "close", None)
        if callable(close_fn):
            close_fn()

    def clear(self) -> None:
        while self._workspaces:
            _identifier, workspace = self._workspaces.popitem(last=False)
            self._close_workspace(workspace)

    def __len__(self) -> int:
        return len(self._workspaces)

    def __contains__(self, identifier: object) -> bool:
        return isinstance(identifier, str) and identifier in self._workspaces

    def __getitem__(self, identifier: str) -> _Workspace:
        return self._workspaces[identifier]

    def get(self, identifier: str, default: Optional[_Workspace] = None) -> Optional[_Workspace]:
        return self._workspaces.get(identifier, default)

    def inventory(self, params: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
        service = self._require_save_service()
        raw_snapshot = params.get("snapshotId") if params is not None else None
        if raw_snapshot is not None and not isinstance(raw_snapshot, str):
            raise ValueError("Save Editor snapshot identity must be a string.")
        return self._inventory(service, raw_snapshot)

    def open(self, params: Optional[Mapping[str, Any]] = None, *, language: Optional[str] = None) -> dict[str, Any]:
        service = self._require_save_service()
        raw = params or {}
        workspace = self._open_workspace(
            service,
            snapshot_id=raw.get("snapshotId"),
            source=raw.get("source"),
            target=raw.get("target"),
        )
        while len(self._workspaces) >= self._max_open:
            _evicted_id, evicted = self._workspaces.popitem(last=False)
            self._close_workspace(evicted)

        workspace_id = uuid.uuid4().hex
        baseline_generation = uuid.uuid4().hex
        workspace.identifier = workspace_id
        workspace.baseline_generation = baseline_generation
        self._workspaces[workspace_id] = workspace
        return workspace.summary(language) if language is not None else workspace.summary()

    def require(self, identifier: object) -> _Workspace:
        if not isinstance(identifier, str) or not identifier or identifier not in self._workspaces:
            raise self._not_open_error(identifier)
        self._workspaces.move_to_end(identifier)
        return self._workspaces[identifier]

    def require_baseline(self, identifier: object, generation: object) -> _Workspace:
        workspace = self.require(identifier)
        if generation != workspace.baseline_generation:
            raise self._stale_baseline_error()
        return workspace

    def rotate_baseline(self, identifier: str) -> str:
        workspace = self.require(identifier)
        new_generation = uuid.uuid4().hex
        workspace.baseline_generation = new_generation
        return new_generation

    def close(self, params: Mapping[str, Any]) -> dict[str, bool]:
        identifier = params.get("workspaceId")
        if not isinstance(identifier, str):
            raise self._not_open_error(identifier)
        self.require(identifier)
        workspace = self._workspaces.pop(identifier)
        self._close_workspace(workspace)
        return {"closed": True}

    def target(self, params: Mapping[str, Any], *, require_baseline: bool = True) -> dict[str, Any]:
        identifier = params.get("workspaceId")
        if require_baseline:
            workspace = self.require_baseline(identifier, params.get("baselineGeneration"))
        else:
            workspace = self.require(identifier)
        return workspace.set_target(params["target"])

    def handle(
        self,
        command: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        language: Optional[str] = None,
        require_baseline: bool = True,
    ) -> dict[str, Any]:
        name = command[len("save_editor_") :] if command.startswith("save_editor_") else command
        payload = params or {}
        if name == "inventory":
            return self.inventory(payload)
        if name == "open":
            return self.open(payload, language=language)
        if name == "close":
            return self.close(payload)
        if name == "target":
            return self.target(payload, require_baseline=require_baseline)
        raise ValueError("Unknown standard Save Editor operation.")
