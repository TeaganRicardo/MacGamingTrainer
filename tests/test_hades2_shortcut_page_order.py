from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
TYPES = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text()
NAVIGATION = (ROOT / "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift").read_text()


def view_block(name: str) -> str:
    marker = f"private var {name}: some View {{"
    start = VIEW.index(marker)
    candidates = [
        position for position in (
            VIEW.find("\n    private var ", start + len(marker)),
            VIEW.find("\n    private func ", start + len(marker)),
        )
        if position >= 0
    ]
    end = min(candidates) if candidates else len(VIEW)
    return VIEW[start:end]


def action_refs(source: str) -> list[str]:
    found = re.findall(
        r"\b(?:shortcut|action):\s*\.([A-Za-z][A-Za-z0-9_]*)"
        r"|\bshortcutText\(\.([A-Za-z][A-Za-z0-9_]*)\)",
        source,
    )
    return list(dict.fromkeys(first or second for first, second in found))


def panel_actions(section: str, panels: list[str]) -> list[str]:
    source = view_block(section)
    ordered = sorted(
        (source.index(name), name) for name in panels if name in source
    )
    return [action for _, name in ordered for action in action_refs(view_block(name))]


registry_block = NAVIGATION.split("static let orderedShortcutActions", 1)[1].split(
    "static func shortcutActions", 1
)[0]
registry = re.findall(r"^\s*\.([A-Za-z][A-Za-z0-9_]*),?$", registry_block, re.M)

expected_common = [
    "invincibility", "infiniteHealth", "infiniteMana", "infiniteMoney", "infiniteRerolls",
    "forceEnableRerolls", "instantCastCooldown", "hexAlwaysReady", "infiniteAmmo", "autoMiniGames",
]
assert registry[:10] == expected_common, "The common controls must retain the accepted visible order."

speed_actions = action_refs(view_block("gameSpeedPanel"))
boon_actions = panel_actions(
    "boonsSection", ["boonRarityPanel", "currentRunEffectsPanel", "boonAcquisitionPanel"]
)

resource_name = (
    "resourcesSection"
    if "private var resourcesSection: some View {" in VIEW
    else "resourceSection"
)
resource_actions = action_refs(view_block("resourcePanel"))
resource_section_actions = action_refs(view_block(resource_name))

family_start = TYPES.index("enum Hades2GatheringFamily")
family_lines = TYPES[family_start:].splitlines()
family_case = next(line for line in family_lines if line.strip().startswith("case "))
families = re.findall(r"[A-Za-z][A-Za-z0-9_]*", family_case.split("case", 1)[1])
mapping_start = TYPES.index("var shortcutAction:", family_start)
mapping_end = TYPES.find("\n    }", mapping_start)
family_mapping = dict(
    re.findall(
        r"case \.([A-Za-z][A-Za-z0-9_]*):\s*\.([A-Za-z][A-Za-z0-9_]*)",
        TYPES[mapping_start:mapping_end],
    )
)
gathering_actions = [family_mapping[family] for family in families]

room_actions = panel_actions(
    "roomsSection", ["nextRoomRewardPanel", "nextOccurrencePanel", "rewardSpawningPanel"]
)
actual = (
    registry[:10]
    + speed_actions
    + boon_actions
    + resource_actions
    + gathering_actions
    + resource_section_actions
    + room_actions
    + ["disableAll"]
)
assert len(actual) == len(set(actual)), f"Duplicate visible shortcut action: {actual}"
assert actual == registry, (
    "Default shortcut allocation/settings must follow the actual workbench order. "
    f"Registry={registry}; rendered={actual}"
)
