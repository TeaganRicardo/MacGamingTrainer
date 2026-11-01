"""Cross-game presentation/icon semantics stay aligned to the Hades II authority."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

manifest = json.loads((ROOT / "Backend/games/hades2/module.json").read_text())
reference_path = ROOT / manifest["supportedBuild"]["referenceDirectory"] / "ui_terminology.json"
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
    "hades.profile.name": "hades2.profile.namePlaceholder",
    "hades.profile.save": "hades2.profile.saveCurrent",
    "hades.profile.load": "hades2.profile.load",
    "hades.profile.empty": "hades2.profile.empty",
    "hades.diagnostics.export": "hades2.diagnostics.export",
    "hades.saveEditor.title": "hades2.saveEditor.title",
    "hades.saveEditor.search": "hades2.saveEditor.workbench.search",
    "hades.saveEditor.empty": "hades2.saveEditor.empty",
    "hades.saveEditor.previous": "hades2.saveEditor.previousPage",
    "hades.saveEditor.next": "hades2.saveEditor.nextPage",
    "hades.saveEditor.source": "hades2.saveEditor.source.label",
    "hades.saveEditor.selectSource": "hades2.saveEditor.source.choose",
    "hades.saveEditor.read": "hades2.saveEditor.source.read",
    "hades.saveEditor.target": "hades2.saveEditor.target.label",
    "hades.saveEditor.selectTarget": "hades2.saveEditor.target.choose",
    "hades.saveEditor.changes": "hades2.saveEditor.review",
    "hades.saveEditor.discard": "hades2.saveEditor.cancelChanges",
    "hades.saveEditor.browse": "hades2.saveEditor.workbench.browse",
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
# Run the unmodified Swift source in a temporary repository whose manifest
# points elsewhere. Source fallback must follow the manifest's reference owner.
swiftc = shutil.which("swiftc")
if not swiftc:
    raise SystemExit("swiftc required")
with tempfile.TemporaryDirectory(prefix="mgt-terminology-manifest-") as temporary:
    repository = Path(temporary)
    source = repository / "Sources/Hades2/Presentation/Hades2Presentation.swift"
    source.parent.mkdir(parents=True)
    source.write_text(hades2_presentation)
    module = repository / "Backend/games/hades2/module.json"
    module.parent.mkdir(parents=True)
    module.write_text(json.dumps({"supportedBuild": {"referenceDirectory": "docs/relocated-reference"}}))
    registry = repository / "docs/relocated-reference/ui_terminology.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps({"officialTerms": {"probe": {
        "value": "迁移术语", "englishValue": "Relocated term",
    }}}))
    main = repository / "main.swift"
    main.write_text('''
struct TrainerTextToken {
    let key: String
    let arguments: [String]
    init(key: String, arguments: [String] = []) { self.key = key; self.arguments = arguments }
}
enum TrainerPresentationLanguage: String, CaseIterable { case zhCN = "zh-CN", en }
let terms = Hades2TerminologyCatalog()
precondition(terms.value(forTerm: "officialTerms.probe", language: .en) == "Relocated term",
             "Swift source fallback did not follow the manifest referenceDirectory")
precondition(terms.value(forTerm: "officialTerms.probe", language: .zhCN) == "迁移术语",
             "Swift source fallback lost the manifest's bilingual reference")
''')
    binary = repository / "terminology-reference"
    subprocess.run([swiftc, str(source), str(main), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

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
assert "HadesShortcutStore.defaultLayout()[self]!" in hades_types
assert "TrainerHotkeyLayout.defaultLayout(" in hades_types
assert "TrainerHotkeyLayout.resolvedLayout(" in hades_types
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
    "actionSpeed", "timeScale", "item", "controls", "defense",
    "duration", "timer", "precision", "dash", "level",
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
    assert f"case .{hades_case}: TrainerSemanticIcon.Concept.{semantic}" in hades_nav

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
for path in (
    ROOT / "Sources/Hades/HadesWorkbenchNavigation.swift",
    ROOT / "Sources/Hades2/Services/Hades2WorkbenchNavigation.swift",
):
    source = path.read_text()
    for semantic in ("logHistory", "clearLogs", "refreshStatus"):
        assert f"TrainerSemanticIcon.Tool.{semantic}" in source

# Every shortcut-visible function owns one icon. The same action icon is reused
# in shortcut settings and function discovery instead of being redrawn there.
assert "extension HadesFeature {" in hades_nav
assert "extension HadesShortcutAction {" in hades_nav
assert "extension ShortcutAction {" in hades2_nav
assert "TrainerSemanticIcon" not in hades_types
assert "TrainerSemanticIcon" not in hades2_types
assert "TrainerShortcutSettingsView(" in hades_view
assert "icon: action.icon" in hades_view
hades2_management = (ROOT / "Sources/Hades2/Views/Hades2ManagementViews.swift").read_text()
assert "TrainerShortcutSettingsView(" in hades2_management
assert "icon: action.icon" in hades2_management
assert "if let icon = HadesWorkbenchIcon.icon(for: titleKey)" in hades_nav
assert "if let feature = HadesFeature.allCases.first(where: { $0.key == titleKey })" in hades_nav
assert "Hades2WorkbenchIcon.icon(for: titleKey)" in hades2_nav
assert '"hades2.spawn.exactBoons"' in hades2_nav
assert "extension Hades2GatheringFamily" in hades2_nav
assert "var icon: String { shortcut?.icon ?? Hades2WorkbenchIcon.icon(for: titleKey) ?? section.icon }" in hades2_nav
for semantic in ("grasp", "spellCharge", "sprintSpeed", "occurrence", "specialReward", "hexReady", "purge",
                 "garden", "targetLevel", "chaosProbability", "prepareSigning", "restoreSigning",
                 "flora", "mining", "digging", "shades"):
    assert f"static let {semantic} =" in hades2_nav
hades_icon_map = hades_nav[hades_nav.index("static func icon(for titleKey: String)") : hades_nav.index("struct HadesWorkbenchEntry")]
for key in (
    "hades.health", "hades.maxHealth", "hades.money", "hades.rerolls", "hades.godGauge",
    "hades.currentTraits", "hades.catalog", "hades.rarity", "hades.level", "hades.apply",
    "hades.remove", "hades.chaosPair", "hades.remainingUses", "hades.activateBlessing",
    "hades.expireEffect", "hades.refreshEffect", "hades.resources", "hades.gainResource",
    "hades.spawnReward", "hades.doorReward", "hades.doorRoute", "hades.restoreDoor",
    "hades.route.thanatos", "hades.chamberObject", "host.refreshStatus", "hades.saveEditor.title",
    "host.saveManagement", "host.shortcutSettings", "hades.manage.profiles",
    "hades.manage.diagnostics", "host.viewLog", "host.viewLogHistory", "host.clearCompletedLogs",
):
    assert f'"{key}"' in hades_icon_map, f"missing Hades discovery icon: {key}"
hades2_icon_map = hades2_nav[hades2_nav.index("static func icon(for titleKey: String)") : hades2_nav.index("extension Hades2GatheringFamily")]
for key in (
    "hades2.vital.health", "hades2.vital.mana", "hades2.vital.runGold", "hades2.vital.armor",
    "hades2.feature.damageMultiplier", "hades2.stat.grasp", "hades2.metric.rerolls",
    "hades2.metric.spellCharge", "hades2.stat.dodge", "hades2.stat.crit",
    "hades2.stat.enemyDamage", "hades2.stat.enemyHealth", "hades2.stat.chargeSpeed",
    "hades2.stat.moveSpeed", "hades2.stat.sprintSpeed", "hades2.stat.dashSpeed",
    "hades2.stat.attackSpeed", "hades2.stat.manaRegen", "hades2.gameSpeed.title",
    "hades2.traits.manager", "hades2.traits.targetLevel", "hades2.traits.targetRarity",
    "hades2.traits.remainingUses", "hades2.traits.expireNow", "hades2.traits.temporary.cancel",
    "hades2.traits.remove", "hades2.traits.removeAllMatching", "hades2.traits.chaos.advance",
    "hades2.traits.chaos.cancelPair", "hades2.rarity.minimum", "hades2.section.elements",
    "hades2.resource.materials", "hades2.gathering.title", "hades2.gathering.restoreNative",
    "hades2.chaosGate.title", "hades2.chaosGate.probability", "hades2.nextRoom.title",
    "hades2.occurrence.title", "hades2.spawn.olympianBoons", "hades2.spawn.pickupRewards",
    "hades2.spawn.characterRewards", "hades2.spawn.exactBoons", "hades2.manage.profiles", "hades2.saveEditor.title",
    "hades2.manage.diagnostics", "hades2.manage.prepareSigning", "hades2.manage.restoreSigning",
    "host.saveManagement", "host.shortcutSettings", "host.viewLog", "host.viewLogHistory",
    "host.clearCompletedLogs", "host.refreshStatus",
):
    assert f'"{key}"' in hades2_icon_map, f"missing Hades II discovery icon: {key}"

assert "searchAliasKeys" not in hades_nav
hades2_host = (ROOT / "Sources/Hades2/Views/Hades2HostActions.swift").read_text()
assert "systemImage: entry.icon" in hades2_host
assert "TrainerSemanticIcon.Concept.controls" in (ROOT / "Sources/Hades/HadesTrainerView.swift").read_text()
assert "TrainerSemanticIcon.Concept.controls" in (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
assert 'static let profiles = "square.stack.3d.up"' in icon_source
assert "static let catalog = TrainerSemanticIcon.Concept.precision" in hades_nav
assert "static let exactBoons = TrainerSemanticIcon.Concept.precision" in hades2_nav
assert 'TrainerIconLabel(' in hades_view and 'title: text("hades.catalog")' in hades_view
assert 'TrainerIconLabel(' in hades2_view and 'title: text("hades2.spawn.exactBoons")' in hades2_view
assert "case .decreaseGameSpeed: TrainerSemanticIcon.Concept.timeScale" in hades2_nav
assert "case .increaseGameSpeed: TrainerSemanticIcon.Concept.timeScale" in hades2_nav
assert 'static let garden = "tree.fill"' in hades2_nav
assert 'static let hexReady = "moon.fill"' in hades2_nav
assert 'static let shades = "person.3.fill"' in hades2_nav
assert "Image(systemName: TrainerSemanticIcon.Action.remove)" in (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
diagnostics_view = (ROOT / "Sources/Core/UI/Components/TrainerDiagnosticsView.swift").read_text()
assert "TrainerSemanticIcon.Tool.exportDiagnostics" in diagnostics_view
assert "TrainerListCard" in diagnostics_view
for path, start, end in (
    ("Sources/Hades/HadesManagement.swift", "struct HadesDiagnosticsView", "@MainActor\nprivate func hadesManagementError"),
    ("Sources/Hades2/Views/Hades2ManagementViews.swift", "struct Hades2DiagnosticsView", "struct Hades2ShortcutSettingsView"),
):
    source = (ROOT / path).read_text()
    adapter = source[source.index(start):source.index(end, source.index(start))]
    assert "TrainerDiagnosticsView(" in adapter
    assert "TrainerListCard" not in adapter and "TrainerSheetScaffold" not in adapter
    assert "model.runDiagnostics" in adapter and "model.exportDiagnostics" in adapter
    assert "ManagementError(model, localization: localization)" in adapter
assert "family.icon" in (ROOT / "Sources/Hades2/Views/Hades2GatheringPanel.swift").read_text()
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
