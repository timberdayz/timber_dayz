from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
PROBE_PATH = ROOT_DIR / "scripts" / "business_overview_split_probe.py"


def load_probe_module():
    if not PROBE_PATH.exists():
        raise FileNotFoundError(f"Missing business overview split probe: {PROBE_PATH}")

    spec = importlib.util.spec_from_file_location("business_overview_split_probe", PROBE_PATH)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_targets_expected_endpoints():
    probe = load_probe_module()

    endpoint_names = {item["name"] for item in probe.BUSINESS_OVERVIEW_ENDPOINTS}

    assert "kpi" in endpoint_names
    assert "comparison" in endpoint_names
    assert "shop_racing" in endpoint_names
    assert "traffic_ranking" in endpoint_names
    assert "operational_metrics" in endpoint_names


def test_summarize_probe_results_groups_by_endpoint():
    probe = load_probe_module()

    summary = probe.summarize_probe_results(
        [
            {"name": "kpi", "ok": True, "elapsed_ms": 100.0, "status": 200},
            {"name": "kpi", "ok": True, "elapsed_ms": 120.0, "status": 200},
            {"name": "comparison", "ok": False, "elapsed_ms": 2200.0, "status": 503},
        ]
    )

    assert summary["kpi"]["count"] == 2
    assert summary["comparison"]["failed"] == 1
    assert "p95_ms" in summary["comparison"]
