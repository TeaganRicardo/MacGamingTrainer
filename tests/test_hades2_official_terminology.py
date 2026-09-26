import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import catalog, localization
from games.hades2.terminology import TermClass, load_hades2_terminology

reference = json.loads(
    (ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json").read_text(encoding="utf-8")
)

assert reference["target"]["languages"] == ["zh-CN", "en"]
for group in ("officialTerms", "nativeChoiceTitles", "officialSourceNames"):
    for row in reference[group].values():
        assert row["id"]
        assert row["value"]
        assert row["englishValue"]
        assert row["source"].endswith(".zh-CN.sjson")
        assert row["englishSource"].endswith(".en.sjson")
for row in reference["productTerms"].values():
    assert row["status"] == "trainer_product_label"
    assert row["value"] and row["englishValue"]

expected_source_ids = {
    source: row["id"] for source, row in reference["officialSourceNames"].items()
}
expected_choice_title_ids = {
    source: row["id"] for source, row in reference["nativeChoiceTitles"].items()
    if source != "SeleneTalents"
}
assert catalog._SPECIAL_SOURCE_LOCALIZATION_IDS == expected_source_ids
assert catalog._NATIVE_CHOICE_TITLE_IDS == expected_choice_title_ids
assert catalog._OLYMPIAN_BOON_TITLE_ID == reference["officialTerms"]["olympianBoons"]["id"]
assert catalog._CHARACTER_REWARD_CATEGORY == reference["productTerms"]["characterRewards"]["value"]
assert catalog._CHARACTER_REWARD_CATEGORY_EN == reference["productTerms"]["characterRewards"]["englishValue"]
assert catalog._OFFICIAL_CATEGORY_TITLE_IDS["卡戎之井"] == reference["officialTerms"]["wellOfCharon"]["id"]
for row in reference["productTerms"].values():
    assert catalog._PRODUCT_LABEL_EN_BY_ZH[row["value"]] == row["englishValue"]

# Current Hades product surfaces must not reintroduce known ad-hoc aliases.
surface_paths = sorted((ROOT / "Sources/Hades2").rglob("*.swift"))
surface_paths += sorted((ROOT / "Backend/games/hades2").glob("*.py"))
surface_paths += [ROOT / "Backend/games/hades2/runtime/hades.lua"]
reference_dir = ROOT / "docs/reference/hades2/1.139672-24556151"
surface_paths += sorted(reference_dir.glob("*.md"))
surface_paths += sorted(reference_dir.glob("*.csv"))
surface_paths += [ROOT / "docs/reference/hades2/README.md"]
surface_text = "\n".join(path.read_text(encoding="utf-8") for path in surface_paths)
for alias in load_hades2_terminology().by_class(TermClass.COMPATIBILITY_ALIAS):
    assert alias.zh_cn not in surface_text, alias.key

# Both languages resolve from the same target-build localization IDs.
official_zh = {}
official_en = {}
for group in ("officialTerms", "nativeChoiceTitles", "officialSourceNames"):
    for row in reference[group].values():
        official_zh[row["id"]] = row["value"]
        official_en[row["id"]] = row["englishValue"]

original = localization.official_display_names
def fake_names(ids, language="zh-CN", game_path=None):
    mapping = official_zh if language == "zh-CN" else official_en if language == "en" else {}
    return {key: value for key, value in mapping.items() if key in ids}

localization.official_display_names = fake_names
try:
    payload = {
        "rewards": [
            {
                "id": "trait:CritBonusBoon", "trait": "CritBonusBoon", "kind": "trait",
                "group": "special", "sourceId": "Artemis", "sourceName": "legacy Artemis",
                "sectionTitle": "legacy Artemis", "category": "legacy special",
                "nativeChoice": True, "name": "CritBonusBoon",
            },
            {
                "id": "trait:AgilityCostume", "trait": "AgilityCostume", "kind": "trait",
                "group": "special", "sourceId": "Arachne", "sourceName": "legacy Arachne",
                "sectionTitle": "legacy Arachne", "category": "legacy special",
                "nativeChoice": True, "name": "AgilityCostume",
            },
            {
                "id": "ZeusUpgrade", "kind": "loot", "group": "olympian",
                "category": "legacy gods", "sectionTitle": "legacy gods", "name": "ZeusUpgrade",
            },
            {
                "id": "trait:TemporaryHealTrait", "trait": "TemporaryHealTrait", "kind": "trait",
                "group": "pickup", "category": "卡戎之井", "sectionTitle": "卡戎之井",
                "name": "TemporaryHealTrait",
            },
        ],
        "resources": [
            {"id": "MetaCurrency", "name": "MetaCurrency", "sectionTitle": "资源"}
        ],
    }
    result = catalog.localize_catalog(payload)
finally:
    localization.official_display_names = original

artemis, arachne, olympian, well = result["rewards"]
assert artemis["sourceName"] == "阿尔忒弥斯"
assert artemis["sourceEnglishName"] == "Artemis"
assert artemis["sectionTitle"] == "阿尔忒弥斯"
assert artemis["englishSectionTitle"] == "Artemis"
assert artemis["nativeChoiceTitle"] == "阿尔忒弥斯的祝福"
assert artemis["nativeChoiceEnglishTitle"] == "Boons of Artemis"
assert artemis["category"] == "角色奖励"
assert artemis["englishCategory"] == "Character Rewards"
assert arachne["sourceName"] == "阿拉克涅"
assert arachne["sourceEnglishName"] == "Arachne"
assert arachne["nativeChoiceTitle"] == "丝绸华服"
assert arachne["nativeChoiceEnglishTitle"] == "Silken Fineries"
assert olympian["category"] == "奥林匹斯的祝福"
assert olympian["englishCategory"] == "Boon of Olympus"
assert olympian["sectionTitle"] == "奥林匹斯诸神"
assert olympian["englishSectionTitle"] == "Olympians"
assert well["englishCategory"] == "Well of Charon"
assert well["englishSectionTitle"] == "Well of Charon"
assert result["resources"][0]["englishSectionTitle"] == "Resources"

state = (ROOT / "Sources/Hades2/Hades2BackendState.swift").read_text(encoding="utf-8")
model = (ROOT / "Sources/Hades2/Hades2Model.swift").read_text(encoding="utf-8")
view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
types = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text(encoding="utf-8")
for declaration in (
    "let englishCategory: String", "let englishSectionTitle: String",
    "let sourceEnglishName: String", "let nativeChoiceEnglishTitle: String",
):
    assert declaration in types
assert 'englishCategory: row["englishCategory"] as? String ?? "Boon"' in state
assert 'englishSectionTitle: row["englishSectionTitle"] as? String ?? ""' in state
assert 'sourceEnglishName: row["sourceEnglishName"] as? String ?? ""' in state
assert 'nativeChoiceEnglishTitle: row["nativeChoiceEnglishTitle"] as? String ?? ""' in state
assert "option.nativeChoiceEnglishTitle" in model
assert "$0.englishCategory.localizedCaseInsensitiveContains(specialSearch)" in view
assert "净化之池" in model and "净化之池" in view
assert "角色奖励" in view and "奥林匹斯的祝福" in view
assert "重塑命运" in view
assert "生成奥林匹斯的祝福" in types
assert "生成角色奖励" in types

print("hades2_official_terminology_ok")
