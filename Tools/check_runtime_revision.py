#!/usr/bin/env python3
"""Require a resident-runtime revision bump when resident source changes.

Which files are resident runtime, and how their revision is spelled, is declared
per game module in `module.json`. This gate used to name the Hades runtime
directly, so a second game with a resident runtime would have gone ungated and
the "shared" gate would have been a single-game gate wearing a generic name.
Discovery is now metadata-driven: every module that declares a `residentRuntime`
is checked, and a module that adds one is gated from that commit onward.

This tool deliberately knows nothing about any particular game. It reads the
declaration, resolves it relative to the module directory, and compares
revisions. A module with no `residentRuntime` is simply not gated.
"""
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

MODULES_DIR = Path('Backend/games')
DECLARATION_KEY = 'residentRuntime'
DEFAULT_PREVIOUS_RE = r'previousModule\.revision\s*~=\s*(\d+)'
DEFAULT_MODULE_RE = r'version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)'

# Distinguishes 'key absent' from 'key present but null'.
_ABSENT = object()


def fail(message) -> NoReturn:
    print(f'runtime revision gate: {message}', file=sys.stderr)
    raise SystemExit(1)


def git(*args):
    # `errors='replace'` rather than a bare `text=True`: a binary resident runtime
    # raised UnicodeDecodeError out of the decoder, so the gate died with a
    # traceback instead of naming the file. A gate that crashes is a gate whose
    # failure is not actionable, and a crash is not a pass.
    result = subprocess.run(['git', *args], text=True, capture_output=True,
                            errors='replace')
    if result.returncode != 0:
        fail(result.stderr.strip() or result.stdout.strip() or 'git command failed')
    return result.stdout


def manifests_at(ref):
    """Every module manifest present at `ref`, as (path, parsed json) pairs."""
    # core.quotePath is off deliberately: with it on, git quotes any path that is
    # not pure ASCII, so a module directory such as `games/hades2` written with an
    # accented character would not end with '/module.json' and would be silently
    # ungated. Not reachable through the loader, which requires dir == id and an
    # ASCII id -- but a discovery step that quietly depends on the filesystem
    # being ASCII is a latent hole, and switching the quoting off costs one
    # argument.
    listing = git('-c', 'core.quotePath=false', 'ls-tree', '-r', '--name-only',
                  ref, '--', MODULES_DIR.as_posix())
    out = []
    for line in listing.splitlines():
        if not line.endswith('/module.json'):
            continue
        raw = git('show', f'{ref}:{line}')
        try:
            data = json.loads(raw)
        except ValueError as error:
            fail(f'{line} is not valid JSON: {error}')
        if not isinstance(data, dict):
            fail(f'{line} must be a JSON object, not {type(data).__name__}')
        out.append((line, data))
    return out


def runtime_is_tracked(ref, runtime):
    """Is `runtime` a file tracked at `ref`?

    Git is asked rather than the filesystem: the gate reads the tree at `ref`,
    which is not necessarily the checkout on disk, so a file that exists locally
    but not in that commit must not satisfy the declaration.
    """
    # A plain blob check is not enough. A SYMLINK is a blob (mode 120000), and
    # `git diff --quiet -- <symlink>` is 0 because the link itself never changes
    # -- so declaring a symlink as the resident runtime disabled gating silently
    # and permanently, including on the commit that introduced it. `git show` on a
    # symlink returns its TARGET PATH as text, which a crafted filename can then
    # satisfy as if it were resident code.
    #
    # So the mode is checked, and only a regular file is accepted. `ls-tree` is
    # used because it reports the mode without a second object lookup, and its
    # path is already validated relative to the module.
    probe = subprocess.run(
        ['git', 'ls-tree', ref, '--', runtime],
        capture_output=True, text=True, errors='replace')
    if probe.returncode != 0:
        return False
    modes = {line.split()[0] for line in probe.stdout.splitlines() if line.strip()}
    return bool(modes) and modes <= {'100644', '100755'}


