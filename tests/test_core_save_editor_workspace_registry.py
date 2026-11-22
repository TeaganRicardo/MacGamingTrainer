"""Behavior contract for Core structured save eligibility, candidate apply, and workspace registry."""

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))

from core.adapter import GameAdapterContext  # noqa: E402
from core.module_manifest import SaveManagementSpec, SaveRootSpec  # noqa: E402
from core.save_resolution import SaveResolutionError, load_save_provider  # noqa: E402
from core.save_service import CoreSaveService  # noqa: E402
import core.structured_save_edit as sse  # noqa: E402
from core.structured_save_edit import StructuredSaveEditSession  # noqa: E402
from games.hades.adapter import HadesAdapter  # noqa: E402
from games.hades.preferences import HadesPreferenceStore  # noqa: E402
from games.hades2.adapter import Hades2Adapter  # noqa: E402
from hades2_resident_session_fakes import hades2_adapter_context  # noqa: E402


class _JsonCodec:
    def decode(self, raw: bytes) -> dict:
        return json.loads(raw.decode("utf-8"))

    def encode(self, doc: dict) -> bytes:
        return json.dumps(doc, sort_keys=True).encode("utf-8")

    def load(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))


CODEC = _JsonCodec()


class _DummyWorkspace:
    def __init__(self, session):
        self._session = session
        self.identifier = ""
        self.baseline_generation = ""
        self.targets_set = []
        self.closed = False

    def summary(self):
        return {
            "workspaceId": self.identifier,
            "baselineGeneration": self.baseline_generation,
            "source": self._session.source,
            "target": self._session.target,
        }

    def set_target(self, target):
        result = self._session.set_target(target)
        self.targets_set.append(result)
        return self.summary()

    def close(self):
        self.closed = True


def _setup(root: Path):
    saves = root / "saves"
    saves.mkdir()
    (saves / "Profile1.sav").write_text('{"gold": 10}', encoding="utf-8")
    (saves / "Profile2.sav").write_text('{"gold": 20}', encoding="utf-8")
    (saves / "notes.txt").write_text("ignored", encoding="utf-8")
    spec = SaveManagementSpec(
        roots=(SaveRootSpec("main", str(saves), ("Profile*.sav", "notes.txt")),),
        provider=None,
        hot_backup=True,
        restore_policy="hotPreferred",
        staged_restore=True,
    )
    service = CoreSaveService("example", spec, root / "data", lambda: False)
    return saves, service


