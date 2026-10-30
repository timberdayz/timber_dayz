"""后端 DB 超时与前端 axios 超时的预算对齐护栏。

背景（2026-10-30）
------------------
前端 axios 超时（``frontend/src/api/index.js`` 的 ``TIMEOUTS``）必须**大于**
后端 DB ``statement_timeout``。否则前端先放弃（报「网络连接 70000ms」），
后端 SQL 还在跑 —— 这就是「超时预算倒置」。

护栏覆盖三件事：
1. 连接池级 ``statement_timeout`` 必须来自配置（可按环境覆盖），不再硬编码；
2. 请求级预算用 ``SET LOCAL`` 局部收紧，不动连接池默认值；
3. 默认预算必须严格小于前端对应接口的 axios 超时。
"""

import re
from pathlib import Path

from backend.utils.config import get_settings

_FRONTEND_API = Path("frontend/src/api/index.js")


def _frontend_timeout_ms(name: str) -> int:
    text = _FRONTEND_API.read_text(encoding="utf-8", errors="replace")
    match = re.search(rf"\b{name}:\s*(\d+)", text)
    assert match, f"前端 TIMEOUTS 里找不到 {name}"
    return int(match.group(1))


def test_database_layer_reads_statement_timeout_from_settings():
    """连接池级 statement_timeout 必须读配置，且不再硬编码 120000。"""
    text = Path("backend/models/database.py").read_text(encoding="utf-8", errors="replace")

    assert "statement_timeout=120000" not in text
    assert 'cursor.execute("SET statement_timeout TO 120000")' not in text
    assert "DB_POOL_STATEMENT_TIMEOUT_MS" in text
    assert "DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS" in text
    # 请求级预算表也来自配置
    assert "REQUEST_STATEMENT_TIMEOUT_MS" in text


def test_request_scope_uses_set_local_not_pool_wide_change():
    """请求级收紧必须用 SET LOCAL（事务内局部），不能改连接池默认值。"""
    text = Path("backend/models/database.py").read_text(encoding="utf-8", errors="replace")

    assert "SET LOCAL statement_timeout" in text
    assert "resolve_request_statement_timeout_ms" in text


def test_statement_timeout_defaults_are_below_frontend_budgets():
    """默认 DB 预算必须严格小于前端 axios 超时。"""
    settings = get_settings()

    # Dashboard 家族：前端 70s
    assert settings.DB_STATEMENT_TIMEOUT_MS < _frontend_timeout_ms("dashboard")
    # 普通接口：前端默认 30s
    assert (
        settings.DB_REQUEST_STATEMENT_TIMEOUT_MS
        < _frontend_timeout_ms("default")
    )
    # 每条按路径的预算都必须小于它对应的前端超时
    frontend_budgets = {
        "/governance/detailed-coverage": ("governance", 120_000),
        "/scan": ("scan", 120_000),
        "/preview": ("preview", 60_000),
        "/ingest": ("ingest", 180_000),
        "/dashboard": ("dashboard", 70_000),
        "/collection": ("collection", 300_000),
        "/mapping": ("mapping", 90_000),
    }
    for fragment, (frontend_name, frontend_budget) in frontend_budgets.items():
        budget = settings.REQUEST_STATEMENT_TIMEOUT_MS[fragment]
        assert budget < frontend_budget, f"{fragment} 的 DB 预算 {budget} >= 前端 {frontend_budget}"
        assert _frontend_timeout_ms(frontend_name) == frontend_budget
    # 连接池级默认仍保留 120s：Celery/后台批量采集导入不经过请求级预算，
    # 把池默认值砍小会打断这些长事务。
    if settings.DB_BATCH_STATEMENT_TIMEOUT_MS <= 0:
        assert settings.DB_POOL_STATEMENT_TIMEOUT_MS >= 120_000
    # 批量长任务预算 0 = 不限制
    assert settings.DB_BATCH_STATEMENT_TIMEOUT_MS >= 0
