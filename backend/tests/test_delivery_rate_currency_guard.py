"""尾程费率的**币种护栏 + 版本化改价 + 停用/启用**（2026-11-17 守护测试）。

三件事，件件都是「录错就把成本底线带偏」：

1. **币种只认人民币等值**
   平台价目表常是新币/马币（Shopee SG = SGD），而尾程计算链**不读汇率**
   （``currency`` 列存了但计算层没用）。照抄新币数字当人民币 = 尾程少算 5 倍
   ⇒ 成本底线偏低 ⇒ **直接漏钱**。
   ⇒ 写入端拒绝非 CNY；取数端遇到遗留的非 CNY 行**不参与计算**
   （宁可算不出来，也不要算错 —— 与「没配费率 ≠ 尾程免费」同一条原则）。

2. **改价必须留痕**
   费率是**版本化只进不退**的：换价 = 旧行闭区间 + 新行今天起生效（POST 端点）。
   在 PATCH 里直接改单价 = 覆盖历史行 ⇒ 事后对不上「当时按多少钱算的」。
   ⇒ PATCH 不接受单价与身份字段（平台/仓/重量段）。

3. **停用优于删除**
   费率有生效日期，硬删会丢历史（事后查不出当时按什么价算的）。
   ⇒ PATCH 支持 status 切换：停用 = 保留行 + 退出当期；启用 = 回到当期。
"""

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.schemas.product_center import (
    DeliveryRateRuleCreateRequest,
    DeliveryRateRuleUpdateRequest,
)
from backend.services.product_delivery_cost_service import DeliveryTier

FRONTEND_PATH = Path("frontend/src/domains/business/views/ProductCenter.vue")
ROUTER_PATH = Path("backend/domains/business/routers/product_center.py")
FINANCE_SERVICE_PATH = Path("backend/services/product_finance_service.py")

CREATE_KWARGS = {
    "platform_code": "shopee",
    "warehouse_code": "SG-01",
    "weight_tier_code": "T01",
    "unit_price": 22.31,
    "effective_from": "2026-01-01",
}


# ---------------------------------------------------------------------------
# 1 · 币种护栏
# ---------------------------------------------------------------------------


def test_delivery_rate_create_rejects_foreign_currency():
    """外币价目表不能直接当人民币存 ⇒ 否则尾程少算 5 倍，底线偏低漏钱。"""
    with pytest.raises(ValidationError) as excinfo:
        DeliveryRateRuleCreateRequest(currency="SGD", **CREATE_KWARGS)
    message = str(excinfo.value)
    assert "CNY" in message or "人民币" in message


def test_delivery_rate_create_accepts_cny():
    row = DeliveryRateRuleCreateRequest(currency="CNY", **CREATE_KWARGS)
    assert row.currency == "CNY"


def test_delivery_rate_create_defaults_to_cny():
    assert DeliveryRateRuleCreateRequest(**CREATE_KWARGS).currency == "CNY"


def test_delivery_rate_update_rejects_foreign_currency():
    with pytest.raises(ValidationError):
        DeliveryRateRuleUpdateRequest(currency="SGD")


def test_delivery_rate_update_rejects_price_overwrite():
    """**改价不能走 PATCH**：费率版本化只进不退，改价必须 POST 新版本。"""
    with pytest.raises(ValidationError):
        DeliveryRateRuleUpdateRequest(unit_price=30.0)


def test_delivery_rate_update_rejects_identity_overwrite():
    """平台 / 仓 / 重量段是这一行的身份 —— 改身份等于换了一档费率。"""
    for field, value in (
        ("platform_code", "tiktok"),
        ("warehouse_code", "MY-01"),
        ("weight_tier_code", "T02"),
    ):
        with pytest.raises(ValidationError):
            DeliveryRateRuleUpdateRequest(**{field: value})


def test_delivery_rate_update_allows_notes_dates_and_status():
    row = DeliveryRateRuleUpdateRequest(
        notes="换价",
        effective_from="2026-02-01",
        status="inactive",
        source="shopee_sg_ratecard_2026",
        version="v2",
    )
    assert row.status == "inactive"
    assert row.notes == "换价"


def test_delivery_rate_lookup_ignores_non_cny_rows():
    """取数端：非人民币等值的遗留行**不参与计算**（宁可算不出来，也不要算错）。"""
    source = FINANCE_SERVICE_PATH.read_text(encoding="utf-8")
    assert "DeliveryRateRule.currency" in source
    assert 'func.coalesce(DeliveryRateRule.currency, "CNY") == "CNY"' in source


