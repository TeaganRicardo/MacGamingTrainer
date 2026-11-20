"""Compile Swift test harnesses against the product's Swift module layout.

The product compiles TrainerCore, one module per game frontend and the App as
separate Swift modules of one package; ``Tools/product_support.py`` owns their
order, dependencies and source files. A harness compiles the same library
modules (TrainerCore, then each game it loads against TrainerCore) and then
itself in the App's place, with a ``@testable import`` of every library
module. A harness names the games it loads, never product source files, so
moving a type between files or modules does not change what it compiles.
``harness_layout`` lists those files.

Each library module is cached as a testable static module
(``<Module>.swiftmodule`` + ``lib<Module>.a``), so TrainerCore compiles once
and each game once against it; a harness then compiles and links in seconds.

Equivalence and staleness guarantees:
- A module's key hashes compiler binary path + ``swiftc --version``, resolved
  macOS SDK path + version + ``DEVELOPER_DIR``, host architecture, normalized
  compile flags, the module name, the keys of the modules it imports, and
  every source file's identity + exact SHA-256 bytes.
- Repository files include their exact resolved path in the key so different
  worktrees/checkouts never share compiled ``#filePath`` literals (which
  ``Hades2Presentation`` uses to locate repository assets).
- Generated bindings are keyed by their place in the generated tree and their
  content digest so equal generated outputs share one cache entry across tests.
- A module with other temporary source files (a patched or copied tree), and
  every module that imports it, builds privately for one compile and never
  enters the shared cache.
- Writes stage into a PID-scoped temporary directory under an exclusive
  ``fcntl.flock`` lock, verify SHA-256 digests of both ``.swiftmodule`` and
  ``.a`` in ``manifest.json``, and recover automatically by rebuilding if any
  cached artifact is missing or corrupted. A shared per-module lease, held
  from first use until the harness has linked, keeps pruning from removing a
  module that a later step still reads.
- Setting ``MGT_SWIFT_TEST_CACHE=0`` bypasses the shared cache completely:
  every module builds privately for that compile, for clean A/B checks.

The Linux lane has a Swift toolchain but no SwiftUI or AppKit, so the product
layout cannot compile there. A portable harness passes explicit ``modules``
built from Foundation-level files and says so where it lists them.
"""
from __future__ import annotations

import fcntl
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
_TOOLS = ROOT / "Tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from swift_module_layout import SWIFT_CORE_MODULE, SWIFT_PACKAGE_NAME  # noqa: E402

CACHE_FORMAT_VERSION = 3
# The harness takes the App module's place in the package.
HARNESS_MODULE_NAME = "TrainerTestHarness"
PACKAGE_FLAGS = ("-package-name", SWIFT_PACKAGE_NAME)
MAX_CACHE_ENTRIES = 16
CACHE_ENV_VAR = "MGT_SWIFT_TEST_CACHE"
CACHE_DIR_ENV_VAR = "MGT_SWIFT_TEST_CACHE_DIR"
_CLT_SDK_PREFIX = "/Library/Developer/CommandLineTools/"
_IMPORT = re.compile(r"^[ \t]*(?:@\w+[ \t]+)*import[ \t]+(\w+)", re.MULTILINE)
# Runs with the checkout's own Tools, which read that checkout's manifests.
_LAYOUT_PROGRAM = """
import json, sys
from importlib import import_module
from pathlib import Path

layout_tool = Path(sys.argv[1])
sys.path.insert(0, str(layout_tool.parent))
swift_library_modules = import_module(layout_tool.stem).swift_library_modules
modules = swift_library_modules([game for game in sys.argv[2].split(',') if game], sys.argv[3])
print(json.dumps([[module['name'], module['dependencies'], [str(path) for path in sources]]
                  for module, sources in modules]))
"""


class SwiftCompilerError(RuntimeError):
    """Raised when the Swift toolchain is unavailable or compilation fails."""


@dataclass(frozen=True)
class SwiftModule:
    """A library module a harness imports: its files and the modules it imports."""

    name: str
    sources: tuple[Path, ...]
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(Path(path) for path in self.sources))
        object.__setattr__(self, "dependencies", tuple(self.dependencies))


