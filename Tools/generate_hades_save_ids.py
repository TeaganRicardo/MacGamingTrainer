"""Generate versioned Hades II Save Editor identities from installed Lua.

Usage: python3 Tools/generate_hades_save_ids.py PATH/TO/Content/Scripts
Prints the native identity module to stdout. Re-run against the supported game
build, inspect the diff, then replace save_native_ids.py.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path


def read(path):
    data = path.read_bytes()
    return data.decode("utf-8-sig"), hashlib.sha256(data).hexdigest()


def quest_ids(source):
    match = re.search(r"(?ms)^QuestOrderData\s*=\s*\{(.*?)^\}", source)
    if not match:
        raise ValueError("QuestOrderData not found")
    return re.findall(r'(?m)^\s*"(Quest[A-Za-z0-9_]+)"\s*,?', match.group(1))


def resource_ids(source):
    marker = re.search(r"(?m)^ResourceDisplayOrderData\s*=", source)
    if marker is None:
        raise ValueError("ResourceData boundary not found")
    # Run-only resources (for example Money) are cleared at the native
    # death/reset boundary and must not appear as persisted inventory.
    scope = source[:marker.start()]
    entries = list(re.finditer(
        r"(?m)^\t([A-Za-z][A-Za-z0-9_]*)\s*=\s*\n\s*\{",
        scope,
    ))
    persistent = []
    for index, entry in enumerate(entries):
        name = entry.group(1)
        if name.startswith("Base"):
            continue
        end = entries[index + 1].start() if index + 1 < len(entries) else len(scope)
        body = scope[entry.end():end]
        if re.search(r"(?m)^\t\tRunResource\s*=\s*true\b", body):
            continue
        persistent.append(name)
    return persistent


def objective_ids(source):
    section = source.split("ObjectiveSetData =", 1)[0]
    direct = re.findall(r"(?m)^\t([A-Za-z_][A-Za-z0-9_]*)\s*=", section)
    arrays = re.findall(
        r"(?ms)^\t\tObjectives\s*=\s*\n\t\t\{(.*?)^\t\t\},",
        source,
    )
    referenced = [
        name for body in arrays
        for name in re.findall(
            r'(?m)^\s*"([A-Za-z][A-Za-z0-9_]*)"\s*[,;]?\s*$',
            body,
        )
    ]
    return sorted(set(direct) | set(referenced))


def npc_ids(scripts):
    keys = set()
    source_hash = hashlib.sha256()
    files = sorted(scripts.glob("NPCData*.lua"))
    if not files:
        raise ValueError("Native NPCData files not found")
    for path in files:
        source, _ = read(path)
        source_hash.update(path.name.encode("utf-8"))
        source_hash.update(b"\0")
        source_hash.update(path.read_bytes())
        source_hash.update(b"\0")
        keys.update(re.findall(
            r"(?m)^\t(NPC_[A-Za-z0-9_]+)\s*=\s*\n\s*\{", source
        ))
    templates = {"NPC_3DGhostAlt", "NPC_Giftable", "NPC_Neutral", "NPC_LightRanged"}
    return sorted(keys - templates), source_hash.hexdigest()


def render(items):
    lines = []
    for start in range(0, len(items), 5):
        lines.append("    " + ", ".join(json.dumps(name) for name in items[start:start + 5]) + ",")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scripts", type=Path, help="Installed Content/Scripts directory")
    parser.add_argument("--version", default="1.143476")
    parser.add_argument("--steam-build", default="25481925")
    args = parser.parse_args()

    quests_source, quest_hash = read(args.scripts / "QuestData.lua")
    resources_source, resource_hash = read(args.scripts / "ResourceData.lua")
    objectives_source, objective_hash = read(args.scripts / "ObjectiveData.lua")
    quests = quest_ids(quests_source)
    resources = resource_ids(resources_source)
    objectives = objective_ids(objectives_source)
    npcs, npc_hash = npc_ids(args.scripts)

    for label, values in (
        ("quests", quests), ("resources", resources),
        ("objectives", objectives), ("NPCs", npcs),
    ):
        if not values or len(values) != len(set(values)):
            raise ValueError("Missing or duplicated native " + label + " identity")

    print(
        f'"""Native Save Editor identities, generated from Hades II {args.version} / Steam {args.steam_build}.\n\n'
        f'QuestData.lua SHA-256 {quest_hash}\n'
        f'ResourceData.lua SHA-256 {resource_hash}\n'
        f'ObjectiveData.lua SHA-256 {objective_hash}\n'
        f'NPCData*.lua bundle SHA-256 {npc_hash}\n'
        'Quest IDs come from QuestOrderData; resources are top-level ResourceData entries\n'
        'excluding abstract Base* templates. Recheck these IDs on target-build changes.\n'
        '"""\n\n'
        f'QUEST_IDS = frozenset((\n{render(quests)}\n))\n\n'
        f'RESOURCE_IDS = frozenset((\n{render(resources)}\n))'
    )
    print(
        f'\nNPC_INTERACTION_IDS = frozenset((\n{render(npcs)}\n))\n\n'
        f'OBJECTIVE_IDS = frozenset((\n{render(objectives)}\n))'
    )


if __name__ == "__main__":
    main()
