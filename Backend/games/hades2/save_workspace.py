"""Structured Hades II save-editor workspace.

The workspace owns Hades profile/target selection and composes the structured
document edit session. Query and mutation semantics are added behind this same
public seam as editor domains are admitted.
"""

from .save_edit import Hades2SaveEditSession
from .save_provider import _active_profile


class Hades2SaveWorkspace:
    """One editor workspace pinned to the active Hades profile save."""

    __slots__ = ("_session", "profile")

    def __init__(self, session, profile):
        self._session = session
        self.profile = profile

    @property
    def relative_path(self):
        return self._session.relative_path

    @property
    def document(self):
        return self._session.document

    @classmethod
    def open(cls, save_service):
        files = tuple(save_service.resolved_files())
        by_path = {row.relative_path: row for row in files}
        active = by_path.get("activeProfile")
        profile = _active_profile(active.source_path) if active is not None else None
        if profile is None:
            raise ValueError("Save Editor could not resolve the active Hades profile.")

        temporary = "{}_Temp.sav".format(profile)
        persistent = "{}.sav".format(profile)
        relative_path = temporary if temporary in by_path else persistent
        if relative_path not in by_path:
            raise ValueError("Save Editor active profile save is missing.")

        return cls(
            Hades2SaveEditSession.open(save_service, relative_path),
            profile,
        )
