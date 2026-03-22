from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "high_frequency_pages_probe.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing high frequency pages probe: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location(
        "high_frequency_pages_probe", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_probe_covers_expected_pages():
    probe = load_script_module()

    page_names = {page["name"] for page in probe.PAGE_SCENARIOS}

    assert "user_management" in page_names
    assert "user_approval" in page_names
    assert "data_sync_files" in page_names
    assert "collection_tasks" in page_names
    assert "collection_history" in page_names
    assert "system_notifications" in page_names
    assert "role_management" in page_names
    assert "account_management" in page_names
    assert "data_quarantine" in page_names
    assert "sessions" in page_names
    assert "notification_preferences" in page_names
    assert "system_config" in page_names
    assert "database_config" in page_names
    assert "security_settings" in page_names
    assert "system_logs" in page_names
    assert "data_backup" in page_names
    assert "system_maintenance" in page_names
    assert "account_alignment" in page_names
    assert "notification_config" in page_names
    assert "permission_management" in page_names
    assert "data_sync_templates" in page_names
    assert "expense_management" in page_names


def test_summarize_page_results_groups_by_page():
    probe = load_script_module()

    summary = probe.summarize_page_results(
        [
            {"page": "user_management", "ok": True, "elapsed_ms": 100.0, "status": 200},
            {"page": "user_management", "ok": True, "elapsed_ms": 120.0, "status": 200},
            {
                "page": "collection_tasks",
                "ok": False,
                "elapsed_ms": 800.0,
                "status": 503,
            },
        ]
    )

    assert summary["user_management"]["count"] == 2
    assert summary["collection_tasks"]["failed"] == 1
    assert summary["collection_tasks"]["statuses"]["503"] == 1


def test_account_management_uses_trailing_slash_endpoint():
    probe = load_script_module()

    account_page = next(
        page for page in probe.PAGE_SCENARIOS if page["name"] == "account_management"
    )
    paths = {item["path"] for item in account_page["requests"]}

    assert "/api/accounts/" in paths
