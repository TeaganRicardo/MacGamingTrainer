"""Authoritative macOS native-fixture watchdog policy.

Three contracts are deliberately kept apart:

* **Semantic readiness** belongs to each fixture: a condition, a narrow deadline
  and a failure that names the unmet predicate.
* **Outer watchdog** belongs here: last-resort hang containment for one named
  journey on one verified execution profile. It is never a latency target.
* **Performance observation** is reported, never asserted.

A budget is resolved once per launch from the verified profile, printed before
the launch, and enforced against the fixture's observed worker tree so an owned
worker cannot outlive the watchdog. Expiry raises `FixtureWatchdogExpired`,
which is a different outcome from a failed semantic assertion.
"""
from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# The hosted macOS runner that .github/workflows/build2-macos.yml uses.
HOSTED_PROFILE = "macos-26"
HOSTED_ARCH = "ARM64"
LOCAL_PROFILE = "local"

# GitHub Actions exports this label from the owning workflow. A hosted run that
# cannot state its profile has no verified budget and must fail closed.
PROFILE_VARIABLE = "MGT_MACOS_RUNNER_LABEL"
SOURCE_VARIABLE = "HEAD_SHA"
TIMINGS_VARIABLE = "MGT_FIXTURE_TIMINGS"

MAXIMUM_BUDGET_SECONDS = 300.0
# Local development has no verified profile. A bounded floor replaces the
# retired global multiplier: a loaded laptop is not a CI failure, and a genuine
# hang still reports within the ceiling instead of running forever.
LOCAL_MINIMUM_SECONDS = 90.0
# New native journeys may launch with `provisional=True` at this documented floor
# before hosted timings are measured, then record a verified per-journey budget.
PROVISIONAL_BUDGET_SECONDS = LOCAL_MINIMUM_SECONDS
GROUP_TERMINATION_GRACE_SECONDS = 2.0
DIAGNOSTIC_TAIL_CHARACTERS = 4096
DIAGNOSTIC_LINE_COUNT = 12


class FixturePolicyError(RuntimeError):
    """The requested journey or execution profile has no verified watchdog."""


@dataclass(frozen=True)
class FixtureBudget:
    """One resolved outer watchdog, valid for exactly one process launch."""

    journey: str
    profile: str
    seconds: float
    provisional: bool = False

    def describe(self) -> str:
        base = f"journey={self.journey} profile={self.profile} budget={self.seconds:g}s"
        return f"{base} provisional=true" if self.provisional else base


class FixtureWatchdogExpired(RuntimeError):
    """The outer watchdog expired; this is not a semantic assertion failure."""

    def __init__(self, budget: FixtureBudget, elapsed: float, phase: str,
                 stdout: str | None, stderr: str | None) -> None:
        super().__init__(
            f"{budget.describe()} elapsed={elapsed:.1f}s "
            f"last_phase={phase or '<none>'}"
        )
        self.budget = budget
        self.elapsed = elapsed
        self.phase = phase
        self.stdout = stdout
        self.stderr = stderr


def validate_journey_budgets(budgets: Mapping[str, float]) -> None:
    """Ensure a domain journey-budget table is non-empty and within policy bounds."""
    if not isinstance(budgets, Mapping) or not budgets:
        raise FixturePolicyError("domain journey budgets must be a non-empty mapping")
    for journey, seconds in budgets.items():
        if not isinstance(journey, str) or not journey or journey != journey.strip():
            raise FixturePolicyError(f"invalid macOS fixture journey name: {journey!r}")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise FixturePolicyError(f"{journey}: budget must be numeric")
        if not 0 < seconds <= MAXIMUM_BUDGET_SECONDS:
            raise FixturePolicyError(
                f"{journey}: budget {seconds!r} must be within (0, {MAXIMUM_BUDGET_SECONDS:g}]"
            )


def resolve_profile(environ: Mapping[str, str] | None = None) -> str:
    """Return the verified profile, or fail closed for an unknown hosted runner."""
    env = os.environ if environ is None else environ
    hosted = env.get("GITHUB_ACTIONS", "").strip().lower() == "true"
    if not hosted:
        return LOCAL_PROFILE
    label = env.get(PROFILE_VARIABLE, "").strip()
    if label != HOSTED_PROFILE:
        raise FixturePolicyError(
            f"unknown hosted macOS runner profile {label or '<unset>'!r}; declare "
            f"{PROFILE_VARIABLE}={HOSTED_PROFILE} and add verified budgets before "
            "running native fixtures"
        )
    architecture = env.get("RUNNER_ARCH", "").strip()
    if architecture and architecture != HOSTED_ARCH:
        raise FixturePolicyError(
            f"hosted profile {HOSTED_PROFILE} requires {HOSTED_ARCH}, got {architecture!r}; "
            "the product declares arm64 only"
        )
    return HOSTED_PROFILE


