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
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2 import error_presentation

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

# 4. Every backend presentation key resolves in every language. Runtime
# refusals live in the same registry; only the generic fallback is separate
# because it has no producer message of its own.
BACKEND_KEYS = {rule["key"] for rule in error_presentation.REGISTRY}
BACKEND_KEYS.add(error_presentation.RUNTIME_FALLBACK_KEY)
for key in sorted(BACKEND_KEYS):
    for language, entries in TABLES.items():
        assert key in entries, f"{language} is missing backend key {key}"

# 5. A prefix rule must not be shadowed by a whole-message rule, and every
#    prefix key must take an argument so an interpolated value is not dropped.
_LITERAL_MESSAGES = [r["message"] for r in error_presentation.REGISTRY
                     if r["match"] == "literal"]
_PREFIX_RULES = [r for r in error_presentation.REGISTRY if r["match"] == "prefix"]
for message in _LITERAL_MESSAGES:
    for rule in _PREFIX_RULES:
        assert not message.startswith(rule["prefix"]), (message, rule["prefix"])
for rule in _PREFIX_RULES:
    # A prefix rule that dropped its remainder would silently discard an
    # interpolated value, so the argument convention is declared per rule and
    # checked here rather than carried in a side table the registry cannot miss.
    assert rule.get("argument") == "remainder", (rule["prefix"], rule.get("argument"))

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
#    This is generated from the parsed source, so a new message cannot ship
#    unregistered. The messages are recovered with `ast`, not a regex: a text
#    scan cannot see a message assembled before it is raised, and it cannot see
#    implicit adjacent-literal concatenation at all.
STRING_ARG = re.compile(r"""f?['"]([^'"\n]+)['"]""")
# A message can also arrive through a table (a stat rule's `error`) and be
# raised later, so the source scan has to read table entries as well.
TABLE_ENTRY = re.compile(r"""['"](?:error|message)['"]\s*:\s*f?['"]([^'"\n]+)['"]""")
FIELD = re.compile(r"\{[^}]*\}")
unregistered = []
# A key can resolve while the *argument boundary* is still wrong, which is how
# half-Chinese, doubled or hole-ridden messages reached the UI while this suite
# stayed green. So each probe is checked for boundary damage too, not just for
# the existence of a key.
BOUNDARY_DAMAGE = re.compile(r"[　-〿＀-￯]")
# A string that reads like a failure rather than a label or a term. Used only to
# decide whether a *non-raised* literal is player-facing copy worth probing.
ERROR_SHAPED = re.compile(
    r"(失败|错误|无法|不可用|未连接|未运行|未解析|未经验证|需要|"
    r"请先|请在|已保留|保持不变|不支持|已结束|已退出|已断开|超时|"
    r"不得|不能|拒绝|不再支持|不一致|不存在|未找到|未知)"
)
# Modules whose CJK strings are never a raised player-facing message.
# `catalog.py` collects warnings and the official term table; `diagnostics.py`
# returns a report whose field values the Host renders in its own table.
ERROR_FREE_MODULES = frozenset(("catalog.py", "diagnostics.py"))


def render(template, arguments):
    for index, argument in enumerate(arguments):
        template = template.replace("{%d}" % index, argument)
    return template


