"""Every key a player can see resolves in both languages.

A missing key shows up on screen as raw `hades2.foo` text, and an unresolved
`{term:...}` or `{0}` placeholder shows up literally (#241). One check covers
the Host table, every game table and the reference fixture, plus the backend
error keys and the cleanup that keeps SJSON markup such as `{#Echo}` off screen.
"""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
import core.protocol  # noqa: E402,F401 - loads every CoreSaveError subclass
from core.errors import CoreSaveError  # noqa: E402
from games.hades2 import error_presentation, localization, terminology  # noqa: E402

LANGUAGES = ("zh-CN", "en")


def strings_table(path):
    rows = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        match = re.fullmatch(r'"([^"]+)"\s*=\s*"(.*)";', line)
        assert match, f"invalid row: {path}: {raw}"
        assert match.group(1) not in rows, f"duplicate key: {path}: {match.group(1)}"
        rows[match.group(1)] = match.group(2)
    return rows


TABLES = {"host": {
    language: strings_table(ROOT / f"Resources/Localization/{language}.lproj/Host.strings") for language in LANGUAGES
}}
for english in [*sorted(ROOT.glob("Sources/*/Presentation/Localization/*.en.json")),
                ROOT / "ContractFixtures/reference_module/frontend/Localization/reference_fixture.en.json"]:
    tables = {
        language: json.loads(english.with_name(english.name.replace(".en.", f".{language}.")).read_text(
            encoding="utf-8"))["entries"]
        for language in LANGUAGES
    }
    namespaces = {key.split(".", 1)[0] for key in tables["en"]}
    assert len(namespaces) == 1, (english, namespaces)
    TABLES[namespaces.pop()] = tables
assert {"host", "hades2", "hades", "referenceFixture"} <= set(TABLES), sorted(TABLES)

# 1. Both languages have the same keys, no blank value and the same {0} arguments.
for namespace, tables in TABLES.items():
    zh, en = tables["zh-CN"], tables["en"]
    assert set(zh) == set(en), (namespace, sorted(set(zh) ^ set(en)))
    for key in zh:
        assert key.startswith(namespace + "."), (namespace, key)
        assert zh[key].strip() and en[key].strip(), f"{key} is blank"
        assert set(re.findall(r"\{\d+\}", zh[key])) == set(re.findall(r"\{\d+\}", en[key])), key

# 2. A {term:group.name} placeholder names a user-facing Hades II registry term
#    with both languages. Only the Hades II presentation resolves them.
REGISTRY = json.loads(terminology._reference_path().read_text(encoding="utf-8"))
USER_FACING_TERMS = ("officialTerms", "nativeChoiceTitles", "officialSourceNames", "productTerms")
for namespace, tables in TABLES.items():
    for language, entries in tables.items():
        for key, value in entries.items():
            for term in re.findall(r"\{term:([^}]+)\}", value):
                assert namespace == "hades2", f"{key} uses {{term:}} outside Hades II"
                group, _, name = term.partition(".")
                entry = REGISTRY.get(group, {}).get(name, {}) if group in USER_FACING_TERMS else {}
                assert entry.get("value") and entry.get("englishValue"), f"{language} {key}: unknown term {term}"

# 3. Every key the code names exists, and every key prefix the code builds on
#    has entries. Identifiers that only look like keys (accessibility IDs,
#    defaults keys, section IDs, profile phases, file names) are skipped.
KEY = re.compile(r"(" + "|".join(map(re.escape, TABLES)) + r")\.[A-Za-z][A-Za-z0-9_.]*")
NOT_A_KEY_CONTEXT = re.compile(
    r"(?:(?:accessibilityIdentifier|forKey|\bid)\s*:|(?:accessibilityIdentifier|trainerSectionTarget|\.emit)\s*\()\s*$")
