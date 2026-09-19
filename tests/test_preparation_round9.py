from pathlib import Path
import tempfile, json, sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))
from games.hades2 import preparation as prep
base=Path(tempfile.mkdtemp(prefix='trainer-prep-round8-'))
prep.DATA=base/'data'
prep.SAVES=base/'saves'
prep.SAVES.mkdir(parents=True)
(prep.SAVES/'Profile1.sav').write_bytes(b'profile-v1')
(prep.SAVES/'saveinfo').write_bytes(b'info-v1')

stopped_calls=[]
prep._require_stopped=lambda:stopped_calls.append(True)
info=prep.backup_saves(run_count=42,allow_running=True)
assert info['backed_up'] and info['runCount']==42 and info['hotBackup'] is True
assert 'Run 42' in info['name'] and len(info['name'].split(' · Run ')[0])==19,info['name']
assert stopped_calls==[], 'hot backup unexpectedly required stopped game'
manifest=json.loads((Path(info['backup'])/'trainer-backup-manifest.json').read_text())
assert manifest['runCount']==42 and manifest['displayName']==info['name'] and manifest['hotBackup'] is True
rows=prep.list_save_backups()
row=next(x for x in rows if x['id']==info['backupId'])
assert row['valid'] and row['name']==info['name'] and row['runCount']==42 and row['hotBackup']

# Rename changes display metadata only; the physical/stable backup ID remains unchanged.
renamed=prep.rename_save_backup(info['backupId'],'赫卡忒前 · Run 42')
assert renamed['backupId']==info['backupId'] and renamed['name']=='赫卡忒前 · Run 42'
row=next(x for x in prep.list_save_backups() if x['id']==info['backupId'])
assert row['id']==info['backupId'] and row['name']=='赫卡忒前 · Run 42'
assert Path(prep.save_backup_folder(info['backupId'])).name==info['backupId']
assert Path(prep.save_backup_folder()).name=='backups'
# Backup deletion is constrained to trainer-created saves-* directories.
delete_id=info['backupId']
assert Path(prep.save_backup_folder(delete_id)).exists()
deleted=prep.delete_save_backup(delete_id)
assert deleted['deleted'] and deleted['backupId']==delete_id and not (prep.DATA/'backups'/delete_id).exists()
for invalid in ('../saves-test','saves-../../evil','/tmp/saves-test','signature-test'):
    try:prep.save_backup_folder(invalid)
    except (ValueError,RuntimeError):pass
    else:raise AssertionError('unsafe backup id accepted: '+invalid)
try:prep.rename_save_backup(info['backupId'],'bad/name')
except ValueError:pass
else:raise AssertionError('unsafe display name accepted')

# A running-game write overlapping the first copy must discard that attempt and retry.
prep.DATA=base/'retry-data'
prep.SAVES=base/'retry-saves'
prep.SAVES.mkdir(parents=True)
source=prep.SAVES/'Profile1.sav'
source.write_bytes(b'before')
original_sha=prep.sha
source_sha_calls=0
def racing_sha(path):
    global source_sha_calls
    path=Path(path)
    if path==source:
        source_sha_calls += 1
        if source_sha_calls==2: # post-copy source verification on the first attempt
            source.write_bytes(b'after')
    return original_sha(path)
prep.sha=racing_sha
retry=prep.backup_saves(run_count=43,allow_running=True)
assert retry['backed_up'] and (Path(retry['backup'])/'Profile1.sav').read_bytes()==b'after'
assert source_sha_calls>=4,source_sha_calls
assert len(list((prep.DATA/'backups').glob('saves-*')))==1,'failed hot snapshot attempt was not cleaned up'

