import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.save_resolution import ResolvedSaveFile


def write_active_profile(path, name):
    raw = b"SGB1" + struct.pack("<I", len(name)) + name.encode("utf-8")
    path.write_bytes(raw)


def write_save(
    path,
    *,
    timestamp,
    location,
    runs,
    grasp,
    fear,
    current_map,
    next_map="",
    version=18,
):
    location_b = location.encode("utf-8")
    current_b = current_map.encode("utf-8")
    next_b = next_map.encode("utf-8")
    raw = bytearray()
    raw += b"SGB1"
    raw += b"\x00" * 4
    raw += struct.pack("<H", version)
    raw += struct.pack("<H", 0)
    raw += struct.pack("<Q", timestamp)
    raw += struct.pack("<I", len(location_b)) + location_b
    raw += struct.pack("<I", runs)
    raw += struct.pack("<I", 0)       # accumulated meta points
    raw += struct.pack("<I", fear)    # active shrine / fear points
    if version >= 17:
        raw += struct.pack("<I", grasp)
    if version >= 18:
        raw += struct.pack("<I", 0)   # cosmetics points
    raw += b"\x00\x00"               # easy/hard mode
    raw += struct.pack("<I", 0)       # notable lua data count
    raw += struct.pack("<I", len(current_b)) + current_b
    raw += struct.pack("<I", len(next_b)) + next_b
    struct.pack_into("<I", raw, 4, zlib.adler32(raw[8:]) & 0xFFFFFFFF)
    path.write_bytes(raw)


base = Path(tempfile.mkdtemp(prefix="mgt-hades-save-provider-"))
game = base / "Hades II.app"
text = game / "Contents/Resources/Content/Game/Text/zh-CN/HelpText.zh-CN.sjson"
text.parent.mkdir(parents=True)
text.write_text(
    """
    { Id = "Location_Home" DisplayName = "三岔路口" }
    { Id = "Location_BiomeF" DisplayName = "厄瑞玻斯" }
    """,
    encoding="utf-8",
)

en_text = game / "Contents/Resources/Content/Game/Text/en/HelpText.en.sjson"
en_text.parent.mkdir(parents=True)
en_text.write_text(
    """
    { Id = "Location_Home" DisplayName = "The Crossroads" }
    { Id = "Location_BiomeF" DisplayName = "Erebus" }
    """,
    encoding="utf-8",
)

saves = base / "saves"
saves.mkdir()
write_active_profile(saves / "activeProfile", "Profile1")
write_save(
    saves / "Profile1.sav",
    timestamp=100,
    location="Location_Home",
    runs=10,
    grasp=29,
    fear=19,
    current_map="Hub_Main",
)
write_save(
    saves / "Profile1_Temp.sav",
    timestamp=200,
    location="Location_BiomeF",
    runs=11,
    grasp=29,
    fear=19,
    current_map="F_Combat20",
)

from games.hades2.save_provider import Hades2SaveProvider

provider = Hades2SaveProvider(game_path=game)
rows = [
    ResolvedSaveFile("main", "activeProfile", saves / "activeProfile"),
    ResolvedSaveFile("main", "Profile1.sav", saves / "Profile1.sav"),
    ResolvedSaveFile("main", "Profile1_Temp.sav", saves / "Profile1_Temp.sav"),
]
no_marker = provider.describe_snapshot(tuple(rows), "2026-09-20T14:37:51")
assert no_marker["defaultName"] == "2026-09-20 14:37 · 第10夜 · 三岔路口"
marker = saves / "Profile1.v.sav"
marker.write_bytes(b"validation-marker")
stamp = 1_700_000_000_000_000_000
os.utime(saves / "Profile1.sav", ns=(stamp, stamp))
os.utime(marker, ns=(stamp + 2_000_000_000, stamp + 2_000_000_000))
rows.append(ResolvedSaveFile("main", "Profile1.v.sav", marker))
resolved = provider.resolve({"main": saves}, tuple(rows))
assert resolved == [
    ("main", "activeProfile"),
    ("main", "Profile1.sav"),
    ("main", "Profile1_Temp.sav"),
    ("main", "Profile1.v.sav"),
]

description = provider.describe_snapshot(tuple(rows), "2026-09-20T14:37:51")
assert description == {
    "defaultName": "2026-09-20 14:37 · 第11夜 · 厄瑞玻斯",
    "nameDetails": ["第11夜", "厄瑞玻斯", "悟性 29", "恐惧 19"],
    "localizedPresentation": {
        "zh-CN": {
            "name": "2026-09-20 14:37 · 第11夜 · 厄瑞玻斯",
            "details": ["第11夜", "厄瑞玻斯", "悟性 29", "恐惧 19"],
        },
        "en": {
            "name": "2026-09-20 14:37 · Night 11 · Erebus",
            "details": ["Night 11", "Erebus", "Grasp 29", "Fear 19"],
        },
    },
}

# Once the base save is newer, the provider describes the hub save and its
# completed run count using the same 第N夜 wording requested by the product.
write_save(
    saves / "Profile1.sav",
    timestamp=300,
    location="Location_Home",
    runs=11,
    grasp=30,
    fear=7,
    current_map="Hub_Main",
)
os.utime(saves / "Profile1.sav", ns=(stamp + 3_000_000_000, stamp + 3_000_000_000))
description = provider.describe_snapshot(tuple(rows), "2026-09-20T15:02:09")
assert description == {
    "defaultName": "2026-09-20 15:02 · 第11夜 · 三岔路口",
    "nameDetails": ["第11夜", "三岔路口", "悟性 30", "恐惧 7"],
    "localizedPresentation": {
        "zh-CN": {
            "name": "2026-09-20 15:02 · 第11夜 · 三岔路口",
            "details": ["第11夜", "三岔路口", "悟性 30", "恐惧 7"],
        },
        "en": {
            "name": "2026-09-20 15:02 · Night 11 · The Crossroads",
            "details": ["Night 11", "The Crossroads", "Grasp 30", "Fear 7"],
        },
    },
}

# Unknown official location falls back to the current map instead of inventing
# a translation or leaking an empty location.
write_save(
    saves / "Profile1_Temp.sav",
    timestamp=400,
    location="Location_Unknown",
    runs=12,
    grasp=30,
    fear=7,
    current_map="F_Combat99",
)
os.utime(marker, ns=(stamp + 5_000_000_000, stamp + 5_000_000_000))
description = provider.describe_snapshot(tuple(rows), "2026-09-20T15:15:00")
assert description["defaultName"] == "2026-09-20 15:15 · 第12夜 · F_Combat99"
assert description["nameDetails"][:2] == ["第12夜", "F_Combat99"]
assert description["localizedPresentation"]["en"]["name"] == "2026-09-20 15:15 · Night 12 · F_Combat99"
assert description["localizedPresentation"]["en"]["details"] == ["Night 12", "F_Combat99", "Grasp 30", "Fear 7"]

# Never guess another profile when activeProfile is corrupt.
(saves / "activeProfile").write_bytes(b"broken")
description = provider.describe_snapshot(tuple(rows), "2026-09-20T15:20:00")
assert description == {"defaultName": None, "nameDetails": []}

print("hades2_save_provider_round21_ok")
