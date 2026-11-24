"""Hades II executable/save preparation. Build-agnostic and recoverable."""
from collections import OrderedDict
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.log_paths import trainer_data_directory
from core.target_probe import AmbiguousTargetError, BoundedCommandTimeoutError, bounded_run, locate_target

from .config import (
    BUNDLE_IDENTIFIER, DISPLAY_NAME, GAME_APP, GAME_ARCHITECTURE, GAME_EXECUTABLE,
    GAME_EXECUTABLE_NAME, GAME_SAVES, MODULE_MANIFEST, STEAM_MANIFEST,
    SUPPORTED_BUILD, resolve_game_install, steam_manifest_for_bundle,
)
from .error_presentation import Hades2PresentationError, Hades2RuntimeError
from .operation_budgets import PROCESS_QUERY_TIMEOUT_SECONDS, SUBPROCESS_TIMEOUT_SECONDS
from .persistence import migrate_legacy_root_data_dir

GAME = GAME_APP
SAVES = GAME_SAVES
_DEFAULT_GAME = GAME_APP
_DEFAULT_EXECUTABLE = GAME_EXECUTABLE
_DEFAULT_STEAM_MANIFEST = STEAM_MANIFEST
_COMPATIBILITY_CACHE_MAX_ENTRIES = 8
_COMPATIBILITY_CACHE: OrderedDict = OrderedDict()
VERSION = SUPPORTED_BUILD['bundleVersion']
STEAM_BUILD = SUPPORTED_BUILD['steamBuildID']
UUID = SUPPORTED_BUILD['uuid']
ORIGINAL_SHA256 = SUPPORTED_BUILD['originalExecutableSHA256']
TIMEOUT = SUBPROCESS_TIMEOUT_SECONDS


def invalidate_compatibility_cache():
    """Discard cached bundle compatibility observations."""
    _COMPATIBILITY_CACHE.clear()


def resolve_paths(game_path=None, *, query_running=True):
    """Return active `(game_app, executable, steam_manifest)` paths."""
    if game_path is not None:
        game = Path(game_path)
        return (
            game,
            game / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME,
            steam_manifest_for_bundle(game),
        )
    if (
        GAME != _DEFAULT_GAME
        or GAME_EXECUTABLE != _DEFAULT_EXECUTABLE
        or STEAM_MANIFEST != _DEFAULT_STEAM_MANIFEST
    ):
        game = Path(GAME)
        exe = (
            Path(GAME_EXECUTABLE)
            if GAME_EXECUTABLE != _DEFAULT_EXECUTABLE
            else game / 'Contents' / 'MacOS' / GAME_EXECUTABLE_NAME
        )
        manifest = (
            Path(STEAM_MANIFEST)
            if STEAM_MANIFEST != _DEFAULT_STEAM_MANIFEST
            else steam_manifest_for_bundle(game)
        )
        return game, exe, manifest

    located_bundle = None
    if query_running:
        try:
            located = locate_target(MODULE_MANIFEST, timeout=PROCESS_QUERY_TIMEOUT_SECONDS)
            if located is not None:
                located_bundle = located.bundle_path
        except (OSError, subprocess.CalledProcessError, BoundedCommandTimeoutError, AmbiguousTargetError):
            located_bundle = None
    return resolve_game_install(located_bundle=located_bundle)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _command(*args, allowed=(0,)):
    try:
        return bounded_run(args, TIMEOUT, capture_output=True, allowed=allowed)
    except BoundedCommandTimeoutError as error:
        program = error.argv[0] if error.argv else 'subprocess'
        raise Hades2RuntimeError('hades2.error.timeout', str(error), (program, f'{error.budget:g}')) from error
    except OSError as error:
        raise Hades2RuntimeError(
            'hades2.error.commandLaunchFailed',
            f'无法运行 {args[0]}：{error}',
            (str(args[0]), str(error)),
        ) from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or b'').decode('utf-8', errors='replace')[-3000:].strip()
        reason = detail or f'exit {error.returncode}'
        raise Hades2RuntimeError(
            'hades2.error.commandFailed',
            f'{args[0]} 失败（{error.returncode}）：{reason}',
            (str(args[0]), str(error.returncode), reason),
        ) from error


