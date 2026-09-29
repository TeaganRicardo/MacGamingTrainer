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
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from module_inventory import ModuleInventoryError, module_manifests_at_ref
from resident_runtime import (
    DECLARATION_KEY,
    ResidentRuntimeDeclarationError,
    parse_resident_runtime_declaration,
)

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
    try:
        manifests = module_manifests_at_ref(ref, Path.cwd())
    except ModuleInventoryError as error:
        fail(str(error))
    for manifest_path, game_id, data in manifests:
        # Distinguish an absent declaration from an explicit null: null is a
        # malformed opt-out and therefore fails through the shared parser.
        declaration = data.get(DECLARATION_KEY, _ABSENT)
        if declaration is _ABSENT:
            continue
        try:
            spec = parse_resident_runtime_declaration(
                declaration,
                manifest_path=manifest_path,
                source_exists=lambda runtime_path: runtime_is_tracked(
                    ref, str(runtime_path)
                ),
                source_description=f"a regular file tracked at {ref}",
            )
        except ResidentRuntimeDeclarationError as error:
            fail(str(error))
        found.append((
            str(spec.runtime_path),
            spec.previous_revision_pattern,
            spec.module_revision_pattern,
        ))
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
