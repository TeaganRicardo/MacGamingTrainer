from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'Backend'))

from games.hades2 import localization

base = Path(tempfile.mkdtemp(prefix='mgt-localization-cache-v0180-'))
game = base/'LateGame.app'
key = (str(game), 'zh-CN')

localization._OFFICIAL_TEXT_CACHE.clear()
assert localization.official_display_names({'WeaponUpgrade'}, 'zh-CN', game_path=game) == {}
assert key not in localization._OFFICIAL_TEXT_CACHE

text = game/'Contents/Resources/Content/Game/Text/zh-CN/RewardText.zh-CN.sjson'
text.parent.mkdir(parents=True)
text.write_text('{ Id = "WeaponUpgrade"\n DisplayName = "月神之锤"\n }', encoding='utf-8')

assert localization.official_display_names({'WeaponUpgrade'}, 'zh-CN', game_path=game) == {
    'WeaponUpgrade': '月神之锤'
}
assert localization._OFFICIAL_TEXT_CACHE[key]['WeaponUpgrade'] == '月神之锤'

print('localization_cache_recovery_v0180_ok')
