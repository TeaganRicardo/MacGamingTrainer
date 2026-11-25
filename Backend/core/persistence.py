"""Atomic text replacement and shared versioned JSON stores for modules.

Callers supply schema versions, normalization/migration callbacks, serializer
formatting, and game-owned error keys/exceptions. Core owns atomic file
replacement, corrupt-file quarantine, name validation, envelope invariants, and
newer-schema write/read refusal.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Iterable
import uuid

SHORTCUT_MODIFIER_MASK = (1 << 8) | (1 << 9) | (1 << 11) | (1 << 12)
_SHORTCUT_ACTION_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def atomic_write_text(path, text, *, encoding="utf-8"):
    """Replace *path* with private, fsynced text staged in its own directory.

    A failed write/flush/file sync/replacement leaves the old destination intact.
    Directory sync is best-effort after replacement: a platform's inability to
    sync the directory must not report failure for an already installed document.
    """
    path = Path(path)
    temporary = None
    descriptor = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix="." + path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
            descriptor = None  # The stream now owns the descriptor.
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
        temporary = None
        fsync_directory(path.parent)
    finally:
        # Cleanup also runs for interruption and fdopen failure. A cleanup error
        # must not replace the error that prevented installing the document.
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def fsync_directory(directory):
    """Attempt directory durability without rejecting a completed replacement."""
    try:
        descriptor = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def quarantine_corrupt_file(path):
    """Move a corrupt user-data file aside without overwriting prior evidence.

    Quarantine is deliberately best-effort. Callers use it only after they have
    established that file contents are unusable; a rename failure must not turn
    a recoverable startup/profile-list path into a fatal error.
    """
    path = Path(path)
    if not path.is_file():
        return None
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = path.with_name(f"{path.name}.corrupt-{stamp}-{uuid.uuid4().hex[:8]}")
    try:
        os.replace(str(path), str(destination))
        fsync_directory(path.parent)
        return destination
    except OSError:
        return None


def read_schema_version(document, *, missing_version=0, error_factory=None):
    """Extract a non-negative integer ``schemaVersion`` from a parsed envelope."""
    if not isinstance(document, dict):
        raise (error_factory or ValueError)("Invalid document shape")
    if "schemaVersion" not in document:
        return missing_version
    value = document["schemaVersion"]
    if type(value) is not int or value < 0:
        raise (error_factory or ValueError)("Invalid schemaVersion")
    return value


def normalize_shortcut_map(raw, *, retired_actions: Iterable[str] = ()):
    """Validate serialized shortcut chord dictionaries and strip retired IDs."""
    if not isinstance(raw, dict):
        return {}
    retired = frozenset(retired_actions)
    result = {}
    layout_version = raw.get("_layoutVersion")
    if type(layout_version) is int and layout_version >= 1:
        result["_layoutVersion"] = layout_version
    actions = sorted(
        action
        for action in raw
        if isinstance(action, str) and _SHORTCUT_ACTION_RE.fullmatch(action) and action not in retired
    )
    for action in actions:
        row = raw.get(action)
        if not isinstance(row, dict) or set(row) != {"keyCode", "modifiers", "keyLabel"}:
            continue
        key_code = row.get("keyCode")
        modifiers = row.get("modifiers")
        label = row.get("keyLabel")
        if type(key_code) is not int or not 0 <= key_code <= 65535:
            continue
        if type(modifiers) is not int or not 0 <= modifiers <= 0xFFFFFFFF or modifiers & ~SHORTCUT_MODIFIER_MASK:
            continue
        if not isinstance(label, str) or not label or len(label) > 16 or any(ord(ch) < 32 for ch in label):
            continue
        result[action] = {
            "keyCode": key_code,
            "modifiers": modifiers,
            "keyLabel": label,
        }
    return result


def default_json_serializer(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def utc_iso_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _UnsupportedProfileSchema(Exception):
    def __init__(self, error: Exception):
        super().__init__(str(error))
        self.error = error


class VersionedDocumentStore:
    """Versioned JSON document store with quarantine and newer-schema refusal."""

    def __init__(
        self,
        path,
        *,
        schema_version: int,
        compatibility_floor: int = 0,
        defaults: Callable[[], dict[str, Any]],
        normalize: Callable[[dict[str, Any], int], dict[str, Any]],
        build_document: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
        serialize: Callable[[dict[str, Any]], str] = default_json_serializer,
        document_label: str = "document",
        quarantine_corrupt: bool = True,
        fallback_on_error: bool = False,
        newer_schema_error: Callable[[int, int], Exception] | None = None,
        older_schema_error: Callable[[int, int], Exception] | None = None,
        read_error: Callable[[str, Exception | None], Exception] | None = None,
        write_error: Callable[[Exception], Exception] | None = None,
        quarantine_failed_error: Callable[[str], Exception] | None = None,
    ):
        self.path = Path(path)
        self.schema_version = schema_version
        self.compatibility_floor = compatibility_floor
        self._defaults = defaults
        self._normalize = normalize
        self._build_document = build_document or (lambda value, version: {**value, "schemaVersion": version})
        self._serialize = serialize
        self._document_label = document_label
        self._quarantine_corrupt = quarantine_corrupt
        self._fallback_on_error = fallback_on_error
        self._newer_schema_error = newer_schema_error or (
            lambda found, supported: ValueError(f"Unsupported newer schemaVersion {found} > {supported}")
        )
        self._older_schema_error = older_schema_error or self._newer_schema_error
        self._read_error = read_error or (lambda reason, exc: ValueError(reason) if exc is None else exc)
        self._write_error = write_error or (lambda exc: exc)
        self._quarantine_failed_error = quarantine_failed_error
        self.unsupported_schema_version = None
        self.write_blocked_error = None

    def _quarantine_or_block(self, reason: str, message: str, *, exc_info: bool = True):
        if not self._quarantine_corrupt:
            return
        quarantined = quarantine_corrupt_file(self.path)
        if exc_info:
            logging.exception(message, quarantined)
        else:
            logging.error(message, quarantined)
        if quarantined is None and self.path.exists() and self._quarantine_failed_error:
            self.write_blocked_error = self._quarantine_failed_error(reason)

    def protect_future_overwrite(self):
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            version = read_schema_version(raw)
        except (OSError, ValueError):
            return
        if version > self.schema_version:
            raise self._newer_schema_error(version, self.schema_version)

    def load(self):
        self.unsupported_schema_version = None
        self.write_blocked_error = None
        if self._fallback_on_error and not self.path.is_file():
            return self._defaults(), False
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            defaults = self._defaults()
            return (defaults, False) if self._fallback_on_error else defaults
        except UnicodeError as exc:
            self._quarantine_or_block("unreadable", f"Quarantined unreadable {self._document_label} as %s")
            if self._fallback_on_error:
                return self._defaults(), False
            raise self._read_error("unreadable", exc) from exc
        except OSError as exc:
            logging.exception("Failed to read versioned document %s", self.path)
            error = self._read_error("io", exc)
            if self._fallback_on_error:
                self.write_blocked_error = error
                return self._defaults(), False
            raise error from exc
        try:
            raw = json.loads(text)
        except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
            self._quarantine_or_block("invalid_json", f"Quarantined invalid {self._document_label} as %s")
            if self._fallback_on_error:
                return self._defaults(), False
            raise self._read_error("invalid_json", exc) from exc
        if not isinstance(raw, dict):
            self._quarantine_or_block(
                "invalid_shape", f"Quarantined invalid {self._document_label} shape as %s", exc_info=False
            )
            if self._fallback_on_error:
                return self._defaults(), False
            raise self._read_error("invalid_shape", None)
        try:
            version = read_schema_version(raw)
        except ValueError as exc:
            self._quarantine_or_block(
                "invalid_version", f"Quarantined {self._document_label} with invalid schema version as %s"
            )
            if self._fallback_on_error:
                return self._defaults(), False
            raise self._read_error("invalid_version", exc) from exc
        if version > self.schema_version:
            error = self._newer_schema_error(version, self.schema_version)
            if self._fallback_on_error:
                self.unsupported_schema_version = version
                self.write_blocked_error = error
                logging.error(
                    "Document %s schema %s is newer than supported %s; preserving file read-only",
                    self.path,
                    version,
                    self.schema_version,
                )
                return self._defaults(), False
            raise error
        if version < self.compatibility_floor:
            error = self._older_schema_error(version, self.schema_version)
            if self._fallback_on_error:
                logging.error(
                    "Document %s schema %s is older than floor %s",
                    self.path,
                    version,
                    self.compatibility_floor,
                )
                return self._defaults(), False
            raise error
        try:
            normalized = self._normalize(raw, version)
        except Exception as exc:
            if self._fallback_on_error:
                raise
            raise self._read_error("invalid_payload", exc) from exc
        return (normalized, True) if self._fallback_on_error else normalized

    def save(self, value: dict[str, Any]):
        if self.write_blocked_error is not None:
            raise self.write_blocked_error
        self.protect_future_overwrite()
        document = self._build_document(value, self.schema_version)
        payload = self._serialize(document)
        try:
            atomic_write_text(self.path, payload)
        except Exception as exc:
            mapped = self._write_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc


class ProfileStore:
    """Shared versioned named-profile store with envelope & newer-schema guards."""

    def __init__(
        self,
        root,
        *,
        schema_version: int,
        compatibility_floor: int,
        payload_key: str,
        normalize_payload: Callable[[dict[str, Any], int], dict[str, Any]],
        prepare_save_payload: Callable[[dict[str, Any]], dict[str, Any]],
        game_id: str | None = None,
        payload_version_key: str | None = None,
        payload_schema_version: int | None = None,
        slug_length: int | None = None,
        serialize: Callable[[dict[str, Any]], str] = default_json_serializer,
        timestamp: Callable[[], str] = utc_iso_timestamp,
        quarantine_corrupt: bool = True,
        create_root_dir: bool = False,
        migrate_envelope: Callable[[dict[str, Any], int], dict[str, Any]] | None = None,
        retired_shortcut_actions: Iterable[str] = (),
        include_shortcuts_in_list: bool = True,
        invalid_name_error: Callable[[str], Exception] | None = None,
        corrupt_error: Callable[[str, Exception | None], Exception] | None = None,
        not_found_error: Callable[[str], Exception] | None = None,
        delete_not_found_error: Callable[[str], Exception] | None = None,
        newer_schema_error: Callable[[int, int], Exception] | None = None,
        older_schema_error: Callable[[int, int], Exception] | None = None,
        newer_payload_schema_error: Callable[[int, int], Exception] | None = None,
        invalid_payload_input_error: Callable[[str], Exception] | None = None,
        list_error: Callable[[Exception], Exception] | None = None,
        write_error: Callable[[Exception], Exception] | None = None,
    ):
        self.root = Path(root)
        if create_root_dir:
            self.root.mkdir(parents=True, exist_ok=True)
        self.schema_version = schema_version
        self.compatibility_floor = compatibility_floor
        self.payload_key = payload_key
        self._normalize_payload = normalize_payload
        self._prepare_save_payload = prepare_save_payload
        self.game_id = game_id
        self.payload_version_key = payload_version_key
        self.payload_schema_version = payload_schema_version
        self._slug_length = slug_length
        self._serialize = serialize
        self._timestamp = timestamp
        self._quarantine_corrupt = quarantine_corrupt
        self._migrate_envelope = migrate_envelope
        self._retired_shortcut_actions = frozenset(retired_shortcut_actions)
        self._include_shortcuts_in_list = include_shortcuts_in_list
        self._invalid_name_error = invalid_name_error or (lambda reason: ValueError(reason))
        self._corrupt_error = corrupt_error or (
            lambda reason, exc: ValueError(reason) if exc is None else ValueError(reason)
        )
        self._not_found_error = not_found_error or (lambda name: ValueError(f"Profile {name!r} not found"))
        self._delete_not_found_error = delete_not_found_error or self._not_found_error
        self._newer_schema_error = newer_schema_error or (
            lambda found, supported: ValueError(f"Unsupported newer Profile schema {found} > {supported}")
        )
        self._older_schema_error = older_schema_error or self._newer_schema_error
        self._newer_payload_schema_error = newer_payload_schema_error or self._newer_schema_error
        self._invalid_payload_input_error = invalid_payload_input_error or (lambda reason: ValueError(reason))
        self._list_error = list_error or (lambda exc: exc)
        self._write_error = write_error or (lambda exc: exc)

        base_fields = {"schemaVersion", "name", "updatedAt", self.payload_key}
        if self.game_id is not None:
            base_fields.add("gameID")
        if self.payload_version_key is not None:
            base_fields.add(self.payload_version_key)
        self._required_fields = frozenset(base_fields)
        self._allowed_fields = frozenset(base_fields | {"shortcuts"})

    @staticmethod
    def sanitize_profile_name(value, error_factory: Callable[[str], Exception] | None = None) -> str:
        fail = error_factory or (lambda reason: ValueError(reason))
        if not isinstance(value, str):
            raise fail("non_string")
        trimmed = value.strip()
        if "/" in trimmed or "\\" in trimmed:
            raise fail("separator")
        if not 1 <= len(trimmed) <= 64 or any(ord(ch) < 32 for ch in trimmed):
            raise fail("length")
        return trimmed

    def sanitize_name(self, value) -> str:
        return self.sanitize_profile_name(value, self._invalid_name_error)

    def path(self, name) -> Path:
        safe = self.sanitize_name(name)
        digest = hashlib.sha256(safe.encode("utf-8")).hexdigest()
        slug = digest[: self._slug_length] if self._slug_length else digest
        return self.root / (slug + ".json")

    def _quarantine(self, path: Path, detail: str):
        if not self._quarantine_corrupt:
            return
        quarantined = quarantine_corrupt_file(path)
        logging.error("%s %s quarantined=%s", detail, path, quarantined)

    def _read_json_dict(self, path: Path, *, quarantine: bool = True) -> dict[str, Any]:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeError as exc:
            if quarantine:
                self._quarantine(path, "Unreadable profile")
            raise self._corrupt_error("unreadable", exc) from exc
        except OSError as exc:
            raise self._corrupt_error("io", exc) from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            if quarantine:
                self._quarantine(path, "Invalid JSON profile")
            raise self._corrupt_error("invalid_json", exc) from exc
        if not isinstance(payload, dict):
            if quarantine:
                self._quarantine(path, "Invalid profile shape")
            raise self._corrupt_error("invalid_shape", None)
        return payload

    def _validate_version(self, path: Path, payload: dict[str, Any], *, quarantine: bool = True):
        try:
            version = read_schema_version(payload)
        except ValueError as exc:
            if quarantine:
                self._quarantine(path, "Invalid profile schemaVersion")
            raise self._corrupt_error("invalid_version", exc) from exc
        if version > self.schema_version:
            raise _UnsupportedProfileSchema(self._newer_schema_error(version, self.schema_version))
        if version < self.compatibility_floor:
            raise _UnsupportedProfileSchema(self._older_schema_error(version, self.schema_version))
        return version

    def _validate_envelope(self, path: Path, raw: dict[str, Any], *, quarantine: bool = True) -> dict[str, Any]:
        version = self._validate_version(path, raw, quarantine=quarantine)
        document = (
            self._migrate_envelope(raw, version)
            if self._migrate_envelope is not None and version < self.schema_version
            else dict(raw)
        )
        try:
            keys = set(document)
            if not self._required_fields <= keys or not keys <= self._allowed_fields:
                raise ValueError("Invalid profile envelope fields")
            if self.game_id is not None and document.get("gameID") != self.game_id:
                raise ValueError("Profile gameID mismatch")

            raw_name = document.get("name")
            name = self.sanitize_name(raw_name)
            if raw_name != name or self.path(name) != path:
                raise ValueError("Profile name mismatch")

            updated_at = document.get("updatedAt", "")
            if (
                not isinstance(updated_at, str)
                or not updated_at
                or len(updated_at) > 128
                or any(ord(ch) < 32 for ch in updated_at)
            ):
                raise ValueError("Invalid profile updatedAt")

            if "shortcuts" in document and not isinstance(document["shortcuts"], dict):
                raise ValueError("Profile shortcuts must be an object")

            payload_data = document.get(self.payload_key)
            if not isinstance(payload_data, dict):
                raise ValueError("Invalid profile payload")

            if self.payload_version_key is not None and self.payload_schema_version is not None:
                payload_version = document.get(self.payload_version_key)
                if type(payload_version) is not int or payload_version < 0:
                    raise ValueError("Invalid nested schemaVersion")
                if payload_version > self.payload_schema_version:
                    raise _UnsupportedProfileSchema(
                        self._newer_payload_schema_error(payload_version, self.payload_schema_version)
                    )
                normalized_payload = self._normalize_payload(payload_data, payload_version)
            else:
                normalized_payload = self._normalize_payload(payload_data, version)
        except _UnsupportedProfileSchema:
            raise
        except Exception as exc:
            if quarantine:
                self._quarantine(path, "Invalid profile envelope")
            raise self._corrupt_error("invalid_envelope", exc) from exc

        return {
            "name": name,
            "updatedAt": updated_at,
            self.payload_key: normalized_payload,
            "shortcuts": normalize_shortcut_map(
                document.get("shortcuts"),
                retired_actions=self._retired_shortcut_actions,
            ),
        }

    def protect_future_overwrite(self, path: Path):
        if not path.is_file():
            return
        try:
            payload = self._read_json_dict(path, quarantine=False)
            version = read_schema_version(payload)
        except Exception:
            return
        if version > self.schema_version:
            raise self._newer_schema_error(version, self.schema_version)
        if self.payload_version_key is not None and self.payload_schema_version is not None:
            payload_version = payload.get(self.payload_version_key)
            if type(payload_version) is int and payload_version > self.payload_schema_version:
                raise self._newer_payload_schema_error(payload_version, self.payload_schema_version)

    def list(self) -> list[dict[str, Any]]:
        try:
            paths = sorted(self.root.glob("*.json"))
        except OSError as exc:
            raise self._list_error(exc) from exc
        rows = []
        for path in paths:
            try:
                raw = self._read_json_dict(path, quarantine=self._quarantine_corrupt)
                envelope = self._validate_envelope(path, raw, quarantine=self._quarantine_corrupt)
                row: dict[str, Any] = {
                    "name": envelope["name"],
                    "updatedAt": envelope["updatedAt"],
                }
                if self._include_shortcuts_in_list:
                    row["shortcuts"] = envelope["shortcuts"]
                rows.append(row)
            except _UnsupportedProfileSchema:
                logging.warning("Ignoring unsupported Profile schema %s", path)
            except Exception:
                logging.exception("Ignoring corrupt profile %s", path)
        rows.sort(key=lambda item: item["name"].casefold())
        return rows

    def load(self, name: str) -> dict[str, Any]:
        path = self.path(name)
        if not path.is_file():
            raise self._not_found_error(name)
        raw = self._read_json_dict(path, quarantine=self._quarantine_corrupt)
        try:
            return self._validate_envelope(path, raw, quarantine=self._quarantine_corrupt)
        except _UnsupportedProfileSchema as wrapper:
            raise wrapper.error

    def save(self, name: str, payload: dict[str, Any], shortcuts: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        safe_name = self.sanitize_name(name)
        if not isinstance(payload, dict):
            raise self._invalid_payload_input_error("payload")
        if shortcuts is not None and not isinstance(shortcuts, dict):
            raise self._invalid_payload_input_error("shortcuts")
        path = self.path(safe_name)
        self.protect_future_overwrite(path)
        normalized = self._prepare_save_payload(payload)
        document: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "name": safe_name,
            "updatedAt": self._timestamp(),
            self.payload_key: normalized,
        }
        if self.game_id is not None:
            document["gameID"] = self.game_id
        if self.payload_version_key is not None and self.payload_schema_version is not None:
            document[self.payload_version_key] = self.payload_schema_version
        if isinstance(shortcuts, dict):
            document["shortcuts"] = normalize_shortcut_map(shortcuts, retired_actions=self._retired_shortcut_actions)
        text = self._serialize(document)
        try:
            atomic_write_text(path, text)
        except Exception as exc:
            mapped = self._write_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        return self.list()

    def delete(self, name: str) -> tuple[str, list[dict[str, Any]]]:
        safe_name = self.sanitize_name(name)
        path = self.path(safe_name)
        if not path.is_file():
            raise self._delete_not_found_error(safe_name)
        try:
            path.unlink()
        except OSError as exc:
            mapped = self._write_error(exc)
            if mapped is exc:
                raise
            raise mapped from exc
        return safe_name, self.list()
