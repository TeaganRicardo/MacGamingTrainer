"""Recoverable Hades II save-edit sessions.

The document owns Hades save meaning. Core Save owns real-file resolution,
rollback capture, atomic replacement, recovery evidence and process-state
safety. This module composes those two interfaces without exposing raw-byte
mutation as a game command.
"""

import hashlib
import os
from pathlib import Path
import tempfile

from core.save_resolution import ResolvedSaveFile

from .save_document import Hades2SaveDocument, HadesSaveFormatError
from .save_provider import editor_files, profile_file_identity


class Hades2SaveEditSession:
    """One structured edit session bound to an observed Hades profile save."""

    __slots__ = (
        "_save_service",
        "_target",
        "_original_sha256",
        "_version_pinned",
        "source",
        "source_sha256",
        "document",
    )

    def __init__(
        self,
        save_service,
        target,
        original_sha256,
        document,
        *,
        version_pinned=False,
        source=None,
    ):
        self._save_service = save_service
        self._target = target
        self._original_sha256 = original_sha256
        self._version_pinned = bool(version_pinned)
        self.source = source
        self.source_sha256 = original_sha256
        self.document = document

    @property
    def relative_path(self):
        return self._target.relative_path if self._target is not None else self.source["relativePath"]

    @property
    def original_sha256(self):
        return self._original_sha256

    @property
    def target(self):
        return ({"rootId": self._target.root_id, "relativePath": self._target.relative_path}
            if self._target is not None else None)

    @staticmethod
    def _resolve_target(save_service, identity):
        if not isinstance(identity, dict) or set(identity) != {"rootId", "relativePath"}:
            raise ValueError("Save Editor target must identify a declared physical file.")
        files = save_service.resolved_files()
        allowed = editor_files(files)
        if identity not in [{"rootId": row["rootId"], "relativePath": row["relativePath"]} for row in allowed]:
            raise ValueError("Save Editor target is missing or unsupported.")
        row = next(row for row in files if (row.root_id, row.relative_path)
            == (identity["rootId"], identity["relativePath"]))
        return ResolvedSaveFile(row.root_id, row.relative_path, row.source_path.resolve())

    def set_target(self, identity):
        self._target = self._resolve_target(self._save_service, identity)

    @classmethod
    def open(cls, save_service, relative_path, *, root_id=None, snapshot_id=None,
             target=None, default_target=True, version_pinned=False):
        if profile_file_identity(relative_path) is None:
            raise ValueError("Save Editor source must be a Hades profile save.")
        matches = [row for row in save_service.source_files(snapshot_id)
            if row.relative_path == relative_path and (root_id is None or row.root_id == root_id)]
        if len(matches) != 1:
            raise ValueError("Save Editor source is missing or ambiguous.")
        selected, raw = save_service.read_source_file(matches[0].root_id, relative_path, snapshot_id)
        document = Hades2SaveDocument.from_bytes(raw)
        identity = {"rootId": selected.root_id, "relativePath": selected.relative_path}
        source = {"kind": "managedBackup" if snapshot_id is not None else "currentFile"}
        if snapshot_id is not None:
            source["snapshotId"] = snapshot_id
        source.update(identity)
        if target is None and default_target:
            targets = editor_files(save_service.resolved_files())
            available = [{"rootId": row["rootId"], "relativePath": row["relativePath"]} for row in targets]
            resolved_target = cls._resolve_target(save_service, identity) if identity in available else None
        elif target is not None:
            resolved_target = cls._resolve_target(save_service, target)
        else:
            resolved_target = None
        return cls(
            save_service,
            resolved_target,
            hashlib.sha256(raw).hexdigest(),
            document,
            version_pinned=version_pinned,
            source=source,
        )

    def apply(self):
        if self._target is None:
            raise ValueError("Save Editor requires an explicitly selected physical write target.")
        if not isinstance(self.document, Hades2SaveDocument):
            raise TypeError("Save Editor applies only structured Hades save documents.")
        encoded = self.document.to_bytes()
        # Validate the complete candidate before crossing the destructive Core
        # transaction seam. This is intentionally a structured Hades document,
        # never an unrestricted caller-provided byte buffer.
        Hades2SaveDocument.from_bytes(encoded)
        encoded_sha256 = hashlib.sha256(encoded).hexdigest()
        if encoded_sha256 == self._original_sha256:
            raise ValueError("Save Editor document has no changes to apply.")

        target_path = Path(self._target.source_path)
        key = (self._target.root_id, self._target.relative_path)

        with tempfile.TemporaryDirectory(prefix="mgt-hades-save-edit-") as td:
            staged = Path(td) / target_path.name
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
                installed = Hades2SaveDocument.load(target_path)
                if installed.to_bytes() != encoded:
                    raise HadesSaveFormatError(
                        "installed Hades save did not round-trip to the edited document"
                    )

            expected_hashes = (
                None if self._version_pinned
                else {key: self._original_sha256}
            )
            result = self._save_service.replace_files(
                (replacement,),
                expected_hashes,
                post_install_verify=verify_installed,
                expected_paths={key: target_path},
            )

        # Successful Core verification means the exact edited bytes are now the
        # new explicit baseline for any later user edit in this same session.
        self._original_sha256 = encoded_sha256
        return {
            "applied": True,
            "relativePath": self._target.relative_path,
            **result,
        }
