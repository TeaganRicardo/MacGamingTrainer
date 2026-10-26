"""Native Hades resource-gain and fish-record command validation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import AdapterError
from games.hades.adapter import HadesAdapter
from games.hades.schema import FISH_BIOMES, FISH_QUALITIES, MUTATING_COMMANDS, ONE_SHOT_COMMANDS


assert {"add_resource", "record_fish"} <= ONE_SHOT_COMMANDS
assert {"add_resource", "record_fish"} <= MUTATING_COMMANDS
assert FISH_BIOMES == {"Tartarus", "Asphodel", "Elysium", "Styx", "Secrets", "Surface"}
assert FISH_QUALITIES == {"Good", "Perfect"}

assert HadesAdapter._mutation_params(
    "add_resource", {"resource": "MetaPoints", "amount": 50}
) == {"resource": "MetaPoints", "amount": 50}
assert HadesAdapter._mutation_params(
    "record_fish", {"biome": "Secrets", "quality": "Perfect"}
) == {"biome": "Secrets", "quality": "Perfect"}


def rejected(command, params):
    try:
        HadesAdapter._mutation_params(command, params)
    except AdapterError as error:
        assert error.code == "invalid_value"
    else:
        raise AssertionError(f"{command} accepted invalid parameters: {params!r}")


for params in (
    {"resource": "unknown", "amount": 1},
    {"resource": "MetaPoints", "amount": 0},
    {"resource": "MetaPoints", "amount": 1_000_001},
    {"resource": "MetaPoints", "amount": True},
):
    rejected("add_resource", params)
for params in (
    {"biome": "UnknownBiome", "quality": "Good"},
    {"biome": "Tartarus", "quality": "Legendary"},
    {"biome": ["Tartarus"], "quality": "Good"},
):
    rejected("record_fish", params)

print("hades_native_gathering_contract_ok")
