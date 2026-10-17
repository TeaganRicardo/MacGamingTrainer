"""Exercise the shipped mailbox protocol through independent shared mappings."""
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
compiler = shutil.which("cc")
assert compiler, "A C compiler is required for the Hades II mailbox protocol"

with tempfile.TemporaryDirectory(prefix="mgt-mailbox-protocol-") as temporary:
    executable = Path(temporary) / "mailbox_protocol"
    subprocess.run([
        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2",
        "-DMGT_MAILBOX_PORTABLE_TEST",
        "-I", str(ROOT / "Backend/games/hades2/native"),
        str(ROOT / "Backend/games/hades2/native/CommandMailbox.c"),
        str(ROOT / "tests/fixtures/hades2/mailbox_protocol.c"),
        "-o", str(executable),
    ], check=True)
    for case in (
        "roundtrip", "validation_and_receipts", "cancellation_and_close",
        "unknown_is_permanent", "cancel_execute_race", "independent_mapping_lifetime",
        "shared_publication_stream", "malformed_shared_fields", "queue_timing",
    ):
        subprocess.run([str(executable), case], check=True, timeout=15)

print("hades2_mailbox_protocol_ok")