def harness_layout(games: Sequence[str], directory: Path, *, checkout: Path = ROOT) -> tuple[SwiftModule, ...]:
    """TrainerCore and each game's frontend module, as the product compiles them.

    ``Tools/product_support.py`` of ``checkout`` derives the layout from that
    checkout's manifests and writes the generated sources under ``directory``.
    """
    layout_tool = Path(checkout) / "Tools/product_support.py"
    result = subprocess.run(
        [sys.executable, "-I", "-c", _LAYOUT_PROGRAM, str(layout_tool), ",".join(games), str(directory)],
        capture_output=True, text=True,
    )
    if result.returncode:
        raise SwiftCompilerError(f"{checkout} could not derive its Swift layout:\n{result.stderr}")
    records = json.loads(result.stdout)
    return tuple(
        SwiftModule(name, tuple(Path(path) for path in sources), tuple(dependencies))
        for name, dependencies, sources in records
    )


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
    generated_root: Path | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """Classify one module's files into stable key records and cache eligibility.

    Files the helper generated under ``generated_root`` are keyed by their
    place there and their content, so equal bindings share one cache entry.
    """
    records: list[dict[str, str]] = []
    cacheable = True
    generated = generated_root.resolve() if generated_root is not None else None
    for raw_path in support_sources:
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"missing Swift support source: {path}")
        digest = _file_sha256(path)
        resolved = path.resolve()
        if generated is not None and resolved.is_relative_to(generated):
            records.append({"kind": "generated", "name": resolved.relative_to(generated).as_posix(),
                            "sha256": digest})
        elif _is_temp_path(resolved):
            # Single-use modified/copied trees in temp dirs must not be
            # served across different temp directories (e.g. #filePath).
            records.append({"kind": "ephemeral", "path": str(resolved), "sha256": digest})
            cacheable = False
        else:
            records.append({"kind": "source", "path": str(resolved), "sha256": digest})
    return records, cacheable


def normalize_support_flags(flags: Sequence[str] = ()) -> tuple[str, ...]:
    """Normalize library module compilation flags."""
    normalized: list[str] = []
    skip_next = False
    for index, flag in enumerate(flags):
        if skip_next:
            skip_next = False
            continue
        if flag in {"-parse-as-library", "-whole-module-optimization", "-enable-testing"}:
            continue
        if flag in {"-num-threads", "-package-name", "-module-name"}:
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
        *PACKAGE_FLAGS,
        *normalized,
    )


