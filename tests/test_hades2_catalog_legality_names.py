import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/reference/hades2/1.139672-24556151"
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.localization import _clean_display_name


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


ledger = {row["id"]: row for row in read_csv(SNAPSHOT / "catalog_legality.csv")}
loot = {row["id"]: row for row in read_csv(SNAPSHOT / "generated/loot.csv")}
consumables = {row["id"]: row for row in read_csv(SNAPSHOT / "generated/consumables.csv")}

# Curated official names are presentation-ready facts. Raw SJSON markup must
# not leak into the ledger even when generated extraction intentionally keeps it.
for identifier, row in ledger.items():
    name = row["official_name_zh_cn"]
    if name:
        assert name == _clean_display_name(name), (identifier, name)

# Hermes loot and its shop wrapper are distinct catalog identities. Compare the
# curated ledger to independently generated rows so the `_Store` presentation
# name cannot drift onto the base LootData identity again.
assert ledger["HermesUpgrade"]["official_name_zh_cn"] == _clean_display_name(
    loot["HermesUpgrade"]["display_name_zh_cn"]
)
assert ledger["ShopHermesUpgrade"]["official_name_zh_cn"] == _clean_display_name(
    consumables["ShopHermesUpgrade"]["display_name_zh_cn"]
)

# SpellDrop is an intentional player-facing linked identity: the internal loot
# object resolves as Selene, while the curated reward label remains Gift of the Moon.
assert ledger["SpellDrop"]["official_name_zh_cn"] == "月之礼赠"

print("hades2_catalog_legality_names_ok")
