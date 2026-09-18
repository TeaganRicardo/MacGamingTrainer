"""Hades II executable/save preparation. Version-bound and recoverable."""
from pathlib import Path
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import time

from .config import GAME_SPEC, STEAM_SPEC, DATA

GAME = GAME_SPEC.app_path
SAVES = GAME_SPEC.save_path
VERSION = '139672'
STEAM_BUILD = '24556151'
UUID = '6DFB0A36-6249-319F-8E18-5FC94898925A'
ORIGINAL_SHA256 = 'bf77da0b5aec6a6a24d1b9a08c8593227c95ec431c19600b2d93b4cb347d08f4'
TIMEOUT = 30


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _command(*args, allowed=(0,)):
    try:
        result = subprocess.run(args, capture_output=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f'{args[0]} 超时（{TIMEOUT} 秒）；操作结果需重新检查。') from error
    except OSError as error:
        raise RuntimeError(f'无法运行 {args[0]}：{error}') from error
    if result.returncode not in allowed:
        detail = (result.stderr or result.stdout).decode('utf-8', errors='replace')[-3000:].strip()
        raise RuntimeError(f'{args[0]} 失败（{result.returncode}）：{detail}')
    return result


def run(*args):
    return _command(*args).stdout


def _require_stopped():
    if _command('/usr/bin/pgrep', '-x', GAME_SPEC.process_name, allowed=(0, 1)).returncode == 0:
        raise RuntimeError(f'请先退出 {GAME_SPEC.display_name}；运行中不能修改签名或恢复存档。')


def _uuid(exe):
    result = run('/usr/bin/xcrun', 'dwarfdump', '--uuid', str(exe)).decode()
    architecture = GAME_SPEC.minimum_architecture
    pattern = r'UUID: ([A-Fa-f0-9-]+) \(' + re.escape(architecture) + r'\)' if architecture else r'UUID: ([A-Fa-f0-9-]+) \([^)]*\)'
    match = re.search(pattern, result)
    if not match:
        suffix = f'（{architecture}）' if architecture else ''
        raise RuntimeError('找不到匹配架构的 Mach-O UUID' + suffix + '。')
    return match.group(1).upper()


def compatibility(strict=True):
    """Report version drift for scanning; mutations retain the strict default."""
    info = plistlib.loads((GAME / 'Contents/Info.plist').read_bytes())
    version = info.get('CFBundleVersion')
    steam = STEAM_SPEC.manifest_path
    match = re.search(r'"buildid"\s+"([0-9]+)"', steam.read_text())
    build = match.group(1) if match else None
    uuid = _uuid(GAME_SPEC.executable_path)
    compatible = version == VERSION and build == STEAM_BUILD and uuid == UUID
    warning = f'未经验证的游戏版本：version={version}, build={build}, UUID={uuid}。'
    if strict and not compatible:
        raise RuntimeError(warning)
    return {'version': version, 'steam_build': build, 'uuid': uuid, 'game': str(GAME),
            'compatible': compatible, 'warnings': [] if compatible else [warning]}


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


def _backup_dir(prefix):
    parent = DATA / 'backups'
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')
    return Path(tempfile.mkdtemp(prefix=prefix + '-' + stamp, dir=parent))


def _records():
    for root in sorted((DATA / 'backups').glob('signature-*'), reverse=True):
        try:
            record = json.loads((root / 'manifest.json').read_text())
        except (OSError, ValueError):
            continue
        if record.get('game') == str(GAME) and record.get('version') == VERSION:
            yield root, record


def _verify_backup(root, record):
    original = root / GAME_SPEC.executable_name
    if record.get('original_sha256') != ORIGINAL_SHA256 or sha(original) != ORIGINAL_SHA256:
        raise RuntimeError('原始备份损坏或不属于已验证版本；拒绝覆盖游戏。')
    if _uuid(original) != UUID:
        raise RuntimeError('备份 UUID 不匹配。')
    return original