def test_foreign_currency_rate_is_not_silently_read_as_cny():
    """护栏不能只写在注释里 —— 取数过滤必须在**同一处**落地。"""
    source = FINANCE_SERVICE_PATH.read_text(encoding="utf-8")
    assert "find_delivery_rate_tiers" in source
    # 取数语句里必须带币种条件（不是只在别处提醒）
    assert source.count('func.coalesce(DeliveryRateRule.currency, "CNY") == "CNY"') >= 1


# ---------------------------------------------------------------------------
# 2 · 改价走 POST（版本化），停用/启用走 PATCH
# ---------------------------------------------------------------------------


def test_router_update_endpoint_uses_an_explicit_allowlist():
    """PATCH 只能改白名单字段（不能像现在这样 ``setattr`` 任意字段）。"""
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert "_DELIVERY_RATE_UPDATABLE_FIELDS" in source


def test_router_update_endpoint_supports_disable_and_enable():
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert '"inactive"' in source
    assert '"active"' in source


def test_router_owns_the_effective_date_on_reprice():
    """**改价的生效日由后端说了算**（SSOT，2026-11-17 修）。

    改价时调用方（卡片 / 明细表）往往把**原行的生效日**一起发过来。
    照用 ⇒ 旧行被闭区间到「原生效日 - 1 天」⇒ 区间倒挂 ⇒ 撞数据库检查约束
    ⇒ 报 409「already exists」（实测卡片改价直接不可用）；就算没撞，
    历史也被抹掉 ⇒ 对不上「当时按多少钱算的」。

    ⇒ 口径钉死：**改价 ⇒ 新价今天起生效，旧价闭区间到昨天。**
    """
    source = ROUTER_PATH.read_text(encoding="utf-8")
    assert "effective_from = max(body.effective_from, today)" in source
    assert "existing.effective_to = effective_from - timedelta(days=1)" in source


# ---------------------------------------------------------------------------
# 3 · 前端：录入要方便、错配要看得见
# ---------------------------------------------------------------------------


def test_frontend_records_cny_price_directly():
    """录入**只填人民币等值**（Walter 2026-11-17 拍板：人工填的就是人民币）。

    ⚠️ 旧设计要求前端填「原币单价 + 币种 + 汇率」再折算 ——
    那层壳**反而制造了漏钱风险**：库里存的是人民币，界面却让人填外币，
    运营照抄官方新币价目表（SGD 2.87）就会被当成 2.87 元人民币存进去
    ⇒ 尾程少算 5 倍多 ⇒ 成本底线偏低 ⇒ 漏钱。
    ⇒ 汇率层从录入界面**整体去掉**：只留一列人民币单价，
    外币痕迹由运营写在**备注**里（自由文本，不参与计算）。
    """
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    # 不再有汇率录入列
    assert 'label="原币单价"' not in source
    assert 'label="币种"' not in source
    assert 'label="汇率→人民币"' not in source
    # 只剩人民币单价一列
    assert 'label="单件尾程费（元）"' in source
    # 前端不再做折算（后端契约本来就只收 CNY）
    assert "exchange_rate" not in source
    assert "deliveryRuleConvertedCny" not in source
    assert "deliveryCurrencyOptions" not in source


def test_frontend_sends_cny_price_unconverted():
    """保存时发出去的就是运营填的那个数字（原样，不做任何乘法）。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "unit_price: row.unit_price" in source
    assert 'currency: "CNY"' in source


def test_frontend_has_card_view_for_platform_warehouse():
    """费率维护是**卡片式**：一个「平台 × 仓」一张卡，卡内按全局段表顺序列全部重量段。

    业务理由（Walter 2026-11-17）：一行一条的表格里，运营改一档价要先在多行中
    **用眼睛找**那一行（平台/仓/段三列并排），且平台与仓在存量行上是禁用的
    ⇒ 找错行、改错行的风险高。卡片把「一个平台在一个仓的全部档位」收在一起，
    切换平台/仓即切换整卡。
    """
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    # 卡片由「平台 + 仓」两个选择器定位，卡内是全局段表的全部段
    assert "deliveryCardForm" in source
    assert "deliveryCardRows" in source
    # 卡片由「平台 + 仓」两个选择器定位
    assert "deliveryCardForm.platform_code" in source
    assert "deliveryCardForm.warehouse_code" in source
    # 卡内按全局段表顺序渲染全部段（不让人挑段 ⇒ 不会漏段、不会选错）
    assert "deliveryCardTiers" in source


def test_frontend_marks_missing_tier_in_card():
    """某段没配价 ⇒ 卡上要**看得见**（否则要等系统报错才知道缺料）。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "deliveryCardTierMissing" in source


