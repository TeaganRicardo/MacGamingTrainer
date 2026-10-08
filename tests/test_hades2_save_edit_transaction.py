import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

import core.save_restore as save_restore_module
from core.module_manifest import SaveManagementSpec, SaveRootSpec
from core.save_restore import SaveBusyError, SaveRestoreError, SaveRollbackError
from core.save_service import CoreSaveService
from games.hades2.save_document import Hades2SaveDocument, HadesSaveFormatError
from games.hades2.save_edit import Hades2SaveEditSession


def _u32(out, value):
    out += struct.pack("<I", value)


def _string(out, value):
    data = value.encode("utf-8")
    _u32(out, len(data))
    out += data


def _lua_value(out, value):
    if value is None:
        out += b"-"
    elif value is False:
        out += b"0"
    elif value is True:
        out += b"1"
    elif isinstance(value, (int, float)):
        out += b"N" + struct.pack("<d", float(value))
    elif isinstance(value, str):
        encoded = value.encode("utf-8")
        out += b"S" + struct.pack("<i", len(encoded)) + encoded
    elif isinstance(value, list):
        out += b"T" + struct.pack("<ii", len(value), 0)
        for index, item in enumerate(value, 1):
            _lua_value(out, index)
            _lua_value(out, item)
    elif isinstance(value, dict):
        out += b"T" + struct.pack("<ii", 0, len(value))
        for key, item in value.items():
            _lua_value(out, key)
            _lua_value(out, item)
    else:
        raise TypeError(type(value))


def _literal_lz4(payload):
    out = bytearray()
    length = len(payload)
    if length < 15:
        out.append(length << 4)
    else:
        out.append(0xF0)
        remaining = length - 15
        while remaining >= 255:
            out.append(255)
            remaining -= 255
        out.append(remaining)
    out += payload
    return bytes(out)


def build_save(meta_points):
    lua_state = {
        "GameState": {
            "MetaPoints": float(meta_points),
            "UnknownFutureField": {"KeepMe": "yes"},
        },
        "CurrentRun": {"RunDepthCache": 7.0},
    }
    luabins = bytearray([1])
    _lua_value(luabins, lua_state)
    compressed = _literal_lz4(luabins)

    body = bytearray()
    body += struct.pack("<HHQ", 0x12, 3, 0x0102030405060708)
    _string(body, "Crossroads")
    body += struct.pack("<III", 42, 314, 9)
    body += struct.pack("<I", 30)
    body += struct.pack("<I", 17)
    body += bytes([0, 1])
    body += struct.pack("<I", 2)
    _string(body, "GameState")
    _string(body, "CurrentRun")
    _string(body, "Hub_Main")
    _string(body, "F_Opening01")
    _u32(body, len(compressed))
    body += compressed

    data = bytearray(b"SGB1\0\0\0\0") + body
    struct.pack_into("<I", data, 4, zlib.adler32(data[8:]) & 0xFFFFFFFF)
    return bytes(data)


BASE = Path(tempfile.mkdtemp(prefix="mgt-hades-save-edit-"))


def make_environment(name, *, running=False, provider=None):
    root = BASE / name
    saves = root / "saves"
    saves.mkdir(parents=True)
    data_root = root / "data"
    save_path = saves / "Profile1.sav"
    original = build_save(123)
    save_path.write_bytes(original)
    state = {"running": running}

    provider_target = None
    provider_loader = None
    if provider is not None:
        provider_target = "games.example.save_provider:Provider"
        provider_loader = lambda _target: provider

    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav",)),),
        provider=provider_target,
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    service = CoreSaveService(
        name,
        spec,
        data_root,
        lambda: state["running"],
        provider_loader=provider_loader,
    )
    return service, save_path, original, state, spec, data_root


def expect_error(error_type, action, label):
    try:
        action()
    except error_type as error:
        return error
    raise AssertionError("{} unexpectedly succeeded".format(label))


