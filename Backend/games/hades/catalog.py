"""Supported-build Hades I reward identities and official bilingual labels."""
import json
from pathlib import Path


_DATA = json.loads(Path(__file__).with_name('catalog.json').read_text())
_ENTRIES = {row['id']: row for row in _DATA['entries']}
_KINDS = frozenset(('all', 'boon', 'hammer', 'chaos', 'curse', 'temporary', 'special', 'keepsake', 'companion'))


def data():
    return _DATA


def get_entry(identifier):
    return _ENTRIES.get(identifier)


def trait_names():
    return _DATA['traitNames']


def _localized(row, language):
    result = {**row, 'name': row['names'][language], 'description': row['descriptions'][language]}
    if 'sourceNames' in row:
        result['sourceName'] = row['sourceNames'][language]
    return result


def catalog(language='zh-CN', query='', kind='all'):
    if language not in ('zh-CN', 'en'):
        raise ValueError('Unsupported Hades catalog language.')
    if kind not in _KINDS:
        raise ValueError('Unsupported Hades catalog kind.')
    if not isinstance(query, str):
        raise ValueError('Hades catalog query must be text.')
    terms = query.casefold().split()
    rows = []
    for entry in _DATA['entries']:
        if kind != 'all' and entry['kind'] != kind:
            continue
        searchable = ' '.join((entry['id'], *entry['names'].values(),
                              *entry['descriptions'].values(), *entry['sourceNames'].values())).casefold()
        if all(term in searchable for term in terms):
            rows.append(_localized(entry, language))
    return rows


def resource_catalog(language='zh-CN'):
    if language not in ('zh-CN', 'en'):
        raise ValueError('Unsupported Hades catalog language.')
    return [_localized(row, language) for row in _DATA['resources']]
