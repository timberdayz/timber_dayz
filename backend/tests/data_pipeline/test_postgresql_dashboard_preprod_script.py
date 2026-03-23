import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_postgresql_dashboard_preprod_check.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing preprod script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("run_postgresql_dashboard_preprod_check", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preprod_script_builds_expected_steps():
    script = load_script_module()
    steps = script.build_preprod_steps("http://localhost:8000")

    assert [step["name"] for step in steps] == [
        "data_pipeline_tests",
        "dashboard_smoke",
        "ops_check",
    ]
    assert steps[1]["command"][-1] == "http://localhost:8000"
