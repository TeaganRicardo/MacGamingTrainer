"""Lua 5.2 local-slot measurement and top-level factory discovery helpers."""

from dataclasses import dataclass
import re
from typing import Callable


_CANDIDATE_IIFE = re.compile(r"=\s*\(\s*function\b")
_TOP_LEVEL_FACTORY = re.compile(
    r"^  (?P<target>(?:local\s+)?[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r"\s*=\s*\(\s*function\s*\([^)]*\)\s*$"
)


@dataclass(frozen=True)
class LocalFactory:
    """A top-level immediately-invoked factory and its function-body insertion point."""

    name: str
    line_number: int
    body_offset: int


def discover_top_level_factories(source: str) -> list[LocalFactory]:
    """Discover every two-space-indented top-level IIFE, failing closed on unknown syntax."""
    factories = []
    seen_names = set()
    offset = 0

    for line_number, line in enumerate(source.splitlines(keepends=True), start=1):
        statement = line.rstrip("\r\n")
        is_top_level_statement = statement.startswith("  ") and not statement.startswith("   ")
        if is_top_level_statement and _CANDIDATE_IIFE.search(statement):
            match = _TOP_LEVEL_FACTORY.fullmatch(statement)
            if match is None:
                raise ValueError(
                    "unrecognized top-level IIFE factory declaration "
                    f"at line {line_number}: {statement.strip()}"
                )
            if not line.endswith(("\n", "\r")):
                raise ValueError(
                    f"top-level IIFE factory at line {line_number} has no body line"
                )

            name = match.group("target")
            if name.startswith("local "):
                name = name[len("local "):].strip()
            if name in seen_names:
                raise ValueError(
                    "duplicate top-level IIFE factory name "
                    f"at line {line_number}: {name}"
                )
            seen_names.add(name)
            factories.append(LocalFactory(name, line_number, offset + len(line)))
        offset += len(line)

    if not factories:
        raise ValueError("no top-level IIFE factories discovered in resident source")
    return factories


def inject_factory_locals(source: str, factory: LocalFactory, declarations: str) -> str:
    """Insert synthetic locals at factory entry so they overlap every factory local."""
    if not 0 < factory.body_offset <= len(source):
        raise ValueError(f"invalid body offset for local-budget probe: {factory.name}")
    if source[factory.body_offset - 1] not in "\r\n":
        raise ValueError(f"factory body offset is not at a line boundary: {factory.name}")
    if declarations and not declarations.endswith("\n"):
        raise ValueError("synthetic local declarations must end with a newline")
    return source[:factory.body_offset] + declarations + source[factory.body_offset:]


def measure_local_reserve(
    source_for_probe: Callable[[str], str],
    compiles: Callable[[str], bool],
    scope_name: str,
) -> int:
    """Use the real compiler callback to find the maximum additional live locals."""
    identifier = re.sub(r"\W", "_", scope_name)

    def compiles_with(extra_locals: int) -> bool:
        names = ", ".join(
            f"__mgt_{identifier}_reserve_{index}" for index in range(1, extra_locals + 1)
        )
        declarations = f"local {names}\n" if extra_locals else ""
        return compiles(source_for_probe(declarations))

    available = 0
    candidate = 1
    while compiles_with(candidate):
        available = candidate
        candidate *= 2
        if candidate > 256:
            raise RuntimeError(
                f"Lua 5.2 {scope_name} reserve probe did not reach the local limit"
            )

    lower, upper = available, candidate
    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if compiles_with(middle):
            lower = middle
        else:
            upper = middle
    return lower


def require_minimum_reserve(scope_name: str, available: int, minimum: int) -> None:
    """Fail the local-cap gate when a measured scope falls below its hard budget."""
    if available < minimum:
        raise ValueError(
            f"{scope_name} below required local reserve: "
            f"available={available} required={minimum}"
        )
