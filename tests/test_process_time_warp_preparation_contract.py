from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "Backend/games/hades2/preparation.py").read_text()

assert "permissions['com.apple.security.get-task-allow'] = True" in source
assert "permissions['com.apple.security.cs.disable-library-validation'] = True" in source
assert source.count("com.apple.security.cs.disable-library-validation") >= 2, (
    "prepare must both write and verify the library-validation entitlement"
)
assert "已准备文件缺少调试权限" in source
assert "已准备文件缺少动态库加载权限" in source

print("process_time_warp_preparation_contract_ok")
