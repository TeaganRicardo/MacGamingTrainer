from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "Backend/games/hades2/preparation.py").read_text()

assert "permissions['com.apple.security.get-task-allow'] = True" in source
assert "permissions['com.apple.security.cs.disable-library-validation'] = True" in source
assert source.count("com.apple.security.cs.disable-library-validation") >= 2, (
    "prepare must both write and verify the library-validation entitlement"
)
assert "已准备文件缺少调试权限" in source
assert "def _stage_prepared(" in source
assert "'upgraded': True" in source
assert "previous_prepared_sha256" in source
assert "def _prepared_hashes(" in source
assert "prepared_entitlements.get('com.apple.security.cs.disable-library-validation')" in source

print("process_time_warp_preparation_contract_ok")
