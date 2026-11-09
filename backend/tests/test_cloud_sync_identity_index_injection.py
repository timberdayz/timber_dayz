"""B 项守护: 同步侧的身份索引**必须真的被注入**, 且取不到时必须**降级而不是崩**。

背景
----
同步侧的身份自洽判定要回答「行内身份键能否唯一归属到一个店铺账号」。
账号 ID(``shopee_my_xhkj1_local``)与平台编号(``1540271739``)是**不同形态**,
纯字符串比较会把同一个店判成矛盾 ⇒ **必须查主数据**。

⇒ 所以工厂必须把主数据索引注入 writer。
⇒ 而索引取不到时, 判定要退化为「只比同形态的键」, **宁可少拦也不误杀** ——
拦错会静默丢数(2026-11-07 事故的形态), 不拦最多留下一批待人工处理。
"""

from __future__ import annotations

from sqlalchemy import create_engine

from backend.services import cloud_b_class_auto_sync_factory as factory
from backend.services.cloud_b_class_auto_sync_factory import (
    _build_cloud_sync_service,
    _load_identity_index,
)


def _sqlite_engine():
    return create_engine("sqlite://", future=True)


def test_load_identity_index_returns_none_when_master_data_unavailable():
    """★ 主数据取不到 ⇒ 返回 None(降级), **不抛异常**。

    主数据暂时不可用不该让整条同步链挂掉。
    """
    engine = _sqlite_engine()
    try:
        # sqlite 里没有 core.shop_accounts 表 ⇒ 查询必然失败
        assert _load_identity_index(engine) is None
    finally:
        engine.dispose()


def test_build_cloud_sync_service_injects_identity_index(monkeypatch):
    """★ 工厂必须把身份索引注入 writer —— 否则判定会一直走降级路径。"""
    sentinel = object()
    monkeypatch.setattr(factory, "_load_identity_index", lambda engine: sentinel)

    local_engine = _sqlite_engine()
    cloud_engine = _sqlite_engine()
    try:
        service = _build_cloud_sync_service(
            local_engine=local_engine,
            cloud_engine=cloud_engine,
            session_factory=_sqlite_engine,
            dry_run=True,
            checkpoint_scope="cloud_sync:test",
        )
        assert service.remote_writer.identity_index is sentinel
    finally:
        local_engine.dispose()
        cloud_engine.dispose()


def test_writer_degrades_to_shape_comparison_without_index():
    """★ 没有索引 ⇒ 判据降级为「只比同形态的键」, 不误杀同店不同形态的数据。"""
    from backend.services.cloud_b_class_sync_service import (
        split_rows_by_identity_consistency,
    )

    rows = [
        {
            "platform_code": "shopee",
            "shop_id": "1540271739",
            "raw_data": {
                "platform_shop_id": "1540271739",
                "shop_account_id": "shopee_my_xhkj1_local",
            },
        }
    ]

    result = split_rows_by_identity_consistency(rows, None)

    assert result.conflict_rows == 0, "降级模式误杀了同店的正常数据"
    assert result.written_rows == 1
