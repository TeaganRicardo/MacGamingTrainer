"""Hades II executable/save preparation. Build-agnostic and recoverable."""
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

from .config import DATA, GAME_SPEC, STEAM_SPEC
from .operation_budgets import SUBPROCESS_TIMEOUT_SECONDS

GAME = GAME_SPEC.app_path
SAVES = GAME_SPEC.save_path
VERSION = '143476'
DISPLAY_VERSION = '1.' + VERSION
STEAM_BUILD = '25481925'
UUID = '35CD2E50-2D78-3A63-835B-3EB1224C6D65'
ORIGINAL_SHA256 = '933a2db2251a3fddd70900016f323338690235c7b3aae63edd4a78ca18c3bfe3'
TIMEOUT = SUBPROCESS_TIMEOUT_SECONDS


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


def compatibility(strict=False):
    """Report version drift without blocking supported operations by default."""
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
        if record.get('game') == str(GAME):
            yield root, record


def _verify_backup(root, record):
    original = root / GAME_SPEC.executable_name
    expected_sha256 = record.get('original_sha256')
    expected_uuid = record.get('uuid')
    if not isinstance(expected_sha256, str) or sha(original) != expected_sha256:
        raise RuntimeError('原始备份损坏或与记录不匹配；拒绝覆盖游戏。')
    if not isinstance(expected_uuid, str) or _uuid(original) != expected_uuid:
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


def _atomic_install(source, destination, expected_current, original_sha256=None, original_uuid=None):
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
        if original_sha256 is not None and expected_source == original_sha256:
            if _uuid(verified) != original_uuid:
                raise RuntimeError('原始恢复副本 UUID 不匹配；未修改游戏。')
        elif expected_source == ORIGINAL_SHA256:
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


def _prepared_hashes(record):
    return {value for key in ('prepared_sha256', 'previous_prepared_sha256') if isinstance((value := record.get(key)), str) and value}


def _stage_prepared(root, record, original, previous_prepared_sha256=None):
    permissions = _entitlements(original)
    (root / 'original-entitlements.plist').write_bytes(plistlib.dumps(permissions))
    permissions['com.apple.security.get-task-allow'] = True
    permissions['com.apple.security.cs.disable-library-validation'] = True
    entitlement_path = root / 'debug-entitlements.plist'
    entitlement_path.write_bytes(plistlib.dumps(permissions))

    staged = root / (GAME_SPEC.executable_name + '.debug')
    shutil.copy2(original, staged)
    run('/usr/bin/codesign', '--force', '--sign', '-', '--identifier',
        GAME_SPEC.bundle_identifier, '--options', 'runtime',
        '--entitlements', str(entitlement_path), str(staged))
    run('/usr/bin/codesign', '--verify', '--strict', str(staged))
    prepared_entitlements = _entitlements(staged)
    if (_uuid(staged) != record.get('uuid') or not prepared_entitlements.get('com.apple.security.get-task-allow')
            or not prepared_entitlements.get('com.apple.security.cs.disable-library-validation')):
        raise RuntimeError('调试签名校验失败；未修改游戏。')
    record.update(status='staged', prepared_sha256=sha(staged))
    if previous_prepared_sha256: record['previous_prepared_sha256'] = previous_prepared_sha256
    else: record.pop('previous_prepared_sha256', None)
    _write_json(root / 'manifest.json', record)
    return staged


def prepare():
    _require_stopped()
    identity = compatibility()
    exe = GAME_SPEC.executable_path
    current = sha(exe)

    for root, record in _records():
        if current not in _prepared_hashes(record):
            continue
        original = _verify_backup(root, record)
        prepared_entitlements = _entitlements(exe)
        if not prepared_entitlements.get('com.apple.security.get-task-allow'):
            raise RuntimeError('已准备文件缺少调试权限。')
        if prepared_entitlements.get('com.apple.security.cs.disable-library-validation'):
            if record.pop('previous_prepared_sha256', None) is not None or record.get('status') != 'prepared':
                record['status'] = 'prepared'
                _write_json(root / 'manifest.json', record)
            return {'prepared': True, 'already_prepared': True, 'backup': str(root), 'manifest': record}

        staged = _stage_prepared(root, record, original, previous_prepared_sha256=current)
        _atomic_install(staged, exe, current)
        record.pop('previous_prepared_sha256', None)
        record['status'] = 'prepared'
        _write_json(root / 'manifest.json', record)
        return {'prepared': True, 'already_prepared': False, 'upgraded': True, 'backup': str(root), 'manifest': record}

    if _entitlements(exe).get('com.apple.security.get-task-allow'):
        raise RuntimeError('当前可执行文件已带调试权限，但没有匹配的原始备份；拒绝覆盖。')
    bundle_signature = _command('/usr/bin/codesign', '--verify', '--strict', str(GAME), allowed=(0, 1))

    root = _backup_dir('signature')
    original = root / GAME_SPEC.executable_name
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
    _atomic_install(staged, exe, current)
    record['status'] = 'prepared'
    _write_json(root / 'manifest.json', record)
    return {'prepared': True, 'already_prepared': False, 'backup': str(root), 'manifest': record}

def restore():
    _require_stopped()
    compatibility()
    exe = GAME_SPEC.executable_path
    current = sha(exe)
    for root, record in _records():
        if current == record.get('original_sha256'):
            return {'restored': True, 'already_restored': True}
        if current not in _prepared_hashes(record):
            continue
        original = _verify_backup(root, record)
        _atomic_install(original, exe, current, record['original_sha256'], record['uuid'])
        record.pop('previous_prepared_sha256', None)
        record['status'] = 'restored'
        _write_json(root / 'manifest.json', record)
        return {'restored': True, 'already_restored': False, 'backup': str(root)}
    raise RuntimeError('没有与当前文件匹配的原始签名备份；游戏可能已更新，拒绝覆盖。')



def official_display_names(*args, **kwargs):
    from .localization import official_display_names as implementation
    kwargs.setdefault('game_path', GAME)
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
