"""Native dialogue source refresh stays out of the search hot path."""
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from games.hades2.save_document import LuaTable
from games.hades2.save_investigation import NativeDialogueInvestigation


def lua(**entries):
    return LuaTable(0, len(entries), list(entries.items()))


def native_tree(root):
    scripts = root / "sources/Scripts"
    english = root / "sources/Text/en"
    chinese = root / "sources/Text/zh-CN"
    for folder in (scripts, english, chinese):
        folder.mkdir(parents=True)
    reset = scripts / "StoryResetData.lua"
    reset.write_text(
        'StoryResetData = { TextLines = { "NemesisRefreshScene01" } }\n',
        encoding="utf-8",
    )
    (scripts / "NPCData_Nemesis.lua").write_text(
        """NemesisRefreshScene01 = {
  { Cue = "/VO/Nemesis_Refresh01", Text = "Authored fallback" },
}
""",
        encoding="utf-8",
    )
    (english / "_NPCData_Nemesis.en.sjson").write_text(
        """{ Texts = [
 { Id = "Nemesis_Refresh01" DisplayName = "first source line" Speaker = "Nemesis" Event = "NemesisRefreshScene01" }
] }
""",
        encoding="utf-8",
    )
    (chinese / "_NPCData_Nemesis.zh-CN.sjson").write_text(
        """{ Texts = [
 { Id = "Nemesis_Refresh01" DisplayName = "第一条源文本" Speaker = "涅墨西斯" Event = "NemesisRefreshScene01" }
] }
""",
        encoding="utf-8",
    )
    return reset, english / "_NPCData_Nemesis.en.sjson"


with tempfile.TemporaryDirectory(prefix="mgt-native-refresh-") as directory:
    game = Path(directory)
    reset, english_text = native_tree(game)
    expected_hash = hashlib.sha256(reset.read_bytes()).hexdigest()
    save = lua(GameState=lua(TextLinesRecord=lua(NemesisRefreshScene01=True)))

    original_read_bytes = Path.read_bytes
    reads = []

    def counted_read_bytes(path):
        if game in path.parents:
            reads.append(path)
        return original_read_bytes(path)

    with patch.object(Path, "read_bytes", counted_read_bytes):
        finding = NativeDialogueInvestigation(game, expected_hash=expected_hash)
        initial_reads = len(reads)
        assert initial_reads >= 4

        # Typeahead can revalidate cheap file metadata, but unchanged searches
        # must not reread/hash the installed source set.
        for term in ("Nemesis", "first", "RefreshScene"):
            result = finding.query(
                save, search=term, offset=0, limit=20,
                language="en", permissions={},
            )
            assert result["total"] >= 1
        assert len(reads) == initial_reads

        # A real source mutation invalidates the in-memory index on the next
        # search and new bytes, not stale evidence, become searchable.
        english_text.write_text(
            """{ Texts = [
 { Id = "Nemesis_Refresh01" DisplayName = "updated native evidence" Speaker = "Nemesis" Event = "NemesisRefreshScene01" }
] }
""",
            encoding="utf-8",
        )
        changed = finding.query(
            save, search="updated native evidence", offset=0, limit=20,
            language="en", permissions={},
        )
        assert changed["total"] == 1
        assert len(reads) > initial_reads

        # Detail retrieval is deliberate evidence access and performs a full
        # byte capture/hash even if the cheap freshness signature is unchanged.
        before_detail = len(reads)
        detail = finding.detail(
            save, "NemesisRefreshScene01", "en", permissions={}
        )
        assert detail["lines"][0]["en"] == ["updated native evidence"]
        assert len(reads) > before_detail

print("hades2_save_native_source_refresh_ok")
