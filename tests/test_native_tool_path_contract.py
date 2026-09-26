import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "Backend/games/hades2/command_router.py": {"run": ["/usr/bin/open", "/usr/bin/open"]},
    "Backend/games/hades2/transport.py": {"check_output": ["/usr/bin/xcrun"]},
    "Backend/core/process_time_warp.py": {"check_output": ["/usr/bin/xcrun"]},
}

for relative, expected_by_method in EXPECTED.items():
    path = ROOT / relative
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = {method: [] for method in expected_by_method}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "subprocess":
            continue
        method = node.func.attr
        assert method in calls, f"{relative}:{node.lineno}: unexpected subprocess.{method} tool call"
        assert node.args and isinstance(node.args[0], (ast.List, ast.Tuple)), (
            f"{relative}:{node.lineno}: subprocess.{method} must use an argv sequence"
        )
        argv = node.args[0]
        assert argv.elts and isinstance(argv.elts[0], ast.Constant), (
            f"{relative}:{node.lineno}: tool executable must be a literal absolute path"
        )
        executable = argv.elts[0].value
        assert isinstance(executable, str) and executable.startswith("/usr/bin/"), (
            f"{relative}:{node.lineno}: PATH-searching executable {executable!r}"
        )
        shell = next((kw.value for kw in node.keywords if kw.arg == "shell"), None)
        assert isinstance(shell, ast.Constant) and shell.value is False, (
            f"{relative}:{node.lineno}: subprocess.{method} must explicitly set shell=False"
        )
        calls[method].append(executable)

    assert calls == expected_by_method, f"{relative}: unexpected subprocess tool paths: {calls!r}"

print("native_tool_path_contract_ok")
