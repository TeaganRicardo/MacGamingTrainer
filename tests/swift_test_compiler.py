"""Shared test-mode Swift compilation helper with keyed support-module cache.

Many macOS frontend and runtime harnesses recompile the exact same 100+ Swift
files under ``Sources/Core`` and ``Sources/Hades*`` plus ``InMemoryDefaults``
and ``ActiveGame.generated.swift``. Compiling that immutable support set once per
exact toolchain/SDK/flag/source digest into a testable static module
(``libMGTTestSupport.a`` + ``MGTTestSupport.swiftmodule``) turns ~40s repeat
compilations into ~1s incremental harness links while keeping clean isolation.

Equivalence and staleness guarantees:
- Cache keys hash compiler binary path + ``swiftc --version``, resolved macOS
  SDK path + version + ``DEVELOPER_DIR``, host architecture, normalized support
  compile flags, and every support file's identity + exact SHA-256 bytes.
- Repository files include their exact resolved path in the key so different
  worktrees/checkouts never share compiled ``#filePath`` literals (which
  ``Hades2Presentation`` uses to locate repository assets).
- Generated files (``ActiveGame.generated.swift``) are keyed by logical role
  and content digest so equal generated outputs share one cache across tests.
- Ephemeral temporary source files other than generated bindings bypass cross-
  process cache reuse so single-use instrumented trees never collide or linger.
- Writes stage into a PID-scoped temporary directory under an exclusive
  ``fcntl.flock`` lock, verify SHA-256 digests of both ``.swiftmodule`` and
  ``.a`` in ``manifest.json``, and recover automatically by rebuilding if any
  cached artifact is missing or corrupted.
- Setting ``MGT_SWIFT_TEST_CACHE=0`` bypasses the cache completely and runs a
  single direct ``swiftc`` invocation for clean A/B equivalence checks.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

CACHE_FORMAT_VERSION = 1
MODULE_NAME = "MGTTestSupport"
MAX_CACHE_ENTRIES = 16
CACHE_ENV_VAR = "MGT_SWIFT_TEST_CACHE"
CACHE_DIR_ENV_VAR = "MGT_SWIFT_TEST_CACHE_DIR"
_GENERATED_FILENAMES = frozenset({"ActiveGame.generated.swift"})
_CLT_SDK_PREFIX = "/Library/Developer/CommandLineTools/"


class SwiftCompilerError(RuntimeError):
    """Raised when the Swift toolchain is unavailable or compilation fails."""


def default_cache_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the persistent directory for cached test support modules."""
    env = os.environ if environ is None else environ
    configured = env.get(CACHE_DIR_ENV_VAR, "").strip()
    if configured:
        return Path(configured)
    home = env.get("HOME", "").strip()
    if home:
        return Path(home) / "Library/Caches/MacGamingTrainer/swift-test-cache"
    return Path(tempfile.gettempdir()) / "mgt-swift-test-cache"


def _is_temp_path(path: Path) -> bool:
    """Return True if *path* lies under the OS temp hierarchy."""
    resolved = path.resolve()
    temp_roots = {Path(tempfile.gettempdir()).resolve(), Path("/tmp").resolve()}
    var_folders = Path("/var/folders")
    if var_folders.exists():
        temp_roots.add(var_folders.resolve())
    return any(root == resolved or root in resolved.parents for root in temp_roots)


