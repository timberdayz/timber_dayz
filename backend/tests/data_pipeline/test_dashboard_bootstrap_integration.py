from pathlib import Path
import asyncio
from unittest.mock import AsyncMock

from backend.services.data_pipeline import dashboard_bootstrap


def test_dashboard_bootstrap_targets_cover_key_modules():
    assert "business_overview" in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
    assert "inventory_backlog" in dashboard_bootstrap.DASHBOARD_MODULE_TARGETS
    assert "ops.dashboard_asset_state" in dashboard_bootstrap.DASHBOARD_REQUIRED_OBJECTS


def test_backend_main_bootstraps_dashboard_assets_only_when_environment_allows():
    """启动时**可以** bootstrap 看板资产，但必须受环境门控。

    守护的是「不要无条件 bootstrap」：无条件执行会在每次重启时把整条看板
    链路重刷一遍（分钟级），把启动拖垮。现在生产环境需要启动时确保资产就绪，
    所以改为**按环境门控**（``should_auto_bootstrap_dashboard_on_startup``），
    守护也跟着升级成「门控必须在位」。
    """
    text = Path("backend/main.py").read_text(encoding="utf-8", errors="replace")

    assert "inspect_dashboard_assets" in text
    assert "should_auto_bootstrap_dashboard_on_startup" in text
    assert "if auto_bootstrap:" in text


def test_bootstrap_dashboard_assets_relaxes_statement_timeout(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(dashboard_bootstrap, "execute_sql_file", AsyncMock())
    monkeypatch.setattr(
        dashboard_bootstrap, "execute_refresh_plan", AsyncMock(return_value="run-1")
    )
    monkeypatch.setattr(
        dashboard_bootstrap, "_load_dashboard_asset_state", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        dashboard_bootstrap,
        "inspect_dashboard_assets",
        AsyncMock(
            return_value={
                "ready": True,
                "missing_objects": [],
                "missing_schemas": [],
                "modules": {
                    "business_overview": {"status": "ready", "ready": True},
                    "inventory_backlog": {"status": "ready", "ready": True},
                },
            }
        ),
    )

    report = asyncio.run(dashboard_bootstrap.bootstrap_dashboard_assets(session))

    executed_sql = str(session.execute.await_args_list[0].args[0])
    assert "SET LOCAL statement_timeout = 0" in executed_sql
    assert report["run_ids"]["business_overview"] == "run-1"
