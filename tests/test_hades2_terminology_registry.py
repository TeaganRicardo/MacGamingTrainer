from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.terminology import TermClass, TerminologyRegistry, load_hades2_terminology


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
        "forbiddenUserFacingAliases": [],
    }

    try:
        TerminologyRegistry.from_reference(reference)
    except ValueError as exc:
        assert "native term lacks localization provenance" in str(exc)
    else:
        raise AssertionError("registry accepted a native term without English provenance")


print("hades2_terminology_registry_ok")