def run(*args):
    return _command(*args).stdout


def _require_stopped():
    try:
        located = locate_target(MODULE_MANIFEST, timeout=PROCESS_QUERY_TIMEOUT_SECONDS)
    except AmbiguousTargetError as error:
        raise Hades2RuntimeError(
            'hades2.error.multipleProcesses',
            f'检测到多个 {DISPLAY_NAME} 进程，请保留一个。',
            (DISPLAY_NAME,),
        ) from error
    except BoundedCommandTimeoutError as error:
        program = error.argv[0] if error.argv else 'subprocess'
        raise Hades2RuntimeError('hades2.error.timeout', str(error), (program, f'{error.budget:g}')) from error
    except OSError as error:
        raise Hades2RuntimeError(
            'hades2.error.commandLaunchFailed',
            f'无法运行 /bin/ps：{error}',
            ('/bin/ps', str(error)),
        ) from error
    except subprocess.CalledProcessError as error:
        raw = error.stderr or error.stdout or ''
        detail = (raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else raw).strip()
        reason = detail or f'exit {error.returncode}'
        raise Hades2RuntimeError(
            'hades2.error.commandFailed',
            f'/bin/ps 失败（{error.returncode}）：{reason}',
            ('/bin/ps', str(error.returncode), reason),
        ) from error
    if located is not None:
        raise Hades2RuntimeError(
            'hades2.error.prepareWhileRunning',
            f'请先退出 {DISPLAY_NAME}；运行中不能修改签名或恢复存档。',
            (DISPLAY_NAME,),
        )


def _uuid(exe):
    result = run('/usr/bin/xcrun', 'dwarfdump', '--uuid', str(exe)).decode()
    architecture = GAME_ARCHITECTURE
    pattern = r'UUID: ([A-Fa-f0-9-]+) \(' + re.escape(architecture) + r'\)' if architecture else r'UUID: ([A-Fa-f0-9-]+) \([^)]*\)'
    match = re.search(pattern, result)
    if not match:
        suffix = f'（{architecture}）' if architecture else ''
        raise Hades2RuntimeError(
            'hades2.error.uuidLookupFailed',
            '找不到匹配架构的 Mach-O UUID' + suffix + '。',
            (suffix,),
        )
    return match.group(1).upper()


def _file_signature(path: Path):
    stat = path.stat()
    return str(path.resolve()), stat.st_mtime_ns, stat.st_size


