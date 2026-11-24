from __future__ import annotations

from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

CheatKind = Literal["toggle", "value", "lock", "one_shot"]

VALID_CHEAT_KINDS: frozenset[str] = frozenset({"toggle", "value", "lock", "one_shot"})


@dataclass(frozen=True)
class CheatLabel:
    """Bilingual player-facing label pair owned by a module's cheat catalog."""

    zh_cn: str
    en: str

    def __post_init__(self) -> None:
        if not self.zh_cn.strip() or not self.en.strip():
            raise ValueError("CheatLabel requires non-empty zh_cn and en strings")

    def resolve(self, language: str = "zh-CN") -> str:
        return self.en if language == "en" else self.zh_cn

    def to_dict(self) -> dict[str, str]:
        return {"zh-CN": self.zh_cn, "en": self.en}


@dataclass(frozen=True)
class CheatBackendAction:
    """Declares which typed backend command handles a cheat definition."""

    command: str
    fixed_params: Mapping[str, Any] = field(default_factory=dict)
    value_param: str | None = None

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("CheatBackendAction requires a non-empty command name")
        if self.value_param is not None and not self.value_param.strip():
            raise ValueError("CheatBackendAction value_param cannot be blank")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": self.command}
        if self.fixed_params:
            payload["fixedParams"] = dict(self.fixed_params)
        if self.value_param is not None:
            payload["valueParam"] = self.value_param
        return payload


@dataclass(frozen=True)
class CheatDefinition:
    """Declarative metadata for one game cheat entry."""

    id: str
    kind: CheatKind
    label: CheatLabel
    action: CheatBackendAction
    help_label: CheatLabel | None = None
    shortcut_id: str | None = None
    aliases: tuple[str, ...] = ()
    default_value: Any = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("CheatDefinition id cannot be blank")
        if self.kind not in VALID_CHEAT_KINDS:
            raise ValueError(f"Unsupported cheat kind {self.kind!r} for {self.id!r}")
        if self.shortcut_id is not None and not self.shortcut_id.strip():
            raise ValueError(f"Blank shortcut_id for cheat {self.id!r}")
        seen_aliases: set[str] = set()
        for alias in self.aliases:
            if not alias.strip():
                raise ValueError(f"Blank alias in cheat {self.id!r}")
            if alias == self.id:
                raise ValueError(f"Cheat {self.id!r} cannot list itself as an alias")
            if alias in seen_aliases:
                raise ValueError(f"Duplicate alias {alias!r} in cheat {self.id!r}")
            seen_aliases.add(alias)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "label": self.label.to_dict(),
            "action": self.action.to_dict(),
        }
        if self.help_label is not None:
            payload["help"] = self.help_label.to_dict()
        if self.shortcut_id is not None:
            payload["shortcutId"] = self.shortcut_id
        if self.aliases:
            payload["aliases"] = list(self.aliases)
        return payload


