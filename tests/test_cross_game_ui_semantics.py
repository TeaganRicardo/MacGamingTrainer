"""Cross-game presentation/icon semantics stay aligned to the Hades II authority."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

reference_path = ROOT / "docs/reference/hades2/1.143476-25481925/ui_terminology.json"
reference = json.loads(reference_path.read_text())
hades_presentation = (ROOT / "Sources/Hades/HadesPresentation.swift").read_text()

pair_pattern = re.compile(
    r'"([^"]+)":\s*\.init\(zhCN:\s*"([^"]*)",\s*en:\s*"([^"]*)"\)'
)
hades_labels = {
    key: {"zh-CN": zh, "en": en}
    for key, zh, en in pair_pattern.findall(hades_presentation)
}

def hades2_labels(language: str) -> dict[str, str]:
    field = "value" if language == "zh-CN" else "englishValue"
    entries = json.loads(
        (ROOT / f"Sources/Hades2/Presentation/Localization/hades2.{language}.json").read_text()
    )["entries"]

    def expand(value: str) -> str:
        def resolve(match: re.Match[str]) -> str:
            group, identity = match.group(1).split(".", 1)
            return reference[group][identity][field]
        return re.sub(r"\{term:([^}]+)\}", resolve, value)

    return {key: expand(value) for key, value in entries.items()}

hades2 = {language: hades2_labels(language) for language in ("zh-CN", "en")}

# Shared product concepts use Hades II wording exactly. Native game-specific
# terms remain module-owned and are intentionally not forced into this table.
shared_labels = {
    "hades.section.runData": "hades2.section.runData",
    "hades.section.common": "hades2.section.common",
    "hades.section.boonsAndEffects": "hades2.section.boonsAndEffects",
    "hades.section.resourcesAndGathering": "hades2.section.resourcesAndGathering",
    "hades.section.roomsAndRewards": "hades2.section.roomsAndRewards",
    "hades.management": "hades2.section.management",
    "hades.section.expand": "hades2.section.expand",
    "hades.section.collapse": "hades2.section.collapse",
    "hades.workbench.search": "hades2.workbench.search",
    "hades.workbench.searchEmpty": "hades2.workbench.searchEmpty",
    "hades.manage.daily": "hades2.manage.daily",
    "hades.manage.settings": "hades2.manage.settings",
    "hades.manage.maintenance": "hades2.manage.maintenance",
    "hades.manage.profiles": "hades2.manage.profiles",
    "hades.manage.diagnostics": "hades2.manage.diagnostics",
    "hades.profile.save": "hades2.profile.saveCurrent",
    "hades.profile.load": "hades2.profile.load",
    "hades.profile.empty": "hades2.profile.empty",
    "hades.diagnostics.export": "hades2.diagnostics.export",
    "hades.saveEditor.title": "hades2.saveEditor.title",
    "hades.invincibility": "hades2.feature.invincibility",
    "hades.fullHealth": "hades2.feature.infiniteHealth",
    "hades.moneyNoDecrease": "hades2.feature.infiniteMoney",
    "hades.rerollsNoDecrease": "hades2.feature.infiniteRerolls",
    "hades.infiniteAmmo": "hades2.feature.infiniteAmmo",
    "hades.forceRerolls": "hades2.feature.forceEnableRerolls",
    "hades.boonRarityEnabled": "hades2.feature.boonRarity",
    "hades.damageMultiplier": "hades2.feature.damageMultiplier",
    "hades.moveSpeedMultiplier": "hades2.stat.moveSpeed",
    "hades.attackSpeedMultiplier": "hades2.stat.attackSpeed",
}
for hades_key, hades2_key in shared_labels.items():
    assert hades_key in hades_labels, f"missing Hades presentation key: {hades_key}"
    for language in ("zh-CN", "en"):
        actual = hades_labels[hades_key][language]
        expected = hades2[language][hades2_key]
        assert actual == expected, (
            f"{language} shared label drift: {hades_key}={actual!r}, "
            f"Hades II {hades2_key}={expected!r}"
        )

hades2_presentation = (ROOT / "Sources/Hades2/Presentation/Hades2Presentation.swift").read_text()
assert "1.143476-25481925/ui_terminology.json" in hades2_presentation
assert "1.139672-24556151/ui_terminology.json" not in hades2_presentation

# Heal Fully was a redundant one-shot beside the durable Infinite Life control.
# It is retired end-to-end; only the preference migration tombstone may retain
# its old identity so existing installations stop carrying the obsolete chord.
hades_types = (ROOT / "Sources/Hades/HadesTypes.swift").read_text()
hades_module = (ROOT / "Sources/Hades/HadesModule.swift").read_text()
hades_nav = (ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift").read_text()
hades_view = (ROOT / "Sources/Hades/HadesTrainerView.swift").read_text()
hades_adapter = (ROOT / "Backend/games/hades/adapter.py").read_text()
hades_schema = (ROOT / "Backend/games/hades/schema.py").read_text()
hades_runtime = (ROOT / "Backend/games/hades/runtime.lua").read_text()

assert "case invincibility, heal," not in hades_types
assert ".heal," not in hades_nav
assert "func heal()" not in hades_module
assert '"hades.heal"' not in hades_presentation
assert '"hades.heal"' not in hades_view
assert "function runtime.heal()" not in hades_runtime
assert "command == 'heal'" not in hades_adapter
assert "'set_value', 'heal', 'set_resource'" not in hades_schema
assert 'removeObject(forKey: "hades.shortcut.heal")' in hades_types
assert "HotkeyChord.defaultShortcut(index: HadesWorkbenchCatalog.orderedShortcutActions.firstIndex(of: self)!)" in hades_types
assert re.search(
    r"orderedShortcutActions:\s*\[HadesShortcutAction\]\s*=\s*\[\s*\.invincibility,\s*\.fullHealth,",
    hades_nav,
), "Hades default shortcut order must start with visible Invincibility / Infinite Life"

# Shared concepts must resolve through one Core semantic icon vocabulary rather
# than each module independently choosing an SF Symbol literal.
icon_source = (ROOT / "Sources/Core/UI/TrainerSemanticIcon.swift").read_text()
for semantic in (
    "protection", "vitality", "energy", "currency", "randomize",
    "refresh", "capacity", "quality", "impact", "movement",
    "actionSpeed", "timeScale", "item",
):
    assert f"static let {semantic} =" in icon_source
for semantic in ("acquire", "apply", "generate", "save", "load", "remove", "restore"):
    assert f"static let {semantic} =" in icon_source
for forbidden in ("Hades", "invincibility", "boonRarity", "reroll"):
    assert forbidden not in icon_source, f"Core icon vocabulary leaked game meaning: {forbidden}"

hades2_types = (ROOT / "Sources/Hades2/Hades2Types.swift").read_text()
paired_icons = {
    "invincibility": "protection",
    "fullHealth": "vitality",
    "moneyNoDecrease": "currency",
    "rerollsNoDecrease": "randomize",
    "forceRerolls": "refresh",
    "infiniteAmmo": "capacity",
    "boonRarityEnabled": "quality",
    "damageMultiplier": "impact",
    "moveSpeedMultiplier": "movement",
    "attackSpeedMultiplier": "actionSpeed",
    "gameSpeed": "timeScale",
}
for hades_case, semantic in paired_icons.items():
    assert f"case .{hades_case}: return TrainerSemanticIcon.Concept.{semantic}" in hades_nav

hades2_nav = (ROOT / "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift").read_text()
hades2_common_icons = {
    "invincibility": "protection",
    "infiniteHealth": "vitality",
    "infiniteMana": "energy",
    "infiniteMoney": "currency",
    "infiniteRerolls": "randomize",
    "forceEnableRerolls": "refresh",
    "infiniteAmmo": "capacity",
}
for h2_case, semantic in hades2_common_icons.items():
    assert f"case .{h2_case}: TrainerSemanticIcon.Concept.{semantic}" in hades2_nav

hades2_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
for semantic in ("impact", "movement", "actionSpeed", "timeScale"):
    assert f"TrainerSemanticIcon.Concept.{semantic}" in hades2_view

for path in (
    ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift",
    ROOT / "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift",
):
    source = path.read_text()
    for semantic in ("metrics", "general", "effects", "inventory", "navigation", "settings"):
        assert f"TrainerSemanticIcon.Section.{semantic}" in source

for path in (
    ROOT / "Sources/Hades/HadesManagement.swift",
    ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift",
):
    source = path.read_text()
    for semantic in ("saveEditor", "saveManagement", "disableAll", "profiles", "shortcuts", "log", "diagnostics"):
        assert f"TrainerSemanticIcon.Tool.{semantic}" in source

# Every shortcut-visible function owns one icon. The same action icon is reused
# in shortcut settings and function discovery instead of being redrawn there.
assert "extension HadesFeature {" in hades_nav
assert "extension HadesShortcutAction {" in hades_nav
assert "extension ShortcutAction {" in hades2_nav
assert "TrainerSemanticIcon" not in hades_types
assert "TrainerSemanticIcon" not in hades2_types
assert "Label(text(action.key), systemImage: action.icon)" in hades_view
hades2_management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text()
assert "Label(text(action.presentationKey), systemImage: action.icon)" in hades2_management
assert "var icon: String { shortcut?.icon ?? section.icon }" in hades_nav
assert "var icon: String { shortcut?.icon ?? section.icon }" in hades2_nav
hades2_host = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text()
assert "systemImage: entry.icon" in hades2_host
assert "systemImage: entry.icon" in hades_nav

# Executable product actions must carry an icon. This deliberately scans both
# game UI trees so new actions cannot silently regress to text-only controls.
for root in (ROOT / "Sources/Hades", ROOT / "Sources/Hades2"):
    for path in root.rglob("*.swift"):
        lines = path.read_text().splitlines()
        for index, line in enumerate(lines):
            if "TrainerPrimaryActionButton(" not in line and "TrainerSecondaryActionButton(" not in line:
                continue
            window = "\n".join(lines[index:index + 7])
            assert "systemImage:" in window, f"missing action icon: {path}:{index + 1}"

print("cross_game_ui_semantics_ok")
