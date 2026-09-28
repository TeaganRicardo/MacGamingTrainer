"""The runtime revision gate must follow module metadata, not a hardcoded game.

The gate used to name `Backend/games/hades2/runtime/hades.lua` directly. That made
a "shared" gate a single-game gate: a second game shipping a resident runtime
would have changed its source with no revision bump and nothing would complain.

So these tests build throwaway repositories with two modules, and check that the
gate covers both, that a module without a declaration is not gated, and that a
declaration which is malformed fails loudly rather than being skipped.
"""
import json
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'Tools/check_runtime_revision.py'

DECLARATION = {
    "source": "runtime/resident.lua",
    "previousRevisionPattern": r"previousModule\.revision\s*~=\s*(\d+)",
    "moduleRevisionPattern": r"version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)",
}

LUA_BODY = (
    "local previousModule = __MacGamingTrainerV1\n"
    "if previousModule and previousModule.revision ~= {rev} then previousModule = nil end\n"
    "local M = {{ version = 1, revision = {rev} }}\n"
)


def run(*args, cwd):
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True)


def commit(repo, message):
    subprocess.run(['git', 'add', '-A'], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-m', message], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL)
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo,
                                   text=True).strip()


def gate(repo, base, head):
    return run('python3', str(SCRIPT), base, head, cwd=repo)


def add_module(repo, game_id, *, declaration=DECLARATION, revision=42,
               runtime_source: Optional[str] = 'runtime/resident.lua',
               omit_declaration: bool = False):
    """Create a module directory with a manifest and, if declared, a runtime."""
    module_dir = repo / 'Backend' / 'games' / game_id
    module_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": 1,
        "id": game_id,
        "displayName": game_id.upper(),
        "protocolVersion": 5,
        "backend": {"adapter": f"games.{game_id}.adapter:Adapter"},
        "targetApplication": {
            "processName": game_id,
            "bundleIdentifier": f"com.example.{game_id}",
        },
    }
    if not omit_declaration:
        # An explicit JSON null is a distinct case from an absent key, so it is
        # written verbatim when declaration is None.
        manifest["residentRuntime"] = declaration
        runtime = module_dir / runtime_source
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_text(LUA_BODY.format(rev=revision), encoding='utf-8')
    (module_dir / 'module.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return module_dir


def bump(repo, module_dir, runtime_source, old, new):
    runtime = module_dir / runtime_source
    runtime.write_text(
        runtime.read_text(encoding='utf-8')
        .replace(f'revision ~= {old}', f'revision ~= {new}')
        .replace(f'revision = {old}', f'revision = {new}'),
        encoding='utf-8')


@contextmanager
def make_repo(prefix: str) -> Iterator[Path]:
    """A throwaway git repo, cleaned up when the block exits."""
    with tempfile.TemporaryDirectory(prefix=prefix) as name:
        repo = Path(name)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=repo, check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'],
                       cwd=repo, check=True)
        subprocess.run(['git', 'config', 'user.name', 'MGT test'], cwd=repo, check=True)
        yield repo


# --- The regression: a second game with a resident runtime is also gated. -----
with make_repo('mgt-runtime-second-game-') as repo:
    add_module(repo, 'alpha')
    add_module(repo, 'beta')
    base = commit(repo, 'baseline: two modules, both with a resident runtime')

    beta = repo / 'Backend/games/beta'
    beta_runtime = beta / 'runtime/resident.lua'
    beta_runtime.write_text(
        beta_runtime.read_text(encoding='utf-8') + '-- a behaviour change, no bump\n',
        encoding='utf-8')
    unbumped = commit(repo, 'change beta runtime without a bump')
    result = gate(repo, base, unbumped)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'beta/runtime/resident.lua' in result.stderr, result.stderr
    # Pin the SPECIFIC failure, not a phrase both failure modes share. The old
    # assertion here tested for 'resident revision', which also matches the
    # missing-markers message -- so a runtime whose synthetic Lua had lost its
    # revision markers satisfied every assertion here while being gated for the
    # wrong reason. Round 2 of review found this (U6).
    assert 'changed without increasing resident revision' in result.stderr, (
        'the second game must be gated for failing to increase its revision, '
        'not for an unrelated reason: ' + result.stderr)

    bump(repo, beta, 'runtime/resident.lua', 42, 43)
    bumped = commit(repo, 'bump beta runtime revision')
    result = gate(repo, base, bumped)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'games/beta/runtime/resident.lua' in result.stdout, result.stdout

    # A change to one module's runtime must not demand the other's revision move.
    (repo / 'README.md').write_text('unrelated\n', encoding='utf-8')
    unrelated = commit(repo, 'unrelated change')
    result = gate(repo, bumped, unrelated)
    assert result.returncode == 0, result.stdout + result.stderr

    # Marker consistency is still enforced, per module.
    beta_runtime = beta / 'runtime/resident.lua'
    beta_runtime.write_text(
        beta_runtime.read_text(encoding='utf-8').replace('revision ~= 43', 'revision ~= 44'),
        encoding='utf-8')
    inconsistent = commit(repo, 'break beta marker consistency')
    result = gate(repo, unrelated, inconsistent)
    assert result.returncode != 0, result.stdout + result.stderr
    assert 'consistent' in result.stderr.lower(), result.stderr
    assert 'beta' in result.stderr, result.stderr

