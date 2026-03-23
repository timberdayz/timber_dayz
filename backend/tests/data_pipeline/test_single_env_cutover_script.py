import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "run_single_env_postgresql_dashboard_cutover.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing single-env cutover script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location(
        "run_single_env_postgresql_dashboard_cutover", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_cutover_script_defines_safe_cleanup_schemas():
    script = load_script_module()

    assert script.DEFAULT_CLEANUP_SCHEMAS == ["a_class", "b_class", "c_class"]


def test_cutover_script_builds_expected_execution_steps():
    script = load_script_module()
    steps = script.build_cutover_steps(cleanup_enabled=True)

    names = [step["name"] for step in steps]
    assert names[:3] == [
        "query_admin_users",
        "ensure_all_roles",
        "create_admin_user",
    ]
    assert "cleanup_business_test_data" in names


def test_single_env_cutover_runbook_exists():
    text = Path(
        "docs/development/CLOUD_DIRECT_POSTGRESQL_DASHBOARD_CUTOVER_RUNBOOK.md"
    ).read_text(encoding="utf-8", errors="replace")

    assert "single-environment direct PostgreSQL Dashboard cutover" in text
    assert "USE_POSTGRESQL_DASHBOARD_ROUTER=true" in text
    assert "ENABLE_METABASE_PROXY=false" in text
    assert "xihong" in text
    assert "a_class" in text
    assert "b_class" in text
    assert "c_class" in text
