import re

_PREVIOUS = re.compile(r'previousModule\.revision\s*~=\s*(\d+)')
_MODULE = re.compile(r'version\s*=\s*1\s*,\s*revision\s*=\s*(\d+)')


def runtime_revision(lua_source):
    previous = _PREVIOUS.search(lua_source)
    module = _MODULE.search(lua_source)
    assert previous is not None, 'previous resident revision guard is missing'
    assert module is not None, 'resident module revision field is missing'
    assert previous.group(1) == module.group(1), 'resident revision markers disagree'
    return int(module.group(1))