# --- A module that declares no runtime is simply not gated. -------------------
with make_repo('mgt-runtime-undescribed-') as repo:
    add_module(repo, 'alpha')
    add_module(repo, 'plain', omit_declaration=True, runtime_source=None)
    base = commit(repo, 'baseline with one module that has no resident runtime')

    plain = repo / 'Backend/games/plain'
    (plain / 'runtime').mkdir(parents=True, exist_ok=True)
    (plain / 'runtime/resident.lua').write_text(
        LUA_BODY.format(rev=7) + '-- changed, and no revision discipline applies\n',
        encoding='utf-8')
    head = commit(repo, 'undeclared runtime source changed')
    result = gate(repo, base, head)
    assert result.returncode == 0, result.stdout + result.stderr

# --- A malformed declaration fails loudly instead of being skipped. -----------
for label, declaration in [
    # A module that DECLARES the key and then nulls it must not be treated as
    # one that never declared it -- that is a silent opt-out, and `.get()`
    # cannot tell the two apart. Found by review.
    ('declaration is an explicit null', None),
    ('source is not a string', {"source": 17}),
    ('source is empty', {"source": "   "}),
    ('declaration is not an object', "runtime/resident.lua"),
    ('pattern does not compile', dict(DECLARATION,
                                      moduleRevisionPattern="revision = (\\d+")),
]:
    with make_repo('mgt-runtime-baddecl-') as repo:
        add_module(repo, 'alpha')
        add_module(repo, 'broken', declaration=declaration)
        base = commit(repo, f'baseline with a malformed declaration ({label})')
        result = gate(repo, base, base)
        assert result.returncode != 0, f'{label}: expected failure\n{result.stdout}'
        assert 'games/broken' in result.stderr, f'{label}: {result.stderr}'
        assert 'residentRuntime' in result.stderr, f'{label}: {result.stderr}'

# --- A module added by this change needs no prior revision to increase. -------
with make_repo('mgt-runtime-new-game-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline with one module')
    add_module(repo, 'fresh')          # arrives with this change
    head = commit(repo, 'add a module that ships a resident runtime')
    result = gate(repo, base, head)
    assert result.returncode == 0, result.stdout + result.stderr

# --- Running the gate from a subdirectory must not be a silent pass. ----------
# Every other path here resolves through git, but MODULES_DIR is a repo-relative
# pathspec, so a run from Backend/ matched nothing and exited 0 with no output.
_sub = run('python3', str(SCRIPT), 'HEAD', 'HEAD', cwd=ROOT / 'Backend')
assert _sub.returncode != 0, (
    'running the gate outside the repository root must fail loudly, not exit 0 '
    'with no output: ' + _sub.stdout + _sub.stderr)
assert 'repository root' in _sub.stderr, _sub.stderr

# --- A declared source must name a file the module actually ships. -------------
# A one-character typo in `source` used to leave every subsequent runtime change
# ungated, silently: the gate validated that the string was non-empty and never
# that it resolved. Found by round 2 of review.
for label, source in [('a typo in the file name', 'runtime/hades2.lua'),
                      ('a file the module does not ship', 'runtime/nope.lua'),
                      ('a directory, not a file', 'runtime'),
                      ('a path escaping the module', '../../../etc/passwd')]:
    with make_repo(f'mgt-runtime-badsource-{abs(hash(source)) % 9973}-') as repo:
        add_module(repo, 'typo', declaration={**DECLARATION, 'source': source})
        head = commit(repo, f'declare a source that is {label}')
        result = gate(repo, head, head)
        assert result.returncode != 0, (
            f'source {source!r} ({label}) must be rejected, not silently ungate '
            'every later change: ' + result.stdout + result.stderr)

# --- A manifest that is valid JSON but not an object. -------------------------
# Load-bearing and untested (M3): removing the rejection made a list-shaped
# manifest a silent opt-out rather than a loud failure.
with make_repo('mgt-runtime-listmanifest-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline')
    manifest = repo / 'Backend/games/beta/module.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps([{"id": "beta"}]), encoding='utf-8')
    head = commit(repo, 'a module.json that is a JSON list')
    result = gate(repo, base, head)
    assert result.returncode != 0, (
        'a list-shaped module.json must be rejected, not silently ungated: '
        + result.stdout + result.stderr)
    assert 'must be a JSON object' in result.stderr, result.stderr

