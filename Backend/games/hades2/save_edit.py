"""Hades II adapter for Core's generic structured save-edit lifecycle."""

from core.structured_save_edit import StructuredSaveEditSession
from .save_document import Hades2SaveDocument
from .save_provider import editor_files, profile_file_identity


class _Hades2SaveCodec:
    """Keep Hades II's version-17/18 container and luabins rules game-owned."""

    def encode(self, document):
        if not isinstance(document, Hades2SaveDocument):
            raise TypeError("Save Editor applies only structured Hades II save documents.")
        return document.to_bytes()

    def decode(self, payload):
        return Hades2SaveDocument.from_bytes(payload)

    def load(self, path):
        return Hades2SaveDocument.load(path)


_CODEC = _Hades2SaveCodec()


class Hades2SaveEditSession:
    """Game adapter retaining Hades II source eligibility and codec semantics."""

    __slots__ = ("_save_service", "_core", "source")

    def __init__(self, save_service, core_session, source):
        self._save_service = save_service
        self._core = core_session
        self.source = source

    @property
    def document(self):
        return self._core.document

    @document.setter
    def document(self, value):
        self._core.document = value

    @property
    def relative_path(self):
        return self._core.relative_path

    @property
    def source_sha256(self):
        return self._core.source_sha256

    @property
    def original_sha256(self):
        return self._core.original_sha256

    @property
    def target(self):
        return self._core.target

    @property
    def recovery_path(self):
        return self._core.recovery_path

    @property
    def recovery_paths(self):
        return self._core.recovery_paths

    @property
    def recovery_unresolved(self):
        return self._core.recovery_unresolved

    @staticmethod
    def _resolve_target(save_service, identity):
        if not isinstance(identity, dict) or set(identity) != {"rootId", "relativePath"}:
            raise ValueError("Save Editor target must identify a declared physical file.")
        allowed = editor_files(save_service.resolved_files())
        if identity not in [
            {"rootId": row["rootId"], "relativePath": row["relativePath"]}
            for row in allowed
        ]:
            raise ValueError("Save Editor target is missing or unsupported.")
        return {"rootId": identity["rootId"], "relativePath": identity["relativePath"]}

    def set_target(self, identity):
        selected = self._resolve_target(self._save_service, identity)
        self._core.set_target(selected)

    @classmethod
    def open(
        cls,
        save_service,
        relative_path,
        *,
        root_id=None,
        snapshot_id=None,
        target=None,
        default_target=True,
        version_pinned=False,
    ):
        if profile_file_identity(relative_path) is None:
            raise ValueError("Save Editor source must be a Hades profile save.")
        matches = [
            row for row in save_service.source_files(snapshot_id)
            if row.relative_path == relative_path
            and (root_id is None or row.root_id == root_id)
        ]
        if len(matches) != 1:
            raise ValueError("Save Editor source is missing or ambiguous.")

        selected = matches[0]
        identity = {"rootId": selected.root_id, "relativePath": selected.relative_path}
        source = {"kind": "managedBackup" if snapshot_id is not None else "currentFile"}
        if snapshot_id is not None:
            source["snapshotId"] = snapshot_id
        source.update(identity)

        target_identity = None
        if target is not None:
            target_identity = cls._resolve_target(save_service, target)
        elif default_target:
            available = [
                {"rootId": row["rootId"], "relativePath": row["relativePath"]}
                for row in editor_files(save_service.resolved_files())
            ]
            if identity in available:
                target_identity = cls._resolve_target(save_service, identity)

        core = StructuredSaveEditSession.open(
            save_service,
            identity,
            _CODEC,
            snapshot_id=snapshot_id,
            target=target_identity,
            version_pinned=version_pinned,
        )
        return cls(save_service, core, source)

    def apply(self):
        return self._core.apply()
