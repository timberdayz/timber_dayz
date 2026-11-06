"""看板「身份冲突告警」的守护测试(WP-5)。

背景
----
2026-06 的 Shopee 错配数据里, 有 18 行的「行内编号」与「行内标签」指向**不同账号**
(采集侧算错编号 ⇒ 标签被整组贴到别的店上), 合计 **8,409 UV** 从看板消失。

看板原来只能报笼统的 ``ambiguous``(候选数 > 1), 分不出「歧义来自编号」还是
「歧义来自两个店名」—— 而这两者的处置方向完全不同。

本测试盯住
----------
1. 新原因码 ``platform_shop_id_conflict`` 归到 ``conflict`` 类;
2. 告警查询**确实**包含按行内事实表直查的诊断分支(不依赖重建物化视图);
3. 诊断分支的判据与历史订正迁移(20261117)同构 —— 编号反查到 B、标签指向 A、A≠B。
"""

from __future__ import annotations

from backend.services.postgresql_dashboard_service import (
    _identity_warning_reason,
    PostgresqlDashboardService,
)


def test_platform_shop_id_conflict_maps_to_conflict_bucket():
    """新原因码必须归到 conflict 类(「去查数据串了」), 不能落到 other。"""
    assert _identity_warning_reason("platform_shop_id_conflict") == "conflict"
    # 既有归类不许被带偏
    assert _identity_warning_reason("ambiguous_shop_label") == "ambiguous"
    assert _identity_warning_reason("unmatched_shop_label") == "unmatched"
    assert _identity_warning_reason("") == "other"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, sink):
        self._sink = sink

    async def execute(self, statement, *args, **kwargs):
        self._sink.append(str(statement))
        return _FakeResult([])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _install_fake_session(monkeypatch, sink):
    """看板服务用模块级 ``AsyncSessionLocal`` ⇒ 换成假的, 把 SQL 抓出来。"""

    def factory():
        return _FakeSession(sink)

    monkeypatch.setattr(
        "backend.services.postgresql_dashboard_service.AsyncSessionLocal",
        factory,
    )


async def _capture_identity_health_sql(monkeypatch, platform=None) -> str:
    """跑一次告警查询, 把实际执行的 SQL 抓出来。"""
    sink: list[str] = []
    _install_fake_session(monkeypatch, sink)
    service = PostgresqlDashboardService()
    await service.get_business_overview_identity_health(
        granularity="monthly",
        target_date="2026-06-30",
        platform=platform,
    )
    return "\n".join(sink)


async def test_identity_health_query_contains_conflict_diagnostic(monkeypatch):
    """告警查询里必须有「编号与标签打架」的诊断分支。"""
    sql = await _capture_identity_health_sql(monkeypatch)
    assert "platform_shop_id_conflicts" in sql
    assert "platform_shop_id_conflict" in sql


async def test_conflict_diagnostic_uses_row_level_fact_table(monkeypatch):
    """诊断必须**直查事实行**(b_class), 而不是依赖物化视图 ——
    因为给 MV 加列需要重建 MV(DROP ... CASCADE 会连删下游对象), 风险太高。"""
    sql = await _capture_identity_health_sql(monkeypatch)
    assert "b_class.fact_shopee_analytics_monthly" in sql
    # 判据: 行内编号反查到账号 B、标签指向账号 A, A ≠ B
    assert "owner.id <> target.id" in sql
    assert "target.platform_shop_id" in sql


async def test_conflict_diagnostic_is_scoped_to_period_and_platform(monkeypatch):
    """诊断必须受期间与平台过滤约束(否则看板会一直挂着历史冲突)。"""
    sql = await _capture_identity_health_sql(monkeypatch, platform="shopee")
    assert "f.platform_code = :platform_code" in sql
    assert "f.metric_date >= :period_key" in sql


async def test_non_monthly_granularity_short_circuits(monkeypatch):
    """非 monthly 粒度直接返回空 —— 既有行为不许被改。"""
    sink: list[str] = []
    _install_fake_session(monkeypatch, sink)
    service = PostgresqlDashboardService()
    result = await service.get_business_overview_identity_health(
        granularity="daily",
        target_date="2026-06-30",
        platform=None,
    )
    assert result["status"] == "ok"
    assert result["warning_count"] == 0
    assert sink == []
