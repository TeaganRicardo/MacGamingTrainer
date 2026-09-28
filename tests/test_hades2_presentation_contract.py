"""Hades II presentation contract.

Hades-owned user-facing copy is authored once and shipped twice (zh-CN, en).
These checks keep the owners in step:

1. the backend error funnel (`games/hades2/error_presentation.py`),
2. the Lua runtime error table (`runtime_error_presentation.py`), and
3. the Swift view/model call sites

all name keys that resolve in every shipped language, and every player-facing
message actually raised in the module is registered. A key present in one
language only, a renamed call site, or a newly raised message that nobody
registered fails here instead of shipping raw copy or a visible `hades2.foo.bar`
string to a player.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import error_presentation
from games.hades2 import runtime_error_presentation

LOCALIZATION = ROOT / "Sources/Hades2/Presentation/Localization"
TABLES = {
    language: json.loads((LOCALIZATION / f"hades2.{language}.json").read_text(encoding="utf-8"))["entries"]
    for language in ("zh-CN", "en")
}
PREFIX = "hades2."
USER_FACING_TERM_GROUPS = (
    "officialTerms",
    "nativeChoiceTitles",
    "officialSourceNames",
    "productTerms",
)
REGISTRY = json.loads(
    (ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json").read_text(encoding="utf-8")
)


def has_cjk(value):
    return any("一" <= character <= "鿿" for character in value)


# 1. Every shipped language defines exactly the same keys.
assert set(TABLES["zh-CN"]) == set(TABLES["en"]), sorted(set(TABLES["zh-CN"]) ^ set(TABLES["en"]))

# 2. Every key is namespaced, no value is empty, and every terminology
#    placeholder names a user-facing registry term that resolves in both
#    languages. An unknown term would render as visible `{term:...}` text.
for language, entries in TABLES.items():
    for key, value in entries.items():
        assert key.startswith(PREFIX), (language, key)
        assert value.strip(), (language, key)
        for term in re.findall(r"\{term:([^}]+)\}", value):
            group, _, term_key = term.partition(".")
            assert group in USER_FACING_TERM_GROUPS, f"{language} {key} term group {group}"
            assert term_key in REGISTRY[group], f"{language} {key} unknown term {term}"
            assert REGISTRY[group][term_key].get("value"), f"{language} {key} term {term} zh-CN"
            assert REGISTRY[group][term_key].get("englishValue"), f"{language} {key} term {term} en"

# 3. Compatibility aliases and internal domain terms cannot reach user surfaces.
FORBIDDEN = {
    entry["value"]
    for group in ("compatibilityAliases", "internalTerms")
    for entry in REGISTRY[group].values()
    if isinstance(entry.get("value"), str)
}
for language, entries in TABLES.items():
    for key, value in entries.items():
        for term in FORBIDDEN:
            assert term not in value, f"{language} {key} leaks non-canonical term {term!r}"

# 4. Every backend presentation key resolves in every language.
BACKEND_KEYS = set(error_presentation.MESSAGE_KEYS.values())
BACKEND_KEYS |= set(error_presentation.PREFIX_KEYS.values())
BACKEND_KEYS.add(runtime_error_presentation._FALLBACK_KEY)
for per_command in runtime_error_presentation._RUNTIME_KEYS.values():
    BACKEND_KEYS |= set(per_command.values())
for key in sorted(BACKEND_KEYS):
    for language, entries in TABLES.items():
        assert key in entries, f"{language} is missing backend key {key}"

# 5. A prefix rule must not be shadowed by a whole-message rule, and every
#    prefix key must take an argument so an interpolated value is not dropped.
for message in error_presentation.MESSAGE_KEYS:
    for prefix in error_presentation.PREFIX_KEYS:
        assert not message.startswith(prefix), (message, prefix)
for prefix, key in error_presentation.PREFIX_KEYS.items():
    assert key in error_presentation._ARGUMENT_KEYS, (prefix, key)

# 6. Interpolated messages keep the value out of the key. The static tail of a
#    composed sentence belongs to the template, not to the argument, so a prefix
#    that absorbs it would render a value that is not the thing that failed.
key, arguments = error_presentation.presentation_for("请先启动 Hades II 并进入存档。")
assert (key, arguments) == ("hades2.error.gameNotRunning", ["Hades II"]), (key, arguments)
key, arguments = error_presentation.presentation_for("查询 Hades II 进程失败（-9）：boom")
assert (key, arguments) == ("hades2.error.processQueryFailed", ["Hades II", "-9", "boom"]), (key, arguments)
key, arguments = error_presentation.presentation_for("未知功能。")
assert (key, arguments) == ("hades2.error.unknownFeature", []), (key, arguments)

# 7. Unregistered text is left alone, so a developer-facing failure is never
#    silently reclassified as player-facing UI copy.
unregistered_text = "Hades II module manifest is missing a valid steamAppId."
assert error_presentation.presentation_for(unregistered_text)[0] is None

# 8. Every player-facing message the module actually raises is registered.
#    This is generated from the source, so a new raise cannot ship unregistered.
RAISED = re.compile(r"""raise\s+\w*(?:Error|Exception)\(\s*f?['"]([^'"\n]+)['"]""")
# A message can also arrive through a table (a stat rule's `error`) and be
# raised later, so the source scan has to read table entries as well.
TABLE_ENTRY = re.compile(r"""['"](?:error|message)['"]\s*:\s*f?['"]([^'"\n]+)['"]""")
FIELD = re.compile(r"\{[^}]*\}")
unregistered = []
for path in sorted((ROOT / "Backend/games/hades2").glob("*.py")):
    if path.name == "error_presentation.py":
        continue  # the migration record itself
    body = path.read_text(encoding="utf-8")
    for match in list(RAISED.finditer(body)) + list(TABLE_ENTRY.finditer(body)):
        message = match.group(1)
        if not has_cjk(message):
            continue  # developer-facing or already language-neutral
        # A template renders with substituted values, so a prefix rule cannot
        # match the source text. Probe the rendered shape, standing a value in
        # for every interpolation, which is what the player actually sees.
        probe = FIELD.sub("X", message)
        if error_presentation.presentation_for(probe)[0] is None:
            unregistered.append(f"{path.name}: {message!r}")
assert not unregistered, sorted(set(unregistered))

# 9. Every Swift call site names a real key, and no Hades Swift file embeds
#    user-facing Chinese copy.
CALL_SITE = re.compile(r'text\("([^"]+)"\)|presentation\("([^"]+)"\)|token\("([^"]+)"\)')
for path in sorted((ROOT / "Sources/Hades2").rglob("*.swift")):
    body = path.read_text(encoding="utf-8")
    for match in CALL_SITE.finditer(body):
        key = next(group for group in match.groups() if group)
        if not key.startswith(PREFIX):
            continue
        # Dynamically composed keys are suffixed onto a prefix, not written out.
        if key.endswith(("\\(rewardID)", "\\(element.id)", "\\(vital)")):
            continue
        for language, entries in TABLES.items():
            assert key in entries, f"{language} is missing referenced key {key}"
    for literal in re.findall(r'"([^"\n]*)"', body):
        # Command names, feature ids, icons and format strings stay neutral.
        assert not has_cjk(literal), f"{path.relative_to(ROOT)} embeds user-facing copy: {literal!r}"

print("hades2_presentation_contract_ok")