# --- A new module's runtime must still expose its revision markers. -----------
# Load-bearing and untested (M4): without it a brand-new game could ship a
# resident runtime with no revision discipline at all.
with make_repo('mgt-runtime-fresh-nomarkers-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline')
    add_module(repo, 'fresh')
    rt = repo / 'Backend/games/fresh/runtime/resident.lua'
    rt.write_text('local M = { version = 1 }\n', encoding='utf-8')
    head = commit(repo, 'a new module whose runtime exposes no revision markers')
    result = gate(repo, base, head)
    assert result.returncode != 0, (
        'a new module with no revision markers must be rejected: '
        + result.stdout + result.stderr)
    assert 'resident revision markers' in result.stderr, result.stderr

# --- Discovery must reach nested manifests, and stay out of fixtures. ---------
# Load-bearing and untested (M6): tightening discovery to the top level of
# Backend/games would silently ungate any module in a subdirectory.
with make_repo('mgt-runtime-nested-') as repo:
    add_module(repo, 'alpha')
    # The MANIFEST is what must be nested: discovery walks every
    # `Backend/games/**/module.json`, so a module whose manifest sits in a
    # subdirectory has to be found and gated too.
    inner = repo / 'Backend/games/beta/inner'
    inner.mkdir(parents=True, exist_ok=True)
    (inner / 'runtime').mkdir(parents=True, exist_ok=True)
    (inner / 'module.json').write_text(json.dumps({
        "schemaVersion": 1, "id": "beta", "displayName": "BETA",
        "protocolVersion": 5,
        "backend": {"adapter": "games.beta.adapter:Adapter"},
        "targetApplication": {"processName": "beta",
                              "bundleIdentifier": "com.example.beta"},
        "residentRuntime": {"source": "runtime/resident.lua"},
    }, indent=2) + '\n', encoding='utf-8')
    rt = inner / 'runtime/resident.lua'
    rt.write_text(LUA_BODY.format(rev=42), encoding='utf-8')
    base = commit(repo, 'baseline: a module in a subdirectory')
    rt.write_text(rt.read_text(encoding='utf-8') + '-- changed, no bump\n',
                  encoding='utf-8')
    head = commit(repo, 'change the nested module runtime without a bump')
    result = gate(repo, base, head)
    assert result.returncode != 0, (
        'a module in a subdirectory must be discovered and gated: '
        + result.stdout + result.stderr)
    assert 'changed without increasing resident revision' in result.stderr, result.stderr

# A reference fixture under Backend/ but outside Backend/games is not a module.
with make_repo('mgt-runtime-fixture-') as repo:
    add_module(repo, 'alpha')
    fixture = repo / 'ContractFixtures/reference_module/backend/module.json'
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(json.dumps({"schemaVersion": 1, "id": "reference"}),
                       encoding='utf-8')
    base = commit(repo, 'baseline: a manifest outside Backend/games')
    (repo / 'Backend/games/alpha/runtime/resident.lua').write_text(
        (repo / 'Backend/games/alpha/runtime/resident.lua').read_text(encoding='utf-8')
        + '-- changed, no bump\n', encoding='utf-8')
    head = commit(repo, 'change the module runtime; the fixture manifest is unrelated')
    result = gate(repo, base, head)
    assert result.returncode != 0, (
        'the real module must still be gated when a fixture manifest exists: '
        + result.stdout + result.stderr)
    assert 'reference_module' not in result.stderr, (
        'a manifest outside Backend/games must not be treated as a module: '
        + result.stderr)

# --- A runtime that stops exposing its revision markers must fail. ------------
# The missing-marker guard in revision_at() had no test of its own: removing it
# left the suite green. Worse, it is load-bearing beyond its error message --
# without it a runtime with NO markers yields a free first bump, because the
# comparison would have nothing to compare and treat the change as new. Found by
# round 2 of review.
for label, body in [
    ('no markers at all', 'local M = { version = 1 }\n'),
    ('only the previous marker',
     'local previousModule = __MacGamingTrainerV1\n'
     'if previousModule and previousModule.revision ~= 42 then end\n'),
    ('only the module marker', 'local M = { version = 1, revision = 42 }\n'),
]:
    with make_repo(f'mgt-runtime-nomarker-{abs(hash(body)) % 9973}-') as repo:
        add_module(repo, 'alpha')
        base = commit(repo, 'baseline')
        rt = repo / 'Backend/games/alpha/runtime/resident.lua'
        rt.write_text(body, encoding='utf-8')
        head = commit(repo, f'runtime with {label}')
        result = gate(repo, base, head)
        assert result.returncode != 0, (
            f'a runtime with {label} must fail, not pass with a free bump: '
            + result.stdout + result.stderr)
        assert 'resident revision markers' in result.stderr, result.stderr

