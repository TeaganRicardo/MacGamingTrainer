from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping


def _reference_path(module_file: Path = Path(__file__)) -> Path:
    module_file = module_file.resolve()
    resource_root = module_file.parents[3]
    bundled_reference = resource_root / "ui_terminology.json"

    if resource_root.name == "Resources" and resource_root.parent.name == "Contents":
        return bundled_reference
    return module_file.parents[3] / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"


class TermClass(str, Enum):
    NATIVE_GAME = "native_game"
    TRAINER_PRODUCT = "trainer_product"
    INTERNAL_DOMAIN = "internal_domain"
    COMPATIBILITY_ALIAS = "compatibility_alias"


class TermLifecycle(str, Enum):
    ACTIVE = "active"
    COMPATIBILITY = "compatibility"


class TermSurface(str, Enum):
    USER_UI = "user_ui"
    USER_ERROR = "user_error"
    DIAGNOSTIC = "diagnostic"
    PROTOCOL = "protocol"
    STORAGE = "storage"
    TEST = "test"
    DOCUMENTATION = "documentation"
    COMPATIBILITY_INPUT = "compatibility_input"


@dataclass(frozen=True)
class _ClassPolicy:
    lifecycle: TermLifecycle
    allowed_surfaces: frozenset[TermSurface]
    forbidden_surfaces: frozenset[TermSurface]


@dataclass(frozen=True)
class TerminologyTerm:
    key: str
    term_class: TermClass
    zh_cn: str
    english: str
    localization_id: str | None
    source_zh_cn: str | None
    source_english: str | None
    owner: str
    game_version: str
    steam_build: str
    user_facing: bool
    lifecycle: TermLifecycle
    allowed_surfaces: frozenset[TermSurface]
    forbidden_surfaces: frozenset[TermSurface]
    alias_of: str | None = None
    reason: str | None = None


