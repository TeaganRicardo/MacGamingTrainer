"""Entity-first Save query contracts: stable groups, bilingual match and bounded pages."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_entities import entity_page


def row(identifier, name, *, entity=None, title=None, value=1, english=None):
    return {
        "id": identifier, "domain": "resources", "rawId": identifier,
        "name": name, "englishName": english or name, "value": value,
        "valueType": "integer", "editable": True, "mutationKinds": ["set"],
        "path": ["GameState", "Resources", identifier],
        **({"entityId": entity, "entityName": title} if entity else {}),
    }


# The old 100-field page boundary must never divide a recognized entity.
multi = [row(f"field:{i:03d}", f"Field {i}", entity="person:Nemesis", title="Nemesis")
         for i in range(112)]
other = row("resource:MetaCurrency", "Zeus Ashes")
result = entity_page([*multi, other], search="", offset=0, limit=1)
assert result["total"] == 2
assert result["hasMore"] is True
assert len(result["entities"]) == 1
assert result["entities"][0]["id"] == "person:Nemesis"
assert len(result["entities"][0]["items"]) == 112
second = entity_page([*multi, other], search="", offset=1, limit=1)
assert second["entities"][0]["id"] == "entry:resource:MetaCurrency"
assert len(second["entities"][0]["items"]) == 1

# Searching either locale should return one entity with ALL its owner fields.
aliases = {"field:111": ("复仇女神",), "resource:MetaCurrency": ("灰烬",)}
found = entity_page([*multi, other], search="复仇女神", offset=0, limit=1, aliases=aliases)
assert found["total"] == 1
assert found["entities"][0]["id"] == "person:Nemesis"
assert len(found["entities"][0]["items"]) == 112
assert entity_page([*multi, other], search="ash", offset=0, limit=20)["total"] == 1
assert entity_page([*multi, other], search="灰烬", offset=0, limit=20, aliases=aliases)["total"] == 1

# Empty browse results must not flood with zero/absent rows. Deliberate search
# must still expose a supported missing value that the player can edit.
zero = row("resource:GiftPoints", "Nectar", value=0)
assert entity_page([zero], search="", offset=0, limit=10)["total"] == 0
assert entity_page([zero], search="Nectar", offset=0, limit=10)["total"] == 1

read_only = row("dialogue:Example", "Played dialogue", value=True)
read_only["editable"] = False
read_only["mutationKinds"] = []
assert entity_page([read_only], search="", offset=0, limit=10)["total"] == 0
assert entity_page([read_only], search="Played", offset=0, limit=10)["total"] == 1

# Stable physical ids, not display labels or positional keys, own grouping.
dupes = [row("a", "Shared", entity="weapon:Dagger", title="Same"),
         row("b", "Shared", entity="weapon:Torch", title="Same")]
grouped = entity_page(dupes, search="same", offset=0, limit=10)
assert [item["id"] for item in grouped["entities"]] == ["weapon:Dagger", "weapon:Torch"]
assert sum(len(item["items"]) for item in grouped["entities"]) == 2

# A player combines an owner and a field name, rather than reproducing the
# punctuation/order of the displayed title. Every word must match the entity.
found = entity_page([*multi, other], search="Nemesis Field 111", offset=0, limit=10)
assert [item["id"] for item in found["entities"]] == ["person:Nemesis"], (
    "search cannot combine a character name with the field being edited"
)
assert len(found["entities"][0]["items"]) == 112
assert entity_page([*multi, other], search="Nemesis absentword", offset=0, limit=10)["total"] == 0
print("save entity pagination, identity and cross-language search: PASS")
