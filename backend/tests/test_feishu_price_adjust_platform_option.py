"""飞书「调价记录表」「平台」单选字段写入的守护测试。

背景（2026-11-17 生产复核发现）
----------------------------------
2026-11-07 的「底线下沉到 SKU × 平台」把 ``platform_code`` 放进了 outbox 载荷，
而 ``_price_adjust_payload`` 把这个**小写 code**（``tiktok``）直接写进飞书
「平台」单选字段。飞书那张表的选项名是 ``TikTok`` / ``Shopee`` / ``Amazon``
（首字母大写），匹配不上任何选项 ⇒ base/v3 的批量新增**整批拒绝**
（``not_found``）。

后果：2026-11-08 起 461 条调价记录**一条都没写进飞书**；失败任务又没有重试
次数上限（退避封顶 1 小时），于是每天再刷几百条失败日志 ——
「最低售价变更通知」这个功能实际上是哑的。

本文件钉死三件事：

1. 「平台」只能写**飞书选项名**，永远不能写 ERP 的小写 code；
2. 选项名认不出来时**不写该字段**（宁可这一格空着，也不能让整批 200 行被拒）；
3. 选项名的真源是 ``core.dim_platforms.name``（ORM），不是硬编码映射。
"""

from __future__ import annotations

import pytest

from backend.services.feishu_projection_service import (
    FEISHU_PRICE_ADJUST_DIRECTION_OPTIONS,
    FEISHU_PRICE_ADJUST_PLATFORM_OPTIONS,
    FEISHU_PRICE_ADJUST_REASON_OPTIONS,
    FeishuProjectionService,
)


class _Task:
    """最小 outbox 任务（只带 ``_price_adjust_payload`` 会读到的字段）。"""

    payload_json = {
        "sku_id": 1048,
        "sku_key": "A-00031-pink",
        "spu": "XH-FASHION-A-00031",
        "platform_code": "tiktok",
        "warehouse_code": "MY-01",
        "sku_name": "商品1",
        "specification": "粉色",
        "old_min_selling_price": "96.85",
        "new_min_selling_price": "105.36",
        "change_rate": 0.08786783686112545,
        "direction": "上升",
        "reason": "库龄档位变化",
        "pricing_tier_label": "日常",
        "age_days": 7,
        "current_qty": 11,
        "inventory_value": 396.0,
    }
    created_at = None


def _service() -> FeishuProjectionService:
    return FeishuProjectionService(db=None)  # type: ignore[arg-type]


def test_platform_field_writes_feishu_option_label_not_raw_code():
    """「平台」必须写飞书选项名（``TikTok``），不能写 ERP 的小写 code（``tiktok``）。

    ⚠️ 这正是 2026-11-08 起 461 条记录全部投递失败的根因：
    base/v3 的批量新增遇到**匹配不上任何选项**的单选值会整批拒绝（not_found），
    一行写错就拖垮整批 200 行。
    """
    fields = _service()._price_adjust_payload(
        _Task(), platform_names={"tiktok": "TikTok"}
    )

    assert fields["平台"] == "TikTok"
    assert fields["平台"] != "tiktok"
    # 其余字段不受影响
    assert fields["ERP SKU"] == "A-00031-pink"
    assert fields["备注"] == "仓库：MY-01"


def test_platform_field_omitted_when_option_label_unknown():
    """认不出的平台**不写「平台」字段**。

    宁可这一格空着（运营还能从别处看出来），也不能写一个匹配不上的值 ——
    那会让**整批**被飞书拒掉，一行都写不进去。
    """
    fields = _service()._price_adjust_payload(
        _Task(), platform_names={"tiktok": "妙手ERP"}
    )

    assert "平台" not in fields
    # 行本身还是要写出去的（不能因为一个字段认不出就丢掉整条通知）
    assert fields["ERP SKU"] == "A-00031-pink"
    assert fields["新最低售价"] == 105.36


def test_platform_field_omitted_without_name_map():
    """拿不到平台名映射时**不写**「平台」，**绝不能**回退成写原始 code。"""
    fields = _service()._price_adjust_payload(_Task())

    assert "平台" not in fields


def test_option_whitelist_matches_feishu_table():
    """白名单必须与飞书「调价记录表」「平台」字段**现有**的选项名逐字一致。

    这张表是外部 Base 的固定结构（与 ERP 无关），所以白名单是"外部契约"，
    不是平台字典：飞书那边改了选项名，这里要**显式**跟着改，
    不能靠猜。
    """
    assert set(FEISHU_PRICE_ADJUST_PLATFORM_OPTIONS) == {"TikTok", "Shopee", "Amazon"}


def test_reason_and_direction_constants_match_feishu_options():
    """「变动原因」「变动方向」是**同一种风险**：ERP 侧加常量、飞书那边手工加选项。

    两边不同步 ⇒ 整批被拒（not_found）⇒ 通知全灭，且没有任何显式报错。
    所以 ERP 侧的每个取值都必须落在飞书现有选项内。
    """
    from backend.services import price_adjust_notify_service as notify

    reasons = {
        value
        for name, value in vars(notify).items()
        if name.startswith("REASON_") and isinstance(value, str)
    }
    directions = {
        value
        for name, value in vars(notify).items()
        if name.startswith("DIRECTION_") and isinstance(value, str)
    }

    assert reasons, "没找到 REASON_* 常量，测试本身失效了"
    assert directions, "没找到 DIRECTION_* 常量，测试本身失效了"
    assert reasons <= set(
        FEISHU_PRICE_ADJUST_REASON_OPTIONS
    ), f"这些变动原因在飞书选项里没有：{sorted(reasons - set(FEISHU_PRICE_ADJUST_REASON_OPTIONS))}"
    assert directions <= set(
        FEISHU_PRICE_ADJUST_DIRECTION_OPTIONS
    ), f"这些变动方向在飞书选项里没有：{sorted(directions - set(FEISHU_PRICE_ADJUST_DIRECTION_OPTIONS))}"


def test_unknown_select_values_are_not_written():
    """单选值认不出飞书选项时**不写这一格**（整批被拒的代价太大）。"""
    task = _Task()
    task.payload_json = dict(
        task.payload_json, reason="新加的原因", direction="新加的方向"
    )

    fields = _service()._price_adjust_payload(task, platform_names={"tiktok": "TikTok"})

    assert "变动原因" not in fields
    assert "变动方向" not in fields
    # 正常的字段照写
    assert fields["平台"] == "TikTok"
    assert fields["ERP SKU"] == "A-00031-pink"


@pytest.mark.asyncio
async def test_platform_names_come_from_dim_platforms(pg_session):
    """平台显示名的真源是 ``core.dim_platforms.name``（ORM），不是硬编码映射。"""
    from modules.core.db import DimPlatform

    pg_session.add(DimPlatform(platform_code="tiktok", name="TikTok"))
    pg_session.add(DimPlatform(platform_code="shopee", name="Shopee"))
    await pg_session.flush()

    names = await _service_with_db(pg_session)._platform_display_names()

    assert names["tiktok"] == "TikTok"
    assert names["shopee"] == "Shopee"
    # 平台 code 本身**不是**显示名 ⇒ 不能拿 code 去填飞书单选
    assert names["tiktok"] != "tiktok"


def _service_with_db(db) -> FeishuProjectionService:
    return FeishuProjectionService(db=db)
