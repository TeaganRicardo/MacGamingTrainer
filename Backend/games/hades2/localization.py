"""Installed Hades II localization lookup.

Only text/resource discovery belongs here; trainer preparation and save restore
do not depend on localization.
"""
from pathlib import Path
import re

from .config import GAME_SPEC

_OFFICIAL_TEXT_CACHE = {}

def _sjson_unescape(value):
    return (value.replace(r'\\"', '"').replace(r'\\n', '\n')
                 .replace(r'\\r', '\r').replace(r'\\t', '\t').replace(r'\\\\', '\\'))

_MARKUP_TOKEN = re.compile(r'\{#[A-Za-z0-9_]+\}|[（(]\s*#[A-Za-z0-9_]+\s*[)）]|(?<!\w)#[A-Za-z][A-Za-z0-9_]*(?!\w)')
_BRACE_MARKUP = re.compile(r'\{[^{}]*\}')

def _clean_display_name(value):
    value = _sjson_unescape(value)
    # DisplayName strings are presentation labels, not dialogue templates.
    # Any brace-delimited control/format token is unrenderable in the trainer
    # and should never leak into picker labels (e.g. {#Emph}, {#Echo}).
    previous=None
    while previous!=value:
        previous=value
        value=_BRACE_MARKUP.sub('',value)
    value = _MARKUP_TOKEN.sub('', value)
    value = value.replace('{','').replace('}','')
    value = re.sub(r'\s{2,}', ' ', value)
    value = re.sub(r'\s+([,，。.!！?？:：;；])', r'\1', value)
    value = re.sub(r'\s*·\s*', ' · ', value)
    return value.strip(' \t\r\n·')

def _load_official_display_names(language, game_path=None):
    language = str(language)
    game = Path(game_path) if game_path is not None else GAME_SPEC.app_path
    cache_key = (str(game), language)
    cached = _OFFICIAL_TEXT_CACHE.get(cache_key)
    if cached is not None:
        return cached
    names = {}
    if not game.exists():
        return names
    roots = [
        game / 'Contents/Resources/Content/Game/Text',
        game / 'Contents/Resources/Game/Text',
        game / 'Contents/Resources/Content/Text',
    ]
    roots = [root for root in roots if root.exists()] or [game]
    candidates = set()
    try:
        for root in roots:
            for path in root.rglob('*.sjson'):
                if path.name.endswith(f'.{language}.sjson') or language in path.parts:
                    candidates.add(path)
        files = sorted(candidates)
    except OSError:
        files = []
    id_pattern = re.compile(r'\bId\s*=\s*"((?:\\.|[^"\\])*)"')
    display_pattern = re.compile(r'\bDisplayName\s*=\s*"((?:\\.|[^"\\])*)"')
    for path in files:
        try:
            text = path.read_text(encoding='utf-8-sig', errors='replace')
        except OSError:
            continue
        ids = list(id_pattern.finditer(text))
        for index, match in enumerate(ids):
            identifier = _sjson_unescape(match.group(1))
            end = ids[index + 1].start() if index + 1 < len(ids) else min(len(text), match.end() + 8192)
            display = display_pattern.search(text, match.end(), end)
            if display and identifier not in names:
                names[identifier] = _clean_display_name(display.group(1))
    _OFFICIAL_TEXT_CACHE[cache_key] = names
    return names

def official_display_names(identifiers, language='zh-CN', game_path=None):
    mapping = _load_official_display_names(language, game_path=game_path)
    return {identifier: mapping[identifier] for identifier in identifiers if identifier in mapping}