def resolve_budget(journey: str, environ: Mapping[str, str] | None = None, *,
                   budgets: Mapping[str, float] | None = None,
                   provisional: bool = False) -> FixtureBudget:
    """Resolve one journey's watchdog for the active profile."""
    if not isinstance(journey, str) or not journey or journey != journey.strip():
        raise FixturePolicyError(f"invalid macOS fixture journey name: {journey!r}")
    is_provisional = False
    if budgets is None:
        if not provisional:
            raise FixturePolicyError("domain journey budgets must be a non-empty mapping")
        hosted = PROVISIONAL_BUDGET_SECONDS
        is_provisional = True
    else:
        if not isinstance(budgets, Mapping):
            raise FixturePolicyError("domain journey budgets must be a non-empty mapping")
        if budgets:
            validate_journey_budgets(budgets)
        elif not provisional:
            raise FixturePolicyError("domain journey budgets must be a non-empty mapping")
        if journey in budgets:
            hosted = budgets[journey]
        elif provisional:
            hosted = PROVISIONAL_BUDGET_SECONDS
            is_provisional = True
        else:
            raise FixturePolicyError(f"undeclared macOS fixture journey: {journey!r}")
    profile = resolve_profile(environ)
    if profile == HOSTED_PROFILE:
        seconds = hosted
    else:
        seconds = min(MAXIMUM_BUDGET_SECONDS, max(hosted, LOCAL_MINIMUM_SECONDS))
    return FixtureBudget(journey, profile, float(seconds), provisional=is_provisional)


def _source_identity(environ: Mapping[str, str]) -> str:
    sha = environ.get(SOURCE_VARIABLE) or environ.get("GITHUB_SHA") or ""
    sha = sha.strip()
    return sha[:12] if sha else "local"


def _record_timing(budget: FixtureBudget, elapsed: float, outcome: str,
                   environ: Mapping[str, str]) -> None:
    """Append one bounded observation. Timing never changes a fixture's verdict."""
    path = environ.get(TIMINGS_VARIABLE, "").strip()
    if not path:
        return
    record = {
        "journey": budget.journey,
        "profile": budget.profile,
        "budget_seconds": budget.seconds,
        "elapsed_seconds": round(elapsed, 3),
        "outcome": outcome,
        "source": _source_identity(environ),
        "architecture": environ.get("RUNNER_ARCH", "").strip() or platform.machine(),
        "image": environ.get("ImageOS", "").strip(),
        "image_version": environ.get("ImageVersion", "").strip(),
    }
    try:
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError as error:
        # Observation must not turn a passing fixture into a failing one.
        print(f"macos_fixture_timing_unwritten {budget.journey}: {error}",
              file=sys.stderr, flush=True)


def _tail(text: str | None, limit: int = DIAGNOSTIC_TAIL_CHARACTERS) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return "...[truncated]\n" + text[-limit:]


def _redact(text: str) -> str:
    home = os.environ.get("HOME", "")
    if len(home) > 1:
        return text.replace(home, "$HOME")
    return text


def _read_phase(phase_file: Path | None) -> str:
    if phase_file is None:
        return ""
    try:
        return phase_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _report_tail(label: str, text: str | None) -> None:
    body = _redact(_tail(text))
    if not body.strip():
        return
    print(f"{label}:\n{body}", file=sys.stderr, flush=True)


def _report_expiry(budget: FixtureBudget, elapsed: float, phase: str,
                   stdout: str | None, stderr: str | None,
                   diagnostics: Sequence[Path], environ: Mapping[str, str]) -> None:
    print(
        "macos_fixture_watchdog_expired "
        f"{budget.describe()} elapsed={elapsed:.1f}s source={_source_identity(environ)}",
        file=sys.stderr, flush=True,
    )
    print(f"macos_fixture_watchdog_last_phase={phase or '<none>'}", file=sys.stderr, flush=True)
    _report_tail("macos_fixture_watchdog_stdout_tail", stdout)
    _report_tail("macos_fixture_watchdog_stderr_tail", stderr)
    for path in diagnostics:
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if not lines:
            continue
        body = "\n".join(lines[-DIAGNOSTIC_LINE_COUNT:])
        print(f"macos_fixture_watchdog_diagnostic {path.name}:\n{_redact(body)}",
              file=sys.stderr, flush=True)


