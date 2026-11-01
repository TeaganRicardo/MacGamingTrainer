"""Bidirectional localization key-use contract for the Hades II presentation tables."""

import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION = ROOT / "Sources/Hades2/Presentation/Localization"
LANGUAGES = ("zh-CN", "en")
SOURCE_ROOTS = (ROOT / "Sources", ROOT / "Backend")

DYNAMIC_PREFIXES = {
    "hades2.occurrence.target.",
    "hades2.gathering.family.",
    "hades2.gathering.collection.",
    "hades2.reward.",
    "hades2.element.",
    "hades2.rarity.",
    "hades2.traits.family.",
    "hades2.gathering.unavailable.",
    "hades2.saveEditor.workbench.section.",
    "hades2.saveEditor.investigate.block.",
    "hades2.saveEditor.discovery.reason.",
    "hades2.saveEditor.group.",
}


def quoted_strings(source, language):
    """Yield localization candidates outside comments and explicit Swift AX IDs."""
    index = 0
    size = len(source)
    swift_context = []
    while index < size:
        if language == "swift" and source.startswith("//", index):
            swift_context.append(" ")
            newline = source.find("\n", index + 2)
            index = size if newline < 0 else newline + 1
            continue
        if language == "swift" and source.startswith("/*", index):
            swift_context.append(" ")
            index += 2
            depth = 1
            while index < size and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            continue
        if language == "python" and source[index] == "#":
            newline = source.find("\n", index + 1)
            index = size if newline < 0 else newline + 1
            continue
        if language == "lua" and source.startswith("--[[", index):
            end = source.find("]]", index + 4)
            index = size if end < 0 else end + 2
            continue
        if language == "lua" and source.startswith("--", index):
            newline = source.find("\n", index + 2)
            index = size if newline < 0 else newline + 1
            continue

        if source[index] not in ("'", '"'):
            if language == "swift":
                swift_context.append(source[index])
            index += 1
            continue

        # An identifier is not displayed copy. Classify this occurrence only:
        # the same literal in a label/localization call must still be checked.
        is_accessibility_identifier = language == "swift" and re.search(
            r"\.\s*accessibilityIdentifier\s*\(\s*$", "".join(swift_context)
        ) is not None
        swift_context = ["<literal>"]
        quote = source[index]
        delimiter = quote * 3 if source.startswith(quote * 3, index) else quote
        index += len(delimiter)
        parts = []
        while index < size:
            if source[index] == "\\":
                parts.append(source[index:index + 2])
                index += 2
                continue
            if source.startswith(delimiter, index):
                if not is_accessibility_identifier:
                    yield "".join(parts)
                index += len(delimiter)
                break
            parts.append(source[index])
            index += 1


