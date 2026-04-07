import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "check_postgresql_dashboard_ops.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing ops checker script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("check_postgresql_dashboard_ops", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ops_checker_script_defines_main():
    script = load_script_module()

    assert hasattr(script, "main")
