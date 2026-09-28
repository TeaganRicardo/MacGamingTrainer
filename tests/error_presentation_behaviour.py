"""Capture the current error-presentation behaviour as a comparable baseline.

#204 collapses seven mapping tables into one declarative registry. The refactor
is only safe if every message resolves to the same key AND the same arguments
before and after. This snapshot is the "before" side of that proof: it probes
every registered message through the real funnel and records the result.

Re-run it with `--compare` after the refactor and diff. A single changed key
means a player's error message silently became a different sentence.

IMPORTANT: this script probes the PUBLIC surface only -- `presentation_for`,
`present_runtime_error`, and the module's own `_FALLBACK_KEY`. An earlier
version enumerated `MESSAGE_KEYS`/`PREFIX_KEYS`/... by name, so the moment the
registry replaced those tables it reported "0 direct mappings" and would have
passed a refactor that broke every single one. A behaviour baseline that reads
the thing it is meant to measure is not a baseline.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Backend"))

logging.disable(logging.CRITICAL)

from games.hades2 import error_presentation as ep  # noqa: E402
from games.hades2 import runtime_error_presentation as rep  # noqa: E402


class _AdapterError(Exception):
    """Stands in for the Core error type the funnel expects."""

    code = "operation_failed"
    presentation = ""
    diagnostic = None

    def __init__(self, code, raw):
        super().__init__(raw)
        self.code = code
        self.presentation = raw
        self.diagnostic = raw


#: The registry must produce at least this many genuine shape collisions for the
#: cross-shape probe set to be worth anything. See MIN_SHAPE_COLLISIONS usage.
MIN_SHAPE_COLLISIONS = 2


def _declared_messages() -> list[str]:
    """Every message the module claims to recognise, from its own declaration.

    `REGISTRY` is the module's declared vocabulary. It is a list of declarative
    rules, so the probeable messages are the literal rules plus a sample for
    each pattern-based rule. That keeps the baseline tied to what the module
    SAYS it handles, rather than to a table layout that a refactor may rename.
    """
    rules = getattr(ep, "REGISTRY", None)
    if rules is None:
        # Pre-registry layout. Kept so the same script can produce the "before"
        # snapshot from a checkout that has not been refactored yet.
        seen: list[str] = []
        for table_name in ("MESSAGE_KEYS", "PREFIX_KEYS", "DELIMITED_AFFIX_KEYS",
                           "SEGMENTED_KEYS", "DELIMITED_KEYS"):
            table = getattr(ep, table_name, None)
            if isinstance(table, dict):
                for key in table:
                    if isinstance(key, str) and key not in seen:
                        seen.append(key)
        return sorted(seen)

    messages: list[str] = []
    for rule in rules:
        shape = rule.get("match")
        if shape == "literal":
            messages.append(rule["message"])
        elif shape == "prefix":
            # A prefix rule matches anything after it; probe with a value that
            # exercises the argument convention.
            messages.append(rule["prefix"] + "sample-value")
        elif shape == "affix":
            messages.append(rule["prefix"] + "sample-value" + rule["suffix"])
        elif shape == "delimited":
            messages.append(rule["open"] + "sample-value" + rule["close"])
        elif shape == "segmented":
            messages.append(
                rule["prefix"] + "sample-value" + rule["separator"]
                + "sample-code" + rule["terminator"] + "sample-detail")
    cross, collisions = _cross_shape_probes(rules)
    # A guard that finds zero collisions is not a guard. This registry has real
    # overlaps, so require the count to be non-trivial: if a future edit removes
    # them all, or the matching regresses, this fails instead of quietly
    # degrading into a self-satisfying set of probes.
    if collisions < MIN_SHAPE_COLLISIONS:
        raise AssertionError(
            f'only {collisions} cross-shape collisions found; this guard needs '
            f'at least {MIN_SHAPE_COLLISIONS} to mean anything')
    return sorted(set(messages) | set(cross))


def _cross_shape_probes(rules) -> set[str]:
    """Messages that two different rule shapes could both claim.

    Every probe above is built from one rule's own fields, so it always
    satisfies the rule it was derived from. That makes each probe blind to
    ordering: if `prefix` were dispatched before `affix`, a prefix probe would
    still be caught by the prefix rule and every test would stay green while
    `请先启动 Hades II 并进入存档。` resolved to the untranslated static tail.

    The order contract is a property of *overlapping* shapes, so the guard has
    to overlap them. Two overlaps exist in this registry:

    - prefix vs affix/segmented -- `请先启动 ` and `查询 ` are prefixes, and the
      same openings appear in an affix and a segmented rule. Correct order
      yields `['Hades II']`; the wrong order yields the whole static tail.
    - prefix vs regex -- four prefixes are a strict prefix of a regex pattern
      (`连接被拒绝：`, `请先退出 `, `无法运行 `, `未经验证的游戏版本：`,
      `未从本机 `). Dispatching prefix first would make those regex rules dead
      code and hand the player a raw remainder instead of split arguments.

    So every prefix is also probed with a message that another shape should
    claim instead, and every regex sample is re-probed so the regex shape is
    observed independently of whether a prefix happens to match it.
    """
    probes: set[str] = set()
    # Counted so the caller can require a minimum: a guard that counts zero
    # collisions is not a guard, it is decoration.
    collisions = 0
    regex_patterns = [r["pattern"] for r in rules if r.get("match") == "regex"]

    # A rule's OWN prefix is not enough. The real competing prefix rules are
    # '请先启动 ' and '查询 ' -- with a TRAILING SPACE -- while the affix and
    # segmented rules carry '请先启动' and '查询' without one. Probing
    # `rule["prefix"] + "Hades II"` therefore never produced a message that
    # starts with the prefix string it was meant to compete with, so every one
    # of those probes was self-satisfying: it could only ever be claimed by the
    # shape it was built from. Found by round-2 review.
    #
    # So the competing prefix is looked up in the registry, and the probe is the
    # affix/segmented rule's own canonical message -- which is exactly the
    # message both shapes would claim.
    def competing_prefix(head: str) -> str | None:
        for r in rules:
            if r.get("match") == "prefix" and r["prefix"].startswith(head):
                return r["prefix"]
        return None

    # The value carries a LEADING SPACE, and that is the whole point.
    #
    # The affix and segmented openings are '请先启动' and '查询' with no trailing
    # space, while the competing prefix rules are '请先启动 ' and '查询 ' WITH
    # one. Concatenating a bare value produced '请先启动Hades II 并进入存档。',
    # which does not start with '请先启动 ' -- so the probe was claimed by exactly
    # one rule, and two versions of this guard counted that as a collision. The
    # counter was incremented on `rival is not None` alone, which says only that
    # some prefix rule extends this opening, never that this message starts with
    # it. Round 2 fixed the lookup and left the concatenation wrong; round 3
    # found the count still read 2 against an oracle that says 0.
    #
    # With the space the message is the affix rule's own canonical output AND a
    # genuine prefix match, so dispatch order alone decides which shape claims
    # it, with two different argument lists. That is what is being counted.
    colliding_value = " Hades II"
    for rule in rules:
        shape = rule.get("match")
        if shape == "affix":
            message = rule["prefix"] + colliding_value + rule["suffix"]
            probes.add(message)
            rival = competing_prefix(rule["prefix"])
            if rival is not None and message.startswith(rival):
                collisions += 1
        elif shape == "segmented":
            message = (rule["prefix"] + colliding_value + rule["separator"]
                       + "-9" + rule["terminator"] + "boom")
            probes.add(message)
            rival = competing_prefix(rule["prefix"])
            if rival is not None and message.startswith(rival):
                collisions += 1

    # For each prefix, find any regex that also matches a message starting with
    # it. Those are the pairs where dispatch order decides the arguments, so
    # probe the real regex message and require the regex shape to win.
    import re as _re
    for rule in rules:
        if rule.get("match") != "prefix":
            continue
        head = rule["prefix"]
        for sample in _regex_probes():
            if sample.startswith(head) and any(
                    _re.match(p, sample) for p in regex_patterns):
                probes.add(sample)
    return probes, collisions
def _regex_probes() -> list[str]:
    """Concrete messages for the pattern rules, so a regex change is caught."""
    samples = {
        "architectureRequired": "Some Game 适配器需要 arm64 原生游戏。",
        "attachDenied": "连接被拒绝：operation not permitted。退出游戏后使用",
        "uuidLookupFailed": "找不到匹配架构的 Mach-O UUID suffix。",
        "missingOfficialNames": "未从本机 Hades II 中文语言文件解析到 3 项",
        "commandFailed": "some tool 失败（1）：detail",
        "timeout": "some tool 超时（30 秒）；",
        "prepareWhileRunning": "请先退出 Hades II；",
        "unverifiedBuildWarning": "未经验证的游戏版本：version=1.2, build=3, UUID=abc。",
        "commandLaunchFailed": "无法运行 some tool：detail",
        "preferenceNewerFormat": "kind 使用了更新的数据格式（schemaVersion=9，当前支持 8），",
        "preferenceOlderFormat": "kind 使用了已不再支持的旧数据格式（schemaVersion=1，当前支持 8），",
    }
    rules = getattr(ep, "REGISTRY", None)
    if rules is None:
        return []
    out = []
    for rule in rules:
        if rule.get("match") != "regex":
            continue
        key = rule["key"].rsplit(".", 1)[-1]
        if key in samples:
            out.append(samples[key])
    return out


def _runtime_messages() -> list[tuple[str, str]]:
    """(command, message) pairs from the per-command runtime tables."""
    pairs: list[tuple[str, str]] = []
    for command, mapping in rep._RUNTIME_KEYS.items():
        for message in mapping:
            pairs.append((command, message))
    for command, composed in getattr(rep, "_COMPOSED_PREFIXES", {}).items():
        for prefix, _ in composed:
            pairs.append((command, f"{prefix} TraitOfHermes"))
    for prefix, _ in getattr(rep, "_SHARED_COMPOSED", ()):
        for command in rep._RUNTIME_KEYS:
            pairs.append((command, f"{prefix} TraitOfHermes"))
    return pairs


def snapshot() -> dict:
    direct = {}
    for message in _declared_messages() + _regex_probes():
        try:
            key, arguments = ep.presentation_for(message)
        except Exception as error:  # a rule that raises is itself a finding
            direct[message] = f"RAISED {type(error).__name__}: {error}"
            continue
        if key is not None:
            direct[message] = {"key": key, "arguments": list(arguments)}

    runtime = {}
    for command, message in _runtime_messages():
        try:
            mapped = rep.present_runtime_error(command, _AdapterError("lua_error", message))
        except Exception as error:
            runtime[f"{command}::{message}"] = f"RAISED {type(error).__name__}: {error}"
            continue
        runtime[f"{command}::{message}"] = {
            "key": getattr(mapped, "presentation", None),
            "arguments": list(getattr(mapped, "arguments", ()) or ()),
        }

    return {
        "direct": direct,
        "runtime": runtime,
        "fallback_key": rep._FALLBACK_KEY,
        "runtime_commands": sorted(rep._RUNTIME_KEYS),
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write the snapshot as JSON")
    parser.add_argument("--compare", type=Path, help="diff against a saved snapshot")
    args = parser.parse_args()

    data = snapshot()

    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        changed = []
        for section in ("direct", "runtime"):
            old = before.get(section, {})
            new = data.get(section, {})
            for key in sorted(set(old) | set(new)):
                if old.get(key) != new.get(key):
                    changed.append((section, key, old.get(key), new.get(key)))
        for key in ("fallback_key", "runtime_commands"):
            if before.get(key) != data.get(key):
                changed.append(("meta", key, before.get(key), data.get(key)))
        if changed:
            for section, key, old, new in changed:
                print(f"CHANGED {section} {key!r}\n  before: {old}\n  after:  {new}")
            print(f"\n{len(changed)} behaviour change(s) — a player's error copy moved")
            raise SystemExit(1)
        print("error_presentation_behaviour_unchanged")
        return

    if args.out:
        args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"wrote {args.out} ({len(data['direct'])} direct, {len(data['runtime'])} runtime)")
        return

    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