def _descendants(pid: int) -> list[int]:
    """Snapshot the fixture's worker tree before it is signalled.

    Once the fixture exits its children are reparented and the parent link is
    gone, so the snapshot has to happen first. Only descendants observed here
    are ever signalled, so an unrelated process is never a target.
    """
    try:
        listing = subprocess.run(
            ["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    children: dict[int, list[int]] = {}
    for line in listing.stdout.splitlines():
        fields = line.split()
        if len(fields) != 2:
            continue
        try:
            child, parent = int(fields[0]), int(fields[1])
        except ValueError:
            continue
        children.setdefault(parent, []).append(child)
    found: list[int] = []
    pending = [pid]
    while pending:
        for child in children.get(pending.pop(), ()):
            if child not in found:
                found.append(child)
                pending.append(child)
    return found


def _signal(pid: int, number: int) -> None:
    try:
        os.kill(pid, number)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate(process: subprocess.Popen, fallback: Sequence[int] = ()) -> None:
    """Stop the fixture and the workers it owns, and nothing else.

    The fixture keeps the harness's process group and session. A new group or a
    detached session changes AppKit activation and key-window state, which made
    a native journey fail its own readiness wait, so ownership is tracked by the
    observed process tree instead. `fallback` holds a snapshot taken at launch,
    because a fixture that exits before the deadline reparents its workers and
    they can no longer be found from its pid.
    """
    owned = list(dict.fromkeys([*_descendants(process.pid), *fallback]))
    if process.poll() is None:
        for pid in owned:
            _signal(pid, signal.SIGTERM)
        try:
            process.terminate()
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=GROUP_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        if process.poll() is None:
            try:
                process.kill()
            except (ProcessLookupError, PermissionError):
                pass
    for pid in owned:
        _signal(pid, signal.SIGKILL)


def _drain(process: subprocess.Popen,
           timeout: float) -> tuple[str | None, str | None]:
    """Collect the fixture's output without outliving its own watchdog.

    A worker that outlived its parent still holds the write end of the pipe, so
    reading to EOF would make the watchdog the hang it exists to report. When
    the grace window expires, stop reading and report without output; the phase
    file and the owned journals still describe the stall.
    """
    try:
        return process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except (ProcessLookupError, PermissionError):
                pass
        return None, None


def run_watchdog(argv: Sequence[str], *, budget: FixtureBudget,
                 environ: Mapping[str, str] | None = None,
                 phase_file: Path | None = None,
                 diagnostics: Iterable[Path] = (), check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Run one fixture under an explicit budget and classify the outcome.

    The fixture keeps the harness's process group and session. Owning a new
    process group, or a detached session, changes AppKit activation and
    key-window state, so a native journey that passed would fail its own
    readiness wait; owned workers are tracked through the observed process tree
    instead.
    """
    if not 0 < budget.seconds <= MAXIMUM_BUDGET_SECONDS:
        raise FixturePolicyError(f"invalid watchdog budget: {budget.describe()}")
    env = os.environ if environ is None else environ
    capture = kwargs.pop("capture_output", False)
    if capture:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    started = time.monotonic()
    process = subprocess.Popen(list(argv), **kwargs)
    # One cheap snapshot at launch: a fixture that exits before its deadline
    # reparents its workers, and their pids can no longer be recovered from it.
    launched = _descendants(process.pid)
    try:
        stdout, stderr = process.communicate(timeout=budget.seconds)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        _terminate(process, launched)
        stdout, stderr = _drain(process, GROUP_TERMINATION_GRACE_SECONDS)
        phase = _read_phase(phase_file)
        _report_expiry(budget, elapsed, phase, stdout, stderr, tuple(diagnostics), env)
        _record_timing(budget, elapsed, "watchdog_expired", env)
        raise FixtureWatchdogExpired(budget, elapsed, phase, stdout, stderr) from None
    elapsed = time.monotonic() - started
    print(f"macos_fixture_watchdog_done {budget.describe()} elapsed={elapsed:.1f}s",
          flush=True)
    _record_timing(budget, elapsed, "completed", env)
    result = subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)
    if check:
        result.check_returncode()
    return result


def launch_fixture(argv: Sequence[str], *, journey: str,
                   budgets: Mapping[str, float] | None = None,
                   provisional: bool = False,
                   environ: Mapping[str, str] | None = None,
                   phase_file: Path | None = None,
                   diagnostics: Iterable[Path] = (), **kwargs) -> subprocess.CompletedProcess:
    """Resolve, announce and enforce one journey's watchdog."""
    budget = resolve_budget(journey, environ, budgets=budgets, provisional=provisional)
    print(f"macos_fixture_watchdog_start {budget.describe()}", flush=True)
    return run_watchdog(argv, budget=budget, environ=environ, phase_file=phase_file,
                        diagnostics=diagnostics, **kwargs)
