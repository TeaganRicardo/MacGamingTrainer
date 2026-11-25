"""Bind resident Lua's identity to the exact source loaded by the backend."""

from hashlib import sha256


REVISION_PLACEHOLDER = "__MGT_RESIDENT_SOURCE_SHA256__"


def resident_source(source: str) -> str:
    """Fill the resident's revision literal without hashing its own expansion.

    Each resident template owns a revision literal. Loaders bind it before
    crossing the game boundary; an opaque caller-supplied bootstrap is unchanged.
    """
    return source.replace(REVISION_PLACEHOLDER, sha256(source.encode("utf-8")).hexdigest())
