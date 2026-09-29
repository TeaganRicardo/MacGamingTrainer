"""Capture the current error-presentation behaviour as a comparable baseline.

#204 collapses seven mapping tables into one declarative registry. The refactor
is only safe if every message resolves to the same key AND the same arguments
before and after. This snapshot is the "before" side of that proof: it probes
every registered message through the real funnel and records the result.

Re-run it with `--compare` after the refactor and diff. A single changed key
means a player's error message silently became a different sentence.

IMPORTANT: this script probes the PUBLIC surface only -- `presentation_for`,
`present_runtime_error`, and the module's own `RUNTIME_FALLBACK_KEY`. An earlier
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


from core.adapter import AdapterError as _AdapterError  # noqa: E402


#: Per-family floors on GENUINE shape contests -- messages that two different
#: shapes claim, with different outcomes.
#:
#: This was previously a single global `MIN_SHAPE_COLLISIONS = 2`, and that was
#: worse than decorative. It never caught the exact regression it was written for:
#: removing the space from a prefix value still left 96 collisions from the
#: prefix-vs-delimited family, comfortably over the floor, while the two families
#: that actually depended on the space dropped to zero. It read like it policed
#: the cross-shape set and silently did not.
#:
#: A global count cannot work here: the prefix-vs-delimited family contributes 96
#: on its own, so it would mask the disappearance of any other family. Each
#: family therefore needs its own floor, and the floors differ because the
#: families differ -- the two prefix families each have exactly one genuine
#: contest, so their floor is 1 and not 2.
MIN_GENUINE_CONTEST_FLOORS = {
    "affix-vs-prefix": 1,
    "segmented-vs-prefix": 1,
    "prefix-vs-delimited": 2,
}

#: Kept for readers of older reports. Not a guard: see the note above.
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

    # prefix vs delimited. Round 3 missed this pair entirely, and it is the one
    # that matters most: a delimited rule is delimited by an OPEN and a CLOSE, so
    # a message that merely CONTAINS the opener competes with a prefix rule whose
    # remainder is that same text. The concrete case, from the live Lua:
    #
    #   prefix     'Trait is not present in the current run: '  -> traitNotPresent
    #   delimited  ' 失败（' ... '）'                   -> commandFailed
    #
    # and 'Trait is not present in the current run:  失败（5）' is claimed
    # by BOTH -- the prefix rule with the remainder ' 失败（5）', and the
    # delimited rule with the argument '5'. Dispatching delimited first turns a
    # precise "this trait is not in your run" into a bare "command failed", and
    # both suites stayed green, because the cross-shape probes above only ever
    # compared affix/segmented against prefix and prefix against regex.
    #
    # So: for every delimited rule, embed its opener and closer inside a message
    # that also starts with a prefix rule's head. The prefix rule must win.
    for rule in rules:
        if rule.get("match") != "delimited":
            continue
        opener, closer = rule["open"], rule["close"]
        for other in rules:
            if other.get("match") != "prefix":
                continue
            head = other["prefix"]
            message = f"{head}{opener}5{closer}"
            # Only a real overlap counts: the message has to be claimed by the
            # delimited rule as well, or this probe is decoration again.
            if opener in message and closer in message and message != opener:
                probes.add(message)
                if message.startswith(head) and opener not in head:
                    collisions += 1
    return probes, collisions

def _claims(rules, message):
    """Every (shape, key) that would claim `message`, per the real matchers.

    This is a decision table, not the dispatcher. It answers "which shapes COULD
    claim this", which is what a contest is, and it deliberately does not consult
    `presentation_for` -- that returns the winner, and a contest is invisible in
    the winner.
    """
    import re as _re
    out = []
    for rule in rules:
        shape = rule.get("match")
        if shape == "literal":
            if message == rule.get("message"):
                out.append((shape, rule["key"]))
        elif shape == "regex":
            if _re.match(rule["pattern"], message):
                out.append((shape, rule["key"]))
        elif shape == "prefix":
            if message.startswith(rule["prefix"]):
                out.append((shape, rule["key"]))
        elif shape == "affix":
            o, c = rule["prefix"], rule["suffix"]
            if message.startswith(o) and message.endswith(c) \
                    and message[len(o):len(message) - len(c)].strip():
                out.append((shape, rule["key"]))
        elif shape == "segmented":
            if message.startswith(rule["prefix"]) and rule["separator"] in message:
                out.append((shape, rule["key"]))
        elif shape in ("delimited", "delimited_affix"):
            o, c = rule.get("open"), rule.get("close")
            if o in message and message.find(c, message.find(o) + len(o)) > message.find(o) + len(o):
                out.append((shape, rule["key"]))
    return out



def _resolve_with(rules, message, shape):
    """What `shape` alone would return for `message`, or None if it cannot claim it.

    A copy of the dispatcher's per-shape semantics, narrowed to one shape. It
    exists so the contest counter can ask what each rival WOULD have produced,
    which is the only way to tell a real contest from a harmless double match.
    """
    import re as _re
    for rule in rules:
        if rule.get("match") != shape:
            continue
        if shape == "regex":
            m = _re.match(rule["pattern"], message)
            if m:
                return rule["key"], list(m.groups())
        elif shape == "prefix":
            if message.startswith(rule["prefix"]):
                return rule["key"], [message[len(rule["prefix"]):]]
        elif shape == "affix":
            o, c = rule["prefix"], rule["suffix"]
            if message.startswith(o) and message.endswith(c) \
                    and message[len(o):len(message) - len(c)].strip():
                return rule["key"], [message[len(o):len(message) - len(c)].strip()]
        elif shape == "segmented":
            lead, sep, tail = rule["prefix"], rule["separator"], rule["terminator"]
            if not message.startswith(lead):
                continue
            rest = message[len(lead):]
            s = rest.find(sep)
            if s < 0:
                continue
            value, rem = rest[:s].strip(), rest[s + len(sep):]
            e = rem.find(tail)
            if e > 0 and value and rem[:e].strip():
                return rule["key"], [value, rem[:e].strip()]
        elif shape == "delimited":
            o, c = rule.get("open"), rule.get("close")
            b = message.find(o)
            if b < 0:
                continue
            e = message.find(c, b + len(o))
            if e > b + len(o):
                return rule["key"], [message[b + len(o):e].strip()]
        elif shape == "literal":
            if message == rule.get("message"):
                return rule["key"], []
    return None


def _same_outcome(rules, message, shape_a, shape_b) -> bool:
    """True when both shapes would produce the same key AND the same arguments."""
    a = _resolve_with(rules, message, shape_a)
    b = _resolve_with(rules, message, shape_b)
    if a is None or b is None:
        return True          # one shape cannot claim it: not a contest
    return a == b


def _genuine_contests_by_family(rules, probes) -> dict:
    """Family -> count of messages that two shapes would answer DIFFERENTLY.

    A contest matters when the rivals disagree about the outcome -- but the
    outcome is the key AND the arguments, and here those two cases disagree on
    the arguments while agreeing on the key:

        '请先启动 Hades II 并进入存档。'
            affix  -> gameNotRunning ['Hades II']
            prefix -> gameNotRunning [' Hades II 并进入存档。']

    So a key-only comparison reports 0 genuine contests for both prefix families
    and the floor fires on a healthy tree. What distinguishes them is the
    arguments: identical keys with different arguments is exactly the failure
    this registry refactor exists to prevent -- a translated message silently
    reverting to its untranslated static tail.
    """
    from itertools import combinations
    families: dict = {name: 0 for name in MIN_GENUINE_CONTEST_FLOORS}
    for message in probes:
        claimed = _claims(rules, message)
        shapes = {s for s, _ in claimed}
        for a, b in combinations(sorted(shapes), 2):
            if _same_outcome(rules, message, a, b):
                continue          # both shapes would answer identically
            name = f"{a}-vs-{b}"
            reverse = f"{b}-vs-{a}"
            for candidate in (name, reverse):
                if candidate in families:
                    families[candidate] += 1
                    break
    return families


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


def _runtime_commands() -> list[str]:
    commands = set()
    for rule in ep.REGISTRY:
        runtime = rule.get("runtime")
        if not isinstance(runtime, dict):
            continue
        scoped = runtime.get("commands")
        if isinstance(scoped, (list, tuple)):
            commands.update(scoped)
    return sorted(commands)


def _runtime_messages() -> list[tuple[str, str]]:
    """Concrete (command, message) probes derived from runtime registry entries."""
    all_commands = _runtime_commands()
    pairs: list[tuple[str, str]] = []
    for rule in ep.REGISTRY:
        runtime = rule.get("runtime")
        if not isinstance(runtime, dict):
            continue
        scoped = runtime.get("commands")
        commands = all_commands if scoped == "*" else list(scoped or ())
        shape = rule.get("match")
        if shape == "literal":
            message = rule["message"]
        elif shape == "prefix":
            message = rule["prefix"] + "TraitOfHermes"
        elif shape == "regex":
            message = runtime.get("sample")
            if not isinstance(message, str) or not message:
                raise AssertionError(f"runtime regex has no concrete sample: {rule}")
        else:
            raise AssertionError(f"unsupported runtime registry shape: {shape}")
        for command in commands:
            pairs.append((command, message))
    return sorted(set(pairs))

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
        "fallback_key": ep.RUNTIME_FALLBACK_KEY,
        "runtime_commands": _runtime_commands(),
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
