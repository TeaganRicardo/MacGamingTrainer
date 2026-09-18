from pathlib import Path
import tempfile
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import preparation, save_service, localization
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService

base = Path(tempfile.mkdtemp(prefix='mgt-r16-services-'))
preparation.DATA = base/'data'
preparation.SAVES = base/'saves'
preparation.SAVES.mkdir(parents=True)
(preparation.SAVES/'Profile1.sav').write_bytes(b'one')
preparation._require_stopped = lambda: None

# New code reaches the dedicated service directly; preparation facades are only
# backwards compatibility shims.
backup = save_service.backup_saves(run_count=7, allow_running=True)
assert backup['backed_up'] and backup['runCount'] == 7
assert save_service.list_save_backups()[0]['id'] == backup['backupId']
assert 'def backup_saves' in (root/'Backend/games/hades2/save_service.py').read_text()
assert 'def backup_saves(*args, **kwargs)' in (root/'Backend/games/hades2/preparation.py').read_text()

# Localization no longer depends on signature/save preparation state.
game = base/'Game.app'
text = game/'Contents/Resources/Content/Game/Text/en/TraitText.sjson'
text.parent.mkdir(parents=True)
text.write_text('{ Id = "TraitX"\n DisplayName = "Trait X"\n }', encoding='utf-8')
localization._OFFICIAL_TEXT_CACHE.clear()
assert localization.official_display_names({'TraitX'}, 'en', game_path=game) == {'TraitX':'Trait X'}

# Preference/profile services are usable without constructing a transport adapter.
store = Hades2PreferenceStore(base/'desired.json')
prefs = store.defaults(); prefs['godMode'] = True; store.save(prefs)
loaded, initialized = store.load()
assert initialized and loaded['godMode'] is True
profiles = Hades2ProfileService(base/'profiles')
profiles.save('test', loaded, {'godMode':1})
assert profiles.load('test')['desired']['godMode'] is True
assert profiles.delete('test')['deleted'] is True

print('hades2_services_round16_ok')