def runtimes_at(ref):
    """(repo-relative runtime path, previous regex, module regex) for each module
    that declares a resident runtime at `ref`, sorted for a stable report."""
    found = []
    for manifest_path, data in manifests_at(ref):
        # `.get()` returns None for an ABSENT key and for an explicit JSON
        # `null`, so testing for None would make `"residentRuntime": null` a
        # silent opt-out: a module that declares the key and then nulls it would
        # be treated as one that never declared it. An explicit null is a
        # malformed declaration, and a malformed declaration must fail.
        declaration = data.get(DECLARATION_KEY, _ABSENT)
        if declaration is _ABSENT:
            continue
        if not isinstance(declaration, dict):
            fail(f'{manifest_path}: {DECLARATION_KEY} must be an object')
        source = declaration.get('source')
        if not isinstance(source, str) or not source.strip():
            fail(f'{manifest_path}: {DECLARATION_KEY}.source must be a non-empty string')
        # Strip, then use the STRIPPED value. Validating `.strip()` and then
        # using the raw string is how one stray space un-gated a whole module:
        # `"runtime/resident.lua "` passed the emptiness check and resolved to a
        # file that does not exist. The tracked-file check below would now catch
        # that anyway, but a declaration that must carry invisible characters to
        # work is a declaration nobody can review.
        source = source.strip()
        # A NUL byte reaches subprocess and raises `ValueError: embedded null
        # byte` -- a traceback rather than a named gate failure. It fails closed,
        # but an unexplained traceback is not a diagnosis. An absolute path or a
        # `..` segment cannot name a file inside the module directory at all, so
        # both are refused by name rather than failing later and less clearly.
        if '\x00' in source or source.startswith('/'):
            fail(f'{manifest_path}: {DECLARATION_KEY}.source must name a file '
                 'inside the module directory')
        if any(segment == '..' for segment in source.split('/')):
            fail(f'{manifest_path}: {DECLARATION_KEY}.source must not traverse '
                 'out of the module directory')
        module_dir = Path(manifest_path).parent
        # The declared source must resolve to a file the module actually ships
        # at this ref. Checking only that `source` is a non-empty string meant a
        # one-character typo in the file name left every subsequent runtime
        # change ungated, silently, forever. A declaration that names nothing is
        # not a weak declaration, it is a broken one.
        runtime = str(module_dir / source)
        if not runtime_is_tracked(ref, runtime):
            fail(f'{manifest_path}: {DECLARATION_KEY}.source {source!r} does not name a '
                 f'file tracked at {ref} (resolved to {runtime})')
        previous = declaration.get('previousRevisionPattern', DEFAULT_PREVIOUS_RE)
        module = declaration.get('moduleRevisionPattern', DEFAULT_MODULE_RE)
        for name, pattern in (('previousRevisionPattern', previous),
                              ('moduleRevisionPattern', module)):
            if not isinstance(pattern, str) or not pattern.strip():
                fail(f'{manifest_path}: {DECLARATION_KEY}.{name} must be a non-empty string')
            try:
                re.compile(pattern)
            except re.error as error:
                fail(f'{manifest_path}: {DECLARATION_KEY}.{name} does not compile: {error}')
        found.append((runtime, re.compile(previous), re.compile(module)))
    return sorted(found)


def _long_bracket_level(text, i):
    """The `=` count of a long bracket opening at `text[i]`, or None.

    Lua's long brackets are LEVELLED: `[==[ ... ]==]`, with an arbitrary number
    of `=`. The previous version matched only the level-0 spelling `[[`, so a
    levelled long comment was not recognised as a comment and a levelled long
    string was not recognised as a string. A decoy marker inside either survived
    into the "code" and `re.search` -- which takes the first match -- read it:

        --[==[
        previousModule.revision ~= 52
        local M = { version = 1, revision = 52 }
        ]==]

    shipped a real behaviour change at rc=0 on the real hades.lua. The level
    must be read, not assumed, and the closer must carry the same level.
    """
    if text[i] != '[':
        return None
    j = i + 1
    while j < len(text) and text[j] == '=':
        j += 1
    if j < len(text) and text[j] == '[':
        return j - i - 1
    return None


