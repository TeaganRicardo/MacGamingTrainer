"""Generate versioned Hades II Save Editor identities from installed Lua.

Usage: python3 Tools/generate_hades_save_ids.py PATH/TO/Content/Scripts
Prints the native identity module to stdout. Re-run against the supported game
build, inspect the diff, then replace save_native_ids.py.
"""

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from pprint import pformat


def read(path):
    data = path.read_bytes()
    # Parse every native Lua file with the same line boundaries regardless of
    # its on-disk newline convention. Provenance still hashes the original bytes.
    source = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return source, hashlib.sha256(data).hexdigest()


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


def story_reset_text_ids(source):
    section = re.search(r"(?ms)^\s*TextLines\s*=\s*\{(.*?)^\s*\},", source)
    if section is None:
        raise ValueError("StoryResetData.TextLines not found")
    # Lua long comments can contain disabled entries; support --[[...]]
    # and --[=[...]=] without treating their contents as active IDs.
    active = re.sub(r"--\[(=*)\[[\s\S]*?\]\1\]", "", section.group(1))
    return sorted(set(re.findall(
        r'(?m)^[ \t]*"([A-Za-z0-9_]+)"[ \t]*,?[ \t]*(?:--[^\r\n]*)?$',
        active,
    )))


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


def field_meanings(scripts):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Backend"))
    from games.hades2.save_investigation import _ASSIGN, _braces, _masked

    interactions, objectives, hashes, inheritance = defaultdict(set), {}, {}, {}
    direct_interactions = set()
    for path in sorted(scripts.glob("*Data*.lua")):
        source, digest = read(path)
        if "SpecialInteractFunctionName" not in source and path.name != "ObjectiveData.lua":
            continue
        hashes[path.name] = digest
        masked = _masked(source, lua=True)
        parents = {}
        pairs = _braces(masked, parents)
        keys = {match.start(2): match.group(1) for match in _ASSIGN.finditer(masked)}
        properties = defaultdict(dict)
        def container(position):
            return max((start for start, end in pairs.items() if start < position < end), default=None)

        for match in re.finditer(r'\bInheritFrom\s*=\s*\{([^{}]*)\}', source):
            if masked[match.start():match.start() + 11] != "InheritFrom":
                continue
            key = keys.get(container(match.start()), "")
            if key.startswith("NPC_") or key.endswith("Familiar"):
                inheritance[key] = re.findall(r'"([^"]+)"', match.group(1))
        for match in re.finditer(r'\b(Name|SpecialInteractFunctionName|Description)\s*=\s*"([^"\n]+)"', source):
            if masked[match.start():match.start() + len(match.group(1))] != match.group(1):
                continue
            opening = container(match.start())
            if opening is not None:
                properties[opening][match.group(1)] = match.group(2)
        for opening, fields in properties.items():
            if path.name == "ObjectiveData.lua" and "Description" in fields:
                key = keys.get(opening)
                if key in objective_ids(source):
                    objectives[key] = fields["Description"]
            handler = fields.get("SpecialInteractFunctionName")
            if handler is None:
                continue
            cursor = opening
            while cursor is not None:
                name = properties.get(cursor, {}).get("Name")
                key = keys.get(cursor, "")
                if name or key.startswith("NPC_") or key.endswith("Familiar"):
                    identity = name or key
                    interactions[identity].add(handler)
                    if cursor == opening:
                        direct_interactions.add(identity)
                    break
                if cursor == opening and key and key not in ("Args", "OverwriteSelf", "SingingOverwriteSelf", "InspectPoint"):
                    interactions[key].add(handler)
                    break
                cursor = parents[cursor]
    def inherited(key, active):
        if key in active:
            raise ValueError("Cyclic native interaction inheritance: " + key)
        handlers = set(interactions.get(key, ()))
        if key not in direct_interactions:
            for parent in inheritance.get(key, ()):
                handlers.update(inherited(parent, active | {key}))
        return handlers

    for key in inheritance:
        handlers = inherited(key, set())
        if handlers:
            interactions[key].update(handlers)
    return {key: tuple(sorted(value)) for key, value in sorted(interactions.items())}, dict(sorted(objectives.items())), hashes


def render(items):
    lines = []
    for start in range(0, len(items), 5):
        lines.append("    " + ", ".join(json.dumps(name) for name in items[start:start + 5]) + ",")
    return "\n".join(lines)


def render_words(items):
    return "\n".join(" ".join(items[start:start + 8]) for start in range(0, len(items), 8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scripts", type=Path, help="Installed Content/Scripts directory")
    supported = json.loads((Path(__file__).resolve().parents[1] / "Backend/games/hades2/module.json").read_text(encoding="utf-8"))["supportedBuild"]
    parser.add_argument("--version", default="1." + supported["bundleVersion"])
    parser.add_argument("--steam-build", default=supported["steamBuildID"])
    args = parser.parse_args()

    quests_source, quest_hash = read(args.scripts / "QuestData.lua")
    resources_source, resource_hash = read(args.scripts / "ResourceData.lua")
    objectives_source, objective_hash = read(args.scripts / "ObjectiveData.lua")
    reset_source, reset_hash = read(args.scripts / "StoryResetData.lua")
    quests = quest_ids(quests_source)
    resources = resource_ids(resources_source)
    objectives = objective_ids(objectives_source)
    reset_text = story_reset_text_ids(reset_source)
    npcs, npc_hash = npc_ids(args.scripts)
    interactions, objective_names, meaning_hashes = field_meanings(args.scripts)

    for label, values in (
        ("quests", quests), ("resources", resources),
        ("objectives", objectives), ("NPCs", npcs),
        ("story-reset dialogue", reset_text),
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
    print("\n# Native handler/description references; display text stays in official localization.")
    for name, value in (("SAVE_FIELD_SOURCE_SHA256", meaning_hashes),
                        ("SPECIAL_INTERACTION_FUNCTIONS", interactions),
                        ("OBJECTIVE_LOCALIZATION_IDS", objective_names)):
        print("\n" + name + " = " + pformat(value, width=110, sort_dicts=True))

    print(
        "\n# Native StoryResetData.TextLines from target "
        f"{args.version} / Steam {args.steam_build}.\n"
        f"# StoryResetData.lua SHA-256 {reset_hash}\n"
        "# A native-authored reset target is necessary, not sufficient, to authorize an\n"
        "# individual edit: companion narrative/gift/run owners are validated separately.\n"
        f'STORY_RESET_TEXT_IDS = frozenset("""\n{render_words(reset_text)}\n""".split())'
    )


if __name__ == "__main__":
    main()
