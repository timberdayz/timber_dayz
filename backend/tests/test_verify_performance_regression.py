from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "verify_performance_regression.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing performance regression script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location(
        "verify_performance_regression", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_regression_plan_for_ci():
    script = load_script_module()

    plan = script.build_regression_plan(mode="ci", backend_reachable=False)
    command = " ".join(plan[0]["command"])

    assert [step["name"] for step in plan] == [
        "perf-regression-tests",
    ]
    assert "pytest" in command
    assert "backend/tests/test_account_alignment_compatibility.py" in command
    assert "backend/tests/test_high_frequency_pages_probe.py" in command
    assert "backend/tests/test_notification_config_routes.py" in command
    assert "backend/tests/test_users_me_sessions.py" in command
    assert "backend/tests/test_data_quarantine_compatibility.py" in command


def test_build_regression_plan_for_local_adds_live_checks():
    script = load_script_module()

    plan = script.build_regression_plan(mode="local", backend_reachable=True)

    names = [step["name"] for step in plan]

    assert "perf-regression-tests" in names
    assert "high-frequency-pages-probe" in names
    assert "business-overview-split-probe" in names
    assert "business-overview-long-run" in names