def main():
    assert hasattr(sse, "StructuredSaveEligibility"), "StructuredSaveEligibility missing"
    assert hasattr(sse, "SaveEditorWorkspaceRegistry"), "SaveEditorWorkspaceRegistry missing"
    assert hasattr(StructuredSaveEditSession, "open_selected"), "open_selected missing"

    eligibility = sse.StructuredSaveEligibility(
        editor_files=lambda files: [
            {"rootId": row.root_id, "relativePath": row.relative_path}
            for row in files
            if row.relative_path.endswith(".sav")
        ],
        is_source=lambda rel: rel.startswith("Profile") and rel.endswith(".sav"),
    )

    with tempfile.TemporaryDirectory(prefix="mgt-core-ws-registry-") as td:
        root = Path(td)
        saves, service = _setup(root)

        # Ineligible source is rejected before decoding.
        try:
            StructuredSaveEditSession.open_selected(
                service, CODEC, eligibility, relative_path="notes.txt", root_id="main"
            )
        except ValueError:
            pass
        else:
            raise AssertionError("ineligible source unexpectedly opened")

        # Non-writable document property + explicit candidate apply.
        session = StructuredSaveEditSession.open_selected(
            service,
            CODEC,
            eligibility,
            relative_path="Profile1.sav",
            root_id="main",
            default_target=True,
        )
        assert session.source == {"kind": "currentFile", "rootId": "main", "relativePath": "Profile1.sav"}
        assert session.target == {"rootId": "main", "relativePath": "Profile1.sav"}
        try:
            session.document = {"gold": 999}  # type: ignore[misc]
        except AttributeError:
            pass
        else:
            raise AssertionError("session.document setter still writable")

        before_doc = dict(session.document)
        try:
            session.apply(dict(before_doc))
        except ValueError:
            pass
        else:
            raise AssertionError("unchanged candidate unexpectedly applied")
        assert session.document == before_doc

        receipt = session.apply({"gold": 77})
        assert receipt["applied"] is True
        assert session.document == {"gold": 77}
        assert json.loads((saves / "Profile1.sav").read_text(encoding="utf-8")) == {"gold": 77}

        # Managed backup source metadata.
        snap = service.backup()
        backup_session = StructuredSaveEditSession.open_selected(
            service,
            CODEC,
            eligibility,
            relative_path="Profile1.sav",
            root_id="main",
            snapshot_id=snap["id"],
            default_target=False,
        )
        assert backup_session.source == {
            "kind": "managedBackup",
            "snapshotId": snap["id"],
            "rootId": "main",
            "relativePath": "Profile1.sav",
        }
        assert backup_session.target is None

        # Unsupported target rejected by set_target via eligibility.
        try:
            backup_session.set_target({"rootId": "main", "relativePath": "notes.txt"})
        except ValueError:
            pass
        else:
            raise AssertionError("ineligible target unexpectedly accepted")

        # Workspace registry: standard routing, baseline check, LRU eviction, clear.
        current_service = [None]
        registry = sse.SaveEditorWorkspaceRegistry(
            lambda: current_service[0],
            inventory=lambda svc, snapshot_id=None: {
                "sources": eligibility.editor_files(svc.source_files(snapshot_id)),
                "targets": eligibility.editor_files(svc.resolved_files()),
                "defaultSource": None,
            },
            open_workspace=lambda svc, *, snapshot_id=None, source=None, target=None: _DummyWorkspace(
                StructuredSaveEditSession.open_selected(
                    svc,
                    CODEC,
                    eligibility,
                    source=source,
                    snapshot_id=snapshot_id,
                    target=target,
                    default_target=True,
                )
            ),
            max_open=2,
        )

        try:
            registry.handle("inventory", {})
        except ValueError as err:
            assert "unavailable" in str(err).lower()
        else:
            raise AssertionError("inventory succeeded with no save_service")

        current_service[0] = service
        inv = registry.handle("inventory", {})
        assert len(inv["sources"]) == 2

        w1 = registry.handle("open", {"source": {"rootId": "main", "relativePath": "Profile1.sav"}})
        w2 = registry.handle("open", {"source": {"rootId": "main", "relativePath": "Profile2.sav"}})
        id1, gen1 = w1["workspaceId"], w1["baselineGeneration"]
        id2, gen2 = w2["workspaceId"], w2["baselineGeneration"]
        assert id1 != id2 and gen1 != gen2

        # Touch w1 so w2 becomes LRU and gets evicted when w3 opens.
        registry.require(id1)
        w3 = registry.handle("open", {"source": {"rootId": "main", "relativePath": "Profile1.sav"}})
        id3 = w3["workspaceId"]
        assert id1 in registry and id3 in registry and id2 not in registry

        # If workspace.summary() fails on open, existing workspaces must not be evicted or leaked.
        created_failing = []

        class _FailingSummaryWorkspace(_DummyWorkspace):
            def summary(self, language="en"):
                raise ValueError("Unsupported editor language.")

        def _failing_open(_svc, *, snapshot_id=None, source=None, target=None):
            ws = _FailingSummaryWorkspace(
                StructuredSaveEditSession.open_selected(
                    _svc, CODEC, eligibility, source=source, snapshot_id=snapshot_id, target=target, default_target=True
                )
            )
            created_failing.append(ws)
            return ws

        failing_registry = sse.SaveEditorWorkspaceRegistry(
            lambda: service,
            inventory=lambda svc, snapshot_id=None: {
                "sources": eligibility.editor_files(svc.source_files(snapshot_id))
            },
            open_workspace=_failing_open,
            max_open=1,
        )
        # Seed one healthy workspace via manual _workspaces insertion or a switchable flag.
        healthy = _DummyWorkspace(session)
        failing_registry._workspaces["keep"] = healthy
        try:
            failing_registry.open({"source": {"rootId": "main", "relativePath": "Profile2.sav"}}, language="fr")
        except ValueError as err:
            assert "Unsupported editor language" in str(err)
        else:
            raise AssertionError("open succeeded when workspace.summary() raised")
        assert list(failing_registry._workspaces) == ["keep"]
        assert not healthy.closed
        assert len(created_failing) == 1 and created_failing[0].closed

        # Stale baseline is rejected cleanly, and rotate_baseline invalidates the prior token.
        try:
            registry.require_baseline(id1, "wrong-generation")
        except ValueError:
            pass
        else:
            raise AssertionError("stale baseline unexpectedly accepted")
        rotated_gen = registry.rotate_baseline(id1)
        assert rotated_gen != gen1
        try:
            registry.require_baseline(id1, gen1)
        except ValueError:
            pass
        else:
            raise AssertionError("previous baseline stayed valid after rotate_baseline")
        assert registry.require_baseline(id1, rotated_gen) is registry[id1]

        # Standard target routing updates target and preserves workspace.
        targeted = registry.handle(
            "target",
            {
                "workspaceId": id1,
                "baselineGeneration": rotated_gen,
                "target": {"rootId": "main", "relativePath": "Profile2.sav"},
            },
        )
        assert targeted["target"] == {"rootId": "main", "relativePath": "Profile2.sav"}

        assert registry.handle("close", {"workspaceId": id1}) == {"closed": True}
        assert id1 not in registry
        registry.clear()
        assert len(registry) == 0

        # Real HadesAdapter binds the Core workspace registry and clears it on rebind and close.
        hades_context = GameAdapterContext(
            game_id="hades",
            display_name="Hades",
            module_protocol_version=3,
            module_dir=ROOT / "Backend/games/hades",
            public_metadata={"protocolVersion": 3},
            home=root / "home",
        )
        hades_adapter = HadesAdapter(
            hades_context,
            runtime=type("_DummyRuntime", (), {"close": lambda self: None})(),
            preferences=HadesPreferenceStore(root / "prefs.json"),
        )
        assert isinstance(hades_adapter.save_workspaces, sse.SaveEditorWorkspaceRegistry)
        assert len(hades_adapter.save_workspaces) == 0
        hades_adapter.bind_save_service(service)
        hades_adapter.save_workspaces._workspaces["synthetic"] = _DummyWorkspace(backup_session)
        assert len(hades_adapter.save_workspaces) == 1
        hades_adapter.bind_save_service(service)
        assert len(hades_adapter.save_workspaces) == 0
        hades_adapter.save_workspaces._workspaces["synthetic"] = _DummyWorkspace(backup_session)
        hades_adapter.close()
        assert len(hades_adapter.save_workspaces) == 0

        # Real Hades2Adapter also uses Core's workspace registry and clears on rebind/close.
        hades2_context = hades2_adapter_context(root / "h2-home")
        hades2_adapter = Hades2Adapter(
            context=hades2_context,
            resident_session=type(
                "_DummySession",
                (),
                {
                    "pid": None,
                    "pending_resume_pid": None,
                    "cleanup_pending": False,
                    "alive": lambda self: False,
                    "close": lambda self: None,
                    "invalidate_generation": lambda self: None,
                },
            )(),
            time_warp_controller=object(),
            game_path=root / "AbsentHades2.app",
        )
        assert isinstance(hades2_adapter.save_workspaces, sse.SaveEditorWorkspaceRegistry)
        assert hades2_adapter._workspace_game_path() == root / "AbsentHades2.app"
        hades2_adapter.bind_save_service(service)
        hades2_adapter.save_workspaces._workspaces["synthetic"] = _DummyWorkspace(backup_session)
        hades2_adapter.bind_save_service(service)
        assert len(hades2_adapter.save_workspaces) == 0
        hades2_adapter.save_workspaces._workspaces["synthetic"] = _DummyWorkspace(backup_session)
        hades2_adapter.close()
        assert len(hades2_adapter.save_workspaces) == 0

    fake_module_name = "games._test_non_provider"
    fake_module = types.ModuleType(fake_module_name)
    fake_module.__file__ = str(ROOT / "Backend/core/save_resolution.py")

    class _NotASaveProvider:
        def __init__(self, context):
            self.context = context

    fake_module.NotASaveProvider = _NotASaveProvider
    sys.modules[fake_module_name] = fake_module
    try:
        try:
            load_save_provider(f"{fake_module_name}:NotASaveProvider")
        except SaveResolutionError as error:
            assert "SaveProvider contract" in str(error), error
        else:
            raise AssertionError("Expected load_save_provider to reject non-SaveProvider object.")
    finally:
        sys.modules.pop(fake_module_name, None)

    print("core_save_editor_workspace_registry_ok")


if __name__ == "__main__":
    main()