def strip_lua_comments(text):
    """Remove Lua comments, respecting string literals.

    A revision marker inside a comment proves nothing: the gate exists to catch a
    behaviour change that forgot its revision bump, and two comment lines
    containing a decoy marker satisfied it, on the real hades.lua, at rc=0, with
    no manifest edit and no other file touched. `re.search` takes the first
    match, so a decoy anywhere above the real marker wins.

    Stripping is string-aware so that a `--` inside a quoted string does not
    truncate the rest of the line, and long-bracket strings are skipped whole.
    Long brackets are levelled, and both the opener and the closer must carry the
    same level -- see `_long_bracket_level`.

    This is a line filter, not a Lua parser: it is only ever used to decide
    which lines may supply a marker, so being conservative -- leaving text alone
    rather than deleting code -- is the safe direction. The one thing it can lose
    is an UNTERMINATED long bracket, which is already invalid Lua.

    Everything here was measured rather than reasoned about. The shapes that
    resolve correctly, and were each checked to still find a real marker after
    stripping: CRLF line endings, a UTF-8 BOM, a shebang line, apostrophes
    inside comments, escaped quotes inside strings, a marker split across a
    comment boundary, a file with no trailing newline, level-0 doc strings, and
    back-to-back long strings at different levels.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        two = text[i:i + 2]
        if two == '--':
            level = _long_bracket_level(text, i + 2)
            if level is None:
                end = text.find('\n', i)
                i = n if end == -1 else end
            else:
                closer = ']' + '=' * level + ']'
                end = text.find(closer, i + 2 + level + 2)
                i = n if end == -1 else end + len(closer)
            continue
        level = _long_bracket_level(text, i)
        if level is not None:
            # A long string. Skipped whole, whatever its level.
            closer = ']' + '=' * level + ']'
            end = text.find(closer, i + level + 2)
            i = n if end == -1 else end + len(closer)
            out.append('""')
            continue
        ch = text[i]
        if ch in ('"', "'"):
            quote = ch
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        out.append(ch)
        i += 1
    return ''.join(out)

def revision_at(ref, runtime, previous_re, module_re):
    # Read the blob as BYTES and decode strictly, rather than accepting whatever
    # `git show` hands back. With `errors='replace'` a non-UTF-8 resident runtime
    # did not crash, which was the previous fix's whole point -- but it then
    # sailed through the marker check on replacement characters and a real
    # revision, so a binary file could satisfy the gate outright. Fails closed
    # with a name attached, which is the only acceptable direction here.
    blob = subprocess.run(['git', 'show', f'{ref}:{runtime}'],
                          capture_output=True).stdout
    try:
        text = blob.decode('utf-8')
    except UnicodeDecodeError as error:
        fail(f'{ref}:{runtime} is not valid UTF-8 text, so it cannot be a '
             f'resident runtime this gate can read: {error}')
    # Markers are matched against code only. A marker in a comment is not a
    # revision, and treating it as one is the whole bypass.
    text = strip_lua_comments(text)
    previous = previous_re.search(text)
    module = module_re.search(text)
    if previous is None or module is None:
        fail(f'{ref}:{runtime} does not expose both resident revision markers')
    values = (int(previous.group(1)), int(module.group(1)))
    if values[0] != values[1]:
        fail(f'{runtime} at {ref} has inconsistent resident revision markers: '
             f'{values[0]} vs {values[1]}')
    return values[0]


def _require_repo_root():
    """Refuse to run outside the repository root.

    MODULES_DIR is a repo-relative pathspec, so running the gate from a
    subdirectory made every discovery query match nothing and the gate exited 0
    with no output -- a silent pass, the worst shape a gate failure can take.
    Review found it: CI happens to run at the root, so it was not exploitable
    there, but a local run from Backend/ was.

    Every other path this gate touches is resolved through git (`ls-tree`,
    `show`, `cat-file`) and is therefore CWD-independent already; only this one
    relative pathspec is not, so this is the whole fix.
    """
    top = subprocess.run(['git', 'rev-parse', '--show-toplevel'],
                         capture_output=True, text=True, errors='replace')
    if top.returncode != 0:
        fail('not inside a git repository')
    if Path(top.stdout.strip()).resolve() != Path.cwd().resolve():
        fail(f'run this gate from the repository root, not {Path.cwd()}')


def main(argv):
    if len(argv) != 3:
        fail('usage: check_runtime_revision.py <base-ref> <head-ref>')
    base, head = argv[1:]
    _require_repo_root()
    merge_base = git('merge-base', base, head).strip()
    if not merge_base:
        fail('unable to resolve merge-base for runtime revision gate')

    # The base is where a runtime that existed before this change must be
    # compared from; the head is what is being proposed. A runtime introduced by
    # this change has no base counterpart, so it is not gated here.
    base_runtimes = {runtime: (prev, mod) for runtime, prev, mod in runtimes_at(merge_base)}
    head_runtimes = {runtime: (prev, mod) for runtime, prev, mod in runtimes_at(head)}

    # The union, not the head set. A runtime gated at the base is still gated at
    # the head, whether or not the head still declares it: iterating head only
    # meant a single commit that dropped `residentRuntime` AND edited the runtime
    # un-gated the file it had just been protecting. The declaration is not
    # authority to ungate -- removing it is itself a gated change.
    for runtime in sorted(set(base_runtimes) | set(head_runtimes)):
        if runtime not in head_runtimes:
            fail(f'{runtime} is declared gated at {merge_base} but not at {head}: '
                 'a change may not un-gate its own resident runtime')
        previous_pattern, module_pattern = head_runtimes[runtime]
        if runtime in base_runtimes:
            # The patterns themselves are part of the gate, so a change that
            # repoints them is itself a gated change. Repointing both at some
            # pre-existing `CHANGELOG_MAX = 99999` in the runtime satisfied the
            # gate with the runtime untouched -- `module.json` was never gated, so
            # the head-side comparison trusted a head-controlled pattern. Read
            # the BASE patterns for the base revision, and require the head
            # patterns to still match the same markers they did at the base.
            base_previous, base_module = base_runtimes[runtime]
            if (previous_pattern.pattern, module_pattern.pattern) != (
                    base_previous.pattern, base_module.pattern):
                fail(f'{runtime}: the revision patterns changed in this commit '
                     f'({base_previous.pattern!r}/{base_module.pattern!r} -> '
                     f'{previous_pattern.pattern!r}/{module_pattern.pattern!r}). '
                     'A change may not redefine how its own revision is read; '
                     'land that in its own commit, reviewed on its own.')
        changed = subprocess.run(
            ['git', 'diff', '--quiet', merge_base, head, '--', runtime],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if changed.returncode == 0:
            continue
        if changed.returncode != 1:
            fail(changed.stderr.strip() or 'unable to compare runtime source')
        if runtime not in base_runtimes:
            # New in this change. It has no prior revision to increase, and the
            # marker consistency check below still applies at the head.
            revision_at(head, runtime, previous_pattern, module_pattern)
            continue
        base_previous, base_module = base_runtimes[runtime]
        base_revision = revision_at(merge_base, runtime, base_previous, base_module)
        head_revision = revision_at(head, runtime, previous_pattern, module_pattern)
        if head_revision <= base_revision:
            fail(
                f'{runtime} changed without increasing resident revision '
                f'({base_revision} -> {head_revision})'
            )
        print(f'runtime_revision_gate_ok {runtime} {base_revision}->{head_revision}')


if __name__ == '__main__':
    main(sys.argv)
