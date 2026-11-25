import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

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

replacement = base/'ReplacementGame.app'
replacement_text = replacement/'Contents/Resources/Content/Game/Text/zh-CN/RewardText.zh-CN.sjson'
replacement_text.parent.mkdir(parents=True)
replacement_text.write_text('{ Id = "WeaponUpgrade"\n DisplayName = "替换目录名称"\n }', encoding='utf-8')
localization.invalidate_display_names()
with patch('games.hades2.preparation.resolve_paths', side_effect=[(game, None, None), (replacement, None, None)]) as resolve:
    assert localization.official_display_names({'WeaponUpgrade'}, 'zh-CN') == {'WeaponUpgrade': '月神之锤'}
    shutil.rmtree(game)
    assert localization.official_display_names({'WeaponUpgrade'}, 'zh-CN') == {'WeaponUpgrade': '替换目录名称'}
    assert resolve.call_count == 2
    assert key not in localization._OFFICIAL_TEXT_CACHE
with patch('games.hades2.preparation.resolve_paths', side_effect=AssertionError('explicit path must not resolve')):
    assert localization.official_display_names({'WeaponUpgrade'}, 'zh-CN', game_path=replacement) == {
        'WeaponUpgrade': '替换目录名称'
    }

print('localization_cache_recovery_v0180_ok')
