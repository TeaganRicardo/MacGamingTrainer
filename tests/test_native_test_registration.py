"""A Darwin test cannot silently become a portable discovery entry."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools"))
from test_inventory import validate_native_inventory

with tempfile.TemporaryDirectory(prefix="mgt-native-test-registration-") as directory:
    root = Path(directory)
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_portable.py").write_text("assert 1 + 1 == 2\n")
    native = tests / "test_third_probe_frontend.py"
    native.write_text('import sys\nif sys.platform != "darwin":\n    raise SystemExit("macOS-only fixture")\n')
    try:
        validate_native_inventory(root, set())
    except ValueError as error:
        assert native.name in str(error) and "macos_only_tests.txt" in str(error)
    else:
        raise AssertionError("unregistered native entry reached portable discovery")
    validate_native_inventory(root, {native.name})
    helper = tests / "native_helper.py"
    helper.write_text(native.read_text())
    native.write_text("from native_helper import run\n")
    try:
        validate_native_inventory(root, set())
    except ValueError as error:
        assert native.name in str(error)
    else:
        raise AssertionError("an indirect native entry silently entered portable discovery")

print("native_test_registration_ok")
