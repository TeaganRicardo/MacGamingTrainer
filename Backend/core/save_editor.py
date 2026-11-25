"""Core Generic Save Editor: base workspace lifecycle and declarative catalog editor."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from typing import TYPE_CHECKING, Any, Generic, Optional, TypeVar
from urllib.parse import quote
import uuid

from .structured_save_edit import (
    SaveEditorWorkspaceRegistry,
    StructuredSaveCodec,
    StructuredSaveEditSession,
    StructuredSaveEligibility,
)

if TYPE_CHECKING:
    from .save_service import CoreSaveService

_Document = TypeVar("_Document")

SUPPORTED_EDITOR_LANGUAGES: tuple[str, ...] = ("en", "zh-CN")
_DEFAULT_UNKNOWN_WARNINGS: dict[str, str] = {
    "en": "The complete gameplay impact of this field is unknown; edits write this value directly.",
    "zh-CN": "此字段的完整游戏影响尚未确认；修改将直接写入该值。",
}
_VALID_VALUE_TYPES = frozenset({"boolean", "integer", "number", "string", "enum", "json"})


def require_editor_language(language: object) -> str:
    """Validate and return a supported Save Editor presentation language."""
    if not isinstance(language, str) or language not in SUPPORTED_EDITOR_LANGUAGES:
        raise ValueError("Unsupported editor language.")
    return language


def localized_text(names: Mapping[str, str], language: str, fallback: str = "") -> str:
    """Resolve a localized string from a language map cleanly."""
    value = names.get(language)
    if isinstance(value, str) and value:
        return value
    english = names.get("en")
    if isinstance(english, str) and english:
        return english
    for item in names.values():
        if isinstance(item, str) and item:
            return item
    return fallback


def paginate_owner_groups(
    rows: Sequence[dict[str, Any]],
    *,
    offset: int,
    limit: int,
    owner_key: str = "ownerId",
) -> tuple[list[dict[str, Any]], int, int]:
    """Return one page of rows grouped by owner without splitting any owner across pages."""
    groups: OrderedDict[Any, list[dict[str, Any]]] = OrderedDict()
    for row in rows:
        groups.setdefault(row.get(owner_key), []).append(row)
    selected: list[dict[str, Any]] = []
    cursor = 0
    start = offset
    for group in groups.values():
        end = cursor + len(group)
        if end > offset and len(selected) < limit:
            if not selected:
                start = cursor
            selected.extend(group)
        cursor = end
    return selected, start, start + len(selected)


def _read_mapping_path(document: Any, path: tuple[Any, ...]) -> tuple[bool, Any]:
    if not path:
        return False, None
    current: Any = document
    for segment in path:
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, deepcopy(current)


def _write_mapping_path(document: Any, path: tuple[Any, ...], value: Any) -> None:
    if not path:
        raise ValueError("Save field path must not be empty.")
    current: Any = document
    for segment in path[:-1]:
        if not isinstance(current, MutableMapping):
            raise ValueError("Save field owner is not a mapping.")
        child = current.get(segment)
        if child is None:
            child = {}
            current[segment] = child
        elif not isinstance(child, MutableMapping):
            raise ValueError("Save field owner is not a mapping.")
        current = child
    if not isinstance(current, MutableMapping):
        raise ValueError("Save field owner is not a mapping.")
    current[path[-1]] = deepcopy(value)


def _delete_mapping_path(document: Any, path: tuple[Any, ...]) -> None:
    if not path:
        raise ValueError("Save field path must not be empty.")
    current: Any = document
    for segment in path[:-1]:
        if not isinstance(current, Mapping) or segment not in current:
            return
        current = current[segment]
    if isinstance(current, MutableMapping) and path[-1] in current:
        del current[path[-1]]


def _values_equal(left: Any, right: Any) -> bool:
    if (type(left) is bool) != (type(right) is bool):
        return False
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return (
            type(left) is type(right)
            and len(left) == len(right)
            and all(_values_equal(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if len(left) != len(right):
            return False
        return all(key in right and _values_equal(value, right[key]) for key, value in left.items())
    return bool(left == right)


def _format_display_value(value: Any, *, present: bool = True) -> str:
    if not present:
        return "∅"
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _infer_value_type(value: Any) -> str:
    if type(value) is bool:
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    return "json"


def _encoded_path_token(path: tuple[Any, ...]) -> str:
    if not path:
        return "$root"
    segments = []
    for part in path:
        if isinstance(part, str):
            segments.append(quote(part, safe="-_"))
        else:
            key_type = type(part)
            # String keys escape ':', so typed segments cannot alias them.
            segments.append(f"{key_type.__module__}.{key_type.__qualname__}:{quote(repr(part), safe='-_')}")
    return "/".join(segments)


@dataclass(frozen=True)
class SaveDomainSpec:
    """One navigable Save Editor category owned by a game module."""

    id: str
    names: Mapping[str, str]
    icon: str = "square.grid.2x2"


@dataclass(frozen=True)
class SaveFieldChoice:
    """One allowed discrete choice for an enum field."""

    value: Any
    names: Mapping[str, str]


@dataclass(frozen=True)
class SaveFieldSpec:
    """Declarative metadata and path/accessor rules for one Save Editor field."""

    id: str
    domain: str
    path: tuple[Any, ...]
    names: Mapping[str, str]
    group_id: str
    group_names: Mapping[str, str]
    owner_id: str
    owner_names: Mapping[str, str]
    value_type: str
    choices: tuple[SaveFieldChoice, ...] = ()
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allow_unset: bool = False
    editable: bool = True
    warnings: Optional[Mapping[str, str]] = None
    read: Optional[Callable[[Any], tuple[bool, Any]]] = None
    write: Optional[Callable[[Any, Any], None]] = None
    delete: Optional[Callable[[Any], None]] = None

    def __post_init__(self) -> None:
        if self.value_type not in _VALID_VALUE_TYPES:
            raise ValueError(f"Unsupported Save Editor value type: {self.value_type!r}")
        if self.value_type == "enum" and not self.choices:
            raise ValueError(f"Enum Save Editor field {self.id!r} requires choices.")

    def read_value(self, document: Any) -> tuple[bool, Any]:
        if self.read is not None:
            return self.read(document)
        return _read_mapping_path(document, self.path)

    def write_value(self, document: Any, value: Any) -> None:
        if self.write is not None:
            self.write(document, value)
            return
        _write_mapping_path(document, self.path, value)

    def delete_value(self, document: Any) -> None:
        if self.delete is not None:
            self.delete(document)
            return
        _delete_mapping_path(document, self.path)


@dataclass(frozen=True)
class SaveFieldCatalog:
    """Game-declared Save Editor domains, curated fields, and optional unknown-field discovery."""

    domains: tuple[SaveDomainSpec, ...]
    fields: tuple[SaveFieldSpec, ...]
    unknown_domain_id: str = "advanced"
    discover_unknown: Optional[Callable[[Any, frozenset[tuple[Any, ...]]], Sequence[SaveFieldSpec]]] = None


def discover_mapping_fields(
    document: Mapping[Any, Any],
    known_paths: frozenset[tuple[Any, ...]],
    *,
    domain: str = "advanced",
    max_depth: int = 12,
) -> tuple[SaveFieldSpec, ...]:
    """Discover round-trippable leaf fields outside `known_paths` with unknown-impact warnings."""
    discovered: list[SaveFieldSpec] = []
    known_prefixes = {kp[:i] for kp in known_paths for i in range(1, len(kp))}

    def walk(node: Mapping[Any, Any], prefix: tuple[Any, ...], depth: int) -> None:
        for key, value in node.items():
            path = (*prefix, key)
            if path in known_paths:
                continue
            if isinstance(value, Mapping) and value and depth < max_depth:
                walk(value, path, depth + 1)
                continue
            if path in known_prefixes:
                continue
            leaf_label = str(key)
            parent_label = " › ".join(str(part) for part in prefix) if prefix else "Document"
            parent_zh = " › ".join(str(part) for part in prefix) if prefix else "根文档"
            group_label = str(prefix[-1]) if prefix else "Root"
            group_zh = str(prefix[-1]) if prefix else "根字段"
            owner_slug = _encoded_path_token(prefix)
            discovered.append(
                SaveFieldSpec(
                    id="discovered:" + _encoded_path_token(path),
                    domain=domain,
                    path=path,
                    names={"en": leaf_label, "zh-CN": leaf_label},
                    group_id="group:" + owner_slug,
                    group_names={"en": group_label, "zh-CN": group_zh},
                    owner_id="owner:" + owner_slug,
                    owner_names={"en": parent_label, "zh-CN": parent_zh},
                    value_type=_infer_value_type(value),
                    allow_unset=True,
                    editable=True,
                    warnings=_DEFAULT_UNKNOWN_WARNINGS,
                )
            )

    walk(document, (), 0)
    return tuple(discovered)


@dataclass(frozen=True)
class SaveEditorSpec(Generic[_Document]):
    """Complete game configuration needed for Core's generic CatalogSaveWorkspace."""

    codec: StructuredSaveCodec[_Document]
    eligibility: StructuredSaveEligibility
    catalog: SaveFieldCatalog
    version_pinned: bool = True
    default_target: bool = False
    clone_document: Optional[Callable[[_Document], _Document]] = None
    allow_running: bool = False