FILE_NAME = re.compile(r"\.(?:json|log|lua|py|strings|swift)$")
SWIFT_TOKENS = re.compile(r'"""[\s\S]*?"""|"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*[\s\S]*?\*/')
LUA_TOKENS = re.compile(r'--\[\[[\s\S]*?\]\]|--[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'')


def literals(path):
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        tree = ast.parse(source)
        docstrings = {
            id(node.body[0].value) for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
        }
        return [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
    found = []
    for match in (SWIFT_TOKENS if path.suffix == ".swift" else LUA_TOKENS).finditer(source):
        token = match.group(0)
        if token.startswith(("//", "/*", "--")):
            continue
        if path.suffix == ".swift" and NOT_A_KEY_CONTEXT.search(source[max(0, match.start() - 60):match.start()]):
            continue
        found.append(token.strip('"\''))
    return found


missing, prefixes = [], set()
for root in ("Sources", "Backend", "ContractFixtures"):
    for path in sorted((ROOT / root).rglob("*")):
        if path.suffix not in (".swift", ".py", ".lua") or not path.is_file():
            continue
        for token in literals(path):
            match = KEY.match(token)
            if not match or FILE_NAME.search(token):
                continue
            namespace = match.group(1)
            if match.end() < len(token) or token.endswith("."):
                prefixes.add((namespace, token[:match.end()].rsplit(".", 1)[0] + ".", path.name))
            elif token not in TABLES[namespace]["en"]:
                missing.append(f"{path.relative_to(ROOT)}: {token}")
assert not missing, "keys missing from the localization tables:\n" + "\n".join(sorted(set(missing)))
assert len(prefixes) > 10, prefixes
for namespace, prefix, name in sorted(prefixes):
    assert any(key.startswith(prefix) for key in TABLES[namespace]["en"]), f"{name}: no entries for {prefix}*"

# 4. Backend errors reach the player as keys in both languages.
hades2_keys = set(TABLES["hades2"]["en"])
for key in {rule["key"] for rule in error_presentation.REGISTRY} | {error_presentation.RUNTIME_FALLBACK_KEY}:
    assert key in hades2_keys, f"Hades II backend key {key} is not localized"


def subclasses(base):
    for subclass in base.__subclasses__():
        yield subclass
        yield from subclasses(subclass)


save_errors = [cls for cls in subclasses(CoreSaveError) if not cls.__name__.startswith("_")]
assert save_errors
for cls in save_errors:
    assert getattr(cls, "presentation_key", "") in TABLES["host"]["en"], cls.__name__

# Drive the real Core server loop: every protocol failure carries a Host key.
SERVER_PROBE = r"""
import sys
sys.path.insert(0, sys.argv[1])
from core.adapter import GameAdapter, GameAdapterContext
import core.server as server
class Fixture(GameAdapter):
    def __init__(self):
        super().__init__(GameAdapterContext('fixture', 'Fixture', 1, None, {}))
    def dispatch(self, command, params, request_id):
        return {}
    def close(self):
        pass
server.create_adapter = lambda game_id: Fixture()
server.main(['--game', 'fixture'])
"""
with tempfile.TemporaryDirectory(prefix="mgt-localization-") as temporary:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("MGT_")}
    environment.update(HOME=temporary, CFFIXED_USER_HOME=temporary)
    requests = (
        "not json",
        '{"id": "", "command": "status", "params": {}}',
        '{"id": "a", "command": "status", "params": {}}',
        '{"id": "a", "command": "other", "params": {}}',
        '{"id": "b", "command": "status", "params": {"v": NaN}}',
    )
    served = subprocess.run([sys.executable, "-c", SERVER_PROBE, str(ROOT / "Backend")],
                            input="\n".join(requests) + "\n", capture_output=True, text=True,
                            env=environment, timeout=60)
    replies = [json.loads(line) for line in served.stdout.splitlines() if line.strip()]
    assert [reply.get("ok") for reply in replies] == [False, False, True, False, False], (replies, served.stderr)
    for reply in replies:
        if reply.get("ok") is False:
            assert reply["error"]["presentation"] in TABLES["host"]["en"], reply
            assert reply["error"].get("diagnostic"), reply

# 5. SJSON markup in official game text never reaches the screen.
for raw, expected in {
    "(#Echo) 回声祝福": "回声祝福",
    "（#Echo） 回声祝福": "回声祝福",
    "{#Echo}回声祝福": "回声祝福",
    "#Echo 回声祝福": "回声祝福",
    "{#Emph}Soul Tonic": "Soul Tonic",
    "{!Icons.Mana} Moon Boon": "Moon Boon",
    "{UnrenderableControl}Clean Name": "Clean Name",
}.items():
    assert localization._clean_display_name(raw) == expected, (raw, localization._clean_display_name(raw))

localization._OFFICIAL_TEXT_CACHE.clear()
with tempfile.TemporaryDirectory(prefix="mgt-localization-") as temporary:
    game = Path(temporary)
    text = game / "Contents/Resources/Content/Game/Text"
    text.mkdir(parents=True)
    (text / "Traits.zh-CN.sjson").write_text("""
Thing = { Id = "EchoMockTrait" DisplayName = "(#Echo) 回声之赐" }
Mana = { Id = "MaxManaDrop" DisplayName = "{#Emph}灵魂滋补剂" }
Owner = { Id = "ArcanaOwner" DisplayName = "猎手" }
Child = { Id = "ArcanaMountedTrait" InheritFrom = "ArcanaOwner" }
Grandchild = { Id = "ArcanaTrayTrait" InheritFrom = "ArcanaMountedTrait" }
""", encoding="utf-8")
    names = localization.official_display_names(
        {"EchoMockTrait", "MaxManaDrop", "ArcanaMountedTrait", "ArcanaTrayTrait"}, "zh-CN", game_path=game)
    assert names == {"EchoMockTrait": "回声之赐", "MaxManaDrop": "灵魂滋补剂",
                     "ArcanaMountedTrait": "猎手", "ArcanaTrayTrait": "猎手"}, names
localization._OFFICIAL_TEXT_CACHE.clear()

print("localization_completeness_ok")