def _entitlements(exe):
    result = _command('/usr/bin/codesign', '-d', '--entitlements', ':-', str(exe))
    combined = result.stdout + result.stderr
    start = combined.find(b'<?xml')
    end = combined.find(b'</plist>', start)
    if start < 0 or end < 0:
        raise RuntimeError('无法读取原始权限；未修改游戏。')
    return plistlib.loads(combined[start:end + len(b'</plist>')])


def _atomic_install(source, destination, expected_current):
    """Verify outside the app, then copy those bytes for same-volume replacement."""
    destination = Path(destination)
    backup_parent = DATA / 'backups'
    backup_parent.mkdir(parents=True, exist_ok=True)
    expected_source = sha(source)
    # Even a renamed executable under .app/Contents/MacOS is interpreted by
    # codesign in bundle context. The original executable's signature must be
    # checked in a separate directory outside the app, where Info.plist and
    # unsealed bundle resources cannot affect standalone signature verification.
    with tempfile.TemporaryDirectory(prefix='verification-', dir=backup_parent) as directory:
        verified = Path(directory) / GAME_SPEC.executable_name
        shutil.copy2(source, verified)
        if sha(verified) != expected_source:
            raise RuntimeError('独立验证副本校验失败；未修改游戏。')
        if expected_source == ORIGINAL_SHA256:
            # This exact local original fails standalone codesign verification
            # (Info.plist requirement), but its known hash and UUID establish
            # the restoration baseline. Do not generalize to other binaries.
            if _uuid(verified) != UUID:
                raise RuntimeError('原始恢复副本 UUID 不匹配；未修改游戏。')
        else:
            run('/usr/bin/codesign', '--verify', '--strict', str(verified))
        fd, name = tempfile.mkstemp(prefix='.trainer-', dir=destination.parent)
        os.close(fd)
        staged = Path(name)
        try:
            shutil.copy2(verified, staged)
            if sha(staged) != expected_source:
                raise RuntimeError('暂存文件校验失败；未修改游戏。')
            # No codesign call here: only install bytes verified outside the app.
            with staged.open('rb') as stream:
                os.fsync(stream.fileno())
            _require_stopped()
            if sha(destination) != expected_current:
                raise RuntimeError('游戏文件在操作期间改变；拒绝覆盖。')
            os.replace(staged, destination)
        finally:
            staged.unlink(missing_ok=True)


def prepare():
    _require_stopped()
    identity = compatibility()
    exe = GAME_SPEC.executable_path
    current = sha(exe)
    for root, record in _records():
        if current == record.get('prepared_sha256'):
            _verify_backup(root, record)
            if not _entitlements(exe).get('com.apple.security.get-task-allow'):
                raise RuntimeError('已准备文件缺少调试权限。')
            return {'prepared': True, 'already_prepared': True, 'backup': str(root), 'manifest': record}
    if _entitlements(exe).get('com.apple.security.get-task-allow') or current != ORIGINAL_SHA256:
        raise RuntimeError('当前可执行文件不是已验证的原版；拒绝将已修改文件备份为原版。')
    root = _backup_dir('signature')
    original = root / GAME_SPEC.executable_name
    shutil.copy2(exe, original)
    record = dict(identity, original_sha256=current, status='backed_up')
    _verify_backup(root, record)
    baseline = _command('/usr/bin/codesign', '--verify', '--strict', str(original), allowed=(0, 1))
    record['original_signature_baseline'] = {
        'returncode': baseline.returncode, 'strict_valid': baseline.returncode == 0,
        'stdout': baseline.stdout.decode('utf-8', errors='replace'),
        'stderr': baseline.stderr.decode('utf-8', errors='replace'),
        'scope': 'Exact locally verified original SHA-256 and UUID only',
    }
    permissions = _entitlements(exe)
    (root / 'original-entitlements.plist').write_bytes(plistlib.dumps(permissions))
    details = _command('/usr/bin/codesign', '-dvvv', str(exe))
    (root / 'original-signature.txt').write_bytes(details.stdout + details.stderr)
    _write_json(root / 'manifest.json', record)
    permissions['com.apple.security.get-task-allow'] = True
    entitlement_path = root / 'debug-entitlements.plist'
    entitlement_path.write_bytes(plistlib.dumps(permissions))
    staged = root / (GAME_SPEC.executable_name + '.debug')
    shutil.copy2(original, staged)
    run('/usr/bin/codesign', '--force', '--sign', '-', '--identifier',
        GAME_SPEC.bundle_identifier, '--options', 'runtime',
        '--entitlements', str(entitlement_path), str(staged))
    run('/usr/bin/codesign', '--verify', '--strict', str(staged))
    if _uuid(staged) != UUID or not _entitlements(staged).get('com.apple.security.get-task-allow'):
        raise RuntimeError('调试签名校验失败；未修改游戏。')
    # Record the prepared hash before installation so a crash remains recoverable.
    record.update(status='staged', prepared_sha256=sha(staged))
    _write_json(root / 'manifest.json', record)
    _atomic_install(staged, exe, current)
    record['status'] = 'prepared'
    _write_json(root / 'manifest.json', record)
    return {'prepared': True, 'already_prepared': False, 'backup': str(root), 'manifest': record}


