import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.sidecar import JsonLineSidecarClient
from games.hades2.transport_client import Hades2LuaTransport, _LLDBWorkerClient

CHILD = '''
from games.hades2.lldb_worker import Hades2LLDBWorker, serve_requests
import sys
class Transport:
    pid = None
    tainted = False
    def alive(self): return self.pid is not None
    def attach(self, pid): self.pid = pid
    def detach(self): self.pid = None
    def close(self): self.detach()
class TimeWarp:
    speed = 1.0
    def set_speed(self, value): self.speed = value; return value
    def reset(self): self.speed = 1.0; return self.speed
    def current_speed(self): return self.speed
worker = Hades2LLDBWorker(transport=Transport(), time_warp_factory=lambda *args: TimeWarp())
serve_requests(sys.stdin, sys.stdout, worker)
'''

with tempfile.TemporaryDirectory(prefix="mgt-speed-sidecar-") as temporary:
    child = Path(temporary) / "worker.py"
    child.write_text(CHILD)
    environment = dict(os.environ, PYTHONPATH=str(ROOT / "Backend"))
    for first_method in ("set_speed", "reset", "current_speed"):
        sidecar = JsonLineSidecarClient([sys.executable, "-u", str(child)],
                                      reply_timeout_seconds=5, env=environment)
        transport = Hades2LuaTransport()
        transport._worker = _LLDBWorkerClient(sidecar=sidecar)
        facade = transport.create_time_warp_controller(Path(temporary) / "helper", ["Hades II"])
        try:
            transport.attach(4242)
            assert facade.set_speed(2.0) == 2.0
            assert facade.current_speed() == 2.0, "idempotent configure replaced the live controller"
            old_child = sidecar._process
            old_child.terminate()
            old_child.wait(timeout=5)
            transport.attach(4242)
            assert sidecar._process is not old_child and transport.alive()
            if first_method == "set_speed":
                assert facade.set_speed(3.0) == 3.0
            else:
                assert getattr(facade, first_method)() == 1.0
            assert facade.set_speed(3.0) == 3.0
            assert facade.current_speed() == 3.0
            assert facade.reset() == 1.0
        finally:
            transport.close()

print("hades2_time_warp_sidecar_recovery_ok")