# --- Invisible characters must not be load-bearing. ---------------------------
# Validating `source.strip()` and then using the raw string meant one stray space
# un-gated the whole module. Found by round 2 of review.
for label, source in [('a trailing space', 'runtime/resident.lua '),
                      ('a leading space', ' runtime/resident.lua'),
                      ('a trailing tab', 'runtime/resident.lua\t')]:
    with make_repo(f'mgt-runtime-ws-{abs(hash(source)) % 9973}-') as repo:
        add_module(repo, 'ws', declaration={**DECLARATION, 'source': source})
        base = commit(repo, 'baseline')
        rt = repo / 'Backend/games/ws/runtime/resident.lua'
        rt.write_text(rt.read_text(encoding='utf-8') + '-- edited, no bump\n',
                      encoding='utf-8')
        head = commit(repo, f'source has {label} and the runtime is edited')
        result = gate(repo, base, head)
        assert result.returncode != 0, (
            f'source with {label} must still gate the runtime, not un-gate it: '
            + result.stdout + result.stderr)

# --- Renaming the source is a rename, not an ungating. ------------------------
# Moving the runtime and repointing the declaration in one commit leaves the old
# path gated at the base and absent at the head. That is the same bypass as
# dropping the declaration, wearing a rename.
with make_repo('mgt-runtime-rename-') as repo:
    add_module(repo, 'mover')
    base = commit(repo, 'baseline')
    old = repo / 'Backend/games/mover/runtime/resident.lua'
    new_path = old.with_name('moved.lua')
    new_path.write_text(old.read_text(encoding='utf-8'), encoding='utf-8')
    old.unlink()
    manifest = repo / 'Backend/games/mover/module.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    data['residentRuntime']['source'] = 'runtime/moved.lua'
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    head = commit(repo, 'rename the runtime and repoint the declaration')
    result = gate(repo, base, head)
    assert result.returncode != 0, (
        'renaming the source out from under the gate must not un-gate it: '
        + result.stdout + result.stderr)

# --- The real repository's own manifest declares the runtime it ships. ---------
real = json.loads((ROOT / 'Backend/games/hades2/module.json').read_text(encoding='utf-8'))
assert 'residentRuntime' in real, 'the Hades module must declare its resident runtime'
_declared = real['residentRuntime']['source']
assert _declared == _declared.strip(), (
    'the declared source must not carry invisible characters; a trailing space '
    'once made the real Hades runtime un-gate silently (review C1)')
assert (ROOT / 'Backend/games/hades2' / _declared).is_file(), (
    'the declared resident runtime source must exist')
# Pin the EXACT source, not merely that some file exists. The old check passed
# for any existing file, so repointing the declaration at a stray file satisfied
# it while the real runtime went un-gated (review U8).
assert _declared == 'runtime/hades.lua', (
    f'the Hades module must declare the runtime it actually ships; got {_declared!r}')

# --- The gate must discover runtimes, not enumerate a hardcoded path. --------
# A substring scan of the source would flag the docstring that explains what the
# gate used to do, which is the wrong thing to police. What actually matters is
# that no path literal drives behaviour: if the gate works on a repository whose
# only game is called something else entirely -- which the second-game case above
# already establishes -- then discovery is metadata-driven by construction.
#
# So the check is the negative of the regression: remove the only declaration in
# this repository and the gate must report nothing to gate, not fall back to a
# remembered Hades path.
with make_repo('mgt-runtime-no-declaration-') as repo:
    add_module(repo, 'onlygame', declaration=DECLARATION)
    base = commit(repo, 'baseline')
    manifest = repo / 'Backend/games/onlygame/module.json'
    data = json.loads(manifest.read_text(encoding='utf-8'))
    del data['residentRuntime']
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    runtime = repo / 'Backend/games/onlygame/runtime/resident.lua'
    runtime.write_text(
        runtime.read_text(encoding='utf-8') + '-- changed with no declaration\n',
        encoding='utf-8')
    head = commit(repo, 'drop the declaration and change the runtime')
    result = gate(repo, base, head)
    # This case used to assert returncode == 0, which enshrined the bypass as
    # expected behaviour: one commit that drops the declaration AND edits the
    # runtime un-gated the file it had just been protecting. Round 2 of review
    # found it, and it was right -- the declaration is not authority to ungate.
    # A runtime gated at the base stays gated at the head.
    assert result.returncode != 0, (
        'dropping the declaration must not un-gate the runtime: '
        + result.stdout + result.stderr)
    assert 'may not un-gate its own resident runtime' in result.stderr, result.stderr
    assert 'runtime_revision_gate_ok' not in result.stdout, (
        f'nothing should have been gated, got: {result.stdout}')