# Successful apply is bound to one structured document, captures a normal
# pre-mutation snapshot, atomically replaces the profile, and reopens it as a
# valid Hades document before reporting success.
service, save_path, original, state, spec, data_root = make_environment("success")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
assert session.original_sha256
assert session.document.lua_state["GameState"]["MetaPoints"] == 123.0
session.document.lua_state["GameState"]["MetaPoints"] = 999.0
result = session.apply()
assert result["applied"] is True
assert result["replaced"] is True
assert result["relativePath"] == "Profile1.sav"
assert result["hot"] is False
assert result["previousSnapshotId"]
installed = Hades2SaveDocument.load(save_path)
assert installed.lua_state["GameState"]["MetaPoints"] == 999.0
assert installed.lua_state["GameState"]["UnknownFutureField"]["KeepMe"] == "yes"
previous = service.store.load_verified_snapshot(result["previousSnapshotId"])
assert (previous["root"] / "files/main/Profile1.sav").read_bytes() == original

snapshot_count = len(service.list_state()["snapshots"])
expect_error(ValueError, session.apply, "unchanged document reapply")
assert len(service.list_state()["snapshots"]) == snapshot_count

# Invalid structured state is rejected before Core crosses the destructive
# transaction seam. No recovery snapshot is created because no mutation was
# attempted.
service, save_path, original, _state, _spec, _data_root = make_environment("invalid-structured")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["UnsupportedValue"] = object()
expect_error(HadesSaveFormatError, session.apply, "invalid structured document")
assert save_path.read_bytes() == original
assert service.list_state()["snapshots"] == []

# The Save Editor surface must accept the Hades document type itself rather
# than any arbitrary object that happens to provide bytes.
class RawWriteSurface:
    def __init__(self, payload):
        self.payload = payload

    def to_bytes(self):
        return self.payload


service, save_path, original, _state, _spec, _data_root = make_environment("raw-surface")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document = RawWriteSurface(build_save(777))
raw_surface_rejected = False
try:
    session.apply()
except TypeError:
    raw_surface_rejected = True

# A running target is refused before recovery capture or file mutation.
service, save_path, original, state, _spec, _data_root = make_environment("running", running=True)
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 200.0
expect_error(SaveBusyError, session.apply, "running-target edit")
assert save_path.read_bytes() == original
assert service.list_state()["snapshots"] == []

# Provider-declared save busy must also veto the cold destructive editor path.
class BusyProvider:
    def resolve(self, roots, declared):
        del roots
        return [(row.root_id, row.relative_path) for row in declared]

    def restore_busy(self, files):
        assert any(row.relative_path == "Profile1.sav" for row in files)
        return True


busy_provider = BusyProvider()
service, save_path, original, _state, _spec, _data_root = make_environment(
    "provider-busy",
    provider=busy_provider,
)
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 201.0
provider_busy_rejected = False
try:
    session.apply()
except SaveBusyError:
    provider_busy_rejected = True

# The source hash captured when the structured document was opened is a stale
# edit guard. A later external write remains authoritative and is never
# overwritten by the old editor session.
service, save_path, original, _state, _spec, _data_root = make_environment("stale")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 300.0
external = build_save(301)
save_path.write_bytes(external)
expect_error(SaveRestoreError, session.apply, "stale edit")
assert save_path.read_bytes() == external
assert service.list_state()["snapshots"] == []

# A target replacement that commits and then reports a write failure is treated
# as a post-mutation failure: rollback restores and verifies the exact original
# bytes while the persistent pre-mutation snapshot remains available.
service, save_path, original, _state, _spec, _data_root = make_environment("write-failure")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 400.0
real_replace = save_restore_module.os.replace
failed_target_write = False


def fail_after_target_replace(source, destination):
    global failed_target_write
    destination = Path(destination)
    if destination == save_path and not failed_target_write:
        failed_target_write = True
        real_replace(source, destination)
        raise OSError("simulated lost write acknowledgement")
    return real_replace(source, destination)


save_restore_module.os.replace = fail_after_target_replace
try:
    expect_error(SaveRestoreError, session.apply, "write failure")
finally:
    save_restore_module.os.replace = real_replace