# Official localization loader reads the installed-style SJSON records directly.
text_game=base/'Hades II.app'
text_dir=text_game/'Contents/Resources/Content/Game/Text/zh-CN'
text_dir.mkdir(parents=True)
(text_dir/'TraitText.zh-CN.sjson').write_text('''\n{\n Id = "SupportingFireBoon"\n DisplayName = "支援火力"\n Description = "x"\n}\n{\n Id = "AnotherTrait"\n DisplayName = "另一个祝福"\n}\n''',encoding='utf-8')
en_dir=text_game/'Contents/Resources/Content/Game/Text/en'
en_dir.mkdir(parents=True)
(en_dir/'TraitText.en.sjson').write_text('''\n{\n Id = "SupportingFireBoon"\n DisplayName = "Support Fire"\n}\n''',encoding='utf-8')
prep.GAME=text_game
prep._OFFICIAL_TEXT_CACHE.clear()
assert prep.official_display_names({'SupportingFireBoon','Missing'},'zh-CN')=={'SupportingFireBoon':'支援火力'}
assert prep.official_display_names({'SupportingFireBoon'},'en')=={'SupportingFireBoon':'Support Fire'}

# Also support language-directory layouts where the filename itself has no
# locale suffix. This prevents a valid installed localization from being
# mistaken for missing text after a bundle layout change.
dir_game=base/'Hades II dir-layout.app'
dir_zh=dir_game/'Contents/Resources/Game/Text/zh-CN'
dir_zh.mkdir(parents=True)
(dir_zh/'TraitText.sjson').write_text('''
{
 Id = "SupportingFireBoon"
 DisplayName = "支援火力（目录布局）"
}
''',encoding='utf-8')
prep.GAME=dir_game
prep._OFFICIAL_TEXT_CACHE.clear()
assert prep.official_display_names({'SupportingFireBoon'},'zh-CN')=={'SupportingFireBoon':'支援火力（目录布局）'}

print('preparation_round8_ok')

# Staged restore is metadata-only while the game is live; applying it later uses
# the existing verified restore path and removes the marker only after success.
base2=Path(tempfile.mkdtemp(prefix='trainer-prep-stage-r9-'))
prep.DATA=base2/'data';prep.SAVES=base2/'saves';prep.SAVES.mkdir(parents=True)
(prep.SAVES/'Profile1.sav').write_bytes(b'original-good')
prep._require_stopped=lambda:None
snapshot=prep.backup_saves(run_count=50,allow_running=True)
(prep.SAVES/'Profile1.sav').write_bytes(b'current-bad')
staged=prep.stage_restore(snapshot['backupId'],run_count=51)
assert staged['staged'] and staged['status']=='staged_until_exit'
assert prep.staged_restore()['backupId']==snapshot['backupId']
# No disk restore happened at staging time.
assert (prep.SAVES/'Profile1.sav').read_bytes()==b'current-bad'
applied=prep.apply_staged_restore()
assert applied['stagedApplied'] and prep.staged_restore() is None
assert (prep.SAVES/'Profile1.sav').read_bytes()==b'original-good'

# Cancellation is idempotent and never touches the actual save tree.
other=next(row for row in prep.list_save_backups() if row['valid'])
prep.stage_restore(other['id'],run_count=52)
assert prep.cancel_staged_restore()['cancelled'] is True
assert prep.cancel_staged_restore()['cancelled'] is False

# A corrupted transaction marker is not save data. It must be quarantined so
# every future scan does not fail forever on an impossible pending restore.
marker = prep.DATA/'staged-restore.json'
marker.write_text('{ broken json', encoding='utf-8')
assert prep.staged_restore() is None
assert not marker.exists()
assert len(list(prep.DATA.glob('staged-restore.json.corrupt-*'))) == 1

# Invalid transaction metadata is handled the same way.
marker.write_text(json.dumps({
    'backupId': other['id'],
    'runCount': -1,
    'stagedAt': '2026-09-19T00:00:00+00:00',
}), encoding='utf-8')
assert prep.staged_restore() is None
assert not marker.exists()
assert len(list(prep.DATA.glob('staged-restore.json.corrupt-*'))) == 2

print('preparation_round9_staged_ok')