@lru_cache(maxsize=16)
def _probe_toolchain_cached(
    swiftc: str,
    cleaned_sdk: str,
    developer_dir: str,
    path_env: str,
) -> dict[str, str]:
    env: dict[str, str] = {}
    if path_env:
        env["PATH"] = path_env
    if developer_dir:
        env["DEVELOPER_DIR"] = developer_dir
    # Apple's /usr/bin/python3 shim injects CommandLineTools SDKROOT into child
    # processes; ignore that shim path so xcrun discovers the selected Xcode SDK
    # (which includes SwiftUIMacros/Xcode plugins) instead of failing on CLT.
    if cleaned_sdk and not cleaned_sdk.startswith(_CLT_SDK_PREFIX):
        env["SDKROOT"] = cleaned_sdk
        resolved_sdk = cleaned_sdk
    else:
        resolved_sdk = ""
    resolved_swiftc = str(Path(swiftc).resolve())
    version = subprocess.check_output(
        [swiftc, "--version"], text=True, stderr=subprocess.STDOUT, env=env
    ).strip()

    sdk_version = ""
    xcrun_swiftc = ""
    if os.uname().sysname == "Darwin":
        try:
            xcrun_swiftc = subprocess.check_output(
                ["xcrun", "--find", "swiftc"],
                text=True, stderr=subprocess.DEVNULL, env=env,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            xcrun_swiftc = ""
        if not resolved_sdk:
            try:
                resolved_sdk = subprocess.check_output(
                    ["xcrun", "--sdk", "macosx", "--show-sdk-path"],
                    text=True, stderr=subprocess.DEVNULL, env=env,
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                resolved_sdk = cleaned_sdk
        if not resolved_sdk and cleaned_sdk:
            resolved_sdk = cleaned_sdk
        try:
            args = ["xcrun"]
            if resolved_sdk:
                args += ["--sdk", resolved_sdk]
            else:
                args += ["--sdk", "macosx"]
            args.append("--show-sdk-version")
            sdk_version = subprocess.check_output(
                args, text=True, stderr=subprocess.DEVNULL, env=env
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            sdk_version = ""

    return {
        "swiftc": swiftc,
        "resolved_swiftc": resolved_swiftc,
        "xcrun_swiftc": xcrun_swiftc,
        "swiftc_version": version,
        "sdk_path": resolved_sdk,
        "sdk_version": sdk_version,
        "developer_dir": developer_dir,
        "arch": platform.machine(),
    }


def probe_toolchain(
    swiftc: str,
    sdk_root: str = "",
    developer_dir: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Capture compiler and macOS SDK identity strings for cache keying."""
    base_env = os.environ if environ is None else environ
    cleaned_sdk = (sdk_root or base_env.get("SDKROOT", "")).strip()
    dev_dir = (developer_dir or base_env.get("DEVELOPER_DIR", "")).strip()
    path_env = base_env.get("PATH", os.environ.get("PATH", ""))
    return _probe_toolchain_cached(swiftc, cleaned_sdk, dev_dir, path_env)


probe_toolchain.cache_clear = _probe_toolchain_cached.cache_clear


def resolve_swiftc(swiftc: str | None = None) -> str:
    """Return a working swiftc executable path or abort cleanly."""
    candidate = swiftc or shutil.which("swiftc")
    if not candidate:
        raise SystemExit("swiftc required")
    return candidate


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _support_file_records(
    support_sources: Sequence[Path],
) -> tuple[list[dict[str, str]], bool]:
    """Classify support files into stable key records and cache eligibility."""
    records: list[dict[str, str]] = []
    cacheable = True
    for raw_path in support_sources:
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"missing Swift support source: {path}")
        digest = _file_sha256(path)
        resolved = path.resolve()
        if _is_temp_path(resolved):
            if path.name in _GENERATED_FILENAMES:
                records.append({"kind": "generated", "name": path.name, "sha256": digest})
            else:
                # Single-use modified/copied trees in temp dirs must not be
                # served across different temp directories (e.g. #filePath).
                records.append({"kind": "ephemeral", "path": str(resolved), "sha256": digest})
                cacheable = False
        else:
            records.append({"kind": "source", "path": str(resolved), "sha256": digest})
    return records, cacheable


def normalize_support_flags(flags: Sequence[str] = ()) -> tuple[str, ...]:
    """Normalize support module compilation flags cleanly."""
    normalized: list[str] = []
    skip_next = False
    for index, flag in enumerate(flags):
        if skip_next:
            skip_next = False
            continue
        if flag in {"-parse-as-library", "-whole-module-optimization", "-enable-testing"}:
            continue
        if flag == "-num-threads":
            if index + 1 < len(flags):
                skip_next = True
            continue
        normalized.append(flag)
    threads = str(max(1, min(os.cpu_count() or 4, 8)))
    return (
        "-parse-as-library",
        "-whole-module-optimization",
        "-num-threads",
        threads,
        "-enable-testing",
        *normalized,
    )


def compute_support_key(
    *,
    toolchain: Mapping[str, str],
    support_flags: Sequence[str],
    file_records: Sequence[Mapping[str, str]],
    module_name: str = MODULE_NAME,
) -> str:
    """Compute a full cryptographic key covering environment, flags, and inputs."""
    payload = {
        "format": CACHE_FORMAT_VERSION,
        "module_name": module_name,
        "toolchain": dict(toolchain),
        "support_flags": list(support_flags),
        "sources": list(file_records),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_cached_entry(entry_dir: Path, expected_key: str) -> bool:
    manifest_path = entry_dir / "manifest.json"
    module_path = entry_dir / f"{MODULE_NAME}.swiftmodule"
    lib_path = entry_dir / f"lib{MODULE_NAME}.a"
    if not (manifest_path.is_file() and module_path.is_file() and lib_path.is_file()):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("version") != CACHE_FORMAT_VERSION:
        return False
    if manifest.get("key") != expected_key:
        return False
    return (
        manifest.get("module_sha256") == _file_sha256(module_path)
        and manifest.get("lib_sha256") == _file_sha256(lib_path)
    )


def _prune_cache(cache_dir: Path, keep_name: str) -> None:
    """Bound local disk usage by retaining only the most recently used entries."""
    candidates: list[tuple[float, Path]] = []
    try:
        children = list(cache_dir.iterdir())
    except OSError:
        return
    for child in children:
        if not child.is_dir() or child.name.startswith(".") or child.name == keep_name:
            continue
        manifest = child / "manifest.json"
        try:
            mtime = manifest.stat().st_mtime if manifest.is_file() else child.stat().st_mtime
            candidates.append((mtime, child))
        except OSError:
            continue
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, stale_dir in candidates[MAX_CACHE_ENTRIES - 1:]:
        shutil.rmtree(stale_dir, ignore_errors=True)


def _sdk_args(toolchain: Mapping[str, str], existing_flags: Sequence[str]) -> list[str]:
    sdk_path = toolchain.get("sdk_path", "")
    if sdk_path and "-sdk" not in existing_flags:
        return ["-sdk", sdk_path]
    return []


def _subprocess_env(base_env: Mapping[str, str], toolchain: Mapping[str, str]) -> dict[str, str]:
    child_env = dict(base_env)
    if "PATH" not in child_env and "PATH" in os.environ:
        child_env["PATH"] = os.environ["PATH"]
    sdk_path = toolchain.get("sdk_path", "")
    if sdk_path:
        child_env["SDKROOT"] = sdk_path
    elif child_env.get("SDKROOT", "").startswith(_CLT_SDK_PREFIX):
        child_env.pop("SDKROOT", None)
    return child_env


def _ensure_support_module(
    *,
    swiftc: str,
    toolchain: Mapping[str, str],
    support_sources: Sequence[Path],
    support_flags: Sequence[str],
    cache_dir: Path,
    key: str,
    cwd: Path | None,
    child_env: Mapping[str, str],
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    locks_dir = cache_dir / ".locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    entry_dir = cache_dir / key[:24]
    lock_path = locks_dir / f"{key[:24]}.lock"

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            if _valid_cached_entry(entry_dir, key):
                try:
                    os.utime(entry_dir / "manifest.json", None)
                except OSError:
                    pass
                return entry_dir

            if entry_dir.exists():
                shutil.rmtree(entry_dir, ignore_errors=True)

            staging_dir = cache_dir / f".staging-{key[:16]}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            staging_dir.mkdir(parents=True, exist_ok=True)
            try:
                module_path = staging_dir / f"{MODULE_NAME}.swiftmodule"
                lib_path = staging_dir / f"lib{MODULE_NAME}.a"
                cmd = [
                    swiftc,
                    *_sdk_args(toolchain, support_flags),
                    *support_flags,
                    "-emit-module",
                    "-emit-module-path",
                    str(module_path),
                    "-emit-library",
                    "-static",
                    "-module-name",
                    MODULE_NAME,
                    *map(str, support_sources),
                    "-o",
                    str(lib_path),
                ]
                subprocess.run(cmd, check=True, cwd=cwd, env=child_env)
                manifest = {
                    "version": CACHE_FORMAT_VERSION,
                    "key": key,
                    "module_sha256": _file_sha256(module_path),
                    "lib_sha256": _file_sha256(lib_path),
                }
                (staging_dir / "manifest.json").write_text(
                    json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
                )
                shutil.rmtree(entry_dir, ignore_errors=True)
                os.replace(staging_dir, entry_dir)
                _prune_cache(cache_dir, entry_dir.name)
                return entry_dir
            except Exception:
                shutil.rmtree(staging_dir, ignore_errors=True)
                raise
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _write_harness_shims(
    harness_sources: Sequence[Path],
    shim_dir: Path,
) -> list[Path]:
    """Create temporary harness shims that import MGTTestSupport."""
    shim_dir.mkdir(parents=True, exist_ok=True)
    shimmed: list[Path] = []
    seen_names: dict[str, int] = {}
    import_line = f"@testable import {MODULE_NAME}"
    for raw_path in harness_sources:
        path = Path(raw_path)
        text = path.read_text(encoding="utf-8")
        if import_line in text or f"import {MODULE_NAME}" in text:
            shimmed.append(path)
            continue
        count = seen_names.get(path.name, 0)
        seen_names[path.name] = count + 1
        target_name = path.name if count == 0 else f"{count}_{path.name}"
        target = shim_dir / target_name
        target.write_text(f"{import_line}\n{text}", encoding="utf-8")
        shimmed.append(target)
    return shimmed


def _filter_direct_flags(flags: Sequence[str]) -> list[str]:
    """Strip flags only meant for support-module multi-file builds if unwanted."""
    return list(flags)


def compile_swift_test(
    *,
    harness_sources: Sequence[Path],
    output: Path,
    support_sources: Sequence[Path] = (),
    flags: Sequence[str] = ("-parse-as-library",),
    support_flags: Sequence[str] | None = None,
    swiftc: str | None = None,
    cwd: Path | None = None,
    cache_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Compile one Swift test executable, reusing a keyed support-module cache."""
    compiler = resolve_swiftc(swiftc)
    env = os.environ if environ is None else environ
    harness_list = [Path(p) for p in harness_sources]
    support_list = [Path(p) for p in support_sources]
    output_path = Path(output)
    sdk_env = env.get("SDKROOT", "").strip()
    dev_env = env.get("DEVELOPER_DIR", "").strip()
    toolchain = probe_toolchain(compiler, sdk_env, dev_env, environ=env)
    child_env = _subprocess_env(env, toolchain)

    cache_enabled = env.get(CACHE_ENV_VAR, "1").strip().lower() not in {"0", "false", "no", "off"}
    if not support_list or not cache_enabled:
        cmd = [
            compiler,
            *_sdk_args(toolchain, flags),
            *_filter_direct_flags(flags),
            *map(str, [*support_list, *harness_list]),
            "-o",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, cwd=cwd, env=child_env)
        return output_path

    file_records, cacheable = _support_file_records(support_list)
    normalized_support_flags = normalize_support_flags(
        flags if support_flags is None else support_flags
    )

    if not cacheable:
        # Single-use temporary source tree (patched/copied sources): still
        # compile faster with WMO + threads, without writing shared cache entries
        # and while honoring caller library-vs-script parsing mode for harness files.
        direct_flags = [
            f
            for f in normalize_support_flags(flags)
            if f != "-enable-testing"
            and (f != "-parse-as-library" or "-parse-as-library" in flags)
        ]
        single_cmd = [
            compiler,
            *_sdk_args(toolchain, direct_flags),
            *direct_flags,
            *map(str, [*support_list, *harness_list]),
            "-o",
            str(output_path),
        ]
        subprocess.run(single_cmd, check=True, cwd=cwd, env=child_env)
        return output_path

    key = compute_support_key(
        toolchain=toolchain,
        support_flags=normalized_support_flags,
        file_records=file_records,
    )
    resolved_cache_dir = cache_dir if cache_dir is not None else default_cache_dir(env)
    module_dir = _ensure_support_module(
        swiftc=compiler,
        toolchain=toolchain,
        support_sources=support_list,
        support_flags=normalized_support_flags,
        cache_dir=resolved_cache_dir,
        key=key,
        cwd=cwd,
        child_env=child_env,
    )

    with tempfile.TemporaryDirectory(prefix="mgt-swift-shim-") as shim_root:
        shimmed = _write_harness_shims(harness_list, Path(shim_root))
        link_flags = [f for f in flags if f != "-whole-module-optimization"]
        cmd = [
            compiler,
            *_sdk_args(toolchain, link_flags),
            *link_flags,
            "-I",
            str(module_dir),
            "-L",
            str(module_dir),
            f"-l{MODULE_NAME}",
            *map(str, shimmed),
            "-o",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, cwd=cwd, env=child_env)
    return output_path
