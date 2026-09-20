#!/usr/bin/env python3
"""Enforce Hades II resident-runtime revision discipline across two git commits."""
from pathlib import Path
import argparse
import re
import subprocess
import sys

RUNTIME_PATH = 'Backend/games/hades2/runtime/hades.lua'
_PREVIOUS_RE = re.compile(r'previousModule\.revision\s*~=\s*(\d+)')
_CURRENT_RE = re.compile(r'\bversion\s*=\s*1\s*,\s*revision\s*=\s*(\d+)')


def _revision(text, label):
    previous = _PREVIOUS_RE.findall(text)
    current = _CURRENT_RE.findall(text)
    if len(previous) != 1 or len(current) != 1:
        raise ValueError(f'{label}: expected exactly one resident revision declaration pair')
    previous_value = int(previous[0])
    current_value = int(current[0])
    if previous_value != current_value:
        raise ValueError(
            f'{label}: resident revision declarations disagree '
            f'(previousModule={previous_value}, module={current_value})'
        )
    return current_value


def _git(repo, *args):
    result = subprocess.run(
        ['git', *args], cwd=repo, text=True, capture_output=True, check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or f'git {" ".join(args)} failed')
    return result.stdout


def _show(repo, revision):
    return _git(repo, 'show', f'{revision}:{RUNTIME_PATH}')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('head')
    parser.add_argument('--repo', default='.')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()

    try:
        head_text = _show(repo, args.head)
        head_revision = _revision(head_text, args.head)
        changed = bool(_git(repo, 'diff', '--name-only', args.base, args.head, '--', RUNTIME_PATH).strip())
        if not changed:
            print(f'runtime_revision_guard_ok unchanged revision={head_revision}')
            return 0

        base_text = _show(repo, args.base)
        base_revision = _revision(base_text, args.base)
        if head_revision <= base_revision:
            raise ValueError(
                f'{RUNTIME_PATH} changed from {args.base} to {args.head}; '
                f'must increase resident revision (base={base_revision}, head={head_revision})'
            )
        print(f'runtime_revision_guard_ok {base_revision}->{head_revision}')
        return 0
    except (ValueError, RuntimeError) as error:
        print(f'runtime_revision_guard_failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