def without_python_docstrings(source):
    """Blank Python docstrings so documentation examples cannot count as code use."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    line_starts = [0]
    line_starts.extend(match.end() for match in re.finditer("\n", source))
    spans = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.body or not isinstance(node.body[0], ast.Expr):
            continue
        value = node.body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            start = line_starts[value.lineno - 1] + value.col_offset
            end = line_starts[value.end_lineno - 1] + value.end_col_offset
            spans.append((start, end))
    characters = list(source)
    for start, end in spans:
        for index in range(start, end):
            if characters[index] not in "\r\n":
                characters[index] = " "
    return "".join(characters)


def production_sources():
    sources = {}
    for root in SOURCE_ROOTS:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix in (".swift", ".py", ".lua"):
                language = {".swift": "swift", ".py": "python", ".lua": "lua"}[path.suffix]
                source = path.read_text(encoding="utf-8")
                if language == "python":
                    source = without_python_docstrings(source)
                sources[path.relative_to(ROOT).as_posix()] = (source, language)
    return sources


def scan_source_keys(sources):
    """Return complete literal keys and the finite dynamic prefixes in use."""
    literal_keys = set()
    dynamic_prefixes = set()
    malformed = []
    for path, (source, language) in sources.items():
        for token in quoted_strings(source, language):
            if not token.startswith("hades2.") or token == "hades2." or token.endswith(".json"):
                continue
            if "\\(" in token:
                prefix = token.split("\\(", 1)[0]
                if prefix.endswith("."):
                    dynamic_prefixes.add(prefix)
                else:
                    malformed.append(f"{path}: unsupported interpolated key {token!r}")
                continue
            if "{" in token:
                prefix = token.split("{", 1)[0]
                if prefix.endswith("."):
                    dynamic_prefixes.add(prefix)
                else:
                    malformed.append(f"{path}: unsupported formatted key {token!r}")
                continue
            if token.endswith("."):
                dynamic_prefixes.add(token)
                continue
            if re.fullmatch(r"hades2\.[A-Za-z0-9_.]+", token):
                literal_keys.add(token)
            else:
                malformed.append(f"{path}: unsupported localization token {token!r}")
    if malformed:
        raise AssertionError("Unclassified localization string construction:\n" + "\n".join(sorted(malformed)))
    return literal_keys, dynamic_prefixes


def enum_cases(source, enum_name):
    match = re.search(
        rf"^\s*enum\s+{re.escape(enum_name)}\b[^\n]*\{{(.*?)^\}}",
        source,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Could not find Swift enum {enum_name}")
    values = []
    for line in match.group(1).splitlines():
        case = re.match(
            r"^\s*case\s+([A-Za-z][A-Za-z0-9_]*(?:\s*,\s*[A-Za-z][A-Za-z0-9_]*)*)\s*$",
            line,
        )
        if case:
            values.extend(part.strip() for part in case.group(1).split(","))
    if not values or len(values) != len(set(values)):
        raise AssertionError(f"Swift enum {enum_name} has no cases or duplicate cases: {values}")
    return set(values)


def require_capture(pattern, source, description, flags=0):
    match = re.search(pattern, source, flags)
    if not match:
        raise AssertionError(f"Could not derive {description} from its owning source")
    return match.group(1)


def dynamic_key_references(sources):
    """Expand each dynamic key only from its owning finite source domain."""
    swift_types = sources["Sources/Hades2/Hades2Types.swift"][0]
    swift_view = sources["Sources/Hades2/Hades2View.swift"][0]
    save_view = sources["Sources/Hades2/Views/Hades2SaveEditorView.swift"][0]
    save_narrative = sources["Backend/games/hades2/save_narrative.py"][0]
    save_investigation = sources["Backend/games/hades2/save_investigation.py"][0]
    runtime_path = ROOT / "Backend/games/hades2/runtime/hades.lua"
    lua = runtime_path.read_text(encoding="utf-8")

    families = enum_cases(swift_types, "Hades2GatheringFamily")
    workbench_sections = enum_cases(save_view, "Hades2SaveWorkbenchSection")

    occurrence_order = lua.index("occurrenceTargetOrder =")
    occurrence_start = lua.index("occurrenceTargets = {", occurrence_order)
    occurrence_body_start = occurrence_start + len("occurrenceTargets = {")
    occurrence_close = re.search(r"^  \}\s*$", lua[occurrence_body_start:], re.MULTILINE)
    if not occurrence_close:
        raise AssertionError("Could not find the end of the resident occurrence-target table")
    occurrence_body = lua[
        occurrence_body_start:occurrence_body_start + occurrence_close.start()
    ]
    occurrence_ids = set(re.findall(r'sourceId\s*=\s*"([^"]+)"', occurrence_body))
    if not occurrence_ids or len(occurrence_ids) != len(
        re.findall(r'sourceId\s*=\s*"([^"]+)"', occurrence_body)
    ):
        raise AssertionError("Resident occurrence-target source IDs are missing or duplicated")

    element_body = require_capture(
        r"M\.observationRetention\.elementOrder\s*=\s*\{([^}]+)\}",
        lua,
        "resident element order",
    )
    element_ids = set(re.findall(r'"([^"]+)"', element_body))

    rarity_body = require_capture(
        r"local rarityOrder\s*=\s*\{([^}]+)\}",
        lua,
        "resident rarity order",
    )
    rarities = set(re.findall(r'"([^"]+)"', rarity_body))
    available_start = lua.index("local function availableRarities")
    available_end = lua.index("local function nativeLevelEligible", available_start)
    available_rarities = lua[available_start:available_end]
    if 'result[#result + 1] = "Legendary"' in available_rarities:
        rarities.add("Legendary")

    family_start = lua.index("local function traitFamily")
    family_end = lua.index("local function availableRarities", family_start)
    trait_families = set(
        re.findall(r'return\s+"([A-Za-z][A-Za-z0-9]*)"', lua[family_start:family_end])
    )

    reward_calls = re.findall(
        r'(?<!func )\brewardLabel\(([^)\n]+)\)',
        swift_view,
    )
    reward_ids = set()
    for argument in reward_calls:
        literal = re.fullmatch(r'\s*"([^"]+)"\s*', argument)
        if not literal:
            raise AssertionError(
                "rewardLabel must be called with explicit IDs so its key domain stays bounded: "
                + argument
            )
        reward_ids.add(literal.group(1))
    if not reward_ids:
        raise AssertionError("No rewardLabel call sites were found")

    gathering_unavailable = set()
    for token in quoted_strings(lua, "lua"):
        prefix = "hades2.gathering.unavailable."
        if token.startswith(prefix):
            suffix = token[len(prefix):]
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", suffix):
                raise AssertionError(f"Unsupported gathering-unavailable key: {token!r}")
            gathering_unavailable.add(suffix)

    reason_function = save_view[
        save_view.index("private func discoveryReason"):
        save_view.index("private func valueText")
    ]
    reason_body = require_capture(
        r"let known\s*=\s*\[(.*?)\]",
        reason_function,
        "Save Editor discovery reason domain",
        re.DOTALL,
    )
    discovery_reasons = set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)"', reason_body))

    dialogue_block_codes = set(re.findall(
        r"DialogueWriteBlocked\(\s*['\"]([A-Za-z][A-Za-z0-9]*)['\"]",
        save_narrative,
    ))
    investigation_block_codes = set(re.findall(
        r"block_code\s*=\s*['\"]([A-Za-z][A-Za-z0-9]*)['\"]",
        save_investigation,
    ))
    investigation_fallbacks = set(re.findall(
        r"decision\.get\(\s*['\"]code['\"]\s*\)\s+or\s+['\"]([A-Za-z][A-Za-z0-9]*)['\"]",
        save_investigation,
    ))
    block_codes = dialogue_block_codes | investigation_block_codes | investigation_fallbacks

    grouping = sources["Sources/Hades2/Views/Hades2SaveEditorEntityGrouping.swift"][0]
    result_groups = set(re.findall(r'"([A-Za-z][A-Za-z0-9]*)"', require_capture(
        r'let order = \[(.*?)\]', grouping, "Save Editor result groups", re.DOTALL)))

    suffixes = {
        "hades2.occurrence.target.": occurrence_ids,
        "hades2.gathering.family.": families,
        "hades2.gathering.collection.": families,
        "hades2.reward.": reward_ids,
        "hades2.element.": element_ids,
        "hades2.rarity.": rarities,
        "hades2.traits.family.": trait_families,
        "hades2.gathering.unavailable.": gathering_unavailable,
        "hades2.saveEditor.workbench.section.": workbench_sections,
        "hades2.saveEditor.investigate.block.": block_codes,
        "hades2.saveEditor.discovery.reason.": discovery_reasons,
        "hades2.saveEditor.group.": result_groups,
    }
    for prefix, values in suffixes.items():
        if not values:
            raise AssertionError(f"Dynamic key source for {prefix!r} produced no suffixes")
    return {
        prefix: {prefix + suffix for suffix in values}
        for prefix, values in suffixes.items()
    }


def analyze_key_usage(entries, references):
    """Return missing references and resource keys with no production owner."""
    return sorted(references - entries), sorted(entries - references)


class LocalizationKeyUsageTests(unittest.TestCase):
    def test_swift_accessibility_identifiers_are_not_display_copy(self):
        keys, prefixes = scan_source_keys({"Example.swift": ('''
            view.accessibilityIdentifier("hades2.identifierOnly")
            view.accessibilityIdentifier(
                /* identifier ownership */ "hades2.multilineIdentifierOnly"
            )
            view.accessibilityIdentifier("hades2.shared")
                .accessibilityLabel(localization.localized("hades2.shared"))
            view.accessibilityIdentifier(localization.localized("hades2.displayedIdentifier"))
            view.accessibilityHint("hades2.hint")
            let title =
                // .accessibilityIdentifier(
                "hades2.afterComment"
            let example = ".accessibilityIdentifier("
            let detail = "hades2.afterString"
        ''', "swift")})
        self.assertEqual(keys, {
            "hades2.shared", "hades2.displayedIdentifier", "hades2.hint",
            "hades2.afterComment", "hades2.afterString",
        })
        self.assertEqual(prefixes, set())

    def test_analyzer_detects_missing_and_orphan_keys(self):
        missing, orphan = analyze_key_usage(
            {"hades2.present", "hades2.orphan"},
            {"hades2.present", "hades2.missing"},
        )
        self.assertEqual(missing, ["hades2.missing"])
        self.assertEqual(orphan, ["hades2.orphan"])

    def test_dynamic_expansion_is_exact_not_a_prefix_allowance(self):
        prefix = "hades2.example."
        references = {prefix + suffix for suffix in {"known"}}
        missing, orphan = analyze_key_usage(
            {prefix + "known", prefix + "unlisted"},
            references,
        )
        self.assertEqual(missing, [])
        self.assertEqual(orphan, [prefix + "unlisted"])

    def test_production_localization_keys_have_bounded_owners(self):
        tables = {
            language: json.loads(
                (LOCALIZATION / f"hades2.{language}.json").read_text(encoding="utf-8")
            )["entries"]
            for language in LANGUAGES
        }
        self.assertEqual(
            set(tables["zh-CN"]),
            set(tables["en"]),
            "English and zh-CN localization key sets differ",
        )

        sources = production_sources()
        literal_keys, observed_prefixes = scan_source_keys(sources)
        self.assertEqual(
            observed_prefixes,
            DYNAMIC_PREFIXES,
            "Dynamic localization key construction changed; derive its finite domain explicitly",
        )
        dynamic_by_prefix = dynamic_key_references(sources)
        self.assertEqual(set(dynamic_by_prefix), DYNAMIC_PREFIXES)
        dynamic_keys = set().union(*dynamic_by_prefix.values())
        references = literal_keys | dynamic_keys

        for language, entries in tables.items():
            missing, orphan = analyze_key_usage(set(entries), references)
            self.assertEqual(
                missing,
                [],
                f"{language} is missing production-referenced localization keys",
            )
            self.assertEqual(
                orphan,
                [],
                f"{language} has localization keys with no production owner; "
                "remove confirmed orphans or add the actual production use:\n"
                + "\n".join(orphan),
            )


if __name__ == "__main__":
    unittest.main()
