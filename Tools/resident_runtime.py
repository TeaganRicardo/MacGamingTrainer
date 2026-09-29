"""Shared resident-runtime declaration validation for build and CI tooling."""
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Pattern

DECLARATION_KEY = "residentRuntime"
DEFAULT_PREVIOUS_RE = r"previousModule\.revision\s*~=\s*(\d+)"
DEFAULT_MODULE_RE = r"version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)"


class ResidentRuntimeDeclarationError(ValueError):
    pass


@dataclass(frozen=True)
class ResidentRuntimeSpec:
    source: str
    runtime_path: Path
    previous_revision_pattern: Pattern[str]
    module_revision_pattern: Pattern[str]


def _error(manifest_path, message):
    return ResidentRuntimeDeclarationError(
        f"{manifest_path}: {DECLARATION_KEY}{message}"
    )


def parse_resident_runtime_declaration(
    declaration,
    *,
    manifest_path,
    source_exists: Callable[[Path], bool],
):
    """Validate one residentRuntime declaration and return its parsed spec.

    The declaration is build-tool metadata, not a Core runtime-manifest field.
    source_exists is supplied by the caller because the ordinary validator
    reads the checkout while the revision gate reads an arbitrary git ref.
    """
    manifest_path = Path(manifest_path)
    if not isinstance(declaration, dict):
        raise _error(manifest_path, " must be an object")

    source = declaration.get("source")
    if not isinstance(source, str) or not source:
        raise _error(manifest_path, ".source must be a non-empty string")
    if source != source.strip():
        raise _error(manifest_path, ".source must not contain leading or trailing whitespace")
    if "\x00" in source:
        raise _error(manifest_path, ".source must name a file inside the module directory")
    posix_source = PurePosixPath(source)
    if posix_source.is_absolute() or ".." in posix_source.parts:
        raise _error(manifest_path, ".source must name a file inside the module directory")

    runtime_path = manifest_path.parent / Path(*posix_source.parts)
    if not source_exists(runtime_path):
        raise _error(
            manifest_path,
            f".source {source!r} does not name a file inside the module directory",
        )

    patterns = {}
    for field, default in (
        ("previousRevisionPattern", DEFAULT_PREVIOUS_RE),
        ("moduleRevisionPattern", DEFAULT_MODULE_RE),
    ):
        value = declaration.get(field, default)
        if not isinstance(value, str) or not value.strip():
            raise _error(manifest_path, f".{field} must be a non-empty string")
        try:
            patterns[field] = re.compile(value)
        except re.error as exc:
            raise _error(manifest_path, f".{field} does not compile: {exc}") from exc

    return ResidentRuntimeSpec(
        source=source,
        runtime_path=runtime_path,
        previous_revision_pattern=patterns["previousRevisionPattern"],
        module_revision_pattern=patterns["moduleRevisionPattern"],
    )
