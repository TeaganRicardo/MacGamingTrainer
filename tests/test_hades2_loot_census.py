from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs/reference/hades2/1.139672-24556151"
LOOT_CSV = SNAPSHOT / "generated/loot.csv"
LEGALITY_CSV = SNAPSHOT / "catalog_legality.csv"


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


loot_rows = read_csv(LOOT_CSV)
legality_rows = read_csv(LEGALITY_CSV)

# LootSetData is copied into the runtime LootData table with OverwriteTableKeys,
# so the generated snapshot intentionally contains both table views. Census
# completeness is therefore defined on unique runtime ids, not raw row count.
unique_loot_ids = {row["id"] for row in loot_rows}
non_targets = {"BaseLoot", "BaseSoundPackage", "Using"}
concrete_loot_ids = unique_loot_ids - non_targets

classified_loot_ids = {
    row["id"] for row in legality_rows if row["kind"] == "loot"
}

assert len(loot_rows) == 38
assert len(unique_loot_ids) == 19
assert len(concrete_loot_ids) == 16
assert concrete_loot_ids == classified_loot_ids, (
    sorted(concrete_loot_ids - classified_loot_ids),
    sorted(classified_loot_ids - concrete_loot_ids),
)

# All regular Olympian LootData objects are concrete direct targets. The
# abstract RewardStoreData "Boon" selector is tracked separately as an alias.
olympian_loot_ids = {
    "ZeusUpgrade",
    "HeraUpgrade",
    "PoseidonUpgrade",
    "DemeterUpgrade",
    "ApolloUpgrade",
    "AphroditeUpgrade",
    "HephaestusUpgrade",
    "HestiaUpgrade",
    "AresUpgrade",
    "HermesUpgrade",
}
legality_by_id = {row["id"]: row for row in legality_rows}
for identifier in olympian_loot_ids:
    assert legality_by_id[identifier]["classification"] == "direct", identifier

for identifier in non_targets:
    assert identifier not in classified_loot_ids

print("hades2_loot_census_ok")