def _parse_policy(term_class: TermClass, row: Mapping[str, Any]) -> _ClassPolicy:
    try:
        lifecycle = TermLifecycle(row["lifecycle"])
        allowed = frozenset(TermSurface(value) for value in row["allowedSurfaces"])
        forbidden = frozenset(TermSurface(value) for value in row["forbiddenSurfaces"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"invalid surface policy for {term_class.value}") from error
    if allowed & forbidden:
        raise ValueError(f"surface policy overlaps allowed/forbidden surfaces for {term_class.value}")
    return _ClassPolicy(lifecycle, allowed, forbidden)


def _source_family(path: str, language: str) -> str:
    suffix = f".{language}.sjson"
    return path[:-len(suffix)] if path.endswith(suffix) else ""


class TerminologyRegistry:
    """Executable view of the target-build terminology evidence map.

    The JSON reference remains the source of truth for localized values,
    provenance, lifecycle and surface policy. This registry turns that evidence
    into one typed API so product code and tests do not each invent their own
    terminology tables.
    """

    def __init__(self, terms: tuple[TerminologyTerm, ...], target: Mapping[str, Any]):
        self._terms = terms
        self.target = dict(target)
        self._by_key = {term.key: term for term in terms}
        self.validate()

    @property
    def terms(self) -> tuple[TerminologyTerm, ...]:
        return self._terms

    def get(self, key: str) -> TerminologyTerm:
        return self._by_key[key]

    def by_class(self, term_class: TermClass) -> tuple[TerminologyTerm, ...]:
        return tuple(term for term in self._terms if term.term_class is term_class)

    def surface_leaks(self, surface: TermSurface, text: str) -> tuple[TerminologyTerm, ...]:
        leaks = []
        for term in self._terms:
            if surface not in term.forbidden_surfaces:
                continue
            values = {term.zh_cn, term.english}
            if any(value and value in text for value in values):
                leaks.append(term)
        return tuple(leaks)

    def validate(self) -> None:
        if self.target.get("languages") != ["zh-CN", "en"]:
            raise ValueError("Hades II terminology registry must expose zh-CN and en")
        if not self.target.get("gameVersion") or not self.target.get("steamBuild"):
            raise ValueError("Hades II terminology registry must identify its target build")
        if len(self._by_key) != len(self._terms):
            raise ValueError("terminology registry contains duplicate stable term IDs")

        for term in self._terms:
            if not term.key or not term.zh_cn or not term.english or not term.owner:
                raise ValueError(f"terminology entry is incomplete: {term.key!r}")
            if term.allowed_surfaces & term.forbidden_surfaces:
                raise ValueError(f"terminology surfaces overlap for {term.key}")
            if term.term_class is TermClass.NATIVE_GAME:
                if not term.localization_id or not term.source_zh_cn or not term.source_english:
                    raise ValueError(f"native term lacks localization provenance: {term.key}")
                if not term.source_zh_cn.endswith(".zh-CN.sjson"):
                    raise ValueError(f"invalid zh-CN source for {term.key}")
                if not term.source_english.endswith(".en.sjson"):
                    raise ValueError(f"invalid English source for {term.key}")
                if _source_family(term.source_zh_cn, "zh-CN") != _source_family(term.source_english, "en"):
                    raise ValueError(f"native bilingual source mismatch for {term.key}")
                if not term.user_facing:
                    raise ValueError(f"native term must be user-facing: {term.key}")
                if term.lifecycle is not TermLifecycle.ACTIVE:
                    raise ValueError(f"native term must be active: {term.key}")
            elif term.term_class is TermClass.TRAINER_PRODUCT:
                if term.localization_id or term.source_zh_cn or term.source_english:
                    raise ValueError(f"trainer product term must not masquerade as native: {term.key}")
                if not term.reason or not term.user_facing:
                    raise ValueError(f"trainer product term lacks ownership rationale: {term.key}")
                if term.lifecycle is not TermLifecycle.ACTIVE:
                    raise ValueError(f"trainer product term must be active: {term.key}")
            elif term.term_class is TermClass.INTERNAL_DOMAIN:
                if term.user_facing:
                    raise ValueError(f"internal domain term cannot be user-facing: {term.key}")
                if term.lifecycle is not TermLifecycle.ACTIVE:
                    raise ValueError(f"internal domain term must be active: {term.key}")
            elif term.term_class is TermClass.COMPATIBILITY_ALIAS:
                if term.user_facing:
                    raise ValueError(f"compatibility alias cannot be user-facing: {term.key}")
                if term.lifecycle is not TermLifecycle.COMPATIBILITY:
                    raise ValueError(f"compatibility alias has invalid lifecycle: {term.key}")
                if not term.alias_of or term.alias_of not in self._by_key:
                    raise ValueError(f"compatibility alias lacks a valid canonical target: {term.key}")
                canonical = self._by_key[term.alias_of]
                if canonical.term_class in {TermClass.COMPATIBILITY_ALIAS, TermClass.INTERNAL_DOMAIN}:
                    raise ValueError(f"compatibility alias targets a non-canonical term: {term.key}")
                if term.zh_cn in {canonical.zh_cn, canonical.english}:
                    raise ValueError(f"compatibility alias duplicates its canonical display: {term.key}")

        native = self.by_class(TermClass.NATIVE_GAME)
        ids = [term.localization_id for term in native]
        if len(ids) != len(set(ids)):
            raise ValueError("native terminology registry contains duplicate localization IDs")

    @classmethod
    def from_reference(cls, reference: Mapping[str, Any]) -> "TerminologyRegistry":
        target = reference.get("target")
        if not isinstance(target, dict):
            raise ValueError("terminology reference is missing target metadata")
        metadata = reference.get("registry")
        if not isinstance(metadata, dict) or not metadata.get("owner"):
            raise ValueError("terminology reference is missing registry ownership metadata")
        owner = metadata["owner"]
        raw_policies = metadata.get("classPolicies")
        if not isinstance(raw_policies, dict):
            raise ValueError("terminology reference is missing class surface policies")
        policies: dict[TermClass, _ClassPolicy] = {}
        for term_class in TermClass:
            row = raw_policies.get(term_class.value)
            if not isinstance(row, dict):
                raise ValueError(f"terminology reference is missing policy for {term_class.value}")
            policies[term_class] = _parse_policy(term_class, row)

        def make_term(
            *,
            key: str,
            term_class: TermClass,
            zh_cn: str,
            english: str,
            user_facing: bool,
            localization_id: str | None = None,
            source_zh_cn: str | None = None,
            source_english: str | None = None,
            alias_of: str | None = None,
            reason: str | None = None,
        ) -> TerminologyTerm:
            policy = policies[term_class]
            return TerminologyTerm(
                key=key,
                term_class=term_class,
                zh_cn=zh_cn,
                english=english,
                localization_id=localization_id,
                source_zh_cn=source_zh_cn,
                source_english=source_english,
                owner=owner,
                game_version=target["gameVersion"],
                steam_build=target["steamBuild"],
                user_facing=user_facing,
                lifecycle=policy.lifecycle,
                allowed_surfaces=policy.allowed_surfaces,
                forbidden_surfaces=policy.forbidden_surfaces,
                alias_of=alias_of,
                reason=reason,
            )

        terms: list[TerminologyTerm] = []
        for group in ("officialTerms", "nativeChoiceTitles", "officialSourceNames"):
            rows = reference.get(group)
            if not isinstance(rows, dict):
                raise ValueError(f"terminology reference is missing {group}")
            for key, row in rows.items():
                terms.append(
                    make_term(
                        key=f"{group}.{key}",
                        term_class=TermClass.NATIVE_GAME,
                        zh_cn=row.get("value", ""),
                        english=row.get("englishValue", ""),
                        localization_id=row.get("id"),
                        source_zh_cn=row.get("source"),
                        source_english=row.get("englishSource"),
                        user_facing=True,
                    )
                )

        products = reference.get("productTerms")
        if not isinstance(products, dict):
            raise ValueError("terminology reference is missing productTerms")
        for key, row in products.items():
            terms.append(
                make_term(
                    key=f"productTerms.{key}",
                    term_class=TermClass.TRAINER_PRODUCT,
                    zh_cn=row.get("value", ""),
                    english=row.get("englishValue", ""),
                    user_facing=True,
                    reason=row.get("reason"),
                )
            )

        internal_terms = reference.get("internalTerms")
        if not isinstance(internal_terms, dict):
            raise ValueError("terminology reference is missing internalTerms")
        for key, row in internal_terms.items():
            value = row.get("value", "")
            terms.append(
                make_term(
                    key=f"internalTerms.{key}",
                    term_class=TermClass.INTERNAL_DOMAIN,
                    zh_cn=value,
                    english=row.get("englishValue", value),
                    user_facing=False,
                    reason=row.get("reason"),
                )
            )

        aliases = reference.get("compatibilityAliases")
        if not isinstance(aliases, dict):
            raise ValueError("terminology reference is missing compatibilityAliases")
        for key, row in aliases.items():
            value = row.get("value", "")
            terms.append(
                make_term(
                    key=f"compatibilityAliases.{key}",
                    term_class=TermClass.COMPATIBILITY_ALIAS,
                    zh_cn=value,
                    english=row.get("englishValue", value),
                    user_facing=False,
                    alias_of=row.get("canonicalTerm"),
                    reason=row.get("reason") or (
                        "Legacy/shorthand form retained only as a compatibility boundary; "
                        "forbidden in canonical product surfaces."
                    ),
                )
            )

        return cls(tuple(terms), target)

    @classmethod
    def load(cls, path: Path | None = None) -> "TerminologyRegistry":
        reference = json.loads((path or _reference_path()).read_text(encoding="utf-8"))
        return cls.from_reference(reference)


@lru_cache(maxsize=1)
def load_hades2_terminology() -> TerminologyRegistry:
    return TerminologyRegistry.load()