# And the gate must not hardcode a path that no declaration could produce.
#
# The whole source is scanned, comments and docstrings stripped. The previous
# version split the file on two string markers and concatenated the two outer
# halves, leaving everything BETWEEN the markers unscanned; round 2 of review
# showed a hardcoded path dropped there is not detected. A substring scan cannot
# be reassembled from fragments and still mean "the whole file".
gate_source = SCRIPT.read_text(encoding='utf-8')
_code = '\n'.join(line.split('#', 1)[0] for line in gate_source.splitlines()
                  if line.split('#', 1)[0].strip())
_code = re.sub(r'"""(?:.|\n)*?"""', '', _code)
_code = re.sub(r"'''(?:.|\n)*?'''", '', _code)
assert '.lua' not in _code, 'the gate must not assume a resident runtime file extension'
assert 'games/' not in _code, 'the gate must not build a per-game path itself'
# Prove the scan covers the file rather than trusting it: plant a hardcoded path
# in the region the old split-based version left unscanned, and require that the
# same scan rejects it.
_planted = gate_source.replace(
    'def fail(', "HARDCODED = 'games/hades2/runtime/x.lua'\ndef fail(", 1)
assert _planted != gate_source, 'the anti-hardcode probe must actually plant something'
_planted_code = '\n'.join(line.split('#', 1)[0] for line in _planted.splitlines()
                          if line.split('#', 1)[0].strip())
assert 'games/' in _planted_code, 'the anti-hardcode scan must inspect the whole source'

# --- A comment is not a revision.  Round 3 finding, confirmed on the real
# hades.lua.  `revision_at` matched with `re.search`, which takes the FIRST match,
# so two comment lines carrying a decoy marker satisfied the gate while the real
# markers stayed put: `runtime_revision_gate_ok ... hades.lua 51->52` on a commit
# whose only change was two comments and a rewritten enemy-scaling function.
# That defeats the gate's entire purpose with the cheapest possible input.
#
# Both directions are asserted.  Rejecting the decoy is the fix; allowing the
# genuine bump is the check that the fix is not simply "reject everything".
with make_repo('mgt-runtime-comment-decoy-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline')
    runtime = repo / 'Backend/games/alpha/runtime/resident.lua'
    original = runtime.read_text(encoding='utf-8')

    runtime.write_text(
        '-- previousModule.revision ~= 43\n'
        '-- version = 1, revision = 43\n' + original
        + '-- REAL: the behaviour change that was never declared\n',
        encoding='utf-8')
    decoyed = commit(repo, 'behaviour change hidden behind comment markers')
    result = gate(repo, base, decoyed)
    assert result.returncode != 0, (
        'a revision marker inside a comment must not satisfy the gate: '
        f'{result.stdout}{result.stderr}')

    # A decoy inside a string literal is the same bypass: `re.search` is not a
    # Lua lexer, so quoting the marker is just as cheap as commenting it out.
    subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
    runtime.write_text(
        'local ARCHIVE_NOTE = "previousModule.revision ~= 43 '
        'version = 1, revision = 43"\n' + original
        + '-- REAL: boss health halved\n', encoding='utf-8')
    decoyed = commit(repo, 'behaviour change hidden behind a string literal')
    result = gate(repo, base, decoyed)
    assert result.returncode != 0, (
        'a revision marker inside a string literal must not satisfy the gate: '
        f'{result.stdout}{result.stderr}')

    # The other direction.  Stripping comments must not break a real bump, and
    # must not be confused by an ordinary comment that happens to quote the old
    # revision -- which is what an earlier, blunter fix did.
    subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
    runtime.write_text(
        '-- note: shipped at revision 42; the bump below is the real one\n'
        + original.replace('revision ~= 42', 'revision ~= 43')
                 .replace('revision = 42', 'revision = 43'),
        encoding='utf-8')
    genuine = commit(repo, 'a genuine revision bump beside a comment quoting 42')
    result = gate(repo, base, genuine)
    assert result.returncode == 0, (
        'a real revision bump must still be allowed, comment stripping included: '
        f'{result.stdout}{result.stderr}')

