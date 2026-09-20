from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .module_manifest import SaveManagementSpec


class SaveResolutionError(RuntimeError):
    code = 'save_unsafe'


@dataclass(frozen=True)
class ResolvedSaveFile:
    root_id: str
    relative_path: str
    source_path: Path


def _load_provider(target):
    module_name, class_name = target.split(':', 1)
    module = import_module(module_name)
    provider_type = getattr(module, class_name, None)
    if not isinstance(provider_type, type):
        raise SaveResolutionError('存档 Provider 类型无效。')
    return provider_type()


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
    provider_loader: Optional[Callable[[str], object]] = None,
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
                if candidate.is_dir():
                    continue
                relative = candidate.relative_to(root).as_posix()
                declared.append(_validate_file(root_spec.id, root, relative))

    rows: Iterable[Tuple[str, str]]
    if spec.provider is None:
        rows = ((row.root_id, row.relative_path) for row in declared)
    else:
        loader = provider_loader or _load_provider
        provider = loader(spec.provider)
        resolve = getattr(provider, 'resolve', None)
        if not callable(resolve):
            raise SaveResolutionError('存档 Provider 缺少 resolve()。')
        rows = resolve(dict(roots), tuple(declared))

    unique = {}
    try:
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