assert failed_target_write is True
assert save_path.read_bytes() == original
state_after_write_failure = service.list_state()
assert len(state_after_write_failure["snapshots"]) == 1
assert state_after_write_failure["recoveryPaths"] == []

# Reopen validation is not the end of the transaction. If another writer
# changes the profile immediately after the validator reads it, the final Core
# state verification must notice the race and roll back instead of reporting
# success.
service, save_path, original, _state, _spec, _data_root = make_environment("post-verify-race")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 500.0
foreign_after_verify = build_save(501)
load_descriptor = Hades2SaveDocument.__dict__["load"]
real_load = Hades2SaveDocument.load


def racing_load(cls, path):
    loaded = real_load(path)
    Path(path).write_bytes(foreign_after_verify)
    return loaded


Hades2SaveDocument.load = classmethod(racing_load)
post_verify_race_blocked = False
try:
    try:
        session.apply()
    except SaveRestoreError:
        post_verify_race_blocked = True
finally:
    Hades2SaveDocument.load = load_descriptor
post_verify_race_rolled_back = save_path.read_bytes() == original

# If target mutation fails and rollback also fails, the contained rollback
# directory remains discoverable through the existing Core Save state instead
# of being hidden or deleted.
service, save_path, original, _state, _spec, _data_root = make_environment("rollback-failure")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 600.0
real_replace = save_restore_module.os.replace
target_replace_calls = 0


def fail_target_and_rollback(source, destination):
    global target_replace_calls
    destination = Path(destination)
    if destination == save_path:
        target_replace_calls += 1
        if target_replace_calls == 1:
            real_replace(source, destination)
            raise OSError("simulated target write failure")
        raise OSError("simulated rollback write failure")
    return real_replace(source, destination)


save_restore_module.os.replace = fail_target_and_rollback
try:
    rollback_error = expect_error(
        SaveRollbackError,
        session.apply,
        "rollback failure",
    )
finally:
    save_restore_module.os.replace = real_replace
recovery_path = Path(rollback_error.recovery_path)
assert recovery_path.is_dir()
assert (recovery_path / "files/main/Profile1.sav").read_bytes() == original
assert str(recovery_path.resolve()) in service.list_state()["recoveryPaths"]

# A control-flow interruption during rollback leaves the same discoverable
# recovery evidence. Recreating/listing the service does not replay the edit,
# and there is no staged instruction to apply later.
service, save_path, original, _state, spec, data_root = make_environment("interrupted")
session = Hades2SaveEditSession.open(service, "Profile1.sav")
session.document.lua_state["GameState"]["MetaPoints"] = 700.0
real_replace = save_restore_module.os.replace
target_replace_calls = 0


def interrupt_rollback(source, destination):
    global target_replace_calls
    destination = Path(destination)
    if destination == save_path:
        target_replace_calls += 1
        if target_replace_calls == 1:
            real_replace(source, destination)
            raise OSError("simulated target failure before rollback")
        raise KeyboardInterrupt()
    return real_replace(source, destination)


save_restore_module.os.replace = interrupt_rollback
try:
    expect_error(KeyboardInterrupt, session.apply, "interrupted rollback")
finally:
    save_restore_module.os.replace = real_replace
bytes_before_reload = save_path.read_bytes()
reloaded = CoreSaveService(
    "interrupted",
    spec,
    data_root,
    lambda: False,
)
reloaded_state = reloaded.list_state()
assert reloaded_state["pendingRestore"] is None
assert len(reloaded_state["recoveryPaths"]) == 1
assert save_path.read_bytes() == bytes_before_reload
recovery_path = Path(reloaded_state["recoveryPaths"][0])
assert (recovery_path / "files/main/Profile1.sav").read_bytes() == original

assert raw_surface_rejected, "Save Editor accepted a non-document raw-byte writer"
assert provider_busy_rejected, "Save Editor ignored provider-declared save busy state"
assert post_verify_race_blocked, "Save Editor reported success after post-validation file replacement"
assert post_verify_race_rolled_back, "post-validation race did not restore the original save"

print("hades2_save_edit_transaction_ok")
