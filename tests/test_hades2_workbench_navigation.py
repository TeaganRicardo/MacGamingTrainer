"""Function search locates the continuous Hades workbench in both languages."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in ('Sources/Hades/HadesWorkbenchNavigation.swift',
             'Sources/Hades2/Views/Hades2HostActions.swift'):
    header_actions = (ROOT/path).read_text()
    assert 'TrainerWorkbenchSearchField(' in header_actions
    assert 'resultsPresented' not in header_actions
SWIFTC = shutil.which('swiftc')
assert SWIFTC, 'swiftc required for workbench search behavior'
reference = json.loads((ROOT/'docs/reference/hades2/1.143476-25481925/ui_terminology.json').read_text())
labels = {}
for language, term_field in [('zh-CN', 'value'), ('en', 'englishValue')]:
    entries = json.loads((ROOT/f'Sources/Hades2/Presentation/Localization/hades2.{language}.json').read_text())['entries']
    for key, value in entries.items():
        def resolve(match):
            group, identity = match.group(1).split('.', 1)
            return reference[group][identity][term_field]
        labels.setdefault(key, []).append(re.sub(r'\{term:([^}]+)\}', resolve, value))
    host = (ROOT/f'Resources/Localization/{language}.lproj/Host.strings').read_text()
    for key, value in re.findall(r'^"([^"]+)"\s*=\s*"((?:\\.|[^"\\])*)";', host, re.M):
        labels.setdefault(key, []).append(json.loads('"'+value+'"'))

HARNESS = r'''
import Foundation
let data = #"""
__LABELS__
"""#.data(using: .utf8)!
let labels = try! JSONDecoder().decode([String: [String]].self, from: data)
func resolve(_ key: String) -> [String] { labels[key] ?? [] }
func matches(_ query: String) -> [Hades2WorkbenchEntry] {
    Hades2WorkbenchCatalog.matches(query, resolving: resolve)
}
let orderedTerms = [["Éther", "材料"], ["Aether", "materials"], ["éTHER", "材料"]]
func genericMatches(_ query: String) -> [Int] {
    TrainerWorkbenchSearch.matches(query, entries: [2, 0, 1]) { orderedTerms[$0] }
}
precondition(genericMatches(" ETHER\t材料 ") == [2, 0], "aliases, diacritics and input order must survive matching")
precondition(genericMatches("材料 ether missing").isEmpty, "every query token must match")
precondition(genericMatches(" \n\t ").isEmpty)
precondition(genericMatches("AETHER MATERIALS") == [1])

var presentation = TrainerWorkbenchSearchPresentation<Int>()
var destinations: [Int] = []
func show(_ query: String, visible: Bool = true) {
    presentation.queryChanged(query, pageVisible: visible, results: genericMatches(query))
}
func submit(_ query: String, visible: Bool = true) {
    presentation.submit(query: query, pageVisible: visible, search: genericMatches,
                        identifier: { $0 }) { destinations.append($0) }
}
func select(_ id: Int, query: String, visible: Bool = true) {
    presentation.select(id, query: query, pageVisible: visible, search: genericMatches,
                        identifier: { $0 }) { destinations.append($0) }
}
show("ether 材料")
precondition(presentation.resultsPresented && presentation.selectedID == 2)
submit("ether 材料")
precondition(destinations == [2] && !presentation.resultsPresented, "submit must navigate to the first ordered result and dismiss")
show("unmatched")
precondition(presentation.resultsPresented && presentation.selectedID == nil, "a nonempty unmatched query must present the empty state")
submit("unmatched")
precondition(destinations == [2] && !presentation.resultsPresented)
show("ether")
submit("")
precondition(destinations == [2] && !presentation.resultsPresented, "clearing must not submit a captured previous result")
show("ether")
presentation.pageVisibilityChanged(false)
precondition(!presentation.resultsPresented && presentation.selectedID == nil)
show("materials", visible: false)
presentation.pageVisibilityChanged(true)
precondition(!presentation.resultsPresented, "returning to a page must not reopen a stale popover")
select(0, query: "ether", visible: false)
submit("ether", visible: false)
precondition(destinations == [2], "hidden-page callbacks must not navigate another page")
show("ether")
presentation.dismiss()
precondition(!presentation.resultsPresented && presentation.selectedID == nil)
select(0, query: "ether")
precondition(destinations == [2], "a queued row action must not outlive its popover")

// Keyboard selection follows stable identities through filtering and catalog
// refreshes, stops at either edge, and resolves today's result on Return.
show("ether")
precondition(presentation.moveSelection(by: 1, query: "ether", pageVisible: true, results: genericMatches("ether")))
precondition(presentation.selectedID == 0)
show("ETHER 材料")
precondition(presentation.selectedID == 0, "query refinement reset a still-present keyboard selection")
presentation.moveSelection(by: 1, query: "ETHER 材料", pageVisible: true, results: genericMatches("ETHER 材料"))
precondition(presentation.selectedID == 0, "Down wrapped past the last result")
presentation.moveSelection(by: -1, query: "ETHER 材料", pageVisible: true, results: genericMatches("ETHER 材料"))
presentation.moveSelection(by: -1, query: "ETHER 材料", pageVisible: true, results: genericMatches("ETHER 材料"))
precondition(presentation.selectedID == 2, "Up wrapped past the first result")
presentation.moveSelection(by: 1, query: "ether", pageVisible: true, results: genericMatches("ether"))
submit("ether")
precondition(destinations == [2, 0], "Return ignored the keyboard-selected destination")
presentation.moveSelection(by: -1, query: "ether", pageVisible: true, results: genericMatches("ether"))
precondition(presentation.resultsPresented && presentation.selectedID == 1, "Up did not reopen the retained query at its last result")
presentation.resultsChanged([2, 1])
precondition(presentation.selectedID == 1, "dynamic aliases reset a surviving result")
presentation.resultsChanged([2])
precondition(presentation.selectedID == 2, "removed selection did not fall back to the first current result")
presentation.resultsChanged([])
precondition(presentation.selectedID == nil && presentation.resultsPresented, "an empty refresh closed the discovery panel")
show("ether")
select(0, query: "aether")
precondition(destinations == [2, 0] && presentation.resultsPresented, "a removed row changed today's query presentation or navigated")
show("ether")
presentation.moveSelection(by: 1, query: "ether", pageVisible: true, results: genericMatches("ether"))
submit("aether")
precondition(destinations == [2, 0, 1], "Return used a stale array while the current query had changed")
precondition(!presentation.moveSelection(by: 1, query: " ", pageVisible: true, results: []))
precondition(!presentation.moveSelection(by: 1, query: "ether", pageVisible: false, results: [2, 0, 1]))
precondition(!presentation.resultsPresented && presentation.selectedID == nil)

precondition(matches("  \n ").isEmpty, "an empty query must preserve the ordinary workbench")
precondition(matches("无限金币").contains { $0.shortcut == .infiniteMoney && $0.section == .common })
precondition(matches(" INFINITE  GOLD ").contains { $0.shortcut == .infiniteMoney }, "English search must tolerate case and spacing")
precondition(matches("悟性").contains { $0.titleKey == "hades2.stat.grasp" && $0.section == .values })
precondition(matches("Grasp").contains { $0.titleKey == "hades2.stat.grasp" && $0.section == .values })
precondition(matches("花园瞬间成熟").contains { $0.shortcut == .matureGarden && $0.section == .resources })
precondition(matches("Chaos Gate").contains { $0.titleKey == "hades2.chaosGate.title" && $0.section == .rooms })
for key in ["hades2.traits.remainingUses", "hades2.traits.expireNow", "hades2.traits.chaos.cancelPair", "hades2.rarity.minimum"] {
    for label in resolve(key) {
        precondition(matches(label).contains { $0.titleKey == key && $0.section == .boons },
                     "a visible non-shortcut function is absent from search: \(label)")
    }
}
precondition(matches("无法匹配的功能").isEmpty)
let entries = Hades2WorkbenchCatalog.entries
precondition(Set(entries.map(\.id)).count == entries.count, "search destinations must be stable and unique")
precondition(Set(Hades2WorkbenchCatalog.orderedShortcutActions) == Set(ShortcutAction.allCases))
precondition(Hades2WorkbenchCatalog.orderedShortcutActions.count == ShortcutAction.allCases.count)
precondition(entries.contains { $0.titleKey == "hades2.feature.damageMultiplier" && $0.shortcut == nil && $0.section == .values })
precondition(!ShortcutAction.allCases.contains { $0.rawValue == "damageEnabled" })
for action in ShortcutAction.allCases {
    precondition(entries.filter { $0.shortcut == action }.count == 1, "a current shortcut action is absent or duplicated")
}
for entry in entries {
    precondition(labels[entry.titleKey]?.count == 2, "search must use shipped bilingual labels: \(entry.titleKey)")
}
precondition(ShortcutAction.allCases.allSatisfy { action in
    matches(resolve(action.presentationKey)[0]).contains { $0.shortcut == action }
})
print("hades2_workbench_navigation_ok")
'''.replace('__LABELS__', json.dumps(labels, ensure_ascii=False))

with tempfile.TemporaryDirectory(prefix='mgt-workbench-navigation-') as temporary:
    main = Path(temporary)/'main.swift'
    binary = Path(temporary)/'search'
    main.write_text(HARNESS)
    subprocess.run([SWIFTC, str(ROOT/'Sources/Core/UI/TrainerSemanticIcon.swift'),
                    str(ROOT/'Sources/Core/UI/TrainerWorkbenchSearch.swift'),
                    str(ROOT/'Sources/Hades2/Generated/Hades2Feature.generated.swift'),
                    str(ROOT/'Sources/Hades2/Hades2Types.swift'),
                    str(ROOT/'Sources/Hades2/Services/Hades2WorkbenchNavigation.swift'),
                    str(main), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

workbench_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text()
assert "specialSearch" not in workbench_view
assert "inline: true" in workbench_view