class MessageVisitor(ast.NodeVisitor):
    """Collect player-facing messages from parsed Python, not from text.

    A regex over raise sites cannot see a message that is *assembled* before it
    is raised (`message = f'…'`, `super().__init__(message)`), and it cannot
    see implicit adjacent-literal concatenation at all — `catalog.py` writes its
    warning across two quoted lines that join into one sentence, so a literal
    scan sees two fragments and matches neither. Parsing removes both problems
    and also settles where a `(code, message)` raise ends without guessing.
    """

    def __init__(self):
        self.messages = []

    def _shape(self, node):
        """Render a string-ish expression as the sentence the player sees.

        Every non-literal part becomes `X`, so the result is the message's
        static shape with its runtime values stood in for.
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(self._shape(value) for value in node.values)
        if isinstance(node, ast.FormattedValue):
            # `{GAME_SPEC.display_name}` is a runtime value, but a dotted
            # attribute chain is a stable product name; treating it as opaque
            # `X` would hide the words the player actually sees.
            if isinstance(node.value, ast.Attribute):
                return self._shape(node.value)
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
            return "X"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            left, right = self._shape(node.left), self._shape(node.right)
            # `a + b` where a side is not a string contributes a value.
            if not left:
                return right or "X"
            if not right:
                return left or "X"
            return left + right
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            return self._shape(node.left) + "X"
        if isinstance(node, ast.Call):
            # `'…{}…'.format(a, b)` and f-string conversions.
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "format":
                template = self._shape(func.value)
                return re.sub(r"\{\}", "X", template)
            if isinstance(func, ast.Attribute) and func.attr in {"join", "strip"}:
                return self._shape(func.value)
            if isinstance(func, ast.Name) and func.id in {"str", "repr", "format"}:
                return "X"
        if isinstance(node, ast.Name) and node.id in {"message", "detail", "warning", "error"}:
            # A variable holding an assembled message.
            return "X"
        if isinstance(node, ast.Attribute):
            # `GAME_SPEC.display_name` is a stable product name the player sees
            # verbatim, so its final component stands in as the value.
            return node.attr
        if isinstance(node, ast.Name):
            return node.id
        return ""

    def _record(self, node):
        text = self._shape(node)
        if not text or not has_cjk(text):
            return
        text = re.sub(r"\s+", " ", text).strip()
        # A substituted value against CJK punctuation is a shape artifact; the
        # real message concatenates without a space.
        text = re.sub(r"\s+([。，、；：）】」』])", r"\1", text)
        if has_cjk(text):
            self.messages.append(text)

    def visit_Raise(self, node):
        if node.exc is not None and isinstance(node.exc, ast.Call):
            arguments = node.exc.args
            # `(code, message)` for the Hades error classes, `(message)` for
            # AdapterError/RuntimeError. A literal first argument is the code;
            # a bare name is not, so it stays.
            if len(arguments) > 1 and isinstance(arguments[0], ast.Constant):
                for argument in arguments[1:]:
                    self._record(argument)
            else:
                for argument in arguments:
                    self._record(argument)
        self.generic_visit(node)

    def visit_Call(self, node):
        # `super().__init__(message)` and `raise`-free construction paths.
        self.generic_visit(node)

    def visit_Assign(self, node):
        if isinstance(node.value, (ast.Constant, ast.JoinedStr, ast.BinOp)):
            if isinstance(node.value, ast.Constant) or isinstance(node.value, ast.JoinedStr):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "message":
                        self._record(node.value)
        self.generic_visit(node)


def raised_messages(body):
    """Yield the player-facing message shape of every raise, via the AST."""
    try:
        tree = ast.parse(body)
    except SyntaxError:
        return []
    visitor = MessageVisitor()
    visitor.visit(tree)
    return visitor.messages


for path in sorted((ROOT / "Backend/games/hades2").glob("*.py")):
    if path.name == "error_presentation.py":
        continue  # the migration record itself
    body = path.read_text(encoding="utf-8")
    # `.format(...)` and `super().__init__(message)` build copy that never
    # appears at a `raise`, so a raise-only scan never probed these. Read the
    # literals of any *error-shaped* string too, but only in modules that raise:
    # `catalog.py` appends to a `warnings` list and `diagnostics.py` returns
    # report data, so neither reaches the error funnel as a raised message.
    if path.name in ERROR_FREE_MODULES:
        assigned = []
    else:
        assigned = [
            literal.group(1)
            for literal in STRING_ARG.finditer(body)
            if has_cjk(literal.group(1)) and ERROR_SHAPED.search(literal.group(1))
        ]
    for message in (
        list(raised_messages(body))
        + [match.group(1) for match in TABLE_ENTRY.finditer(body)]
        + assigned
    ):
        if not has_cjk(message):
            continue  # developer-facing or already language-neutral
        # A template renders with substituted values, so a prefix rule cannot
        # match the source text. Probe the rendered shape, standing a value in
        # for every interpolation, which is what the player actually sees.
        probe = FIELD.sub("X", message)
        key, arguments = error_presentation.presentation_for(probe)
        if key is None:
            unregistered.append(f"{path.name}: {message!r}")
            continue
        template = TABLES["en"].get(key)
        assert template is not None, f"{key} is missing from the en table"
        # Every placeholder the template declares must receive a real value:
        # an unfilled `{n}` is a visible hole, and it means the rule captured
        # fewer arguments than the sentence needs. An empty value is allowed
        # only for the optional detail some sentences genuinely omit.
        placeholders = re.findall(r"\{(\d+)\}", template)
        assert len(arguments) == len(placeholders), (
            f"{path.name}: {message!r} -> {key} takes {len(placeholders)} "
            f"placeholder(s) but the rule produced {arguments!r}"
        )
        rendered = render(template, arguments)
        # An argument is runtime *text* — a name, a path, a count. Any CJK in it
        # means the rule captured part of the sentence's own static wording, so
        # that wording rides along untranslated into the localized sentence. This
        # is the general form of the boundary check, and it does not depend on
        # which punctuation a particular sentence happens to use.
        for index, argument in enumerate(arguments):
            if not argument:
                continue
            assert not has_cjk(argument), (
                f"{path.name}: {message!r} -> {key} argument {index} "
                f"({argument!r}) carries untranslated sentence text"
            )
        assert not any(
            BOUNDARY_DAMAGE.search(argument) for argument in arguments if argument
        ), f"{path.name}: {message!r} -> {key} arguments {arguments!r} absorbed the sentence tail"
        # The Host drops unfilled placeholders, so a hole is silently swallowed
        # rather than shown. Assert the real render leaves none behind.
        assert not re.search(r"\{\d+\}", rendered), (
            f"{path.name}: {message!r} -> {key} left a hole: {rendered!r}"
        )
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

# 11b. A feature row must never carry a literal title. Every player-visible
# title in the module's main view goes through the seam so a language switch
# re-renders it. One row passed a bare literal, which froze English into the
# combat screen and made the table edit that fixed it invisible to the player.
_view = (ROOT / "Sources/Hades2/Hades2View.swift").read_text(encoding="utf-8")
_trait_manager = _view[
    _view.index("private var currentRunTraitsPanel"):
    _view.index("private var resourceSection")
]
assert "trait.removalScopeAllMatching" in _trait_manager
assert "hades2.traits.removeAllMatching" in _trait_manager

_literal_titles = re.findall(
    r'feature(?:Row|MultiplierRow)\(\s*("(?:[^"\\]|\\.)*")', _view)
assert not _literal_titles, (
    "a feature row carries a literal title instead of a presentation key, so "
    f"its text cannot re-render on a language switch: {_literal_titles}")

# 11c. Exact Boons keep bilingual recognition in the Chinese UI. The catalog
# already carries both names and the filter searches both; the picker label must
# preserve that pairing without echoing Chinese back into the English UI or
# falling back to a raw Trait ID when one side is missing.
_exact_label = _view[
    _view.index("private func exactItemLabel"):
    _view.index("private func spawnRow")
]
assert "if localization.language == .en" in _exact_label
assert "return option.englishName" in _exact_label
assert "option.englishName != option.name" in _exact_label
assert '"\\(option.name) · \\(option.englishName)"' in _exact_label
assert "if !option.name.isEmpty { return option.name }" in _exact_label
assert "if !option.englishName.isEmpty { return option.englishName }" in _exact_label
_exact_filter = _view[
    _view.index("private var exactBoons"):
    _view.index("private var material:")
]
assert "$0.name.localizedCaseInsensitiveContains(exactSearch)" in _exact_filter
assert "$0.englishName.localizedCaseInsensitiveContains(exactSearch)" in _exact_filter

# 11d. A Trainer Product Term must be declared in the terminology registry and
# referenced through it, not spelled out in a table. A hardcoded bilingual pair
# records its provenance only in a comment.
_reg = json.loads(
    (ROOT / "docs/reference/hades2/1.139672-24556151/ui_terminology.json").read_text(encoding="utf-8"))
_god = (_reg.get("productTerms") or {}).get("invincibility")
assert _god, "the invincibility Trainer Product Term is not declared in the registry"
assert _god["value"] != _god["englishValue"], "a product term pair must differ by language"
for _language, _entries in TABLES.items():
    assert _entries.get("hades2.feature.invincibility") == "{term:productTerms.invincibility}", (
        f"{_language} spells the invincibility label out instead of using the registry")

# 12. No player-facing entry may ship as the same string in both languages.
# A zh-CN table entry that is byte-identical to its en counterpart means the
# Chinese user is reading untranslated English. God mode was the only such
# entry: the pre-B03 Chinese literal "无敌" was replaced by "Invincibility" when
# the tables were authored, and nothing flagged it.
# A registry-backed entry is language-neutral BY DESIGN: both tables hold the
# same {term:...} token and the resolver picks the language. Only flag a
# pair that is identical AND carries no token, which means a language
# leaked into the zh table as literal text.
_identical = sorted(k for k, v in TABLES["en"].items()
                   if TABLES["zh-CN"].get(k) == v and "{term:" not in v)
assert not _identical, (
    "zh-CN and en entries are identical, so a Chinese user reads untranslated "
    f"English: {_identical}")

print("hades2_presentation_contract_ok")
