"""Offline transport: the shipped Hades II resident in a Lua 5.2 process with synthetic native stubs.

Tests set `MGT_PROFILE_EVENTS` (stderr log path) and the inventory sizes
`MGT_PROFILE_TRAITS`, `MGT_PROFILE_CATALOG` and `MGT_PROFILE_RESOURCES`.
"""
import os
from pathlib import Path
import subprocess
import time

from core import operation_profile as profile
from games.hades2.resident_session import lua_value
from lua_runtime_support import require_lua52

ROOT = Path(__file__).resolve().parents[3]
RESIDENT_FIXTURE = Path(__file__).resolve().parent / "offline_resident.lua"


class OfflineLuaTransport:
    def __init__(self):
        self.pid, self.tainted, self.last_duration = 4242, False, 0.0
        self.last_expression_duration, self.last_attach_profile = 0.0, {}
        self.counter = 0
        self.events = open(os.environ["MGT_PROFILE_EVENTS"], "a", encoding="utf-8")
        self.lua = subprocess.Popen([
            require_lua52("offline resident"), str(RESIDENT_FIXTURE),
            str(ROOT / "Backend/games/hades2/runtime/hades.lua"), "1",
            os.environ.get("MGT_PROFILE_TRAITS", "32"), os.environ.get("MGT_PROFILE_CATALOG", "96"),
            os.environ.get("MGT_PROFILE_RESOURCES", "32"), "serve",
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.events, text=True, bufsize=1)

    def alive(self):
        return self.pid is not None and self.lua.poll() is None

    def attach(self, pid):
        assert pid == 4242

    def detach(self):
        self.pid = None

    def close(self):
        self.pid = None
        self.lua.stdin.close()
        try:
            self.lua.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.lua.kill()
            self.lua.wait(timeout=2)
        self.lua.stdout.close()
        self.events.close()

    def execute(self, source, **kwargs):
        identity = profile.correlation() or {"request_id": "unobserved", "command": "fixture"}
        started = time.perf_counter()
        self.lua.stdin.write(identity["request_id"] + "\t" + identity["command"] + "\t" + lua_value(source) + "\n")
        self.lua.stdin.flush()
        result = self.lua.stdout.readline()
        if not result:
            raise RuntimeError("offline resident exited: " + Path(self.events.name).read_text()[-4000:])
        self.last_duration = time.perf_counter() - started
        return result.strip()

    def acknowledge_result(self):
        # The synchronous pipe has already consumed the complete reply; there
        # is no shared mailbox slot to release.
        pass
