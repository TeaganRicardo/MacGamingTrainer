from pathlib import Path
import tempfile
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import localization
from games.hades2.preferences import Hades2PreferenceStore
from games.hades2.profile_service import Hades2ProfileService

base = Path(tempfile.mkdtemp(prefix='mgt-r16-services-'))

# Localization no longer depends on signature/save preparation state.
game = base/'Game.app'
text = game/'Contents/Resources/Content/Game/Text/en/TraitText.sjson'
text.parent.mkdir(parents=True)
text.write_text('{ Id = "TraitX"\n DisplayName = "Trait X"\n }', encoding='utf-8')
localization._OFFICIAL_TEXT_CACHE.clear()
assert localization.official_display_names({'TraitX'}, 'en', game_path=game) == {'TraitX':'Trait X'}

# Language-directory layouts remain supported without save/preparation coupling.
dir_game = base/'DirGame.app'
dir_text = dir_game/'Contents/Resources/Game/Text/zh-CN/TraitText.sjson'
dir_text.parent.mkdir(parents=True)
dir_text.write_text('{ Id = "TraitY"\n DisplayName = "目录布局"\n }', encoding='utf-8')
localization._OFFICIAL_TEXT_CACHE.clear()
assert localization.official_display_names({'TraitY'}, 'zh-CN', game_path=dir_game) == {'TraitY':'目录布局'}

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
