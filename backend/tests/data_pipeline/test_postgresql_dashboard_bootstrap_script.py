import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "bootstrap_postgresql_dashboard.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing bootstrap script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("bootstrap_postgresql_dashboard", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bootstrap_script_exposes_dashboard_targets():
    script = load_script_module()

    assert "api.business_overview_operational_metrics_module" in script.DASHBOARD_BOOTSTRAP_TARGETS
    assert "api.business_overview_comparison_module" in script.DASHBOARD_BOOTSTRAP_TARGETS
    assert "ops.pipeline_run_log" in script.DASHBOARD_REQUIRED_OBJECTS
    assert "core.field_alias_rules" in script.DASHBOARD_REQUIRED_OBJECTS


def test_bootstrap_script_supports_check_mode():
    script = load_script_module()

    parser = script.build_parser()
    args = parser.parse_args(["--check"])

    assert args.check is True