def compatibility(strict=False, game_path=None, *, query_running=True):
    """Report version drift without blocking supported operations by default."""
    game, exe, steam = resolve_paths(game_path=game_path, query_running=query_running)
    info_path = game / 'Contents/Info.plist'
    if not game.exists() or not info_path.is_file() or not exe.is_file():
        raise Hades2PresentationError(
            'not_installed',
            'hades2.error.gameNotInstalled',
            (DISPLAY_NAME,),
            diagnostic=f'{DISPLAY_NAME} is not installed (expected at {game}).',
        )
    cache_key = None
    try:
        cache_key = (
            *_file_signature(info_path),
            *_file_signature(exe),
            *_file_signature(steam),
            _uuid,
        )
    except OSError:
        cache_key = None

    if cache_key is not None and cache_key in _COMPATIBILITY_CACHE:
        _COMPATIBILITY_CACHE.move_to_end(cache_key)
        cached = _COMPATIBILITY_CACHE[cache_key]
        if strict and not cached['compatible']:
            raise Hades2RuntimeError(
                'hades2.error.unverifiedBuildWarning',
                cached['warnings'][0],
                (str(cached['version']), str(cached['steam_build']), str(cached['uuid'])),
            )
        return dict(cached, warnings=list(cached['warnings']))

    info = plistlib.loads(info_path.read_bytes())
    version = info.get('CFBundleVersion')
    try:
        manifest_text = steam.read_text(encoding='utf-8', errors='replace')
    except OSError:
        manifest_text = ''
    match = re.search(r'"buildid"\s+"([0-9]+)"', manifest_text)
    build = match.group(1) if match else None
    uuid = _uuid(exe)
    compatible = version == VERSION and build == STEAM_BUILD and uuid == UUID
    warning = f'未经验证的游戏版本：version={version}, build={build}, UUID={uuid}。'
    result = {
        'version': version,
        'steam_build': build,
        'uuid': uuid,
        'game': str(game),
        'compatible': compatible,
        'warnings': [] if compatible else [warning],
    }
    if cache_key is not None:
        _COMPATIBILITY_CACHE[cache_key] = dict(result, warnings=list(result['warnings']))
        _COMPATIBILITY_CACHE.move_to_end(cache_key)
        while len(_COMPATIBILITY_CACHE) > _COMPATIBILITY_CACHE_MAX_ENTRIES:
            _COMPATIBILITY_CACHE.popitem(last=False)
    if strict and not compatible:
        raise Hades2RuntimeError(
            'hades2.error.unverifiedBuildWarning',
            warning,
            (str(version), str(build), str(uuid)),
        )
    return result


def _write_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _backup_dir(parent, prefix):
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')
    return Path(tempfile.mkdtemp(prefix=prefix + '-' + stamp, dir=parent))


def _records(backup_parent, game):
    for root in sorted(backup_parent.glob('signature-*'), reverse=True):
        try:
            record = json.loads((root / 'manifest.json').read_text())
        except (OSError, ValueError):
            continue
        if record.get('game') == str(game):
            yield root, record


def _verify_backup(root, record):
    original = root / GAME_EXECUTABLE_NAME
    expected_sha256 = record.get('original_sha256')
    expected_uuid = record.get('uuid')
    if not isinstance(expected_sha256, str) or sha(original) != expected_sha256:
        raise Hades2RuntimeError('hades2.error.backupCorrupt', '原始备份损坏或与记录不匹配；拒绝覆盖游戏。')
    if not isinstance(expected_uuid, str) or _uuid(original) != expected_uuid:
        raise Hades2RuntimeError('hades2.error.backupUUIDMismatch', '备份 UUID 不匹配。')
    return original


def _entitlements(exe):
    result = _command('/usr/bin/codesign', '-d', '--entitlements', ':-', str(exe))
    combined = result.stdout + result.stderr
    start = combined.find(b'<?xml')
    end = combined.find(b'</plist>', start)
    if start < 0 or end < 0:
        raise Hades2RuntimeError('hades2.error.permissionsUnreadable', '无法读取原始权限；未修改游戏。')
    return plistlib.loads(combined[start:end + len(b'</plist>')])