def compute_support_key(
    *,
    toolchain: Mapping[str, str],
    support_flags: Sequence[str],
    file_records: Sequence[Mapping[str, str]],
    module_name: str = SWIFT_CORE_MODULE,
    dependencies: Mapping[str, str] | None = None,
) -> str:
    """Compute a full cryptographic key covering environment, flags, and inputs."""
    payload = {
        "format": CACHE_FORMAT_VERSION,
        "module_name": module_name,
        "dependencies": dict(dependencies or {}),
        "toolchain": dict(toolchain),
        "support_flags": list(support_flags),
        "sources": list(file_records),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_cached_entry(entry_dir: Path, expected_key: str, module_name: str) -> bool:
    manifest_path = entry_dir / "manifest.json"
    module_path = entry_dir / f"{module_name}.swiftmodule"
    lib_path = entry_dir / f"lib{module_name}.a"
    if not (manifest_path.is_file() and module_path.is_file() and lib_path.is_file()):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("version") != CACHE_FORMAT_VERSION:
        return False
    if manifest.get("key") != expected_key or manifest.get("module") != module_name:
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
        # Another compile step or test process may hold a lease on this module.
        # Pruning must respect the same per-key lock used by active readers.
        lock_path = cache_dir / ".locks" / f"{stale_dir.name}.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            try:
                shutil.rmtree(stale_dir, ignore_errors=True)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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


def _force_load(library: Path) -> list[str]:
    """Link every object of a static module, as the product does, so runtime
    conformance lookup sees the whole module."""
    if os.uname().sysname == "Darwin":
        return ["-Xlinker", "-force_load", "-Xlinker", str(library)]
    return ["-Xlinker", "--whole-archive", "-Xlinker", str(library), "-Xlinker", "--no-whole-archive"]


def _build_module(
    *,
    swiftc: str,
    toolchain: Mapping[str, str],
    module: SwiftModule,
    support_flags: Sequence[str],
    dependency_dirs: Sequence[Path],
    directory: Path,
    cwd: Path | None,
    child_env: Mapping[str, str],
) -> None:
    """Compile one library module into ``directory`` against its dependencies only."""
    directory.mkdir(parents=True, exist_ok=True)
    search_paths = [argument for path in dependency_dirs for argument in ("-I", str(path))]
    cmd = [
        swiftc,
        *_sdk_args(toolchain, support_flags),
        *support_flags,
        *search_paths,
        "-emit-module",
        "-emit-module-path",
        str(directory / f"{module.name}.swiftmodule"),
        "-emit-library",
        "-static",
        "-module-name",
        module.name,
        *map(str, module.sources),
        "-o",
        str(directory / f"lib{module.name}.a"),
    ]
    subprocess.run(cmd, check=True, cwd=cwd, env=child_env)


def _ensure_module(
    *,
    swiftc: str,
    toolchain: Mapping[str, str],
    module: SwiftModule,
    support_flags: Sequence[str],
    dependency_dirs: Sequence[Path],
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
            if _valid_cached_entry(entry_dir, key, module.name):
                return entry_dir

            if entry_dir.exists():
                shutil.rmtree(entry_dir, ignore_errors=True)

            staging_dir = cache_dir / f".staging-{key[:16]}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            try:
                _build_module(
                    swiftc=swiftc,
                    toolchain=toolchain,
                    module=module,
                    support_flags=support_flags,
                    dependency_dirs=dependency_dirs,
                    directory=staging_dir,
                    cwd=cwd,
                    child_env=child_env,
                )
                manifest = {
                    "version": CACHE_FORMAT_VERSION,
                    "key": key,
                    "module": module.name,
                    "module_sha256": _file_sha256(staging_dir / f"{module.name}.swiftmodule"),
                    "lib_sha256": _file_sha256(staging_dir / f"lib{module.name}.a"),
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


@contextmanager
def _leased_entry(
    cache_dir: Path,
    key: str,
    module_name: str,
    build_entry: Callable[[], Path],
) -> Iterator[Path]:
    """Yield a valid cached module while holding a shared lease on it.

    A miss builds under the exclusive lock, then re-validates under the lease:
    if another compile pruned the entry in between, it rebuilds instead of
    handing a missing module to a later step. Pruners skip leased entries.
    """
    entry_dir = cache_dir / key[:24]
    lock_path = cache_dir / ".locks" / f"{key[:24]}.lock"
    for attempt in range(3):
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                if _valid_cached_entry(entry_dir, key, module_name):
                    try:
                        os.utime(entry_dir / "manifest.json", None)
                    except OSError:
                        pass
                    yield entry_dir
                    return
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        if attempt < 2:
            entry_dir = build_entry()
    raise SwiftCompilerError(f"Swift test cache entry for {module_name} was repeatedly evicted before use")


def _write_harness_shims(
    harness_sources: Sequence[Path],
    shim_dir: Path,
    modules: Sequence[str],
) -> list[Path]:
    """Copy harness files that do not import every library module, adding a
    ``@testable import`` for each module they do not import."""
    shim_dir.mkdir(parents=True, exist_ok=True)
    shimmed: list[Path] = []
    seen_names: dict[str, int] = {}
    for raw_path in harness_sources:
        path = Path(raw_path)
        text = path.read_text(encoding="utf-8")
        imported = set(_IMPORT.findall(text))
        missing = [module for module in modules if module not in imported]
        if not missing:
            shimmed.append(path)
            continue
        count = seen_names.get(path.name, 0)
        seen_names[path.name] = count + 1
        target_name = path.name if count == 0 else f"{count}_{path.name}"
        target = shim_dir / target_name
        target.write_text("".join(f"@testable import {module}\n" for module in missing) + text, encoding="utf-8")
        shimmed.append(target)
    return shimmed


def _patch_modules(
    library: Sequence[SwiftModule],
    patched: Mapping[Path, Path],
    instrumentation: Mapping[str, Sequence[Path]],
) -> tuple[SwiftModule, ...]:
    """Replace product files with patched copies and add instrumentation files.

    Every patched file and instrumented module must be part of the harness, so
    a moved file fails loudly instead of silently compiling the original.
    """
    replacements = {Path(original).resolve(): Path(copy) for original, copy in patched.items()}
    unused = set(replacements)
    result = []
    for module in library:
        sources = []
        for path in module.sources:
            replacement = replacements.get(path.resolve())
            if replacement is not None:
                unused.discard(path.resolve())
            sources.append(replacement or path)
        sources += [Path(path) for path in instrumentation.get(module.name, ())]
        result.append(SwiftModule(module.name, tuple(sources), module.dependencies))
    if unused:
        raise SwiftCompilerError(f"patched files are not compiled by this harness: {sorted(map(str, unused))}")
    unknown = set(instrumentation) - {module.name for module in library}
    if unknown:
        raise SwiftCompilerError(f"instrumented modules are not compiled by this harness: {sorted(unknown)}")
    return tuple(result)


def main_actor_entrypoint(body: str) -> str:
    """Run synchronous Swift fixture statements from an explicit MainActor entry point."""
    return (
        "\n@main struct Main {\n"
        "    @MainActor static func main() throws {\n"
        + textwrap.indent(body.strip("\n"), "        ")
        + "\n    }\n}\n"
    )


def compile_swift_test(
    *,
    harness_sources: Sequence[Path],
    output: Path,
    games: Sequence[str] = (),
    checkout: Path = ROOT,
    modules: Sequence[SwiftModule] | None = None,
    patched: Mapping[Path, Path] | None = None,
    instrumentation: Mapping[str, Sequence[Path]] | None = None,
    flags: Sequence[str] = ("-parse-as-library",),
    support_flags: Sequence[str] | None = None,
    swiftc: str | None = None,
    cwd: Path | None = None,
    cache_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Compile one Swift test executable against the product's module layout.

    By default the harness imports TrainerCore and the frontend module of each
    of ``games`` from ``checkout``. ``modules`` replaces the layout
    with explicit library modules in build order (portable harnesses only).
    ``patched`` maps product files to patched copies that replace them in
    their module, and ``instrumentation`` adds files (for example a trace type
    that patched code calls) to named modules. ``flags`` apply to the harness;
    ``support_flags`` (default: ``flags``) to the library modules.
    """
    compiler = resolve_swiftc(swiftc)
    env = os.environ if environ is None else environ
    output_path = Path(output)
    toolchain = probe_toolchain(
        compiler, env.get("SDKROOT", "").strip(), env.get("DEVELOPER_DIR", "").strip(), environ=env
    )
    child_env = _subprocess_env(env, toolchain)
    cache_enabled = env.get(CACHE_ENV_VAR, "1").strip().lower() not in {"0", "false", "no", "off"}
    resolved_cache_dir = cache_dir if cache_dir is not None else default_cache_dir(env)
    normalized_support_flags = normalize_support_flags(flags if support_flags is None else support_flags)

    with tempfile.TemporaryDirectory(prefix="mgt-swift-test-") as scratch_root, ExitStack() as leases:
        scratch = Path(scratch_root)
        generated_root = scratch / "generated"
        if modules is None:
            library = harness_layout(games, generated_root, checkout=checkout)
        else:
            if games:
                raise ValueError("explicit modules replace the product layout; do not also name games")
            library = tuple(modules)
        if patched or instrumentation:
            library = _patch_modules(library, patched or {}, instrumentation or {})

        module_dirs: dict[str, Path] = {}
        module_keys: dict[str, str | None] = {}
        for module in library:
            missing = [name for name in module.dependencies if name not in module_dirs]
            if missing:
                raise SwiftCompilerError(f"{module.name} imports modules not built before it: {missing}")
            dependency_dirs = [module_dirs[name] for name in module.dependencies]
            records, cacheable = _support_file_records(module.sources, generated_root)
            if cache_enabled and cacheable and all(module_keys[name] for name in module.dependencies):
                key = compute_support_key(
                    toolchain=toolchain,
                    support_flags=normalized_support_flags,
                    file_records=records,
                    module_name=module.name,
                    dependencies={name: module_keys[name] for name in module.dependencies},
                )

                def build_entry(module=module, key=key, dependency_dirs=dependency_dirs) -> Path:
                    return _ensure_module(
                        swiftc=compiler,
                        toolchain=toolchain,
                        module=module,
                        support_flags=normalized_support_flags,
                        dependency_dirs=dependency_dirs,
                        cache_dir=resolved_cache_dir,
                        key=key,
                        cwd=cwd,
                        child_env=child_env,
                    )

                module_dirs[module.name] = leases.enter_context(
                    _leased_entry(resolved_cache_dir, key, module.name, build_entry)
                )
                module_keys[module.name] = key
            else:
                directory = scratch / "modules" / module.name
                _build_module(
                    swiftc=compiler,
                    toolchain=toolchain,
                    module=module,
                    support_flags=normalized_support_flags,
                    dependency_dirs=dependency_dirs,
                    directory=directory,
                    cwd=cwd,
                    child_env=child_env,
                )
                module_dirs[module.name] = directory
                module_keys[module.name] = None

        shimmed = _write_harness_shims(harness_sources, scratch / "harness", [module.name for module in library])
        link_flags = [flag for flag in flags if flag != "-whole-module-optimization"]
        if "-package-name" not in link_flags:
            link_flags += PACKAGE_FLAGS
        if "-module-name" not in link_flags:
            link_flags += ["-module-name", HARNESS_MODULE_NAME]
        cmd = [
            compiler,
            *_sdk_args(toolchain, link_flags),
            *link_flags,
            *(argument for directory in module_dirs.values() for argument in ("-I", str(directory))),
            *(argument for module in library
              for argument in _force_load(module_dirs[module.name] / f"lib{module.name}.a")),
            *map(str, shimmed),
            "-o",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, cwd=cwd, env=child_env)
    return output_path
