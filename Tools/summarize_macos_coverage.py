#!/usr/bin/env python3
"""State what a macOS lane selected, executed, passed, failed and deferred.

A green macOS check has to describe its own coverage. This reports the selected
inventory for the lane, the executed results, each deferred journey with the
owner that verifies it instead, and the observed journey timings.

Timing is reported, never asserted: a slow journey is not a failure here, and a
missing timing record is not one either. The only hard failures are coverage
contract violations, where a lane could otherwise imply coverage it did not run.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "Tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ci_docs_only import load_macos_only_tests
from select_macos_pr_tests import PR_DEFERRED

MAXIMUM_TIMING_LINES = 40


class CoverageError(RuntimeError):
    """The lane would report coverage it cannot prove."""


def _identity() -> dict[str, str]:
    sha = (os.environ.get("HEAD_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    return {
        "source": sha[:12] if sha else "local",
        "profile": (os.environ.get("MGT_MACOS_RUNNER_LABEL") or "local").strip(),
        "image": "/".join(
            part for part in (
                os.environ.get("ImageOS", "").strip(),
                os.environ.get("ImageVersion", "").strip(),
            ) if part
        ) or "local",
        "architecture": os.environ.get("RUNNER_ARCH", "").strip() or "local",
    }


def _lines(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_results(path: Path | None) -> list[dict[str, str]]:
    results = []
    for line in _lines(path):
        parts = line.split("\t")
        if len(parts) < 2 or parts[1] not in {"pass", "fail"}:
            raise CoverageError(f"unreadable result row: {line!r}")
        results.append({"test": parts[0], "status": parts[1]})
    return results


def read_timings(path: Path | None) -> list[dict]:
    records = []
    for line in _lines(path):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise CoverageError(f"unreadable timing record: {line!r}") from error
        if not isinstance(record, dict) or "journey" not in record:
            raise CoverageError(f"timing record is missing its journey: {line!r}")
        records.append(record)
    return records


def coverage(lane: str, selected: list[str], results: list[dict[str, str]],
             inventory: set[str]) -> dict[str, object]:
    if not inventory:
        raise CoverageError("the macOS inventory is empty; convergence would verify nothing")
    if not selected and lane == "convergence":
        # Convergence is the only lane that must cover the whole inventory.
        raise CoverageError("convergence selected no macOS test")
    undeclared = sorted(set(selected) - inventory)
    if undeclared:
        raise CoverageError(f"{lane} lane selected tests outside the inventory: {undeclared}")

    deferred = {} if lane == "convergence" else dict(PR_DEFERRED)
    unverifiable = sorted(set(deferred) - inventory)
    if unverifiable:
        raise CoverageError(
            f"deferred tests are missing from the convergence inventory: {unverifiable}"
        )

    executed = [row["test"] for row in results]
    unexpected = sorted(set(executed) - set(selected))
    if unexpected:
        raise CoverageError(f"{lane} lane executed unselected tests: {unexpected}")
    not_run = sorted(set(selected) - set(executed))
    if not_run:
        raise CoverageError(f"{lane} lane selected but never executed: {not_run}")

    passed = [row["test"] for row in results if row["status"] == "pass"]
    failed = [row["test"] for row in results if row["status"] == "fail"]
    return {
        "lane": lane,
        "selected": len(selected),
        "executed": len(executed),
        "passed": len(passed),
        "failed": len(failed),
        "deferred": len(deferred),
        "deferred_tests": deferred,
        "not_selected": len(inventory - set(selected) - set(deferred)),
        "inventory": len(inventory),
        "deferred_covered": True,
        "passed_tests": passed,
        "failed_tests": failed,
    }


def timing_summary(records: list[dict], baseline: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[float]] = {}
    budgets: dict[tuple[str, str], float] = {}
    for record in list(baseline) + list(records):
        try:
            journey = str(record["journey"])
            profile = str(record.get("profile", "unknown"))
            elapsed = float(record["elapsed_seconds"])
        except (KeyError, TypeError, ValueError) as error:
            raise CoverageError(f"timing record is incomplete: {record!r}") from error
        grouped.setdefault((profile, journey), []).append(elapsed)
        try:
            budgets[(profile, journey)] = float(record["budget_seconds"])
        except (KeyError, TypeError, ValueError):
            pass
    summary = []
    for (profile, journey), samples in sorted(grouped.items()):
        summary.append({
            "profile": profile,
            "journey": journey,
            "samples": len(samples),
            "minimum": round(min(samples), 3),
            "median": round(statistics.median(samples), 3),
            "maximum": round(max(samples), 3),
            "budget_seconds": budgets.get((profile, journey)),
        })
    return summary


def render(report: dict[str, object], timings: list[dict], identity: dict[str, str]) -> str:
    lines = [
        f"macOS coverage lane={report['lane']} profile={identity['profile']} "
        f"source={identity['source']} image={identity['image']} arch={identity['architecture']}",
        f"  selected={report['selected']} executed={report['executed']} "
        f"passed={report['passed']} failed={report['failed']} deferred={report['deferred']} "
        f"not_selected={report['not_selected']}",
    ]
    for name, deferral in sorted(report["deferred_tests"].items()):
        lines.append(f"  deferred {name} reason=\"{deferral.reason}\" owner=\"{deferral.verification_owner}\"")
    lines.append(
        f"  inventory={report['inventory']} deferred_covered="
        f"{str(report['deferred_covered']).lower()}"
    )
    if timings:
        lines.append(f"  timings={len(timings)} journey/profile samples (observation only, no threshold)")
        for row in timings[:MAXIMUM_TIMING_LINES]:
            budget = f" budget={row['budget_seconds']:g}s" if row["budget_seconds"] else ""
            lines.append(
                f"  timing profile={row['profile']} journey={row['journey']} "
                f"samples={row['samples']} min={row['minimum']:g}s "
                f"median={row['median']:g}s max={row['maximum']:g}s{budget}"
            )
    return "\n".join(lines)


def write_jsonl(path: Path, report: dict[str, object], timings: list[dict],
                identity: dict[str, str]) -> None:
    rows = [{
        "kind": "coverage",
        "lane": report["lane"],
        "selected": report["selected"],
        "executed": report["executed"],
        "passed": report["passed"],
        "failed": report["failed"],
        "deferred": report["deferred"],
        "not_selected": report["not_selected"],
        "inventory": report["inventory"],
        "deferred_covered": report["deferred_covered"],
        **identity,
    }]
    for name in report["passed_tests"]:
        rows.append({"kind": "result", "test": name, "status": "pass"})
    for name in report["failed_tests"]:
        rows.append({"kind": "result", "test": name, "status": "fail"})
    for row in timings:
        rows.append({"kind": "timing", **row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=("pr", "convergence"), required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--timings", type=Path)
    parser.add_argument("--baseline", type=Path, help="earlier timing JSONL for a nonblocking trend")
    parser.add_argument("--output", type=Path, help="write the combined machine-readable JSONL here")
    parser.add_argument("--summary", type=Path, help="append the rendered block here")
    args = parser.parse_args(argv)

    identity = _identity()
    try:
        report = coverage(
            args.lane,
            _lines(args.selected),
            read_results(args.results),
            load_macos_only_tests(ROOT),
        )
        timings = timing_summary(read_timings(args.timings), read_timings(args.baseline))
    except CoverageError as error:
        print(f"macOS coverage contract violated: {error}", file=sys.stderr)
        return 2

    block = render(report, timings, identity)
    print(block, flush=True)
    summary = args.summary or (Path(os.environ["GITHUB_STEP_SUMMARY"])
                               if os.environ.get("GITHUB_STEP_SUMMARY") else None)
    if summary is not None:
        try:
            with summary.open("a", encoding="utf-8") as stream:
                stream.write("### macOS coverage\n\n```\n" + block + "\n```\n")
        except OSError as error:
            print(f"macOS coverage summary not written: {error}", file=sys.stderr)
    if args.output is not None:
        try:
            write_jsonl(args.output, report, timings, identity)
        except OSError as error:
            print(f"macOS coverage artifact not written: {error}", file=sys.stderr)
    # A produced report is a success. Failed tests are already the runner's own
    # exit status; only a coverage contract violation fails closed above.
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
