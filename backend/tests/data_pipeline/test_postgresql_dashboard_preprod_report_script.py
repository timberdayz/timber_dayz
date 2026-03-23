import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "generate_postgresql_dashboard_preprod_report.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing preprod report script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location(
        "generate_postgresql_dashboard_preprod_report", SCRIPT_PATH
    )
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_preprod_report_script_parses_smoke_lines():
    script = load_script_module()
    rows = script.parse_smoke_lines(
        [
            '{"name":"business_overview_kpi","status_code":200,"ok":true,"url":"http://x/api/dashboard/business-overview/kpi"}',
            '{"name":"annual_summary_kpi","status_code":503,"ok":false,"url":"http://x/api/dashboard/annual-summary/kpi"}',
        ]
    )

    assert rows[0]["name"] == "business_overview_kpi"
    assert rows[0]["status"] == "200"
    assert rows[1]["name"] == "annual_summary_kpi"
    assert rows[1]["status"] == "503"


def test_preprod_report_script_renders_markdown_report():
    script = load_script_module()
    report = script.render_report(
        environment="preprod",
        base_url="http://localhost:8001",
        branch="codex/postgresql-api-semantic-mart-cutover",
        commit="abc123",
        operator="tester",
        router_enabled=True,
        startup_log_ok=True,
        test_summary="93 passed",
        smoke_rows=[
            {"name": "business_overview_kpi", "path": "/api/dashboard/business-overview/kpi", "status": "200", "notes": "ok"},
            {"name": "annual_summary_kpi", "path": "/api/dashboard/annual-summary/kpi", "status": "503", "notes": "failed"},
        ],
        ops_ok=True,
    )

    assert "# PostgreSQL Dashboard Pre-Prod Check Report" in report
    assert "codex/postgresql-api-semantic-mart-cutover" in report
    assert "93 passed" in report
    assert "/api/dashboard/business-overview/kpi" in report
    assert "/api/dashboard/annual-summary/kpi" in report
    assert "yes" in report
