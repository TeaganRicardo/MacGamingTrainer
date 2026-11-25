"""Behavior contract for Core Generic Save Editor, per-game codec/catalog seam, and Hades I/II adoption."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Backend"))
sys.path.insert(0, str(ROOT / "tests/fixtures"))

from core.adapter import GameAdapter, GameAdapterContext  # noqa: E402
from core.module_manifest import GameModuleManifest, SaveManagementSpec, SaveRootSpec  # noqa: E402
from core.protocol import JsonlRequestRouter  # noqa: E402
from core.save_editor import (  # noqa: E402
    CatalogSaveWorkspace,
    CoreSaveWorkspace,
    SaveDomainSpec,
    SaveEditorSpec,
    SaveFieldCatalog,
    SaveFieldChoice,
    SaveFieldSpec,
    discover_mapping_fields,
)
from core.save_restore import SaveBusyError, SaveRestoreTransaction  # noqa: E402
from core.save_service import CoreSaveService  # noqa: E402
from core.structured_save_edit import StructuredSaveEligibility  # noqa: E402
from games.hades.adapter import HadesAdapter  # noqa: E402
from games.hades.preferences import HadesPreferenceStore  # noqa: E402
from games.hades.save_document import HadesSaveDocument  # noqa: E402
from games.hades.save_workspace import HadesSaveWorkspace  # noqa: E402
from games.hades2.adapter import Hades2Adapter  # noqa: E402
from games.hades2.save_document import Hades2SaveDocument, Hades2SaveHeader, LuaTable as Hades2LuaTable  # noqa: E402
from games.hades2.save_workspace import Hades2SaveWorkspace  # noqa: E402
from hades_save import environment as hades_environment  # noqa: E402


class _SampleJsonCodec:
    """Pure JSON game codec enforcing top-level schema validation without Core edits."""

    def decode(self, payload: bytes) -> dict:
        doc = json.loads(payload.decode("utf-8"))
        if not isinstance(doc, dict) or doc.get("formatVersion") != 1:
            raise ValueError("Unsupported sample save format.")
        return doc

    def encode(self, document: dict) -> bytes:
        if not isinstance(document, dict) or document.get("formatVersion") != 1:
            raise TypeError("Sample save document must carry formatVersion=1.")
        return json.dumps(document, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")

    def load(self, path: Path) -> dict:
        return self.decode(path.read_bytes())


class _RoundedSampleJsonCodec(_SampleJsonCodec):
    def encode(self, document: dict) -> bytes:
        normalized = deepcopy(document)
        inventory = normalized.get("inventory")
        if isinstance(inventory, dict) and "speed" in inventory:
            inventory["speed"] = round(inventory["speed"], 1)
        return super().encode(normalized)


def _sample_spec(*, codec=None, include_parent_field: bool = False) -> SaveEditorSpec[dict]:
    catalog = SaveFieldCatalog(
        domains=(
            SaveDomainSpec("general", {"en": "General", "zh-CN": "常规"}, icon="gearshape"),
            SaveDomainSpec("inventory", {"en": "Inventory", "zh-CN": "物品栏"}, icon="bag"),
            SaveDomainSpec("advanced", {"en": "Advanced", "zh-CN": "高级"}, icon="wrench"),
        ),
        fields=(
            SaveFieldSpec(
                id="player.heroName",
                domain="general",
                path=("player", "heroName"),
                names={"en": "Hero Name", "zh-CN": "角色名称"},
                group_id="profile",
                group_names={"en": "Profile", "zh-CN": "档案"},
                owner_id="owner.player",
                owner_names={"en": "Player", "zh-CN": "角色"},
                value_type="string",
            ),
            SaveFieldSpec(
                id="player.hardcore",
                domain="general",
                path=("player", "hardcore"),
                names={"en": "Hardcore Mode", "zh-CN": "硬核模式"},
                group_id="profile",
                group_names={"en": "Profile", "zh-CN": "档案"},
                owner_id="owner.player",
                owner_names={"en": "Player", "zh-CN": "角色"},
                value_type="boolean",
            ),
            SaveFieldSpec(
                id="player.difficulty",
                domain="general",
                path=("player", "difficulty"),
                names={"en": "Difficulty", "zh-CN": "难度"},
                group_id="rules",
                group_names={"en": "Rules", "zh-CN": "规则"},
                owner_id="owner.rules",
                owner_names={"en": "Game Rules", "zh-CN": "游戏规则"},
                value_type="enum",
                choices=(
                    SaveFieldChoice("normal", {"en": "Normal", "zh-CN": "普通"}),
                    SaveFieldChoice("hard", {"en": "Hard", "zh-CN": "困难"}),
                ),
            ),
            SaveFieldSpec(
                id="inventory.gold",
                domain="inventory",
                path=("inventory", "gold"),
                names={"en": "Gold", "zh-CN": "金币"},
                group_id="currency",
                group_names={"en": "Currency", "zh-CN": "货币"},
                owner_id="owner.inventory",
                owner_names={"en": "Stash", "zh-CN": "仓库"},
                value_type="integer",
                min_value=0,
                max_value=999,
            ),
            SaveFieldSpec(
                id="inventory.speed",
                domain="inventory",
                path=("inventory", "speed"),
                names={"en": "Speed Multiplier", "zh-CN": "速度倍率"},
                group_id="currency",
                group_names={"en": "Currency", "zh-CN": "货币"},
                owner_id="owner.inventory",
                owner_names={"en": "Stash", "zh-CN": "仓库"},
                value_type="number",
                min_value=0.5,
                max_value=5.0,
            ),
            SaveFieldSpec(
                id="formatVersion",
                domain="advanced",
                path=("formatVersion",),
                names={"en": "Format Version", "zh-CN": "格式版本"},
                group_id="meta",
                group_names={"en": "Metadata", "zh-CN": "元数据"},
                owner_id="owner.meta",
                owner_names={"en": "Metadata", "zh-CN": "元数据"},
                value_type="integer",
                editable=False,
            ),
        ),
        discover_unknown=discover_mapping_fields,
    )
    eligibility = StructuredSaveEligibility(
        editor_files=lambda files: [
            {"rootId": row.root_id, "relativePath": row.relative_path, "label": row.relative_path}
            for row in files
            if row.relative_path.endswith(".json")
        ],
        is_source=lambda relative_path: relative_path.startswith("Slot") and relative_path.endswith(".json"),
        default_source=lambda files: (
            {"rootId": files[0].root_id, "relativePath": "Slot1.json"}
            if any(row.relative_path == "Slot1.json" for row in files)
            else None
        ),
    )
    spec = SaveEditorSpec(codec=codec or _SampleJsonCodec(), eligibility=eligibility, catalog=catalog)
    if include_parent_field:
        parent = SaveFieldSpec(
            id="inventory",
            domain="advanced",
            path=("inventory",),
            names={"en": "Inventory Object", "zh-CN": "物品栏对象"},
            group_id="inventory-parent",
            group_names={"en": "Inventory Object", "zh-CN": "物品栏对象"},
            owner_id="owner.inventory-parent",
            owner_names={"en": "Inventory", "zh-CN": "物品栏"},
            value_type="json",
        )
        spec = replace(spec, catalog=replace(spec.catalog, fields=(parent, *spec.catalog.fields)))
    return spec


class SampleJsonGameAdapter(GameAdapter):
    """Third-game adapter proving Save Editor works with zero Core edits."""

    def __init__(
        self, context: GameAdapterContext, *, max_open: int = 2, codec=None, include_parent_field: bool = False
    ) -> None:
        super().__init__(context)
        self.save_workspaces = CatalogSaveWorkspace.registry(
            lambda: self.save_service,
            _sample_spec(codec=codec, include_parent_field=include_parent_field),
            max_open=max_open,
        )

    def dispatch(self, command: str, params: dict, request_id: str):
        if command.startswith("save_editor_"):
            return self.dispatch_save_editor(command, params)
        if command == "status":
            return {"connected": False}
        raise ValueError("Unsupported sample command.")

    def close(self) -> None:
        if self.save_workspaces is not None:
            self.save_workspaces.clear()


def _write_sample_saves(saves_dir: Path) -> None:
    saves_dir.mkdir(parents=True, exist_ok=True)
    slot1 = {
        "formatVersion": 1,
        "player": {"heroName": "Astra", "hardcore": False, "difficulty": "normal"},
        "inventory": {"gold": 50, "speed": 1.25},
        "customStats": {"luckyCharm": True},
        "ephemeral": "remove-me",
        "opaqueNested": {"keep": [1, 2, {"tag": "preserved"}]},
    }
    slot2 = {
        "formatVersion": 1,
        "player": {"heroName": "OldHero", "hardcore": True, "difficulty": "hard"},
        "inventory": {"gold": 5, "speed": 1.0},
    }
    (saves_dir / "Slot1.json").write_text(json.dumps(slot1, sort_keys=True), encoding="utf-8")
    (saves_dir / "Slot2.json").write_text(json.dumps(slot2, sort_keys=True), encoding="utf-8")


def main() -> None:
    assert issubclass(CatalogSaveWorkspace, CoreSaveWorkspace)
    assert issubclass(HadesSaveWorkspace, CoreSaveWorkspace)
    assert issubclass(Hades2SaveWorkspace, CoreSaveWorkspace)

    discovered_collision_check = discover_mapping_fields(
        {"a": {"b": 1}, "a.b": 2, "a/b": 3, "$root": 4, "root": {"x": 5}},
        frozenset(),
    )
    assert len({field.id for field in discovered_collision_check}) == 5
    by_path = {field.path: field for field in discovered_collision_check}
    assert by_path[("$root",)].owner_id == "owner:$root"
    assert by_path[("root", "x")].owner_id == "owner:root"
    assert by_path[("$root",)].owner_id != by_path[("root", "x")].owner_id

    typed_document = {1: {"v": 10}, "1": {"v": 20}, "builtins.int:1": {"v": 30}}
    typed_fields = discover_mapping_fields(typed_document, frozenset())
    assert len({field.id for field in typed_fields}) == 3
    assert len({field.owner_id for field in typed_fields}) == 3
    typed_spec = _sample_spec()
    typed_spec = replace(typed_spec, catalog=replace(typed_spec.catalog, fields=()))
    typed_workspace = CatalogSaveWorkspace(SimpleNamespace(document=typed_document), typed_spec)
    assert typed_workspace.query()["total"] == 3
    typed_by_path = {field.path: field for field in typed_fields}
    integer_field = typed_by_path[(1, "v")]
    string_field = typed_by_path[("1", "v")]
    assert typed_workspace.detail(integer_field.id)["row"]["value"] == 10
    assert typed_workspace.detail(string_field.id)["row"]["value"] == 20
    integer_field.write_value(typed_document, 11)
    string_field.write_value(typed_document, 21)
    assert typed_document == {1: {"v": 11}, "1": {"v": 21}, "builtins.int:1": {"v": 30}}

    for key in (False, 1.5, None, b"key", (1, "key")):
        paired = discover_mapping_fields({key: 1, str(key): 2}, frozenset())
        assert len({field.id for field in paired}) == 2

    # A custom catalog/discoverer also cannot silently shadow a field ID.
    collision = replace(string_field, id=integer_field.id)
    for curated, extras in (
        ((integer_field, collision), ()),
        ((integer_field,), (collision,)),
        ((), (integer_field, collision)),
    ):
        collision_spec = replace(
            typed_spec,
            catalog=replace(typed_spec.catalog, fields=curated, discover_unknown=lambda _document, _known: extras),
        )
        collision_workspace = CatalogSaveWorkspace(SimpleNamespace(document=typed_document), collision_spec)
        try:
            collision_workspace.query()
        except ValueError as error:
            assert integer_field.id in str(error)
        else:
            raise AssertionError("Duplicate field identity was silently accepted")

    ancestor_skip_check = discover_mapping_fields(
        {"knownParent": {}, "nonEmptyParent": {"known": 1, "sibling": 2}},
        frozenset({("knownParent", "leaf"), ("nonEmptyParent", "known")}),
    )
    assert [field.path for field in ancestor_skip_check] == [("nonEmptyParent", "sibling")]

    with tempfile.TemporaryDirectory(prefix="mgt-generic-save-editor-") as td:
        root = Path(td)

        # 1. Brand-new 3rd game running purely on Core Save Editor + codec + catalog.
        sample_saves = root / "sample/saves"
        _write_sample_saves(sample_saves)
        sample_spec = SaveManagementSpec(
            roots=(SaveRootSpec("main", str(sample_saves), ("Slot*.json",)),),
            provider=None,
            hot_backup=True,
            restore_policy="hotPreferred",
            staged_restore=True,
        )
        sample_ctx = GameAdapterContext(
            game_id="sample_json",
            display_name="Sample JSON Game",
            module_protocol_version=1,
            module_dir=root / "sample/module",
            public_metadata={"protocolVersion": 1},
            save_management=sample_spec,
            home=root / "sample/home",
        )
        # Generic editing is cold by default even if save backups/restores support hot mode.
        policy_saves = root / "policy/saves"
        _write_sample_saves(policy_saves)
        policy_spec = replace(sample_spec, roots=(replace(sample_spec.roots[0], path=str(policy_saves)),))
        running = {"value": False}
        policy_service = CoreSaveService("policy_json", policy_spec, root / "policy/data", lambda: running["value"])
        selected = {"rootId": "main", "relativePath": "Slot1.json"}
        policy_editor = CatalogSaveWorkspace.open(policy_service, _sample_spec(), source=selected, target=selected)
        policy_generation = policy_editor.baseline_generation
        policy_editor.stage("inventory.gold", "set", 71, baseline_generation=policy_generation)
        policy_before = (policy_saves / "Slot1.json").read_bytes()
        running["value"] = True
        try:
            policy_editor.apply(baseline_generation=policy_generation)
        except SaveBusyError:
            pass
        else:
            raise AssertionError("Generic Save Editor wrote while running without an explicit policy")
        assert (policy_saves / "Slot1.json").read_bytes() == policy_before
        assert policy_service.list_state()["snapshots"] == []
        assert policy_editor.baseline_generation == policy_generation
        assert policy_editor.review()["count"] == 1 and not policy_editor.recovery_unresolved
        running["value"] = False
        assert policy_editor.apply(baseline_generation=policy_generation)["hot"] is False

        # An owning module may opt in; the same verified transaction retains the exact prior bytes.
        running["value"] = True
        hot_editor = CatalogSaveWorkspace.open(
            policy_service, replace(_sample_spec(), allow_running=True), source=selected, target=selected,
        )
        hot_before = (policy_saves / "Slot1.json").read_bytes()
        hot_editor.stage("inventory.gold", "set", 72, baseline_generation=hot_editor.baseline_generation)
        hot_receipt = hot_editor.apply(baseline_generation=hot_editor.baseline_generation)
        assert hot_receipt["hot"] is True and hot_receipt["runtimeReloaded"] is False
        prior = policy_service.store.load_verified_snapshot(hot_receipt["previousSnapshotId"])
        assert (prior["root"] / "files/main/Slot1.json").read_bytes() == hot_before

        # Review must describe the codec-normalized bytes that Apply will install.
        rounded_saves = root / "rounded/saves"
        _write_sample_saves(rounded_saves)
        rounded_spec = replace(sample_spec, roots=(replace(sample_spec.roots[0], path=str(rounded_saves)),))
        rounded_ctx = replace(sample_ctx, game_id="rounded_json", save_management=rounded_spec, home=root / "rounded/home")
        rounded_adapter = SampleJsonGameAdapter(rounded_ctx, codec=_RoundedSampleJsonCodec())
        rounded_router = JsonlRequestRouter(rounded_adapter, save_data_root=root / "rounded/data", target_running_probe=lambda: False)
        try:
            rounded_open = rounded_router.handle({
                "id": "rounded-open", "command": "save_editor_open",
                "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
            })["result"]
            rounded_ws, rounded_gen = rounded_open["workspaceId"], rounded_open["baselineGeneration"]
            rounded_router.handle({
                "id": "rounded-target", "command": "save_editor_target",
                "params": {"workspaceId": rounded_ws, "baselineGeneration": rounded_gen,
                           "target": {"rootId": "main", "relativePath": "Slot1.json"}},
            })
            rounded_router.handle({
                "id": "rounded-stage", "command": "save_editor_stage",
                "params": {"workspaceId": rounded_ws, "baselineGeneration": rounded_gen,
                           "entryId": "inventory.speed", "operation": "set", "value": 1.72},
            })
            rounded_review = rounded_router.handle({
                "id": "rounded-review", "command": "save_editor_review",
                "params": {"workspaceId": rounded_ws, "baselineGeneration": rounded_gen},
            })["result"]
            assert rounded_review["actions"][0]["after"] == "1.7"
            assert rounded_review["actions"][0]["value"] == 1.7
            rounded_apply = rounded_router.handle({
                "id": "rounded-apply", "command": "save_editor_apply",
                "params": {"workspaceId": rounded_ws, "baselineGeneration": rounded_gen},
            })
            assert rounded_apply["ok"] is True, rounded_apply
            assert json.loads((rounded_saves / "Slot1.json").read_text(encoding="utf-8"))["inventory"]["speed"] == 1.7
        finally:
            rounded_router.close()

        # Parent/child staged fields are rejected because their combined result
        # cannot be represented as two independent signed-off actions.
        overlap_adapter = SampleJsonGameAdapter(sample_ctx, include_parent_field=True)
        overlap_router = JsonlRequestRouter(overlap_adapter, save_data_root=root / "overlap/data", target_running_probe=lambda: False)
        try:
            overlap_open = overlap_router.handle({
                "id": "overlap-open", "command": "save_editor_open",
                "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
            })["result"]
            overlap_ws, overlap_gen = overlap_open["workspaceId"], overlap_open["baselineGeneration"]
            overlap_router.handle({
                "id": "overlap-stage-parent", "command": "save_editor_stage",
                "params": {"workspaceId": overlap_ws, "baselineGeneration": overlap_gen,
                           "entryId": "inventory", "operation": "set", "value": {"gold": 10, "speed": 1.0}},
            })
            overlap_child = overlap_router.handle({
                "id": "overlap-stage-child", "command": "save_editor_stage",
                "params": {"workspaceId": overlap_ws, "baselineGeneration": overlap_gen,
                           "entryId": "inventory.gold", "operation": "set", "value": 20},
            })
            assert overlap_child["ok"] is False and overlap_child["error"]["code"] == "invalid_request"
        finally:
            overlap_router.close()

        sample_adapter = SampleJsonGameAdapter(sample_ctx, max_open=2)
        router = JsonlRequestRouter(sample_adapter, save_data_root=root / "sample/data", target_running_probe=lambda: False)
        try:
            inv = router.handle({"id": "inv", "command": "save_editor_inventory", "params": {}})
            assert inv["ok"] is True
            assert len(inv["result"]["sources"]) == 2
            assert inv["result"]["defaultSource"] == {"rootId": "main", "relativePath": "Slot1.json"}

            opened = router.handle({"id": "open-zh", "command": "save_editor_open", "params": {"language": "zh-CN"}})
            assert opened["ok"] is True, opened
            res = opened["result"]
            ws_id = res["workspaceId"]
            gen = res["baselineGeneration"]
            assert res["target"] is None
            assert [d["title"] for d in res["domains"]] == ["常规", "物品栏", "高级"]

            # Owner-complete pagination: owner.player has 2 fields (heroName, hardcore), so limit=1 returns whole owner!
            page1 = router.handle(
                {
                    "id": "q-page1",
                    "command": "save_editor_query",
                    "params": {"workspaceId": ws_id, "domain": "general", "language": "zh-CN", "limit": 1},
                }
            )["result"]
            assert [r["id"] for r in page1["rows"]] == ["player.heroName", "player.hardcore"]
            assert page1["total"] == 3 and page1["nextOffset"] == 2
            assert page1["rows"][0]["name"] == "角色名称"
            page2 = router.handle(
                {
                    "id": "q-page2",
                    "command": "save_editor_query",
                    "params": {
                        "workspaceId": ws_id,
                        "domain": "general",
                        "language": "en",
                        "offset": page1["nextOffset"],
                        "limit": 1,
                    },
                }
            )["result"]
            assert [r["id"] for r in page2["rows"]] == ["player.difficulty"]

            # Unknown round-trippable fields appear in "advanced" as editable with unknown-impact warning.
            adv = router.handle(
                {
                    "id": "q-adv",
                    "command": "save_editor_query",
                    "params": {"workspaceId": ws_id, "domain": "advanced", "language": "en", "limit": 50},
                }
            )["result"]
            adv_by_id = {row["id"]: row for row in adv["rows"]}
            assert adv_by_id["formatVersion"]["editable"] is False
            assert adv_by_id["discovered:customStats/luckyCharm"]["editable"] is True
            assert "unknown" in adv_by_id["discovered:customStats/luckyCharm"]["warning"].lower()
            assert "unset" in adv_by_id["discovered:ephemeral"]["operations"]

            # Detail lookup.
            det = router.handle(
                {
                    "id": "det",
                    "command": "save_editor_detail",
                    "params": {"workspaceId": ws_id, "entryId": "inventory.gold", "language": "zh-CN"},
                }
            )["result"]["row"]
            assert det["name"] == "金币" and det["value"] == 50

            # Target selection requires baseline.
            bad_target = router.handle(
                {
                    "id": "bad-target",
                    "command": "save_editor_target",
                    "params": {"workspaceId": ws_id, "target": {"rootId": "main", "relativePath": "Slot2.json"}},
                }
            )
            assert bad_target["ok"] is False
            target_workspace = sample_adapter.save_workspaces[ws_id]
            with patch.object(target_workspace, "summary", side_effect=RuntimeError("summary unavailable")):
                failed_target = router.handle(
                    {
                        "id": "failed-target-summary",
                        "command": "save_editor_target",
                        "params": {
                            "workspaceId": ws_id,
                            "baselineGeneration": gen,
                            "target": {"rootId": "main", "relativePath": "Slot2.json"},
                        },
                    }
                )
            assert failed_target["ok"] is False
            assert target_workspace.session.target is None, "failed target confirmation left an Apply destination installed"

            targeted = router.handle(
                {
                    "id": "good-target",
                    "command": "save_editor_target",
                    "params": {
                        "workspaceId": ws_id,
                        "baselineGeneration": gen,
                        "target": {"rootId": "main", "relativePath": "Slot2.json"},
                    },
                }
            )
            assert targeted["ok"] is True
            assert targeted["result"]["target"] == {"rootId": "main", "relativePath": "Slot2.json"}

            # Invalid language or overflow integers fail closed without corrupting pending state.
            for bad_lang_cmd, bad_lang_params in (
                ("save_editor_open", {"language": 123}),
                ("save_editor_detail", {"workspaceId": ws_id, "entryId": "inventory.gold", "language": 123}),
                (
                    "save_editor_stage",
                    {
                        "workspaceId": ws_id,
                        "baselineGeneration": gen,
                        "entryId": "inventory.gold",
                        "operation": "set",
                        "value": 100,
                        "language": 123,
                    },
                ),
            ):
                bad_lang_res = router.handle({"id": f"bad-lang-{bad_lang_cmd}", "command": bad_lang_cmd, "params": bad_lang_params})
                assert bad_lang_res["ok"] is False, (bad_lang_cmd, bad_lang_res)

            # Staging validates types/bounds cleanly without corrupting pending state.
            for bad_id, eid, op, val in (
                ("bad-bool", "player.hardcore", "set", "yes"),
                ("bad-int", "inventory.gold", "set", 1500),
                ("bad-huge-int", "inventory.gold", "set", 10**400),
                ("bad-huge-number", "inventory.speed", "set", 10**400),
                ("bad-float-int", "inventory.gold", "set", 10.5),
                ("bad-enum", "player.difficulty", "set", "nightmare"),
                ("bad-readonly", "formatVersion", "set", 2),
            ):
                rej = router.handle(
                    {
                        "id": bad_id,
                        "command": "save_editor_stage",
                        "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": eid, "operation": op, "value": val},
                    }
                )
                assert rej["ok"] is False and rej["error"]["code"] == "invalid_request", (bad_id, rej)
            assert router.handle({"id": "rev0", "command": "save_editor_review", "params": {"workspaceId": ws_id}})["result"]["count"] == 0

            # Nested bool vs int in JSON arrays/mappings is treated as a real change, not a no-op.
            nested_bool_stage = router.handle(
                {
                    "id": "st-nested-bool",
                    "command": "save_editor_stage",
                    "params": {
                        "workspaceId": ws_id,
                        "baselineGeneration": gen,
                        "entryId": "discovered:opaqueNested/keep",
                        "operation": "set",
                        "value": [True, 2, {"tag": "preserved"}],
                    },
                }
            )
            assert nested_bool_stage["ok"] is True and nested_bool_stage["result"]["count"] == 1
            router.handle({"id": "canc-nested-bool", "command": "save_editor_cancel", "params": {"workspaceId": ws_id, "baselineGeneration": gen}})

            # Valid stage + noop unstage + explicit unstage + cancel.
            st1 = router.handle(
                {
                    "id": "st1",
                    "command": "save_editor_stage",
                    "params": {
                        "workspaceId": ws_id,
                        "baselineGeneration": gen,
                        "entryId": "inventory.gold",
                        "operation": "set",
                        "value": 777,
                        "language": "zh-CN",
                    },
                }
            )["result"]
            assert st1["count"] == 1 and st1["actions"][0]["before"] == "50" and st1["actions"][0]["after"] == "777"
            # Setting back to baseline removes from pending cleanly.
            st_reset = router.handle(
                {
                    "id": "st-reset",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": "inventory.gold", "operation": "set", "value": 50},
                }
            )["result"]
            assert st_reset["count"] == 0

            router.handle(
                {
                    "id": "st2",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": "inventory.gold", "operation": "set", "value": 888},
                }
            )
            unstaged = router.handle(
                {
                    "id": "unst",
                    "command": "save_editor_unstage",
                    "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": "inventory.gold"},
                }
            )["result"]
            assert unstaged["count"] == 0

            # Stage curated + unknown edits, cancel once, then re-stage and apply.
            router.handle(
                {
                    "id": "st-tmp",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": "player.hardcore", "operation": "set", "value": True},
                }
            )
            canceled = router.handle(
                {"id": "canc", "command": "save_editor_cancel", "params": {"workspaceId": ws_id, "baselineGeneration": gen}}
            )["result"]
            assert canceled["count"] == 0

            for idx, (eid, op, val) in enumerate(
                (
                    ("player.heroName", "set", "Selene"),
                    ("player.hardcore", "set", True),
                    ("player.difficulty", "set", "hard"),
                    ("inventory.gold", "set", 650),
                    ("inventory.speed", "set", 2.5),
                    ("discovered:customStats/luckyCharm", "set", False),
                    ("discovered:ephemeral", "unset", None),
                ),
                start=1,
            ):
                ok_stage = router.handle(
                    {
                        "id": f"stage-{idx}",
                        "command": "save_editor_stage",
                        "params": {
                            "workspaceId": ws_id,
                            "baselineGeneration": gen,
                            "entryId": eid,
                            "operation": op,
                            "value": val,
                        },
                    }
                )
                assert ok_stage["ok"] is True, ok_stage

            # Workspace limit protects dirty CatalogSaveWorkspace when max_open slots are filled.
            second_open = router.handle(
                {
                    "id": "open-2",
                    "command": "save_editor_open",
                    "params": {"source": {"rootId": "main", "relativePath": "Slot2.json"}},
                }
            )
            assert second_open["ok"] is True
            ws2_id = second_open["result"]["workspaceId"]
            ws2_gen = second_open["result"]["baselineGeneration"]
            router.handle(
                {
                    "id": "stage-ws2",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": ws2_id, "baselineGeneration": ws2_gen, "entryId": "inventory.gold", "operation": "set", "value": 99},
                }
            )
            limit_hit = router.handle(
                {
                    "id": "open-limit",
                    "command": "save_editor_open",
                    "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
                }
            )
            assert limit_hit["ok"] is False and limit_hit["error"]["code"] == "workspace_limit", limit_hit
            router.handle({"id": "close-ws2", "command": "save_editor_close", "params": {"workspaceId": ws2_id}})

            # Apply rejects missing/stale baseline, succeeds with current baseline, and rotates baseline.
            stale_apply = router.handle({"id": "apply-stale", "command": "save_editor_apply", "params": {"workspaceId": ws_id}})
            assert stale_apply["ok"] is False

            slot2_before = (sample_saves / "Slot2.json").read_bytes()
            applied = router.handle(
                {"id": "apply-ok", "command": "save_editor_apply", "params": {"workspaceId": ws_id, "baselineGeneration": gen}}
            )
            assert applied["ok"] is True, applied
            receipt = applied["result"]
            new_gen = receipt["baselineGeneration"]
            assert receipt["applied"] is True and receipt["verified"] is True
            assert new_gen != gen
            assert receipt["previousSnapshotId"]

            # Old baseline is rejected after apply.
            stale_after = router.handle(
                {
                    "id": "stage-stale",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": ws_id, "baselineGeneration": gen, "entryId": "inventory.gold", "operation": "set", "value": 1},
                }
            )
            assert stale_after["ok"] is False

            # Re-open Slot2.json from disk and verify edits + unknown + untouched sibling data persisted.
            reopened = router.handle(
                {
                    "id": "reopen",
                    "command": "save_editor_open",
                    "params": {"source": {"rootId": "main", "relativePath": "Slot2.json"}},
                }
            )["result"]
            re_ws = reopened["workspaceId"]
            re_rows = {
                row["id"]: row
                for row in router.handle(
                    {"id": "re-q", "command": "save_editor_query", "params": {"workspaceId": re_ws, "limit": 50}}
                )["result"]["rows"]
            }
            assert re_rows["player.heroName"]["value"] == "Selene"
            assert re_rows["player.hardcore"]["value"] is True
            assert re_rows["player.difficulty"]["value"] == "hard"
            assert re_rows["inventory.gold"]["value"] == 650
            assert re_rows["inventory.speed"]["value"] == 2.5
            assert re_rows["discovered:customStats/luckyCharm"]["value"] is False
            assert "discovered:ephemeral" not in re_rows
            slot2_disk = json.loads((sample_saves / "Slot2.json").read_text(encoding="utf-8"))
            assert slot2_disk["opaqueNested"] == {"keep": [1, 2, {"tag": "preserved"}]}
            assert receipt["installedSHA256"] != sha256(slot2_before).hexdigest()

            # Managed backup editing requires explicit target selection.
            snap = router.save_service.backup()
            bak_open = router.handle(
                {
                    "id": "bak-open",
                    "command": "save_editor_open",
                    "params": {"snapshotId": snap["id"], "source": {"rootId": "main", "relativePath": "Slot2.json"}},
                }
            )["result"]
            assert bak_open["source"]["kind"] == "managedBackup" and bak_open["target"] is None
            bak_ws, bak_gen = bak_open["workspaceId"], bak_open["baselineGeneration"]
            router.handle(
                {
                    "id": "bak-stage",
                    "command": "save_editor_stage",
                    "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen, "entryId": "inventory.gold", "operation": "set", "value": 42},
                }
            )
            no_target_apply = router.handle(
                {"id": "bak-apply-no-target", "command": "save_editor_apply", "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen}}
            )
            assert no_target_apply["ok"] is False

            # Concurrent write race rolls back cleanly leaving target untouched.
            router.handle(
                {
                    "id": "bak-target",
                    "command": "save_editor_target",
                    "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen, "target": {"rootId": "main", "relativePath": "Slot1.json"}},
                }
            )
            orig_slot1 = (sample_saves / "Slot1.json").read_bytes()
            orig_capture = SaveRestoreTransaction._capture_rollback

            def _racing_capture(self, *args, **kwargs):
                res = orig_capture(self, *args, **kwargs)
                (sample_saves / "Slot1.json").write_bytes(b'{"formatVersion":1,"raced":true}')
                return res

            with patch.object(SaveRestoreTransaction, "_capture_rollback", _racing_capture):
                raced_reply = router.handle(
                    {"id": "bak-apply-race", "command": "save_editor_apply", "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen}}
                )
            assert raced_reply["ok"] is False and isinstance(raced_reply["error"], dict)
            # Restore original Slot1 bytes for subsequent recovery test, verifying target stayed at raced value (rolled back from our write).
            assert json.loads((sample_saves / "Slot1.json").read_text(encoding="utf-8")) == {"formatVersion": 1, "raced": True}
            (sample_saves / "Slot1.json").write_bytes(orig_slot1)

            # Lost ack + failed rollback locks workspace and refuses replay.
            real_replace = SaveRestoreTransaction._replace_file
            replace_calls = []

            def _fail_ack_and_rollback(self, source, destination, digest, **options):
                replace_calls.append(Path(destination))
                if len(replace_calls) == 1:
                    real_replace(self, source, destination, digest, **options)
                    raise OSError("synthetic lost write ack")
                raise OSError("synthetic failed rollback")

            with patch.object(SaveRestoreTransaction, "_replace_file", _fail_ack_and_rollback):
                fail_reply = router.handle(
                    {"id": "bak-apply-lost", "command": "save_editor_apply", "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen}}
                )
            assert fail_reply["ok"] is False and fail_reply["error"]["code"] == "rollback_failed", fail_reply
            assert fail_reply["error"].get("recoveryPath")
            assert len(replace_calls) == 2
            replay_reply = router.handle(
                {"id": "bak-apply-replay", "command": "save_editor_apply", "params": {"workspaceId": bak_ws, "baselineGeneration": bak_gen}}
            )
            assert replay_reply["ok"] is False and replay_reply["error"]["code"] == "rollback_failed"
            assert len(replace_calls) == 2, "unresolved recovery workspace replayed Apply"
            assert sample_adapter.save_workspaces[bak_ws].recovery_unresolved is True
            # A second workspace and a fresh Core Save service must inherit the
            # physical target fence. An unrelated save target remains writable.
            second_open = router.handle({
                "id": "second-open-slot1",
                "command": "save_editor_open",
                "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
            })["result"]
            second_ws = second_open["workspaceId"]
            second_gen = second_open["baselineGeneration"]
            router.handle({
                "id": "second-target-slot1",
                "command": "save_editor_target",
                "params": {"workspaceId": second_ws, "baselineGeneration": second_gen,
                           "target": {"rootId": "main", "relativePath": "Slot1.json"}},
            })
            router.handle({
                "id": "second-stage-slot1",
                "command": "save_editor_stage",
                "params": {"workspaceId": second_ws, "baselineGeneration": second_gen,
                           "entryId": "inventory.gold", "operation": "set", "value": 77},
            })
            second_apply = router.handle({
                "id": "second-apply-slot1",
                "command": "save_editor_apply",
                "params": {"workspaceId": second_ws, "baselineGeneration": second_gen},
            })
            assert second_apply["ok"] is False and second_apply["error"]["code"] == "rollback_failed"

            fresh_adapter = SampleJsonGameAdapter(sample_ctx)
            fresh_router = JsonlRequestRouter(
                fresh_adapter, save_data_root=root / "sample/data", target_running_probe=lambda: False
            )
            try:
                fresh_open = fresh_router.handle({
                    "id": "fresh-open-slot1", "command": "save_editor_open",
                    "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
                })["result"]
                fresh_ws, fresh_gen = fresh_open["workspaceId"], fresh_open["baselineGeneration"]
                fresh_router.handle({
                    "id": "fresh-target-slot1", "command": "save_editor_target",
                    "params": {"workspaceId": fresh_ws, "baselineGeneration": fresh_gen,
                               "target": {"rootId": "main", "relativePath": "Slot1.json"}},
                })
                fresh_router.handle({
                    "id": "fresh-stage-slot1", "command": "save_editor_stage",
                    "params": {"workspaceId": fresh_ws, "baselineGeneration": fresh_gen,
                               "entryId": "inventory.gold", "operation": "set", "value": 88},
                })
                fresh_apply = fresh_router.handle({
                    "id": "fresh-apply-slot1", "command": "save_editor_apply",
                    "params": {"workspaceId": fresh_ws, "baselineGeneration": fresh_gen},
                })
                assert fresh_apply["ok"] is False and fresh_apply["error"]["code"] == "rollback_failed"

                # Explicitly restore the captured baseline bytes. The fence is
                # then durably marked resolved, and later writes remain allowed.
                recovery_root = Path(fail_reply["error"]["recoveryPath"])
                baseline_file = recovery_root / "files/main/Slot1.json"
                (sample_saves / "Slot1.json").write_bytes(baseline_file.read_bytes())
                resolved_adapter = SampleJsonGameAdapter(sample_ctx)
                resolved_router = JsonlRequestRouter(
                    resolved_adapter, save_data_root=root / "sample/data", target_running_probe=lambda: False
                )
                try:
                    for index, value in enumerate((111, 112), start=1):
                        resolved_open = resolved_router.handle({
                            "id": f"resolved-open-{index}", "command": "save_editor_open",
                            "params": {"source": {"rootId": "main", "relativePath": "Slot1.json"}},
                        })["result"]
                        resolved_ws, resolved_gen = resolved_open["workspaceId"], resolved_open["baselineGeneration"]
                        resolved_router.handle({
                            "id": f"resolved-target-{index}", "command": "save_editor_target",
                            "params": {"workspaceId": resolved_ws, "baselineGeneration": resolved_gen,
                                       "target": {"rootId": "main", "relativePath": "Slot1.json"}},
                        })
                        resolved_router.handle({
                            "id": f"resolved-stage-{index}", "command": "save_editor_stage",
                            "params": {"workspaceId": resolved_ws, "baselineGeneration": resolved_gen,
                                       "entryId": "inventory.gold", "operation": "set", "value": value},
                        })
                        resolved_apply = resolved_router.handle({
                            "id": f"resolved-apply-{index}", "command": "save_editor_apply",
                            "params": {"workspaceId": resolved_ws, "baselineGeneration": resolved_gen},
                        })
                        assert resolved_apply["ok"] is True, resolved_apply
                finally:
                    resolved_router.close()

                unrelated_open = fresh_router.handle({
                    "id": "fresh-open-slot2", "command": "save_editor_open",
                    "params": {"source": {"rootId": "main", "relativePath": "Slot2.json"}},
                })["result"]
                unrelated_ws, unrelated_gen = unrelated_open["workspaceId"], unrelated_open["baselineGeneration"]
                fresh_router.handle({
                    "id": "fresh-target-slot2", "command": "save_editor_target",
                    "params": {"workspaceId": unrelated_ws, "baselineGeneration": unrelated_gen,
                               "target": {"rootId": "main", "relativePath": "Slot2.json"}},
                })
                fresh_router.handle({
                    "id": "fresh-stage-slot2", "command": "save_editor_stage",
                    "params": {"workspaceId": unrelated_ws, "baselineGeneration": unrelated_gen,
                               "entryId": "inventory.gold", "operation": "set", "value": 99},
                })
                unrelated_apply = fresh_router.handle({
                    "id": "fresh-apply-slot2", "command": "save_editor_apply",
                    "params": {"workspaceId": unrelated_ws, "baselineGeneration": unrelated_gen},
                })
                assert unrelated_apply["ok"] is True, unrelated_apply
            finally:
                fresh_router.close()
        finally:
            router.close()

        # 2. Hades I adoption through CoreSaveWorkspace + SaveEditorWorkspaceRegistry.
        h1_saves, h1_seed_service = hades_environment(root / "hades1/env")
        h1_ctx = GameAdapterContext(
            game_id="hades",
            display_name="Hades",
            module_protocol_version=3,
            module_dir=ROOT / "Backend/games/hades",
            public_metadata={"protocolVersion": 3},
            save_management=h1_seed_service.spec,
            home=root / "hades1/home",
        )
        h1_adapter = HadesAdapter(
            h1_ctx,
            runtime=SimpleNamespace(close=lambda: None),
            preferences=HadesPreferenceStore(root / "hades1/prefs.json"),
        )
        h1_router = JsonlRequestRouter(h1_adapter, save_data_root=root / "hades1/data", target_running_probe=lambda: False)
        try:
            h1_open = h1_router.handle(
                {
                    "id": "h1-open",
                    "command": "save_editor_open",
                    "params": {
                        "source": {"rootId": "main", "relativePath": "Profile1.sav"},
                        "target": {"rootId": "main", "relativePath": "Profile2.sav"},
                    },
                }
            )["result"]
            h1_ws, h1_gen = h1_open["workspaceId"], h1_open["baselineGeneration"]
            h1_stage = h1_router.handle(
                {
                    "id": "h1-stage",
                    "command": "save_editor_stage",
                    "params": {
                        "workspaceId": h1_ws,
                        "baselineGeneration": h1_gen,
                        "entryId": "resource:MetaPoints",
                        "operation": "set",
                        "value": {"luaType": "number", "value": 432},
                    },
                }
            )
            assert h1_stage["ok"] is True
            h1_apply = h1_router.handle(
                {"id": "h1-apply", "command": "save_editor_apply", "params": {"workspaceId": h1_ws, "baselineGeneration": h1_gen}}
            )
            assert h1_apply["ok"] is True and h1_apply["result"]["verified"] is True
            assert HadesSaveDocument.load(h1_saves / "Profile2.sav").lua_state["GameState"]["Resources"]["MetaPoints"] == 432
        finally:
            h1_router.close()

        # 3. Hades II adoption through CoreSaveWorkspace + SaveEditorWorkspaceRegistry.
        h2_home = root / "hades2/home"
        h2_saves = root / "hades2/saves"
        h2_saves.mkdir(parents=True)
        profile = b"Profile1"
        (h2_saves / "activeProfile").write_bytes(b"SGB1" + struct.pack("<I", len(profile)) + profile)

        def tbl(items):
            return Hades2LuaTable(0, len(items), items)

        h2_root = tbl([
            ("GameState", tbl([("Resources", tbl([("MetaCurrency", 15.0)])), ("GameplayTime", 50.0), ("TotalTime", 80.0)])),
            ("CurrentRun", tbl([])),
        ])
        h2_header = Hades2SaveHeader(
            game_version=0x12,
            save_flags=0,
            timestamp=100,
            location="Crossroads",
            completed_runs=1,
            accumulated_meta_points=0,
            active_shrine_points=0,
            meta_upgrade_level=0,
            cosmetics_points=0,
            easy_mode=0,
            hard_mode=0,
            notable_lua_data=("GameState", "CurrentRun"),
            map_name="Hub_Main",
            next_map_name="F_Opening01",
        )
        (h2_saves / "Profile1.sav").write_bytes(Hades2SaveDocument(h2_header, [h2_root]).to_bytes())
        h2_manifest = GameModuleManifest.load(ROOT / "Backend/games/hades2/module.json")
        h2_spec = SaveManagementSpec(
            roots=(SaveRootSpec("main", str(h2_saves), ("Profile*.sav", "activeProfile")),),
            provider="games.hades2.save_provider:Hades2SaveProvider",
            hot_backup=True,
            restore_policy="hotPreferred",
            staged_restore=True,
        )
        h2_base_ctx = GameAdapterContext.from_manifest(h2_manifest, home=h2_home)
        h2_ctx = GameAdapterContext(
            game_id=h2_base_ctx.game_id,
            display_name=h2_base_ctx.display_name,
            module_protocol_version=h2_base_ctx.module_protocol_version,
            module_dir=h2_base_ctx.module_dir,
            public_metadata=h2_base_ctx.public_metadata,
            process_name=h2_base_ctx.process_name,
            save_management=h2_spec,
            executable_path_suffix=h2_base_ctx.executable_path_suffix,
            steam_launch_url=h2_base_ctx.steam_launch_url,
            home=h2_home,
        )
        h2_stub_session = SimpleNamespace(
            pid=None,
            pending_resume_pid=None,
            cleanup_pending=False,
            alive=lambda: False,
            close=lambda: None,
            invalidate_generation=lambda: None,
        )
        h2_adapter = Hades2Adapter(
            context=h2_ctx,
            resident_session=h2_stub_session,
            time_warp_controller=object(),
            game_path=root / "AbsentHades2.app",
        )
        h2_router = JsonlRequestRouter(h2_adapter, save_data_root=root / "hades2/data", target_running_probe=lambda: False)
        try:
            h2_open = h2_router.handle({"id": "h2-open", "command": "save_editor_open", "params": {}})["result"]
            h2_ws, h2_gen = h2_open["workspaceId"], h2_open["baselineGeneration"]
            h2_stage = h2_router.handle(
                {
                    "id": "h2-stage",
                    "command": "save_editor_stage",
                    "params": {
                        "workspaceId": h2_ws,
                        "baselineGeneration": h2_gen,
                        "entryId": "resource:MetaCurrency",
                        "operation": "set",
                        "value": 345,
                        "language": "en",
                    },
                }
            )
            assert h2_stage["ok"] is True
            h2_apply = h2_router.handle(
                {"id": "h2-apply", "command": "save_editor_apply", "params": {"workspaceId": h2_ws, "baselineGeneration": h2_gen}}
            )
            assert h2_apply["ok"] is True and h2_apply["result"]["verified"] is True
            assert Hades2SaveDocument.load(h2_saves / "Profile1.sav").lua_state["GameState"]["Resources"]["MetaCurrency"] == 345.0
        finally:
            h2_router.close()

    print("core_generic_save_editor_ok")


if __name__ == "__main__":
    main()
