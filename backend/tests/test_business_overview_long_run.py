from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "business_overview_long_run.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(
            f"Missing business overview long-run script: {SCRIPT_PATH}"
        )

    spec = importlib.util.spec_from_file_location(
        "business_overview_long_run", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summarize_rounds_tracks_page_success_rate():
    script = load_script_module()

    summary = script.summarize_rounds(
        [
            {
                "round": 1,
                "ok": True,
                "elapsed_ms": 1000.0,
                "endpoint_results": [
                    {"name": "kpi", "ok": True, "elapsed_ms": 100.0, "status": 200},
                    {
                        "name": "comparison",
                        "ok": True,
                        "elapsed_ms": 300.0,
                        "status": 200,
                    },
                ],
            },
            {
                "round": 2,
                "ok": False,
                "elapsed_ms": 5000.0,
                "endpoint_results": [
                    {"name": "kpi", "ok": True, "elapsed_ms": 120.0, "status": 200},
                    {
                        "name": "comparison",
                        "ok": False,
                        "elapsed_ms": 4000.0,
                        "status": 503,
                    },
                ],
            },
        ]
    )

    assert summary["round_count"] == 2
    assert summary["successful_rounds"] == 1
    assert summary["failed_rounds"] == 1
    assert summary["page_success_rate"] == 50.0
    assert "page_p95_ms" in summary


def test_summarize_rounds_breaks_down_endpoint_metrics():
    script = load_script_module()

    summary = script.summarize_rounds(
        [
            {
                "round": 1,
                "ok": True,
                "elapsed_ms": 1000.0,
                "endpoint_results": [
                    {"name": "kpi", "ok": True, "elapsed_ms": 100.0, "status": 200},
                    {
                        "name": "comparison",
                        "ok": False,
                        "elapsed_ms": 3000.0,
                        "status": 503,
                    },
                ],
            }
        ]
    )

    assert summary["endpoints"]["kpi"]["count"] == 1
    assert summary["endpoints"]["comparison"]["failed"] == 1
    assert summary["endpoints"]["comparison"]["statuses"]["503"] == 1


def test_summarize_resource_samples_extracts_peaks():
    script = load_script_module()

    summary = script.summarize_resource_samples(
        [
            {
                "cpu_usage": 10.0,
                "memory_usage": 20.0,
                "thread_count": 30,
                "sync_pool": {"checked_out": 1, "overflow": 0},
                "async_pool": {"checked_out": 2, "overflow": 0},
            },
            {
                "cpu_usage": 40.0,
                "memory_usage": 50.0,
                "thread_count": 60,
                "sync_pool": {"checked_out": 3, "overflow": 1},
                "async_pool": {"checked_out": 4, "overflow": 2},
            },
        ]
    )

    assert summary["cpu_peak"] == 40.0
    assert summary["memory_peak"] == 50.0
    assert summary["thread_peak"] == 60
    assert summary["sync_pool_checked_out_peak"] == 3
    assert summary["async_pool_overflow_peak"] == 2