def test_frontend_batch_add_lands_back_on_card():
    """批量新增完成后**回到卡片视图**（批量只是铺价的手段，不是终点）。

    业务理由（Walter 2026-11-17）：批量录完如果还停在批量弹窗里，
    运营无法一眼核对/微调每一档 ⇒ 后续修改仍然困难。
    """
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "批量新增尾程费率" in source
    assert "deliveryBatchRows" in source
    # 批量保存后要定位到对应的卡片
    assert "deliveryCardForm.platform_code = " in source
    assert "deliveryCardForm.warehouse_code = " in source


def test_frontend_warns_on_duplicated_weight_tiers():
    """同一个「平台 × 仓 × 重量段」填两行 ⇒ 选档歧义 ⇒ 系统算不出来。

    ⚠️ 批次 6：重量段是**全局一套**的，段与段之间**不会**重叠
    （不重叠由段表保证）⇒ 不再有「区间重叠」提示；
    真正要拦的是「同一个平台 × 仓 × 段填了两行当期」。
    """
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "deliveryTierDuplicateHint" in source
    assert "deliveryTierOverlapHint" not in source


def test_frontend_can_disable_a_rate_tier():
    """停用比删除安全（费率有生效日期，删除会丢历史）。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "停用" in source
    assert "启用" in source


def test_frontend_price_change_opens_a_new_version():
    """改价必须走 POST（新版本：旧行闭区间）⇒ 不能走 PATCH 覆盖历史行。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "createDeliveryRateRule" in source
    assert "updateDeliveryRateRule" in source


def test_frontend_warns_when_platform_has_no_delivery_cost_rate():
    """平台没配「尾程占收入比」⇒ 尾程不进成本底线 ⇒ 录入费率的人要知道。"""
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "尾程占收入比" in source
    assert "deliveryPlatformSplitHint" in source


# ---------------------------------------------------------------------------
# 4 · 换价（同档位）必须能走通：旧行闭区间 + 新行今天起生效
# ---------------------------------------------------------------------------


def test_same_tier_price_change_is_not_rejected_as_overlap():
    """同段换价 = 旧行**马上闭区间** + 新行今天起生效。

    ⚠️ 批次 6 起重量段是**全局一套**的 ⇒ 不再有「区间重叠」这回事
    （段与段不重叠由段表保证）；但「同一个平台 × 仓 × 段填两行当期」仍然要拦
    ⇒ 换价时必须把旧行闭区间，而不是报 409。

    ⚠️ 2026-11-17：闭区间的终点按**今天**算，不能按调用方传来的原生效日 ——
    照原生效日算会把旧价闭成倒挂区间（``effective_to < effective_from``）
    ⇒ 撞检查约束 ⇒ 报 409「already exists」（实测卡片改价直接不可用），
    而且历史被抹掉 ⇒ 对不上「当时按多少钱算的」。
    """
    source = ROUTER_PATH.read_text(encoding="utf-8")
    # 同段判定仍在（写法二选一：等于 / 不等于则跳过）
    assert (
        "weight_tier_code == body.weight_tier_code" in source
        or "weight_tier_code != body.weight_tier_code" in source
    )
    # 闭区间终点 = 新行生效日 - 1 天
    assert "existing.effective_to = effective_from - timedelta(days=1)" in source
    # 新行生效日从今天起算
    assert "effective_from = max(body.effective_from, today)" in source
    # 旧写法（照调用方的原生效日闭区间）不许再回来
    assert (
        "existing.effective_to = body.effective_from - timedelta(days=1)" not in source
    )


# ---------------------------------------------------------------------------
# 5 · 批次 6：按段选档后的原因码
# ---------------------------------------------------------------------------


def test_old_kg_based_reason_codes_are_gone():
    """按段定价后，「重量落在所有档位之外」这类原因**不再存在**。"""
    source = Path("backend/services/product_delivery_cost_service.py").read_text(
        encoding="utf-8"
    )
    assert "weight_above_top_tier" not in source
    assert "weight_below_bottom_tier" not in source
    assert "missing_weight_tier" in source
    assert "missing_delivery_rate_for_tier" in source


def test_frontend_reports_the_new_reason_codes():
    source = FRONTEND_PATH.read_text(encoding="utf-8")
    assert "missing_weight_tier" in source
    assert "missing_delivery_rate_for_tier" in source
    assert "weight_above_top_tier" not in source
    assert "weight_below_bottom_tier" not in source


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])
