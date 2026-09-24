from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

REFERENCE_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
)


class TermClass(str, Enum):
    NATIVE_GAME = "native_game"
    TRAINER_PRODUCT = "trainer_product"
    INTERNAL_DOMAIN = "internal_domain"
    COMPATIBILITY_ALIAS = "compatibility_alias"


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
    reason: str | None = None


class TerminologyRegistry:
    """Executable view of the target-build terminology evidence map.

    The JSON reference remains the source of truth for localized values and
    provenance. This registry turns that evidence into one typed API so
    product code and tests do not each invent their own terminology tables.
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

    def validate(self) -> None:
        if self.target.get("languages") != ["zh-CN", "en"]:
            raise ValueError("Hades II terminology registry must expose zh-CN and en")
        if not self.target.get("gameVersion") or not self.target.get("steamBuild"):
            raise ValueError("Hades II terminology registry must identify its target build")

        for term in self._terms:
            if not term.key or not term.zh_cn or not term.english:
                raise ValueError(f"terminology entry is incomplete: {term.key!r}")
            if term.term_class is TermClass.NATIVE_GAME:
                if not term.localization_id or not term.source_zh_cn or not term.source_english:
                    raise ValueError(f"native term lacks localization provenance: {term.key}")
                if not term.source_zh_cn.endswith(".zh-CN.sjson"):
                    raise ValueError(f"invalid zh-CN source for {term.key}")
                if not term.source_english.endswith(".en.sjson"):
                    raise ValueError(f"invalid English source for {term.key}")
                if not term.user_facing:
                    raise ValueError(f"native term must be user-facing: {term.key}")
            elif term.term_class is TermClass.TRAINER_PRODUCT:
                if term.localization_id or term.source_zh_cn or term.source_english:
                    raise ValueError(f"trainer product term must not masquerade as native: {term.key}")
                if not term.reason or not term.user_facing:
                    raise ValueError(f"trainer product term lacks ownership rationale: {term.key}")
            elif term.term_class is TermClass.INTERNAL_DOMAIN:
                if term.user_facing:
                    raise ValueError(f"internal domain term cannot be user-facing: {term.key}")
            elif term.term_class is TermClass.COMPATIBILITY_ALIAS:
                if term.user_facing:
                    raise ValueError(f"compatibility alias cannot be user-facing: {term.key}")

        native = self.by_class(TermClass.NATIVE_GAME)
        ids = [term.localization_id for term in native]
        if len(ids) != len(set(ids)):
            raise ValueError("native terminology registry contains duplicate localization IDs")

    @classmethod
    def from_reference(cls, reference: Mapping[str, Any]) -> "TerminologyRegistry":
        target = reference.get("target")
        if not isinstance(target, dict):
            raise ValueError("terminology reference is missing target metadata")

        terms: list[TerminologyTerm] = []
        for group in ("officialTerms", "nativeChoiceTitles", "officialSourceNames"):
            rows = reference.get(group)
            if not isinstance(rows, dict):
                raise ValueError(f"terminology reference is missing {group}")
            for key, row in rows.items():
                terms.append(
                    TerminologyTerm(
                        key=f"{group}.{key}",
                        term_class=TermClass.NATIVE_GAME,
                        zh_cn=row.get("value", ""),
                        english=row.get("englishValue", ""),
                        localization_id=row.get("id"),
                        source_zh_cn=row.get("source"),
                        source_english=row.get("englishSource"),
                        owner="Backend/games/hades2",
                        game_version=target["gameVersion"],
                        steam_build=target["steamBuild"],
                        user_facing=True,
                    )
                )

        products = reference.get("productTerms")
        if not isinstance(products, dict):
            raise ValueError("terminology reference is missing productTerms")
        for key, row in products.items():
            terms.append(
                TerminologyTerm(
                    key=f"productTerms.{key}",
                    term_class=TermClass.TRAINER_PRODUCT,
                    zh_cn=row.get("value", ""),
                    english=row.get("englishValue", ""),
                    localization_id=None,
                    source_zh_cn=None,
                    source_english=None,
                    owner="Backend/games/hades2",
                    game_version=target["gameVersion"],
                    steam_build=target["steamBuild"],
                    user_facing=True,
                    reason=row.get("reason"),
                )
            )

        for alias in reference.get("forbiddenUserFacingAliases", []):
            terms.append(
                TerminologyTerm(
                    key=f"compatibilityAliases.{alias}",
                    term_class=TermClass.COMPATIBILITY_ALIAS,
                    zh_cn=alias,
                    english=alias,
                    localization_id=None,
                    source_zh_cn=None,
                    source_english=None,
                    owner="Backend/games/hades2",
                    game_version=target["gameVersion"],
                    steam_build=target["steamBuild"],
                    user_facing=False,
                    reason="Legacy/shorthand form retained only as a compatibility boundary; forbidden in canonical product surfaces.",
                )
            )

        for identifier in ("TalentDrop", "SpellDrop", "MetaCurrencyDrop", "group = special", "group = olympian"):
            terms.append(
                TerminologyTerm(
                    key=f"internalDomain.{identifier}",
                    term_class=TermClass.INTERNAL_DOMAIN,
                    zh_cn=identifier,
                    english=identifier,
                    localization_id=None,
                    source_zh_cn=None,
                    source_english=None,
                    owner="Backend/games/hades2",
                    game_version=target["gameVersion"],
                    steam_build=target["steamBuild"],
                    user_facing=False,
                )
            )

        return cls(tuple(terms), target)

    @classmethod
    def load(cls, path: Path = REFERENCE_PATH) -> "TerminologyRegistry":
        reference = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_reference(reference)


@lru_cache(maxsize=1)
def load_hades2_terminology() -> TerminologyRegistry:
    return TerminologyRegistry.load()
