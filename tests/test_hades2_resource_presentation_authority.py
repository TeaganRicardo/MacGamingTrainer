import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import catalog, localization


def localized(payload, zh, en):
    original = localization.official_display_names

    def fake_names(identifiers, language="zh-CN", game_path=None):
        source = zh if language == "zh-CN" else en if language == "en" else {}
        return {key: source[key] for key in identifiers if key in source}

    localization.official_display_names = fake_names
    try:
        return catalog.localize_catalog(payload)
    finally:
        localization.official_display_names = original


# The resident/runtime side owns stable resource identity and live values only.
# Presentation resolves after the transport boundary from the current installed
# game's localization identity, never from a resident-authored historical name.
official = localized(
    {
        "resources": [{
            "id": "MetaCurrency",
            "displayId": "MetaCurrency",
            "name": "过期骨头",
            "englishName": "stale bones",
            "sectionId": "InventoryScreen_GardenTab",
            "sectionKind": "plants",
        }]
    },
    {
        "MetaCurrency": "骨骸",
        "InventoryScreen_GardenTab": "花园",
    },
    {
        "MetaCurrency": "Bones",
        "InventoryScreen_GardenTab": "Garden",
    },
)
row = official["resources"][0]
assert row["name"] == "骨骸"
assert row["englishName"] == "Bones"
assert row["nameSource"] == "official_zh"
assert row["englishNameSource"] == "official_en"
assert row["sectionTitle"] == "花园"
assert row["englishSectionTitle"] == "Garden"
assert row["sectionTitleSource"] == "official_zh"
assert row["englishSectionTitleSource"] == "official_en"

# One missing language falls back to the other language resolved from the same
# current-build localization identity instead of reviving a stale historical
# resident table.
english_only = localized(
    {
        "resources": [{
            "id": "MetaCurrency",
            "displayId": "MetaCurrency",
            "name": "过期骨头",
            "sectionKind": "resources",
        }]
    },
    {},
    {"MetaCurrency": "Bones"},
)
row = english_only["resources"][0]
assert row["name"] == "Bones"
assert row["englishName"] == "Bones"
assert row["nameSource"] == "official_en_fallback"
assert row["englishNameSource"] == "official_en"

chinese_only = localized(
    {
        "resources": [{
            "id": "MetaCurrency",
            "displayId": "MetaCurrency",
            "englishName": "stale bones",
            "sectionKind": "resources",
        }]
    },
    {"MetaCurrency": "骨骸"},
    {},
)
row = chinese_only["resources"][0]
assert row["name"] == "骨骸"
assert row["englishName"] == "骨骸"
assert row["nameSource"] == "official_zh"
assert row["englishNameSource"] == "official_zh_fallback"

# If neither installed language can name a future resource, the product fallback
# is explicit, bilingual and keeps the stable id visible for diagnosis.
unknown = localized(
    {
        "resources": [{
            "id": "FutureResource",
            "displayId": "FutureResourceTitle",
            "sectionKind": "fish",
        }]
    },
    {},
    {},
)
row = unknown["resources"][0]
assert row["name"] == "未知资源 · FutureResource"
assert row["englishName"] == "Unknown Resource · FutureResource"
assert row["nameSource"] == "trainer_generic_zh"
assert row["englishNameSource"] == "trainer_generic_en"
assert row["sectionTitle"] == "鱼类"
assert row["englishSectionTitle"] == "Fish"
assert row["sectionTitleSource"] == "trainer_product_zh"
assert row["englishSectionTitleSource"] == "trainer_product_en"

# The resident source must not remain a second resource-name catalog. It emits
# stable presentation identities, while the Swift view selects the localized
# section supplied by the Hades presentation boundary.
lua = (ROOT / "Backend/games/hades2/runtime/hades.lua").read_text(encoding="utf-8")
assert "Resource DisplayName values from build 1.139672" not in lua
assert "name = names[id] or id" not in lua
assert "displayId =" in lua
assert "sectionId =" in lua
assert "sectionKind =" in lua

view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
assert "localization.language == .en ? item.englishSectionTitle : item.sectionTitle" in view

print("hades2_resource_presentation_authority_ok")
