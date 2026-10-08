"""Generate versioned Hades II Save Editor identities from installed Lua.

Usage: python3 Tools/generate_hades_save_ids.py PATH/TO/Content/Scripts
Prints the checked native identity module to stdout; redirect to
Backend/games/hades2/save_native_ids.py after reviewing build/version.
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
        raise ValueError("QuestOrderData not found; inspect native format")
    entries = re.findall(r'^\s*"(Quest[A-Za-z0-9_]+)"\s*,?', match.group(1), re.M)
    return entries


def resource_ids(source):
    marker = re.search(r"(?m)^ResourceDisplayOrderData\s*=", source)
    if marker is None:
        raise ValueError("ResourceData block boundary not found")
    entries = re.findall(
        r"(?m)^\t([A-Za-z][A-Za-z0-9_]*)\s*=\s*\n\s*\{",
        source[:marker.start()],
    )
    return [entry for entry in entries if not entry.startswith("Base")]


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
    quests = quest_ids(quests_source)
    resources = resource_ids(resources_source)
    if not quests or not resources or len(set(quests)) != len(quests) or len(set(resources)) != len(resources):
        raise ValueError("Missing or duplicated native identities; inspect source")
    print(
        f'"""Native Save Editor identities, generated from Hades II {args.version} / Steam {args.steam_build}.\n\n'
        f'QuestData.lua SHA-256 {quest_hash}\n'
        f'ResourceData.lua SHA-256 {resource_hash}\n'
        'Quest IDs come from QuestOrderData; resources are top-level ResourceData entries\n'
        'excluding abstract Base* templates. Recheck these IDs on target-build changes.\n'
        '"""\n\n'
        f'QUEST_IDS = frozenset((\n{render(quests)}\n))\n\n'
        f'RESOURCE_IDS = frozenset((\n{render(resources)}\n))'
    )


if __name__ == "__main__":
    main()