class CheatCatalog:
    """Validated ordered registry of one game's declarative cheat definitions."""

    def __init__(
        self,
        definitions: tuple[CheatDefinition, ...] | list[CheatDefinition],
        *,
        retired_ids: Collection[str] = (),
    ) -> None:
        self.definitions: tuple[CheatDefinition, ...] = tuple(definitions)
        self.retired_ids: frozenset[str] = frozenset(retired_ids)
        self._by_id: dict[str, CheatDefinition] = {}
        self._aliases: dict[str, str] = {}
        self._shortcuts: dict[str, CheatDefinition] = {}

        for definition in self.definitions:
            if definition.id in self._by_id:
                raise ValueError(f"Duplicate cheat id {definition.id!r}")
            if definition.id in self.retired_ids:
                raise ValueError(f"Cheat id {definition.id!r} cannot also be marked retired")
            self._by_id[definition.id] = definition

        for definition in self.definitions:
            for alias in definition.aliases:
                if alias in self._by_id:
                    raise ValueError(f"Alias {alias!r} collides with canonical cheat id")
                if alias in self.retired_ids:
                    raise ValueError(f"Alias {alias!r} cannot also be marked retired")
                if alias in self._aliases:
                    raise ValueError(f"Duplicate alias {alias!r} across cheat definitions")
                self._aliases[alias] = definition.id
            if definition.shortcut_id is not None:
                if definition.shortcut_id in self._shortcuts:
                    raise ValueError(f"Duplicate shortcut_id {definition.shortcut_id!r}")
                self._shortcuts[definition.shortcut_id] = definition

    def __len__(self) -> int:
        return len(self.definitions)

    def __iter__(self) -> Iterator[CheatDefinition]:
        return iter(self.definitions)

    def ids(self) -> tuple[str, ...]:
        return tuple(definition.id for definition in self.definitions)

    def ids_for_kind(self, kind: CheatKind) -> tuple[str, ...]:
        if kind not in VALID_CHEAT_KINDS:
            raise ValueError(f"Unsupported cheat kind {kind!r}")
        return tuple(definition.id for definition in self.definitions if definition.kind == kind)

    def alias_map(self) -> dict[str, str]:
        return dict(self._aliases)

    def definition(self, cheat_id: str) -> CheatDefinition:
        canonical = self.resolve_id(cheat_id)
        if canonical is None:
            raise KeyError(cheat_id)
        return self._by_id[canonical]

    def resolve_id(self, cheat_id: str) -> str | None:
        if cheat_id in self._by_id:
            return cheat_id
        return self._aliases.get(cheat_id)

    def resolve_shortcut_id(self, action_id: str) -> str | None:
        if action_id in self._shortcuts:
            return action_id
        canonical_cheat = self._aliases.get(action_id)
        if canonical_cheat is None:
            return None
        return self._by_id[canonical_cheat].shortcut_id

    def by_kind(self, kind: CheatKind) -> tuple[CheatDefinition, ...]:
        if kind not in VALID_CHEAT_KINDS:
            raise ValueError(f"Unsupported cheat kind {kind!r}")
        return tuple(definition for definition in self.definitions if definition.kind == kind)

    def migrate_identity_map(
        self,
        raw: Mapping[str, Any],
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve legacy cheat IDs into canonical IDs with canonical keys winning."""

        migrated: dict[str, Any] = dict(defaults) if defaults is not None else {}
        explicit_canonicals = {key for key in raw if key in self._by_id}

        for raw_key, value in raw.items():
            if raw_key in self.retired_ids:
                continue
            canonical = self.resolve_id(raw_key)
            if canonical is None:
                continue
            if raw_key != canonical and canonical in explicit_canonicals:
                # When both canonical and legacy keys appear, the canonical value wins.
                continue
            migrated[canonical] = value
        return migrated

    def migrate_shortcut_payload(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        """Map persisted shortcut keys to canonical IDs while dropping retired actions."""

        migrated: dict[str, Any] = {}
        explicit_keys = {key for key in raw if key not in self._aliases and key not in self.retired_ids}

        for raw_key, value in raw.items():
            if raw_key in self.retired_ids:
                continue
            resolved = self.resolve_shortcut_id(raw_key)
            target_key = resolved if resolved is not None else raw_key
            if raw_key != target_key and target_key in explicit_keys:
                continue
            migrated[target_key] = value
        return migrated

    def validate_commands(self, supported_commands: Collection[str]) -> None:
        """Ensure every declared cheat backend command exists in the module contract."""

        supported = set(supported_commands)
        missing = sorted(
            {definition.action.command for definition in self.definitions if definition.action.command not in supported}
        )
        if missing:
            raise ValueError(f"Cheat catalog references unknown commands: {', '.join(missing)}")

    def to_list(self) -> list[dict[str, Any]]:
        return [definition.to_dict() for definition in self.definitions]
