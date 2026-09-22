from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
SWIFTC = shutil.which("swiftc")
if not SWIFTC:
    raise SystemExit("swiftc required")

harness = r'''
import Foundation

func fail(_ message: String) -> Never {
    fputs("FAIL: \(message)\n", stderr)
    exit(1)
}

func pump(_ seconds: TimeInterval) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

let scheduler = Hades2MutationScheduler()
var events: [String] = []

scheduler.schedule(key: "health", delay: 0.05) { events.append("old") }
scheduler.schedule(key: "health", delay: 0.05) { events.append("new") }
pump(0.15)
if events != ["new"] { fail("same-key replacement executed stale action: \(events)") }

events.removeAll()
scheduler.schedule(key: "dodge", delay: 0.08) { events.append("dodge-stale") }
scheduler.schedule(key: "crit", delay: 0.08) { events.append("crit-kept") }
scheduler.cancel(key: "dodge")
pump(0.15)
if events != ["crit-kept"] { fail("single-key cancel removed the wrong work or left stale work: \(events)") }
if scheduler.pendingCount != 0 { fail("single-key cancel left completed entries behind") }

events.removeAll()
scheduler.schedule(key: "mana", delay: 0.08) { events.append("stale") }
scheduler.invalidateAll()
pump(0.15)
if !events.isEmpty { fail("barrier allowed stale mutation: \(events)") }
if scheduler.pendingCount != 0 { fail("barrier did not clear pending entries") }

events.removeAll()
scheduler.schedule(key: "armor", delay: 0.03) { events.append("post-barrier") }
pump(0.10)
if events != ["post-barrier"] { fail("scheduler unusable after barrier: \(events)") }

events.removeAll()
scheduler.schedule(key: "a", delay: 5.0) { events.append("a-old") }
scheduler.schedule(key: "b", delay: 5.0) { events.append("b") }
scheduler.schedule(key: "a", delay: 5.0) { events.append("a-new") }
scheduler.flushAll()
if events != ["b", "a-new"] { fail("flush did not preserve latest submission order: \(events)") }
pump(0.05)
if events != ["b", "a-new"] { fail("flushed work executed twice: \(events)") }

print("hades2_mutation_scheduler_round17_ok")
'''

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    main = td / "main.swift"
    binary = td / "mutation_test"
    main.write_text(textwrap.dedent(harness))
    subprocess.run([
        SWIFTC,
        str(ROOT / "Sources/Hades2/Services/Hades2MutationScheduler.swift"),
        str(main),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    proc = subprocess.run([str(binary)], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    print(proc.stdout.strip())
