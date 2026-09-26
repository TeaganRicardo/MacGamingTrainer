import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.terminology import (
    TermClass,
    TermLifecycle,
    TermSurface,
    TerminologyRegistry,
    load_hades2_terminology,
)


def test_registry_loads_target_build_and_all_term_classes():
    registry = load_hades2_terminology()

    assert registry.target == {
        "gameVersion": "1.139672",
        "steamBuild": "24556151",
        "languages": ["zh-CN", "en"],
    }
    assert registry.by_class(TermClass.NATIVE_GAME)
    assert registry.by_class(TermClass.TRAINER_PRODUCT)
    assert registry.by_class(TermClass.INTERNAL_DOMAIN)
    assert registry.by_class(TermClass.COMPATIBILITY_ALIAS)


def test_native_terms_keep_shared_localization_provenance():
    registry = load_hades2_terminology()

    for term in registry.by_class(TermClass.NATIVE_GAME):
        assert term.localization_id
        assert term.source_zh_cn.endswith(".zh-CN.sjson")
        assert term.source_english.endswith(".en.sjson")
        assert term.user_facing is True

    olympian = registry.get("officialTerms.olympianBoons")
    assert olympian.localization_id == "Boon"
    assert olympian.zh_cn == "奥林匹斯的祝福"
    assert olympian.english == "Boon of Olympus"


def test_product_terms_are_explicit_trainer_owned_pairs():
    registry = load_hades2_terminology()

    for term in registry.by_class(TermClass.TRAINER_PRODUCT):
        assert term.localization_id is None
        assert term.source_zh_cn is None
        assert term.source_english is None
        assert term.reason
        assert term.user_facing is True

    character_rewards = registry.get("productTerms.characterRewards")
    assert character_rewards.zh_cn == "角色奖励"
    assert character_rewards.english == "Character Rewards"


def test_legacy_aliases_and_internal_terms_are_not_user_facing():
    registry = load_hades2_terminology()

    aliases = registry.by_class(TermClass.COMPATIBILITY_ALIAS)
    assert {term.zh_cn for term in aliases} >= {
        "特殊祝福",
        "诸神祝福",
        "重骰",
        "祝福出售界面",
        "出售祝福",
        "原生三选一",
        "卡俄斯祝福",
    }
    assert all(not term.user_facing for term in aliases)

    internal = registry.by_class(TermClass.INTERNAL_DOMAIN)
    assert {term.zh_cn for term in internal} == {
        "TalentDrop",
        "SpellDrop",
        "MetaCurrencyDrop",
        "group = special",
        "group = olympian",
    }
    assert all(not term.user_facing for term in internal)


def test_registry_rejects_native_term_without_provenance():
    reference = {
        "target": {"gameVersion": "1.139672", "steamBuild": "24556151", "languages": ["zh-CN", "en"]},
        "officialTerms": {
            "broken": {
                "value": "坏术语",
                "englishValue": "Broken Term",
                "id": "Broken",
                "source": "HelpText.zh-CN.sjson",
            }
        },
        "nativeChoiceTitles": {},
        "officialSourceNames": {},
        "productTerms": {},
        "internalTerms": {},
        "compatibilityAliases": {},
        "registry": {
            "owner": "Backend/games/hades2",
            "classPolicies": {
                "native_game": {"lifecycle": "active", "allowedSurfaces": ["user_ui"], "forbiddenSurfaces": []},
                "trainer_product": {"lifecycle": "active", "allowedSurfaces": ["user_ui"], "forbiddenSurfaces": ["protocol"]},
                "internal_domain": {"lifecycle": "active", "allowedSurfaces": ["protocol"], "forbiddenSurfaces": ["user_ui"]},
                "compatibility_alias": {"lifecycle": "compatibility", "allowedSurfaces": ["compatibility_input"], "forbiddenSurfaces": ["user_ui"]},
            },
        },
    }

    try:
        TerminologyRegistry.from_reference(reference)
    except ValueError as exc:
        assert "native term lacks localization provenance" in str(exc)
    else:
        raise AssertionError("registry accepted a native term without English provenance")


def test_registry_tracks_policy_lifecycle_alias_targets_and_internal_terms():
    registry = load_hades2_terminology()

    alias = registry.get("compatibilityAliases.specialBoon")
    assert alias.alias_of == "productTerms.characterRewards"
    assert alias.lifecycle is TermLifecycle.COMPATIBILITY
    assert TermSurface.COMPATIBILITY_INPUT in alias.allowed_surfaces
    assert TermSurface.USER_UI in alias.forbidden_surfaces

    internal = registry.get("internalTerms.talentDrop")
    assert internal.owner == "Backend/games/hades2"
    assert internal.lifecycle is TermLifecycle.ACTIVE
    assert TermSurface.USER_UI in internal.forbidden_surfaces

    native = registry.get("officialTerms.boon")
    assert native.lifecycle is TermLifecycle.ACTIVE
    assert TermSurface.USER_UI in native.allowed_surfaces


def test_registry_rejects_mismatched_native_bilingual_source_pair():
    reference_path = ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["officialTerms"]["boon"]["englishSource"] = "TraitText.en.sjson"

    try:
        TerminologyRegistry.from_reference(reference)
    except ValueError as exc:
        assert "bilingual source mismatch" in str(exc)
    else:
        raise AssertionError("registry accepted native zh-CN/en values from different localization tables")


def test_registry_reports_forbidden_surface_leakage_from_registry_policy():
    registry = load_hades2_terminology()

    leaks = registry.surface_leaks(TermSurface.USER_UI, "按钮：特殊祝福 / TalentDrop")
    assert {term.key for term in leaks} == {
        "compatibilityAliases.specialBoon",
        "internalTerms.talentDrop",
    }
    assert registry.surface_leaks(TermSurface.USER_UI, "角色奖励 / Character Rewards") == ()


def test_aliases_have_one_authoritative_registry_representation():
    reference_path = ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    assert "forbiddenUserFacingAliases" not in reference
    assert {row["value"] for row in reference["compatibilityAliases"].values()} == {
        term.zh_cn for term in load_hades2_terminology().by_class(TermClass.COMPATIBILITY_ALIAS)
    }


def test_registry_rejects_alias_target_regression():
    reference_path = ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference["compatibilityAliases"]["specialBoon"]["canonicalTerm"] = "productTerms.missing"

    try:
        TerminologyRegistry.from_reference(reference)
    except ValueError as exc:
        assert "valid canonical target" in str(exc)
    else:
        raise AssertionError("registry accepted an alias whose canonical target disappeared")


for _test in (
    test_registry_loads_target_build_and_all_term_classes,
    test_native_terms_keep_shared_localization_provenance,
    test_product_terms_are_explicit_trainer_owned_pairs,
    test_legacy_aliases_and_internal_terms_are_not_user_facing,
    test_registry_rejects_native_term_without_provenance,
    test_registry_tracks_policy_lifecycle_alias_targets_and_internal_terms,
    test_registry_rejects_mismatched_native_bilingual_source_pair,
    test_registry_reports_forbidden_surface_leakage_from_registry_policy,
    test_aliases_have_one_authoritative_registry_representation,
    test_registry_rejects_alias_target_regression,
):
    _test()

print("hades2_terminology_registry_ok")