def _atomic_install(source, destination, expected_current, original_sha256=None, original_uuid=None, *, backup_parent):
    """Verify outside the app, then copy those bytes for same-volume replacement."""
    destination = Path(destination)
    backup_parent.mkdir(parents=True, exist_ok=True)
    expected_source = sha(source)
    # Even a renamed executable under .app/Contents/MacOS is interpreted by
    # codesign in bundle context. The original executable's signature must be
    # checked in a separate directory outside the app, where Info.plist and
    # unsealed bundle resources cannot affect standalone signature verification.
    with tempfile.TemporaryDirectory(prefix='verification-', dir=backup_parent) as directory:
        verified = Path(directory) / GAME_EXECUTABLE_NAME
        shutil.copy2(source, verified)
        if sha(verified) != expected_source:
            raise Hades2RuntimeError('hades2.error.verificationFailed', '独立验证副本校验失败；未修改游戏。')
        if original_sha256 is not None and expected_source == original_sha256:
            if _uuid(verified) != original_uuid:
                raise Hades2RuntimeError('hades2.error.restoreUUIDMismatch', '原始恢复副本 UUID 不匹配；未修改游戏。')
        elif expected_source == ORIGINAL_SHA256:
            # This exact local original fails standalone codesign verification
            # (Info.plist requirement), but its known hash and UUID establish
            # the restoration baseline. Do not generalize to other binaries.
            if _uuid(verified) != UUID:
                raise Hades2RuntimeError('hades2.error.restoreUUIDMismatch', '原始恢复副本 UUID 不匹配；未修改游戏。')
        else:
            run('/usr/bin/codesign', '--verify', '--strict', str(verified))
        fd, name = tempfile.mkstemp(prefix='.trainer-', dir=destination.parent)
        os.close(fd)
        staged = Path(name)
        try:
            shutil.copy2(verified, staged)
            if sha(staged) != expected_source:
                raise Hades2RuntimeError('hades2.error.stagedVerificationFailed', '暂存文件校验失败；未修改游戏。')
            # No codesign call here: only install bytes verified outside the app.
            with staged.open('rb') as stream:
                os.fsync(stream.fileno())
            _require_stopped()
            if sha(destination) != expected_current:
                raise Hades2RuntimeError('hades2.error.fileChangedDuringOperation', '游戏文件在操作期间改变；拒绝覆盖。')
            os.replace(staged, destination)
            invalidate_compatibility_cache()
        finally:
            staged.unlink(missing_ok=True)


def _prepared_hashes(record):
    return {value for key in ('prepared_sha256', 'previous_prepared_sha256') if isinstance((value := record.get(key)), str) and value}


def _stage_prepared(root, record, original, previous_prepared_sha256=None):
    permissions = _entitlements(original)
    (root / 'original-entitlements.plist').write_bytes(plistlib.dumps(permissions))
    permissions['com.apple.security.get-task-allow'] = True
    permissions['com.apple.security.cs.disable-library-validation'] = True
    entitlement_path = root / 'debug-entitlements.plist'
    entitlement_path.write_bytes(plistlib.dumps(permissions))

    staged = root / (GAME_EXECUTABLE_NAME + '.debug')
    shutil.copy2(original, staged)
    run('/usr/bin/codesign', '--force', '--sign', '-', '--identifier',
        BUNDLE_IDENTIFIER, '--options', 'runtime',
        '--entitlements', str(entitlement_path), str(staged))
    run('/usr/bin/codesign', '--verify', '--strict', str(staged))
    prepared_entitlements = _entitlements(staged)
    if (_uuid(staged) != record.get('uuid') or not prepared_entitlements.get('com.apple.security.get-task-allow')
            or not prepared_entitlements.get('com.apple.security.cs.disable-library-validation')):
        raise Hades2RuntimeError('hades2.error.signingVerificationFailed', '调试签名校验失败；未修改游戏。')
    record.update(status='staged', prepared_sha256=sha(staged))
    if previous_prepared_sha256: record['previous_prepared_sha256'] = previous_prepared_sha256
    else: record.pop('previous_prepared_sha256', None)
    _write_json(root / 'manifest.json', record)
    return staged


def _resolve_backup_parent(data_dir=None):
    resolved = trainer_data_directory('hades2') if data_dir is None else Path(data_dir)
    migrate_legacy_root_data_dir(resolved)
    return resolved / 'backups'


