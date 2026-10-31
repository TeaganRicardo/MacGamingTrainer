"""Generic recoverable lifecycle for game-owned structured save documents.

Core owns physical source/target identity, pinned digests, candidate staging,
verified replacement, baseline advancement and terminal recovery evidence.
Game adapters supply a structured codec and retain save eligibility and meaning.
There is deliberately no apply-bytes entrypoint.
"""
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from typing import Protocol

from .save_resolution import ResolvedSaveFile


class StructuredSaveCodec(Protocol):
    """Game-owned adapter for one structured save document format."""

    def decode(self, payload: bytes):
        """Decode bytes into the game's structured document type."""
        ...

    def encode(self, document) -> bytes:
        """Encode only the game's structured document type."""
        ...


class StructuredSaveEditValidationError(ValueError):
    """A structured candidate did not survive the game's codec validation."""


class StructuredSaveEditSession:
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
        save_service,
        codec,
        source_file,
        source_identity,
        target,
        original_sha256,
        document,
        *,
        version_pinned=False,
    ):
        self._save_service = save_service
        self._codec = codec
        self._source_file = source_file
        self._source_identity = dict(source_identity)
        self._target = target
        self._version_pinned = bool(version_pinned)
        self._source_sha256 = original_sha256
        self._original_sha256 = original_sha256
        self._document = document
        self._recovery_paths = ()
        self._recovery_unresolved = False

    @classmethod
    def open(
        cls,
        save_service,
        source_identity,
        codec,
        *,
        snapshot_id=None,
        target=None,
        version_pinned=False,
    ):
        source_identity = cls._identity(source_identity, "source")
        selected, raw = save_service.read_source_file(
            source_identity["rootId"],
            source_identity["relativePath"],
            snapshot_id,
        )
        document = codec.decode(raw)
        session = cls(
            save_service,
            codec,
            selected,
            source_identity,
            None,
            sha256(raw).hexdigest(),
            document,
            version_pinned=version_pinned,
        )
        if target is not None:
            session.set_target(target)
        return session

    @staticmethod
    def _identity(identity, role):
        if (
            not isinstance(identity, dict)
            or set(identity) != {"rootId", "relativePath"}
            or not isinstance(identity["rootId"], str)
            or not identity["rootId"]
            or not isinstance(identity["relativePath"], str)
            or not identity["relativePath"]
        ):
            raise ValueError(
                "Structured Save Editor {} must identify one physical save file.".format(role)
            )
        return {"rootId": identity["rootId"], "relativePath": identity["relativePath"]}

    def _resolve_target(self, identity):
        identity = self._identity(identity, "target")
        matches = [
            row for row in self._save_service.resolved_files()
            if (row.root_id, row.relative_path)
            == (identity["rootId"], identity["relativePath"])
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
    def document(self):
        return self._document

    @document.setter
    def document(self, value):
        self._document = value

    @property
    def source_identity(self):
        return dict(self._source_identity)

    @property
    def source_sha256(self):
        return self._source_sha256

    @property
    def original_sha256(self):
        return self._original_sha256

    @property
    def target(self):
        if self._target is None:
            return None
        return {
            "rootId": self._target.root_id,
            "relativePath": self._target.relative_path,
        }

    @property
    def relative_path(self):
        return (
            self._target.relative_path
            if self._target is not None
            else self._source_file.relative_path
        )

    @property
    def recovery_path(self):
        return self._recovery_paths[0] if len(self._recovery_paths) == 1 else None

    @property
    def recovery_paths(self):
        return self._recovery_paths

    @property
    def recovery_unresolved(self):
        return self._recovery_unresolved

    def set_target(self, identity):
        self._target = self._resolve_target(identity)
        return self.target

    def _encode(self, document):
        payload = self._codec.encode(document)
        if type(payload) is not bytes:
            raise TypeError("Structured save codec must return bytes.")
        return payload

    def _recovery_snapshot(self):
        paths = self._save_service.recovery_paths()
        if not isinstance(paths, (list, tuple)) or any(not isinstance(path, str) for path in paths):
            raise RuntimeError("Core Save returned invalid recovery evidence.")
        return frozenset(paths)

    def _record_recovery(self, paths):
        self._recovery_paths = tuple(sorted(set(paths)))
        self._recovery_unresolved = True

    def _capture_recovery_after_failure(self, error, before):
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

    def _require_resolved(self):
        if not self._recovery_unresolved:
            return
        detail = (
            ": " + ", ".join(self._recovery_paths)
            if self._recovery_paths
            else "; recovery state could not be inspected"
        )
        error = ValueError(
            "An earlier structured Save Editor Apply has unresolved recovery evidence" + detail
        )
        error.recovery_paths = self._recovery_paths
        if self._recovery_paths:
            error.recovery_path = "\n".join(self._recovery_paths)
        raise error

    def apply(self):
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

        with tempfile.TemporaryDirectory(prefix="mgt-structured-save-edit-") as temporary:
            staged = Path(temporary) / target_path.name
            with staged.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

            replacement = ResolvedSaveFile(
                self._target.root_id,
                self._target.relative_path,
                staged,
            )

            def verify_installed():
                installed = self._codec.decode(target_path.read_bytes())
                if self._encode(installed) != encoded:
                    raise StructuredSaveEditValidationError(
                        "Installed structured save did not round-trip to the edited document."
                    )

            expected_hashes = (
                None if self._version_pinned else {key: self._original_sha256}
            )
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

        # Advance only after Core confirms the selected physical replacement,
        # codec validation and rollback cleanup. The original source digest is
        # deliberately retained for the lifetime of this session.
        self._original_sha256 = encoded_sha256
        return {
            "applied": True,
            "relativePath": self._target.relative_path,
            "runtimeReloaded": False,
            **result,
        }
