"""Recoverable Hades II save-edit sessions.

The document owns Hades save meaning. Core Save owns real-file resolution,
rollback capture, atomic replacement, recovery evidence and process-state
safety. This module composes those two interfaces without exposing raw-byte
mutation as a game command.
"""

import hashlib
import os
from pathlib import Path
import re
import tempfile

from core.save_resolution import ResolvedSaveFile

from .save_document import Hades2SaveDocument, HadesSaveFormatError


_PROFILE_SAVE_RE = re.compile(r"^Profile[0-9]+(?:_Temp)?[.]sav$")


class Hades2SaveEditSession:
    """One structured edit session bound to an observed Hades profile save."""

    __slots__ = (
        "_save_service",
        "_target",
        "_original_sha256",
        "_version_pinned",
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
    ):
        self._save_service = save_service
        self._target = target
        self._original_sha256 = original_sha256
        self._version_pinned = bool(version_pinned)
        self.document = document

    @property
    def relative_path(self):
        return self._target.relative_path

    @property
    def original_sha256(self):
        return self._original_sha256

    @classmethod
    def open(cls, save_service, relative_path, *, version_pinned=False):
        if (
            not isinstance(relative_path, str)
            or _PROFILE_SAVE_RE.fullmatch(relative_path) is None
        ):
            raise ValueError("Save Editor target must be a Hades profile save.")

        matches = [
            row
            for row in save_service.resolved_files()
            if row.relative_path == relative_path
        ]
        if len(matches) != 1:
            raise ValueError("Save Editor target is missing or ambiguous.")

        target = matches[0]
        if not isinstance(target, ResolvedSaveFile):
            raise TypeError("Save Editor target must be a resolved save file.")
        raw = Path(target.source_path).read_bytes()
        document = Hades2SaveDocument.from_bytes(raw)
        return cls(
            save_service,
            target,
            hashlib.sha256(raw).hexdigest(),
            document,
            version_pinned=version_pinned,
        )

    def apply(self):
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
            )

        # Successful Core verification means the exact edited bytes are now the
        # new explicit baseline for any later user edit in this same session.
        self._original_sha256 = encoded_sha256
        return {
            "applied": True,
            "relativePath": self._target.relative_path,
            **result,
        }
