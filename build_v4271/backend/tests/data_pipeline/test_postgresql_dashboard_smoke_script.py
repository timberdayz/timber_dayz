import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "smoke_postgresql_dashboard_routes.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing smoke script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("smoke_postgresql_dashboard_routes", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_smoke_script_builds_expected_plan():
    script = load_script_module()
    names = [step["name"] for step in script.build_smoke_plan()]

    assert names == [
        "business_overview_kpi",
        "business_overview_comparison",
        "business_overview_shop_racing",
        "business_overview_operational_metrics",
        "annual_summary_kpi",
        "annual_summary_trend",
        "annual_summary_platform_share",
        "annual_summary_by_shop",
        "annual_summary_target_completion",
    ]
