import os
import re
import stat
from contextlib import ExitStack
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple, TypedDict, runtime_checkable

from .errors import CoreSaveError
from .module_manifest import SaveManagementSpec

HOT_SAVE_HOLDING_PREFIX = '.trainer-hot-save-'
_HOT_SAVE_HOLDING_NAME = re.compile(re.escape(HOT_SAVE_HOLDING_PREFIX) + '[0-9a-f]{32}')


class SaveResolutionError(CoreSaveError):
    code = 'save_unsafe'
    presentation_key = 'host.save.error.unsafe'


@dataclass(frozen=True)
class ResolvedSaveFile:
    root_id: str
    relative_path: str
    source_path: Path


@dataclass(frozen=True)
class SaveProviderContext:
    module_dir: Path
    game_path: Optional[Path] = None


class LocalizedSnapshotDescription(TypedDict):
    name: str
    details: List[str]


class SnapshotDescription(TypedDict, total=False):
    defaultName: Optional[str]
    nameDetails: List[str]
    localizedPresentation: Dict[str, LocalizedSnapshotDescription]


@runtime_checkable
class SaveProvider(Protocol):
    """Optional game policy for Core Save transactions."""

    context: SaveProviderContext

    def resolve(self, roots: Mapping[str, Path], declared: Tuple[ResolvedSaveFile, ...]) -> Iterable[Tuple[str, str]]:
        """Choose members by declared root ID and relative path."""
        return [(row.root_id, row.relative_path) for row in declared]

    def restore_busy(self, files: Tuple[ResolvedSaveFile, ...]) -> bool:
        return False

    def describe_snapshot(self, files: Tuple[ResolvedSaveFile, ...], created_at: str) -> Optional[SnapshotDescription]:
        return None


class DefaultSaveProvider(SaveProvider):
    """Initialize the context for providers that inherit the default hooks."""

    def __init__(self, context: SaveProviderContext) -> None:
        self.context = context


def read_resolved_save_file(root, row):
    """Read one regular file through a contained, captured directory chain."""
    root = Path(root).expanduser()
    try:
        if root.is_symlink() or row.source_path.is_symlink():
            raise SaveResolutionError('Save source cannot be a symbolic link.')
        canonical_root = root.resolve(strict=True)
        canonical_file = row.source_path.resolve(strict=True)
        relative = canonical_file.relative_to(canonical_root)
        root_metadata = canonical_root.stat()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        with ExitStack() as stack:
            descriptor = os.open(canonical_root, flags)
            stack.callback(os.close, descriptor)
            captured = os.fstat(descriptor)
            if (captured.st_dev, captured.st_ino) != (root_metadata.st_dev, root_metadata.st_ino):
                raise SaveResolutionError('Save source directory changed while opening.')
            directories = [(canonical_root, descriptor)]
            parent = canonical_root
            for component in relative.parts[:-1]:
                descriptor = os.open(component, flags, dir_fd=descriptor)
                stack.callback(os.close, descriptor)
                parent /= component
                directories.append((parent, descriptor))
            file_descriptor = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            source = stack.enter_context(os.fdopen(file_descriptor, 'rb'))
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise SaveResolutionError('Save source is not a regular file.')
            raw = source.read()
            if (
                root.is_symlink()
                or root.resolve() != canonical_root
                or row.source_path.is_symlink()
                or row.source_path.resolve() != canonical_file
            ):
                raise SaveResolutionError('Save source path changed while reading.')
            for path, directory in directories:
                captured, current = os.fstat(directory), path.stat()
                if (captured.st_dev, captured.st_ino) != (current.st_dev, current.st_ino):
                    raise SaveResolutionError('Save source directory changed while reading.')
            return raw
    except (OSError, ValueError) as error:
        raise SaveResolutionError('Save source is missing or outside its declared directory.') from error


def load_save_provider(target: str, *, context: Optional[SaveProviderContext] = None) -> SaveProvider:
    module_name, class_name = target.split(':', 1)
    module = import_module(module_name)
    provider_type = getattr(module, class_name, None)
    if not isinstance(provider_type, type):
        raise SaveResolutionError('存档 Provider 类型无效。')
    if context is None:
        # Standalone service callers have a provider declaration but no adapter context.
        package = import_module('.'.join(module_name.split('.')[:2]))
        if package.__file__ is None:
            raise SaveResolutionError('Save Provider module directory is unavailable.')
        context = SaveProviderContext(Path(package.__file__).resolve().parent)
    provider = provider_type(context)
    if not isinstance(provider, SaveProvider):
        raise SaveResolutionError('Save Provider must implement the SaveProvider contract.')
    return provider


def _validate_relative(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise SaveResolutionError('存档 Provider 返回了无效相对路径。')
    path = Path(value)
    if path.is_absolute() or '..' in path.parts or str(path) in ('', '.'):
        raise SaveResolutionError('存档 Provider 返回了越界路径。')
    return path


def _validate_file(root_id, root, relative):
    relative_path = _validate_relative(relative)
    candidate = root / relative_path
    if candidate.is_symlink():
        raise SaveResolutionError('存档文件不能是符号链接。')
    root_resolved = root.resolve(strict=False)
    try:
        candidate.resolve(strict=False).relative_to(root_resolved)
    except ValueError as error:
        raise SaveResolutionError('存档文件越过声明的根目录。') from error
    if not candidate.is_file():
        raise SaveResolutionError('存档 Provider 返回的文件不存在或不是常规文件。')
    return ResolvedSaveFile(root_id, relative_path.as_posix(), candidate)


def resolve_save_files(
    spec: SaveManagementSpec,
    provider_loader: Optional[Callable[[str], SaveProvider]] = None,
) -> List[ResolvedSaveFile]:
    roots: Dict[str, Path] = {}
    declared: List[ResolvedSaveFile] = []

    for root_spec in spec.roots:
        root = Path(root_spec.path).expanduser()
        if root.is_symlink():
            raise SaveResolutionError('存档根目录不能是符号链接。')
        roots[root_spec.id] = root
        if not root.exists():
            continue
        if not root.is_dir():
            raise SaveResolutionError('存档根路径不是目录。')
        for pattern in root_spec.include:
            for candidate in root.glob(pattern):
                if _HOT_SAVE_HOLDING_NAME.fullmatch(candidate.name) or candidate.is_dir():
                    continue
                relative = candidate.relative_to(root).as_posix()
                declared.append(_validate_file(root_spec.id, root, relative))

    unique = {}
    try:
        rows: Iterable[Tuple[str, str]]
        if spec.provider is None:
            rows = ((row.root_id, row.relative_path) for row in declared)
        else:
            loader = provider_loader or load_save_provider
            provider = loader(spec.provider)
            rows = provider.resolve(dict(roots), tuple(declared))
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise SaveResolutionError('存档 Provider 必须返回 (rootId, relativePath)。')
            root_id, relative = row
            if root_id not in roots:
                raise SaveResolutionError('存档 Provider 返回了未声明的根目录。')
            resolved = _validate_file(root_id, roots[root_id], relative)
            unique[(resolved.root_id, resolved.relative_path)] = resolved
    except SaveResolutionError:
        raise
    except Exception as error:
        raise SaveResolutionError('存档 Provider 解析失败。') from error

    return [unique[key] for key in sorted(unique)]