# --- A symlink is not a resident runtime.  Round 3 finding.  `cat-file -t`
# reports a symlink as `blob`, and `git diff --quiet -- <symlink>` is 0 because
# the LINK never changes -- so declaring one disabled gating silently and
# permanently, including on the commit that introduced it.  Worse, `git show` on a
# symlink returns its TARGET PATH as text, so a crafted filename could satisfy a
# marker search with a path instead of with code.
#
# The case edits the symlink's TARGET between two commits.  That is the exact
# shape of the bypass: the path the gate watches never changes, so the gate sees
# no change at all, while the file the game actually loads is rewritten.
with make_repo('mgt-runtime-symlink-') as repo:
    module_dir = repo / 'Backend/games/alpha'
    module_dir.mkdir(parents=True)
    (module_dir / 'NOTES.md').write_text('unrelated\n', encoding='utf-8')
    add_module(repo, 'alpha')
    # Commit the notes file alongside the module so that "change only an
    # unrelated file" has something tracked to change. `git reset --hard` removes
    # untracked files, so writing a fresh file after the reset would leave nothing
    # to commit and the case would fail in setup instead of testing anything.
    (module_dir / 'NOTES.md').write_text('unrelated, and tracked\n',
                                        encoding='utf-8')
    (module_dir / 'runtime/real.lua').write_text(
        LUA_BODY.format(rev=42), encoding='utf-8')
    (module_dir / 'runtime/link.lua').symlink_to('real.lua')
    manifest = json.loads((module_dir / 'module.json').read_text(encoding='utf-8'))
    manifest['residentRuntime']['source'] = 'runtime/link.lua'
    (module_dir / 'module.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    declared = commit(repo, 'declare a symlink as the resident runtime')
    (module_dir / 'runtime/real.lua').write_text(
        LUA_BODY.format(rev=42) + '-- REAL: the whole runtime, rewritten\n',
        encoding='utf-8')
    rewritten = commit(repo, 'rewrite the file the symlink points at')
    result = gate(repo, declared, rewritten)
    assert result.returncode != 0, (
        'a symlink declared as the resident runtime must not disable gating; '
        'the target changed while the watched path did not: '
        f'{result.stdout}{result.stderr}')
    assert 'regular file' in result.stderr or 'tracked' in result.stderr, (
        'the failure must say the source is not a regular tracked file: '
        f'{result.stderr!r}')

    # The declaration is refused on its own merits, not from the diff. That is the
    # whole point: `git diff` on a symlink is 0, so anything derived from the diff
    # sees no change at all, forever.
    subprocess.run(['git', 'reset', '-q', '--hard', declared], cwd=repo, check=True)
    (module_dir / 'NOTES.md').write_text('unrelated, and changed\n',
                                        encoding='utf-8')
    unrelated = commit(repo, 'change only the unrelated file')
    result = gate(repo, declared, unrelated)
    assert result.returncode != 0, (
        'a symlink declaration must be rejected even when the commit changes '
        f'nothing the gate would otherwise look at: {result.stdout}')


# --- The patterns are part of the gate.  Round 3 finding.  `module.json` was
# never itself gated, so the head-side comparison trusted a HEAD-CONTROLLED
# pattern.  Repointing both patterns at a pre-existing `CHANGELOG_MAX = 99999`
# satisfied the gate with the runtime untouched:
# `runtime_revision_gate_ok ... resident.lua 42->99999`, rc=0.
with make_repo('mgt-runtime-repointed-patterns-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline')
    module_dir = repo / 'Backend/games/alpha'
    runtime = module_dir / 'runtime/resident.lua'
    runtime.write_text('local CHANGELOG_MAX = 99999\n'
                       + runtime.read_text(encoding='utf-8'), encoding='utf-8')
    manifest = json.loads((module_dir / 'module.json').read_text(encoding='utf-8'))
    manifest['residentRuntime']['previousRevisionPattern'] = r'CHANGELOG_MAX = (\d+)'
    manifest['residentRuntime']['moduleRevisionPattern'] = r'CHANGELOG_MAX = (\d+)'
    (module_dir / 'module.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    repointed = commit(repo, 'repoint the revision patterns')
    result = gate(repo, base, repointed)
    assert result.returncode != 0, (
        'repointing the revision patterns in the same commit must not satisfy '
        f'the gate: {result.stdout}{result.stderr}')
    assert 'patterns' in result.stderr, (
        'the failure must name the patterns, or it reads as an unrelated '
        f'rejection: {result.stderr!r}')

    # The other direction: from a CLEAN baseline, a commit that leaves the
    # patterns alone must still be allowed, or the guard would simply forbid
    # ever touching module.json again. The reset matters: without it the base is
    # still the original commit while HEAD already carries the repointed
    # patterns, so the case measures the violation it just proved rather than the
    # thing it is trying to check.
    # A real bump, with the patterns untouched, is the ordinary happy path and
    # must not be reported as a pattern violation.
    subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
    bump(repo, module_dir, 'runtime/resident.lua', 42, 43)
    bumped = commit(repo, 'a genuine revision bump, patterns untouched')
    result = gate(repo, base, bumped)
    assert result.returncode == 0, (
        'a genuine bump with unchanged patterns is not a pattern violation: '
        f'{result.stdout}{result.stderr}')
    assert 'patterns' not in result.stderr, (
        'the pattern guard must not fire on an unchanged declaration: '
        f'{result.stderr!r}')

    # And with nothing changed at all, the gate passes: the patterns are only
    # a violation when a commit actually changes them.
    assert gate(repo, base, base).returncode == 0, (
        'the gate must pass on an unchanged tree: '
        f'{gate(repo, base, base).stderr}')

# --- A resident runtime that is not text is rejected, and the rejection is
# named.  Two distinct defects, and the first fix for the first one made the
# second worse.
#
# With a bare `text=True`, a byte outside UTF-8 raised UnicodeDecodeError out of
# subprocess: an unexplained traceback rather than a diagnosis. Adding
# `errors='replace'` fixed the crash -- and then let a binary blob satisfy the
# gate outright, because the marker regex still matched the ASCII text sitting
# between the replacement characters. So the blob must now be decoded STRICTLY
# and rejected with a name, which fails closed in the only direction available.
#
# The marker text is embedded in the blob on purpose, with a non-UTF-8 byte
# spliced INTO each marker. That is what makes the case discriminate: a strict
# decoder rejects the file, while any replace-style decoder quietly repairs the
# damaged marker into a valid one and lets the blob through. A blob with an
# intact marker would pass under both and prove nothing.
with make_repo('mgt-runtime-binary-source-') as repo:
    add_module(repo, 'alpha')
    module_dir = repo / 'Backend/games/alpha'
    runtime = module_dir / 'runtime/resident.lua'
    # 0x80 is not valid UTF-8 anywhere. Splicing it into `revision ~=` and into
    # `revision =` is what a lossy decode would paper over.
    body = (LUA_BODY.format(rev=42).encode('utf-8')
            .replace(b'revision ~= 42', b'revision ~= \x80 42')
            .replace(b'revision = 42', b'revision = \x80 42'))
    runtime.write_bytes(b'\x7fELF\x02\x01\x01\x00' + body)
    base = commit(repo, 'a resident runtime that is not text')
    # The runtime must actually CHANGE between the two refs. An unchanged runtime
    # short-circuits on `git diff --quiet` before its contents are ever read, so
    # comparing base to base would pass for a reason that has nothing to do with
    # decoding -- and a case that passes for the wrong reason is worse than none.
    runtime.write_bytes(b'\x7fELF\x02\x01\x01\x01' + body + b'\x00')
    changed = commit(repo, 'and a change to it')
    result = gate(repo, base, changed)
    assert result.returncode != 0, (
        f'a resident runtime that is not UTF-8 text must be rejected: {result.stdout}')
    assert 'Traceback' not in result.stderr, (
        'a non-UTF-8 resident runtime must be a named gate failure, not a '
        f'traceback: {result.stderr!r}')
    assert 'runtime revision gate' in result.stderr, (
        f'the failure must come from the gate: {result.stderr!r}')
    assert 'UTF-8' in result.stderr, (
        'the failure must say the source is not readable text, otherwise a '
        f'reviewer sees a missing-marker message and looks in the wrong place: '
        f'{result.stderr!r}')

# --- A malformed `source` is a named failure, not a traceback.  A NUL byte
# reaches `subprocess` and raises `ValueError: embedded null byte`.  It fails
# closed, but an unexplained traceback is not a diagnosis, and it is not what the
# other malformed declarations produce.
with make_repo('mgt-runtime-nul-source-') as repo:
    add_module(repo, 'alpha')
    module_dir = repo / 'Backend/games/alpha'
    manifest = json.loads((module_dir / 'module.json').read_text(encoding='utf-8'))
    manifest['residentRuntime']['source'] = 'runtime/resident\x00.lua'
    (module_dir / 'module.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    base = commit(repo, 'a NUL byte in the declared source')
    result = gate(repo, base, base)
    result = gate(repo, base, base)
    assert result.returncode != 0, (
        f'a NUL byte in a declared source must be rejected: {result.stdout}')
    assert 'Traceback' not in result.stderr, (
        'a malformed source must be a named gate failure, not a traceback: '
        f'{result.stderr!r}')
    assert 'runtime revision gate' in result.stderr, (
        f'the failure must come from the gate: {result.stderr!r}')

# --- Lua long brackets are LEVELLED, and the stripper must read the level.
# Round 4 finding: the round-3 fix stripped `--` comments, but recognised only
# the level-0 spelling `[[`. A levelled long comment was therefore not a comment
# and a levelled long string was not a string, so a decoy marker inside either
# survived into the code and `re.search` -- first match wins -- read it:
#
#     --[==[
#     previousModule.revision ~= 52
#     local M = { version = 1, revision = 52 }
#     ]==]
#
# shipped a real behaviour change at rc=0 on the real hades.lua. This is round 3's
# finding wearing a different hat: the fix's own lexer gap was the bypass. The
# stripper is the SOLE defence here, so a gap in it is a hole in the gate.
#
# The cases are written to discriminate a level-aware stripper from one that just
# searches for a closer: in `back-to-back levelled strings, different levels` a
# stripper that finds ANY `]=]` would close the level-1 string early and leave its
# decoy in the "code". That is the specific mistake being guarded against, and it
# is why the level must be matched on the opener AND the closer.
with make_repo('mgt-runtime-levelled-brackets-') as repo:
    add_module(repo, 'alpha')
    base = commit(repo, 'baseline')
    runtime = repo / 'Backend/games/alpha/runtime/resident.lua'
    original = runtime.read_text(encoding='utf-8')

    levelled = {
        'levelled long comment (level 1)':
            '--[==[\npreviousModule.revision ~= 43\n'
            'local M = { version = 1, revision = 43 }\n]==]\n',
        'levelled long comment (level 3)':
            '--[===[\npreviousModule.revision ~= 43\n'
            'local M = { version = 1, revision = 43 }\n]===]\n',
        'levelled long string (level 2)':
            'local N = [==[previousModule.revision ~= 43 '
            'version = 1, revision = 43]==]\n',
        'back-to-back levelled strings, different levels':
            'local A = [=[previousModule.revision ~= 43]=\n'
            'local B = [==[version = 1, revision = 43]==]\n',
        'levelled string closed by a wrong-level bracket':
            'local A = [==[previousModule.revision ~= 43]==]\n'
            'local B = [=[version = 1, revision = 43]=]\n',
        'levelled comment containing a level-0 string':
            '--[==[local N = [[previousModule.revision ~= 43]]]==]\n',
        'levelled comment after a levelled string':
            'local A = [=[x]=\n--[==[\npreviousModule.revision ~= 43\n]==]\n',
    }
    for label, prefix in levelled.items():
        subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
        runtime.write_text(prefix + original + '\n-- REAL: an undeclared change\n',
                           encoding='utf-8')
        head = commit(repo, f'decoy via {label}')
        result = gate(repo, base, head)
        assert result.returncode != 0, (
            f'a revision marker inside {label} must not satisfy the gate; the '
            f'stripper has to read the bracket level, not just look for a closer: '
            f'{result.stdout}{result.stderr}')

    # The over-strip direction. A levelled doc string is ordinary in Lua source,
    # and a genuine bump that sits below one must still be allowed -- otherwise
    # the fix would simply forbid the file from containing long comments.
    subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
    runtime.write_text(
        '---[==[ module documentation, as used throughout this file ]==]\n'
        + original.replace('revision ~= 42', 'revision ~= 43')
                 .replace('revision = 42', 'revision = 43'),
        encoding='utf-8')
    genuine = commit(repo, 'a genuine bump below a levelled doc string')
    result = gate(repo, base, genuine)
    assert result.returncode == 0, (
        'a genuine revision bump below a levelled doc string must still be '
        f'allowed: {result.stdout}{result.stderr}')

    # And the shapes the stripper must not damage: CRLF, a BOM, a shebang, a
    # string containing `--`, and a file with no trailing newline. Each of these
    # carries a REAL marker, so a stripper that eats any of them reports a
    # missing-marker failure on a file that plainly has one.
    for label, transform in (
        ('CRLF line endings', lambda s: s.replace('\n', '\r\n')),
        ('UTF-8 BOM', lambda s: '\ufeff' + s),
        ('shebang line', lambda s: '#!/usr/bin/env lua\n' + s),
        ('a string containing --', lambda s: 'local s = "a -- b"\n' + s),
        ('no trailing newline', lambda s: s.rstrip('\n')),
    ):
        subprocess.run(['git', 'reset', '-q', '--hard', base], cwd=repo, check=True)
        runtime.write_text(transform(original), encoding='utf-8')
        head = commit(repo, f'{label}')
        result = gate(repo, base, head)
        # These carry no revision change, so the gate must NOT report a missing
        # marker -- the commit only relocates whitespace, and the revision is
        # unchanged on both sides.
        assert 'does not expose both resident revision markers' not in result.stderr, (
            f'stripping must not lose a real marker in {label}: {result.stderr!r}')

print('runtime_revision_gate_ok')

workflow = (ROOT / '.github/workflows/linux-contracts.yml').read_text(encoding='utf-8')
assert 'fetch-depth: 0' in workflow
assert 'Tools/check_runtime_revision.py' in workflow
assert 'github.event.pull_request.base.sha' in workflow
assert 'github.event.before' in workflow
