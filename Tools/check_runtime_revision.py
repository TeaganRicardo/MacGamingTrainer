#!/usr/bin/env python3
"""Require a resident-runtime revision bump when Hades Lua source changes."""
import re
import subprocess
import sys
from pathlib import Path

RUNTIME = Path('Backend/games/hades2/runtime/hades.lua')
PREVIOUS_RE = re.compile(r'previousModule\.revision\s*~=\s*(\d+)')
MODULE_RE = re.compile(r'version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)')


def fail(message):
    print(f'runtime revision gate: {message}', file=sys.stderr)
    raise SystemExit(1)


def git(*args):
    result = subprocess.run(['git', *args], text=True, capture_output=True)
    if result.returncode != 0:
        fail(result.stderr.strip() or result.stdout.strip() or 'git command failed')
    return result.stdout


def revision_at(ref):
    text = git('show', f'{ref}:{RUNTIME.as_posix()}')
    previous = PREVIOUS_RE.search(text)
    module = MODULE_RE.search(text)
    if previous is None or module is None:
        fail(f'{ref} does not expose both resident revision markers')
    values = (int(previous.group(1)), int(module.group(1)))
    if values[0] != values[1]:
        fail(f'{ref} resident revision markers are not consistent: {values[0]} vs {values[1]}')
    return values[0]


def main(argv):
    if len(argv) != 3:
        fail('usage: check_runtime_revision.py <base-ref> <head-ref>')
    base, head = argv[1:]
    changed = subprocess.run(
        ['git', 'diff', '--quiet', base, head, '--', RUNTIME.as_posix()],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if changed.returncode == 0:
        return
    if changed.returncode != 1:
        fail(changed.stderr.strip() or 'unable to compare runtime source')

    base_revision = revision_at(base)
    head_revision = revision_at(head)
    if head_revision <= base_revision:
        fail(
            f'{RUNTIME} changed without increasing resident revision '
            f'({base_revision} -> {head_revision})'
        )
    print(f'runtime_revision_gate_ok {base_revision}->{head_revision}')


if __name__ == '__main__':
    main(sys.argv)