class CoreSaveWorkspace(Generic[_Document]):
    """Shared base Save Editor workspace owning baseline checks, pending rollback, summary, and Apply."""

    def __init__(
        self,
        session: StructuredSaveEditSession[_Document],
        *,
        stale_baseline_error: Optional[Callable[[], Exception]] = None,
    ) -> None:
        self.session = session
        self.identifier: str = uuid.uuid4().hex
        self.baseline_generation: str = uuid.uuid4().hex
        self._pending: OrderedDict[str, Any] = OrderedDict()
        self._stale_baseline_error = stale_baseline_error

    @property
    def _session(self) -> StructuredSaveEditSession[_Document]:
        return self.session

    @property
    def pending(self) -> OrderedDict[str, Any]:
        return self._pending

    @pending.setter
    def pending(self, value: Mapping[str, Any] | Iterable[tuple[str, Any]]) -> None:
        if isinstance(value, OrderedDict):
            self._pending = value
        else:
            self._pending = OrderedDict(value)

    @property
    def document(self) -> _Document:
        return self.session.document

    @property
    def relative_path(self) -> str:
        return self.session.relative_path

    @property
    def recovery_unresolved(self) -> bool:
        return bool(getattr(self.session, "recovery_unresolved", False))

    def require_baseline(self, generation: object) -> None:
        if generation != self.baseline_generation:
            if self._stale_baseline_error is not None:
                raise self._stale_baseline_error()
            raise ValueError("This control belongs to an earlier document baseline. Refresh the editor before editing.")

    def summary_envelope(
        self,
        *,
        domains: Sequence[Any],
        review: Optional[Mapping[str, Any]] = None,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "workspaceId": self.identifier,
            "baselineGeneration": self.baseline_generation,
            "source": dict(self.session.source),
            "sourceSHA256": self.session.source_sha256,
            "target": self.session.target,
            "domains": list(domains),
            "recoveryPath": self.session.recovery_path,
            "recoveryPaths": list(self.session.recovery_paths),
            "recoveryUnresolved": self.session.recovery_unresolved,
        }
        if review is not None:
            payload["review"] = dict(review)
        if extra:
            payload.update(extra)
        return payload

    def set_target_for_baseline(
        self,
        target: object,
        *,
        baseline_generation: object,
        language: Optional[str] = None,
    ) -> dict[str, Any]:
        self.require_baseline(baseline_generation)
        previous_target = self.session.target
        self.session.set_target(target)
        summary_fn: Any = getattr(self, "summary")
        try:
            if language is not None:
                result = summary_fn(language)
            else:
                result = summary_fn()
            if not isinstance(result, dict):
                raise TypeError("Workspace summary() must return a mapping.")
            return result
        except Exception:
            try:
                self.session.restore_target(previous_target)
            except Exception:
                # A previous target that disappeared during confirmation must
                # never leave the newly selected destination writable.
                self.session.restore_target(None)
            raise

    def _mutate_pending(
        self,
        updater: Callable[[], None],
        reviewer: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = OrderedDict(self._pending)
        try:
            updater()
            return reviewer()
        except Exception:
            self._pending.clear()
            self._pending.update(snapshot)
            raise

    def clear_pending(self) -> None:
        self._pending.clear()

    def commit_candidate(
        self,
        candidate: _Document,
        *,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        result = self.session.apply(candidate)
        self.clear_pending()
        self.baseline_generation = uuid.uuid4().hex
        receipt: dict[str, Any] = {
            **result,
            "verified": True,
            "workspaceId": self.identifier,
            "baselineGeneration": self.baseline_generation,
        }
        if hasattr(self.session, "source"):
            receipt["source"] = self.session.source
        if hasattr(self.session, "target"):
            receipt["target"] = self.session.target
        if hasattr(self.session, "source_sha256"):
            receipt["sourceSHA256"] = self.session.source_sha256
        if hasattr(self.session, "original_sha256"):
            receipt["installedSHA256"] = self.session.original_sha256
        if extra:
            receipt.update(extra)
        return receipt


class CatalogSaveWorkspace(CoreSaveWorkspace[_Document]):
    """Generic data-driven Save Editor workspace powered by a game's codec and field catalog."""

    def __init__(
        self,
        session: StructuredSaveEditSession[_Document],
        spec: SaveEditorSpec[_Document],
        *,
        stale_baseline_error: Optional[Callable[[], Exception]] = None,
    ) -> None:
        super().__init__(session, stale_baseline_error=stale_baseline_error)
        self.spec = spec

    @staticmethod
    def inventory(
        service: CoreSaveService,
        eligibility: StructuredSaveEligibility,
        snapshot_id: Optional[str] = None,
    ) -> dict[str, Any]:
        files = service.source_files(snapshot_id)
        sources = eligibility.editor_files(files)
        targets = eligibility.editor_files(service.resolved_files())
        default_source = eligibility.default_source(files) if callable(eligibility.default_source) else None
        source_identities = {(str(row["rootId"]), str(row["relativePath"])) for row in sources}
        if default_source is not None:
            key = (str(default_source["rootId"]), str(default_source["relativePath"]))
            if key not in source_identities:
                default_source = None
        return {
            "sources": sources,
            "targets": targets,
            "defaultSource": default_source,
        }

    @classmethod
    def open(
        cls,
        service: CoreSaveService,
        spec: SaveEditorSpec[_Document],
        *,
        snapshot_id: Optional[str] = None,
        source: Optional[Mapping[str, Any]] = None,
        target: Optional[Mapping[str, Any]] = None,
    ) -> CatalogSaveWorkspace[_Document]:
        session = StructuredSaveEditSession.open_selected(
            service,
            spec.codec,
            spec.eligibility,
            source=source,
            snapshot_id=snapshot_id,
            target=target,
            default_target=spec.default_target,
            version_pinned=spec.version_pinned,
            allow_running=spec.allow_running,
        )
        return cls(session, spec)

    @classmethod
    def registry(
        cls,
        get_save_service: Callable[[], Optional[CoreSaveService]],
        spec: SaveEditorSpec[_Document],
        **kwargs: Any,
    ) -> SaveEditorWorkspaceRegistry[CatalogSaveWorkspace[_Document]]:
        def _inventory(service: CoreSaveService, snapshot_id: Optional[str] = None) -> dict[str, Any]:
            return cls.inventory(service, spec.eligibility, snapshot_id)

        def _open(service: CoreSaveService, **open_kwargs: Any) -> CatalogSaveWorkspace[_Document]:
            return cls.open(service, spec, **open_kwargs)

        return SaveEditorWorkspaceRegistry(
            get_save_service,
            inventory=_inventory,
            open_workspace=_open,
            **kwargs,
        )

    def _effective_fields(self) -> tuple[SaveFieldSpec, ...]:
        curated = self.spec.catalog.fields
        discover = self.spec.catalog.discover_unknown
        known_paths = frozenset(field.path for field in curated if field.path)
        extras: Sequence[SaveFieldSpec]
        if discover is None:
            extras = ()
        elif discover is discover_mapping_fields:
            if not isinstance(self.document, Mapping):
                raise TypeError("discover_mapping_fields requires a Mapping document.")
            extras = discover_mapping_fields(
                self.document,
                known_paths,
                domain=self.spec.catalog.unknown_domain_id,
            )
        else:
            extras = discover(self.document, known_paths)
        by_id: OrderedDict[str, SaveFieldSpec] = OrderedDict()
        for field in (*curated, *extras):
            if field.id in by_id:
                raise ValueError(f"Duplicate Save Editor field ID: {field.id}")
            by_id[field.id] = field
        return tuple(by_id.values())

    def _field_map(self) -> OrderedDict[str, SaveFieldSpec]:
        return OrderedDict((field.id, field) for field in self._effective_fields())

    def _build_row(self, field: SaveFieldSpec, language: str) -> dict[str, Any]:
        present, value = field.read_value(self.document)
        name = localized_text(field.names, language, field.id)
        english_name = localized_text(field.names, "en", field.id)
        group = localized_text(field.group_names, language, field.group_id)
        owner = localized_text(field.owner_names, language, field.owner_id)
        if not field.editable:
            operations: list[str] = []
        elif field.allow_unset and present:
            operations = ["set", "unset"]
        else:
            operations = ["set"]
        choices = [
            {"value": choice.value, "name": localized_text(choice.names, language, str(choice.value))}
            for choice in field.choices
        ]
        constraints: Optional[dict[str, Any]] = None
        if field.min_value is not None or field.max_value is not None:
            constraints = {}
            if field.min_value is not None:
                constraints["min"] = field.min_value
            if field.max_value is not None:
                constraints["max"] = field.max_value
        warning_text = localized_text(field.warnings, language) if field.warnings else None
        return {
            "id": field.id,
            "baselineGeneration": self.baseline_generation,
            "domain": field.domain,
            "name": name,
            "englishName": english_name,
            "group": group,
            "groupId": field.group_id,
            "owner": owner,
            "ownerId": field.owner_id,
            "valueType": field.value_type,
            "value": value if present else None,
            "displayValue": _format_display_value(value, present=present),
            "editable": field.editable,
            "operations": operations,
            "choices": choices,
            "constraints": constraints,
            "warning": warning_text or None,
            "hasChildren": False,
        }

    @staticmethod
    def _coerce_value(field: SaveFieldSpec, value: Any) -> Any:
        kind = field.value_type
        if kind == "boolean":
            if type(value) is not bool:
                raise ValueError(f"Field {field.id!r} requires a boolean value.")
            return value
        if kind == "integer":
            if type(value) is bool or not isinstance(value, int):
                raise ValueError(f"Field {field.id!r} requires an integer value.")
            if field.min_value is not None and value < field.min_value:
                raise ValueError(f"Field {field.id!r} value is below the minimum ({field.min_value}).")
            if field.max_value is not None and value > field.max_value:
                raise ValueError(f"Field {field.id!r} value exceeds the maximum ({field.max_value}).")
            return value
        if kind == "number":
            if type(value) is bool or not isinstance(value, (int, float)):
                raise ValueError(f"Field {field.id!r} requires a finite numeric value.")
            try:
                numeric = float(value)
            except OverflowError as error:
                raise ValueError(f"Field {field.id!r} requires a finite numeric value.") from error
            if not math.isfinite(numeric):
                raise ValueError(f"Field {field.id!r} requires a finite numeric value.")
            if field.min_value is not None and numeric < field.min_value:
                raise ValueError(f"Field {field.id!r} value is below the minimum ({field.min_value}).")
            if field.max_value is not None and numeric > field.max_value:
                raise ValueError(f"Field {field.id!r} value exceeds the maximum ({field.max_value}).")
            return numeric
        if kind == "string":
            if not isinstance(value, str):
                raise ValueError(f"Field {field.id!r} requires a string value.")
            return value
        if kind == "enum":
            for choice in field.choices:
                if _values_equal(choice.value, value):
                    return deepcopy(choice.value)
            raise ValueError(f"Field {field.id!r} does not allow choice {value!r}.")
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(f"Field {field.id!r} requires a strict JSON value.") from error
        return json.loads(encoded)

    def _clone_document(self) -> _Document:
        if self.spec.clone_document is not None:
            return self.spec.clone_document(self.document)
        encoded = self.spec.codec.encode(self.document)
        return self.spec.codec.decode(encoded)

    def _plan(self, language: str) -> tuple[_Document, dict[str, Any]]:
        lang = require_editor_language(language)
        candidate = self._clone_document()
        field_map = self._field_map()
        staged: list[tuple[str, SaveFieldSpec, dict[str, Any]]] = []
        for entry_id, intent in self._pending.items():
            field = field_map.get(entry_id)
            if field is None:
                raise ValueError("Staged entry is no longer present in the document.")
            if not field.editable:
                raise ValueError("Save Editor field is read-only.")
            staged.append((entry_id, field, intent))

        for index, (_entry_id, field, _intent) in enumerate(staged):
            path = field.path
            if not path:
                continue
            for _other_id, other, _other_intent in staged[index + 1 :]:
                other_path = other.path
                if not other_path:
                    continue
                shared = min(len(path), len(other_path))
                if path[:shared] == other_path[:shared]:
                    raise ValueError("Staged Save Editor fields overlap; review and apply them separately.")

        actions: list[dict[str, Any]] = []
        for entry_id, field, intent in staged:
            present, before = field.read_value(self.document)
            operation = intent["operation"]
            if operation == "unset":
                if not field.allow_unset or not present:
                    raise ValueError("Staged operation no longer matches its entry.")
                field.delete_value(candidate)
            elif operation == "set":
                field.write_value(candidate, intent["after"])
            else:
                raise ValueError("Unsupported Save Editor operation.")
            actions.append(
                {
                    "id": entry_id,
                    "name": localized_text(field.names, lang, entry_id),
                    "before": _format_display_value(before, present=present),
                    "after": None,
                    "operation": operation,
                    "valueType": field.value_type,
                    "value": None,
                    "effects": [],
                }
            )

        encoded = self.spec.codec.encode(candidate)
        normalized = self.spec.codec.decode(encoded)
        if self.spec.codec.encode(normalized) != encoded:
            raise ValueError("Save codec output is not stable after decode; review cannot verify the installed result.")
        for action, (_entry_id, field, intent) in zip(actions, staged):
            present, value = field.read_value(normalized)
            if intent["operation"] == "unset":
                if present:
                    raise ValueError("Save codec did not preserve the staged removal.")
            elif not present:
                raise ValueError("Save codec did not preserve the staged field.")
            action["after"] = _format_display_value(value, present=present)
            action["value"] = deepcopy(value) if present else None

        return normalized, {
            "baselineGeneration": self.baseline_generation,
            "actions": actions,
            "count": len(actions),
            "effectCount": 0,
        }

    def _localized_domains(self, lang: str) -> list[dict[str, str]]:
        return [
            {
                "id": domain.id,
                "title": localized_text(domain.names, lang, domain.id),
                "icon": domain.icon,
            }
            for domain in self.spec.catalog.domains
        ]

    def summary(self, language: str = "en") -> dict[str, Any]:
        lang = require_editor_language(language)
        return self.summary_envelope(domains=self._localized_domains(lang), review=self.review(lang))

    def set_target(
        self,
        target: object,
        *,
        baseline_generation: object,
        language: str = "en",
    ) -> dict[str, Any]:
        lang = require_editor_language(language)
        return self.set_target_for_baseline(
            target,
            baseline_generation=baseline_generation,
            language=lang,
        )

    def query(
        self,
        *,
        domain: Optional[str] = None,
        language: str = "en",
        query: str = "",
        offset: int = 0,
        limit: int = 40,
    ) -> dict[str, Any]:
        lang = require_editor_language(language)
        valid_domains = {spec.id for spec in self.spec.catalog.domains}
        if domain is not None and domain not in valid_domains:
            raise ValueError("Save Editor domain is unknown.")
        if not isinstance(query, str) or len(query) > 256:
            raise ValueError("Save Editor search must be at most 256 characters.")
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Invalid editor page.")
        rows: list[dict[str, Any]] = []
        for field in self._effective_fields():
            if domain is not None and field.domain != domain:
                continue
            rows.append(self._build_row(field, lang))
        words = query.casefold().split()
        if words:
            filtered: list[dict[str, Any]] = []
            for row in rows:
                searchable = " ".join(
                    (
                        str(row["id"]),
                        str(row["name"]),
                        str(row["englishName"]),
                        str(row["group"]),
                        str(row["owner"]),
                        str(row["displayValue"]),
                    )
                ).casefold()
                if all(word in searchable for word in words):
                    filtered.append(row)
            rows = filtered
        selected, start, next_offset = paginate_owner_groups(rows, offset=offset, limit=limit)
        return {
            "workspaceId": self.identifier,
            "baselineGeneration": self.baseline_generation,
            "domain": domain,
            "domains": self._localized_domains(lang),
            "rows": selected,
            "total": len(rows),
            "offset": start,
            "limit": len(selected),
            "nextOffset": next_offset,
        }

    def detail(self, entry_id: str, language: str = "en") -> dict[str, Any]:
        lang = require_editor_language(language)
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("Invalid editor entry identity.")
        field = self._field_map().get(entry_id)
        if field is None:
            raise ValueError("Editor entry does not exist.")
        return {"row": self._build_row(field, lang)}

    def stage(
        self,
        entry_id: str,
        operation: str,
        value: Any = None,
        language: str = "en",
        *,
        baseline_generation: object,
    ) -> dict[str, Any]:
        self.require_baseline(baseline_generation)
        lang = require_editor_language(language)
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("Invalid editor entry identity.")
        field = self._field_map().get(entry_id)
        if field is None:
            raise ValueError("Editor entry does not exist.")
        if not field.editable:
            raise ValueError("Save Editor field is read-only.")
        if operation not in ("set", "unset"):
            raise ValueError("Unsupported Save Editor operation.")
        present, before = field.read_value(self.document)
        if operation == "unset":
            if not field.allow_unset or not present:
                raise ValueError("This operation is unavailable for the selected entry.")
            unchanged = False
            coerced = None
        else:
            coerced = self._coerce_value(field, value)
            unchanged = present and _values_equal(before, coerced)

        def update() -> None:
            if unchanged:
                self._pending.pop(entry_id, None)
            else:
                self._pending[entry_id] = {"id": entry_id, "operation": operation, "after": coerced}

        return self._mutate_pending(update, lambda: self.review(lang))

    def unstage(
        self,
        entry_id: str,
        language: str = "en",
        *,
        baseline_generation: object,
    ) -> dict[str, Any]:
        self.require_baseline(baseline_generation)
        lang = require_editor_language(language)
        if not isinstance(entry_id, str) or not entry_id:
            raise ValueError("Invalid editor entry identity.")

        def update() -> None:
            self._pending.pop(entry_id, None)

        return self._mutate_pending(update, lambda: self.review(lang))

    def cancel(self, language: str = "en", *, baseline_generation: object) -> dict[str, Any]:
        self.require_baseline(baseline_generation)
        lang = require_editor_language(language)

        def update() -> None:
            self.clear_pending()

        return self._mutate_pending(update, lambda: self.review(lang))

    def review(self, language: str = "en") -> dict[str, Any]:
        _, review_payload = self._plan(language)
        return review_payload

    def apply(self, *, baseline_generation: object) -> dict[str, Any]:
        self.require_baseline(baseline_generation)
        if not self._pending:
            raise ValueError("There are no staged changes to apply.")
        candidate, _ = self._plan("en")
        return self.commit_candidate(candidate)