def restore():
    _require_stopped()
    compatibility()
    exe = GAME_SPEC.executable_path
    current = sha(exe)
    if current == ORIGINAL_SHA256:
        return {'restored': True, 'already_restored': True}
    for root, record in _records():
        if current != record.get('prepared_sha256'):
            continue
        original = _verify_backup(root, record)
        _atomic_install(original, exe, current)
        record['status'] = 'restored'
        _write_json(root / 'manifest.json', record)
        return {'restored': True, 'already_restored': False, 'backup': str(root)}
    raise RuntimeError('没有与当前文件匹配的原始签名备份；游戏可能已更新，拒绝覆盖。')


# Compatibility facades retained for callers from pre-v0.16 releases. New code
# imports save_service/localization directly.
def backup_saves(*args, **kwargs):
    from .save_service import backup_saves as implementation
    return implementation(*args, **kwargs)

def list_save_backups(*args, **kwargs):
    from .save_service import list_save_backups as implementation
    return implementation(*args, **kwargs)

def rename_save_backup(*args, **kwargs):
    from .save_service import rename_save_backup as implementation
    return implementation(*args, **kwargs)

def delete_save_backup(*args, **kwargs):
    from .save_service import delete_save_backup as implementation
    return implementation(*args, **kwargs)

def save_backup_folder(*args, **kwargs):
    from .save_service import save_backup_folder as implementation
    return implementation(*args, **kwargs)

def staged_restore(*args, **kwargs):
    from .save_service import staged_restore as implementation
    return implementation(*args, **kwargs)

def stage_restore(*args, **kwargs):
    from .save_service import stage_restore as implementation
    return implementation(*args, **kwargs)

def cancel_staged_restore(*args, **kwargs):
    from .save_service import cancel_staged_restore as implementation
    return implementation(*args, **kwargs)

def apply_staged_restore(*args, **kwargs):
    from .save_service import apply_staged_restore as implementation
    return implementation(*args, **kwargs)

def restore_saves(*args, **kwargs):
    from .save_service import restore_saves as implementation
    return implementation(*args, **kwargs)

from .localization import _OFFICIAL_TEXT_CACHE

def official_display_names(*args, **kwargs):
    from .localization import official_display_names as implementation
    kwargs.setdefault('game_path', GAME)
    return implementation(*args, **kwargs)

if __name__ == '__main__':
    import sys
    try:
        commands = {'prepare': prepare, 'restore': restore, 'backup_saves': backup_saves, 'compatibility': compatibility, 'list_save_backups': list_save_backups}
        result = commands[sys.argv[1] if len(sys.argv) > 1 else 'prepare']()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
