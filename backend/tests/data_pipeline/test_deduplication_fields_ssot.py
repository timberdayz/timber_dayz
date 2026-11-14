# -*- coding: utf-8 -*-
"""去重字段的 SSOT 守护（2026-11-14）。

背景
----
「这个维度用哪些列算行身份」这件事曾经有**三处**声明：

1. 模板的去重字段表（**权威**）；
2. 域默认去重字段表 ``DEFAULT_DEDUPLICATION_FIELDS``（第 2 处）；
3. 核心字段清单里 ``in_hash=true`` 的条目（第 3 处，声明副本）。

第 2 处的失效方式极其危险（开发库实测）：

* 27 个维度全部配了模板 ⇒ 它**平时走不到**（死代码）；
* 但只要走到（模板缺失 / 导入漏配），它会用**标准字段键**
  （``platform_sku`` / ``product_id`` / ``warehouse_name``）
  去妙手的中文表头里取值 ⇒ **一个都取不到**
  ⇒ 3 个不同 SKU 算出**完全相同**的指纹
  ⇒ 同一天所有行互相覆盖 ⇒ **一天只剩一行，而且全程不报错**。

⇒ 现在：模板没配去重字段 ⇒ **显式报错**；域默认表降级为**推荐值**
（工作台的建议，用户可以改），不再是回落。

本文件锁住三件事
----------------
1. 漏配 ⇒ 报错（不是静默算错）；
2. 模块里**不再有**域默认表与子类型默认表；
3. 推荐值只走推荐函数，**不进**指纹计算路径。
"""

from __future__ import annotations

import inspect

import pytest

from backend.services import deduplication_fields_config as config
from backend.services.deduplication_fields_config import (
    DeduplicationFieldsNotConfiguredError,
    get_deduplication_fields,
    get_recommended_deduplication_fields,
)


def test_missing_template_fields_fail_loudly():
    """模板没配去重字段 ⇒ 明确报错，绝不静默算出同一个指纹。"""
    for domain in ("orders", "products", "inventory", "services", "analytics"):
        for template_fields in (None, []):
            with pytest.raises(DeduplicationFieldsNotConfiguredError):
                get_deduplication_fields(domain, template_fields=template_fields)


def test_error_message_points_at_the_fix():
    """报错信息必须说清「去哪配」，否则用户只能干瞪眼。"""
    with pytest.raises(DeduplicationFieldsNotConfiguredError) as excinfo:
        get_deduplication_fields("inventory", template_fields=None)
    message = str(excinfo.value)
    assert "inventory" in message
    assert "去重字段" in message


def test_template_fields_still_win():
    """模板配了字段 ⇒ 照常使用（并追加系统身份字段）。"""
    fields = get_deduplication_fields(
        "inventory",
        template_fields=["*商品SKU", "仓库"],
        sub_domain=None,
    )
    assert "*商品SKU" in fields
    assert "仓库" in fields
    # 系统身份字段是**强制追加**的（不是第二份声明）
    assert "platform_code" in fields
    assert "shop_id" in fields


def test_domain_default_tables_are_gone():
    """域默认表与子类型默认表必须**不存在**（否则会被当成回落再加回来）。"""
    assert not hasattr(config, "DEFAULT_DEDUPLICATION_FIELDS")
    assert not hasattr(config, "SUB_DOMAIN_DEDUPLICATION_FIELDS")
    assert not hasattr(config, "get_default_deduplication_fields")


def test_hash_path_never_touches_the_recommendation_table():
    """指纹计算路径不许碰推荐值 —— 推荐是给用户看的，不是权威。"""
    source = inspect.getsource(config.get_deduplication_fields)
    assert "RECOMMENDED_DEDUPLICATION_FIELDS" not in source
    assert "get_recommended_deduplication_fields" not in source


def test_recommendation_role_is_preserved():
    """推荐值仍然可用（工作台要给它建议），且别名域归一后结果一致。"""
    assert get_recommended_deduplication_fields("orders") == ["order_id"]
    assert get_recommended_deduplication_fields("traffic") == (
        get_recommended_deduplication_fields("analytics")
    )
    # 未知域返回空列表（**不代表可以回落**）
    assert get_recommended_deduplication_fields("not_a_domain") == []
