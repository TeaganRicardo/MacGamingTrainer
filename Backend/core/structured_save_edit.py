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
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Optional, Protocol, TypeVar

from .save_resolution import ResolvedSaveFile

if TYPE_CHECKING:
    from .save_service import CoreSaveService

_Document = TypeVar("_Document")


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


class StructuredSaveEditValidationError(ValueError):
    """A structured candidate did not survive the game's codec validation."""


class StructuredSaveEditRecoveryError(ValueError):
    """A prior uncertain Apply locks this session until recovery is inspected."""

    code = "rollback_failed"

    def __init__(self, recovery_paths: Iterable[str]) -> None:
        self.recovery_paths = tuple(recovery_paths)
        self.arguments: tuple[str, ...]
        if self.recovery_paths:
            display = "\n".join(self.recovery_paths)
            super().__init__(
                "A previous structured Save Editor Apply could not be rolled back. "
                "Recovery evidence was preserved at: " + display
            )
            self.presentation = "host.save.error.rollbackFailed"
            self.arguments = (display,)
            self.recovery_path = display
        else:
            super().__init__(
                "A previous structured Save Editor Apply has unresolved recovery evidence; "
                "the recovery location could not be inspected."
            )
            self.presentation = "host.save.error.recoveryUnresolved"
            self.arguments = ()


class StructuredSaveEditSession(Generic[_Document]):
    """One pinned structured source and explicit physical replacement target."""

    __slots__ = (
        "_save_service",
        "_codec",
        "_source_file",
        "_source_identity",
        "_target",
        "_version_pinned",
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
    ) -> None:
        self._save_service = save_service
        self._codec = codec
        self._source_file = source_file
        self._source_identity = dict(source_identity)
        self._target = target
        self._version_pinned = bool(version_pinned)
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
        )
        if target is not None:
            session.set_target(target)
        return session

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

    @document.setter
    def document(self, value: _Document) -> None:
        self._document = value

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
        direct = getattr(error, "recovery_path", None)
        if direct is not None:
            self._record_recovery((str(direct),))
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

    def apply(self) -> dict[str, object]:
        self._require_resolved()
        if self._target is None:
            raise ValueError("Save Editor requires an explicitly selected physical write target.")

        encoded = self._encode(self._document)
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