def prepare(data_dir=None):
    backup_parent = _resolve_backup_parent(data_dir)
    _require_stopped()
    game, exe, _steam = resolve_paths(query_running=False)
    identity = compatibility(query_running=False)
    current = sha(exe)

    for root, record in _records(backup_parent, game):
        if current not in _prepared_hashes(record):
            continue
        original = _verify_backup(root, record)
        prepared_entitlements = _entitlements(exe)
        if not prepared_entitlements.get('com.apple.security.get-task-allow'):
            raise Hades2RuntimeError('hades2.error.missingDebugPermission', '已准备文件缺少调试权限。')
        if prepared_entitlements.get('com.apple.security.cs.disable-library-validation'):
            if record.pop('previous_prepared_sha256', None) is not None or record.get('status') != 'prepared':
                record['status'] = 'prepared'
                _write_json(root / 'manifest.json', record)
            return {'prepared': True, 'already_prepared': True, 'backup': str(root), 'manifest': record}

        staged = _stage_prepared(root, record, original, previous_prepared_sha256=current)
        _atomic_install(staged, exe, current, backup_parent=backup_parent)
        record.pop('previous_prepared_sha256', None)
        record['status'] = 'prepared'
        _write_json(root / 'manifest.json', record)
        return {'prepared': True, 'already_prepared': False, 'upgraded': True, 'backup': str(root), 'manifest': record}

    if _entitlements(exe).get('com.apple.security.get-task-allow'):
        raise Hades2RuntimeError('hades2.error.noMatchingBackup', '当前可执行文件已带调试权限，但没有匹配的原始备份；拒绝覆盖。')
    bundle_signature = _command('/usr/bin/codesign', '--verify', '--strict', str(game), allowed=(0, 1))

    root = _backup_dir(backup_parent, 'signature')
    original = root / GAME_EXECUTABLE_NAME
    shutil.copy2(exe, original)
    record = dict(identity, original_sha256=current, status='backed_up')
    _verify_backup(root, record)
    baseline = _command('/usr/bin/codesign', '--verify', '--strict', str(original), allowed=(0, 1))
    record['original_signature_baseline'] = {
        'bundle_returncode': bundle_signature.returncode,
        'bundle_stderr': bundle_signature.stderr.decode('utf-8', errors='replace'),
        'returncode': baseline.returncode, 'strict_valid': baseline.returncode == 0,
        'stdout': baseline.stdout.decode('utf-8', errors='replace'),
        'stderr': baseline.stderr.decode('utf-8', errors='replace'),
        'scope': 'Signature verification is diagnostic; exact executable SHA-256 and UUID are retained for restore',
    }
    details = _command('/usr/bin/codesign', '-dvvv', str(exe))
    (root / 'original-signature.txt').write_bytes(details.stdout + details.stderr)
    _write_json(root / 'manifest.json', record)

    staged = _stage_prepared(root, record, original)
    _atomic_install(staged, exe, current, backup_parent=backup_parent)
    record['status'] = 'prepared'
    _write_json(root / 'manifest.json', record)
    return {'prepared': True, 'already_prepared': False, 'backup': str(root), 'manifest': record}


def restore(data_dir=None):
    backup_parent = _resolve_backup_parent(data_dir)
    _require_stopped()
    game, exe, _steam = resolve_paths(query_running=False)
    compatibility(query_running=False)
    current = sha(exe)
    for root, record in _records(backup_parent, game):
        if current == record.get('original_sha256'):
            return {'restored': True, 'already_restored': True}
        if current not in _prepared_hashes(record):
            continue
        original = _verify_backup(root, record)
        _atomic_install(original, exe, current, record['original_sha256'], record['uuid'], backup_parent=backup_parent)
        record.pop('previous_prepared_sha256', None)
        record['status'] = 'restored'
        _write_json(root / 'manifest.json', record)
        return {'restored': True, 'already_restored': False, 'backup': str(root)}
    raise Hades2RuntimeError(
        'hades2.error.noOriginalBackup',
        '没有与当前文件匹配的原始签名备份；游戏可能已更新，拒绝覆盖。',
    )


def official_display_names(*args, **kwargs):
    from .localization import official_display_names as implementation
    if len(args) < 3 and 'game_path' not in kwargs:
        kwargs['game_path'] = resolve_paths()[0]
    return implementation(*args, **kwargs)

if __name__ == '__main__':
    import sys
    try:
        commands = {'prepare': prepare, 'restore': restore, 'compatibility': compatibility}
        result = commands[sys.argv[1] if len(sys.argv) > 1 else 'prepare']()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
