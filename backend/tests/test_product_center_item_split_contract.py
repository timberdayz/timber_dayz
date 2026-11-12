"""商品中心响应模型的**款 / 货分离**契约（2026-11-12 · 批次 C）。

背景
----
``backend/schemas/product_center.py`` 的 ``ProductCenterItem`` 一模两用：

* 对 **SPU 行** —— ``spu`` 是**标识**（主键），``active`` 是字段；
* 对 **SKU 行** —— ``spu`` 是**从 ``bridge_spu_sku`` 当前有效绑定算出来的投影**，
  ``active`` 恒为 None（schema 里的注释自己就承认了这一点）。

⇒ 同一个字段名 ``spu`` 在两种语义下含义不同（标识 vs 引用），
   而调用方拿到 ``ProductCenterItem`` **无法判断自己拿的是哪一种**。

本文件锁定：

* 款与货各有自己的响应模型（``SpuItem`` / ``SkuItem``），
  **标识与引用不再共用同一个字段**；
* ``active`` 只属于款 —— 货没有这个列（货用 ``status``）；
* 列表响应与批量写入响应也一分为二，
  不再出现「同一个响应模型既能装款也能装货」的情况；
* 旧的``ProductCenterItem`` / ``ProductCenterListResponse`` /
  ``BulkMutationResponse`` **必须消失** ——
  留着它们，就等于留着一扇后门：下一个人又会拿它去装两种东西。

⚠️ 路由必须**按端点**选模型：SPU 的端点用款模型，SKU 的端点用货模型。
   用错 ⇒ 字段被 Pydantic 静默丢弃（``extra='ignore'``），
   前端拿到空值却没有任何报错。
"""

from __future__ import annotations

from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = PROJECT_ROOT / "backend/domains/business/routers/product_center.py"


def _router_source() -> str:
    return ROUTER_PATH.read_text(encoding="utf-8")


def _schema_module():
    from backend.schemas import product_center

    return product_center


# ---------------------------------------------------------------------------
# ① 旧模型必须消失
# ---------------------------------------------------------------------------


def test_ambiguous_product_center_item_is_gone():
    """``ProductCenterItem`` 必须被拆掉 —— 留着就是留后门。"""
    module = _schema_module()

    assert not hasattr(module, "ProductCenterItem"), (
        "ProductCenterItem 仍在 —— 它同时表示款与货，" "调用方分不清 spu 是标识还是引用"
    )


def test_ambiguous_list_response_is_gone():
    """``ProductCenterListResponse`` 一分为二。"""
    module = _schema_module()

    assert not hasattr(module, "ProductCenterListResponse")


def test_ambiguous_bulk_mutation_response_is_gone():
    """``BulkMutationResponse`` 一分为二。"""
    module = _schema_module()

    assert not hasattr(module, "BulkMutationResponse")


# ---------------------------------------------------------------------------
# ② 款模型：spu 是标识
# ---------------------------------------------------------------------------


def test_spu_item_exists_and_spu_is_the_identifier():
    """款模型里 ``spu`` 是**标识** ⇒ 必填。"""
    from backend.schemas.product_center import SpuItem

    assert "spu" in SpuItem.model_fields
    assert SpuItem.model_fields["spu"].is_required() is True


def test_spu_item_carries_the_spu_only_fields():
    """款独有：经营状态、软删标记、品类、款级风控率。"""
    from backend.schemas.product_center import SpuItem

    fields = SpuItem.model_fields
    for name in (
        "spu_name",
        "biz_status",
        "active",
        "category_l1",
        "category_l2",
        "category_l1_code",
        "category_l2_code",
        "logistics_damage_rate",
        "return_loss_rate",
        "owner_user_id",
    ):
        assert name in fields, name


def test_spu_item_has_no_sku_columns():
    """款模型不该带 SKU 的列。"""
    from backend.schemas.product_center import SpuItem

    fields = SpuItem.model_fields
    for name in ("sku_id", "sku_key", "weight_kg", "min_selling_price"):
        assert name not in fields, name


# ---------------------------------------------------------------------------
# ③ 货模型：spu 是引用
# ---------------------------------------------------------------------------


def test_sku_item_exists_and_carries_its_own_identifier():
    """货模型里标识是 ``sku_id`` / ``sku_key``。"""
    from backend.schemas.product_center import SkuItem

    fields = SkuItem.model_fields
    assert "sku_id" in fields
    assert "sku_key" in fields


def test_sku_item_spu_is_a_reference_not_an_identifier():
    """货模型里 ``spu`` 是**引用**（可空）—— 它可能还没挂到任何款上。"""
    from backend.schemas.product_center import SkuItem

    fields = SkuItem.model_fields
    assert "spu" in fields
    assert fields["spu"].is_required() is False


def test_sku_item_exposes_the_binding_effective_date():
    """归属的生效日必须露出来（时态）。"""
    from backend.schemas.product_center import SkuItem

    fields = SkuItem.model_fields
    assert "spu_effective_from" in fields
    assert fields["spu_effective_from"].is_required() is False


def test_sku_item_has_no_active_field():
    """``active`` 只属于款 —— 货用 ``status``。

    留着 ``active`` 在货模型里，恒为 None，
    就是「同一个模型两套语义」的残留。
    """
    from backend.schemas.product_center import SkuItem

    assert "active" not in SkuItem.model_fields


def test_sku_item_carries_the_pricing_fields():
    """定价底线是「货 × 平台」的量 ⇒ 只在货模型上。"""
    from backend.schemas.product_center import SkuItem

    fields = SkuItem.model_fields
    for name in (
        "creator_commission_rate",
        "creator_commission_rate_fallback",
        "current_discount_rate",
        "clearance_max_discount_rate",
        "min_selling_price",
        "min_selling_price_source",
        "min_selling_price_is_override",
        "min_selling_price_override",
        "min_selling_price_missing_reasons",
        "pricing_tier_label",
        "pricing_days_since_restock",
        "pricing_tier_source",
        "min_selling_price_by_platform",
    ):
        assert name in fields, name
        assert fields[name].is_required() is False, name


def test_sku_item_validates_a_bare_orm_row():
    """裸 ORM 行必须能校验（列表接口就是拿裸行拼的）。"""
    from backend.schemas.product_center import SkuItem
    from modules.core.db import DimErpSku

    row = DimErpSku(sku_id=9001, sku_key="TEST-SKU-1", sku_name="测试SKU")
    item = SkuItem.model_validate(row)

    assert item.sku_id == 9001
    assert item.sku_key == "TEST-SKU-1"
    assert item.min_selling_price is None
    assert item.pricing_tier_source is None
    assert item.min_selling_price_missing_reasons == []


def test_spu_item_validates_a_bare_orm_row():
    """裸 SPU 行必须能校验，且 ``active`` 读得到（软删标记）。"""
    from backend.schemas.product_center import SpuItem
    from modules.core.db import DimSpu

    deleted = SpuItem.model_validate(DimSpu(spu="SPU-DELETED", active=False))
    assert deleted.active is False

    alive = SpuItem.model_validate(DimSpu(spu="SPU-ALIVE", active=True))
    assert alive.active is True


# ---------------------------------------------------------------------------
# ④ 列表 / 批量响应一分为二
# ---------------------------------------------------------------------------


def test_spu_list_response_carries_spu_items():
    from backend.schemas.product_center import SpuItem, SpuListResponse

    assert SpuListResponse.model_fields["data"].annotation == list[SpuItem]


def test_sku_list_response_carries_sku_items():
    from backend.schemas.product_center import SkuItem, SkuListResponse

    assert SkuListResponse.model_fields["data"].annotation == list[SkuItem]


def test_bulk_mutation_responses_are_split():
    from backend.schemas.product_center import (
        SkuBulkMutationResponse,
        SkuItem,
        SpuBulkMutationResponse,
        SpuItem,
    )

    assert SpuBulkMutationResponse.model_fields["items"].annotation == list[SpuItem]
    assert SkuBulkMutationResponse.model_fields["items"].annotation == list[SkuItem]
    for model in (SpuBulkMutationResponse, SkuBulkMutationResponse):
        assert "created" in model.model_fields
        assert "updated" in model.model_fields


def test_list_responses_keep_the_pagination_shape():
    """两个列表响应都保留分页字段 —— 一分为二不该把分页弄丢。"""
    from backend.schemas.product_center import SkuListResponse, SpuListResponse

    for model in (SpuListResponse, SkuListResponse):
        for name in ("page", "page_size", "total", "total_pages"):
            assert name in model.model_fields, name


# ---------------------------------------------------------------------------
# ⑤ 路由必须按端点选对模型
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route_path,expected_model",
    [
        ('@router.get("/api/spus", response_model=SpuListResponse)', "SpuListResponse"),
        (
            '@router.post("/api/spus", response_model=SpuItem, status_code=201)',
            "SpuItem",
        ),
        ('@router.patch("/api/spus/{spu}", response_model=SpuItem)', "SpuItem"),
        (
            '@router.post("/api/spus/bulk", response_model=SpuBulkMutationResponse)',
            "SpuBulkMutationResponse",
        ),
        ('@router.get("/api/skus", response_model=SkuListResponse)', "SkuListResponse"),
        (
            '@router.post("/api/skus", response_model=SkuItem, status_code=201)',
            "SkuItem",
        ),
        ('@router.patch("/api/skus/{sku_id}", response_model=SkuItem)', "SkuItem"),
        (
            '@router.post("/api/skus/bulk", response_model=SkuBulkMutationResponse)',
            "SkuBulkMutationResponse",
        ),
    ],
)
def test_router_uses_the_matching_response_model(route_path, expected_model):
    """每个端点必须声明**与自己的实体相符**的响应模型。

    用错模型 ⇒ 字段被静默丢弃 ⇒ 前端拿到空值却没有任何报错。
    """
    source = _router_source()

    assert route_path in source, f"路由未按预期声明响应模型：{route_path}"


def test_router_no_longer_references_the_ambiguous_models():
    source = _router_source()

    # ⚠️ 必须按**词边界**匹配 —— 否则 ``SpuBulkMutationResponse`` 会被
    #    ``BulkMutationResponse`` 的子串匹配误伤。
    import re

    for name in (
        "ProductCenterItem",
        "ProductCenterListResponse",
        "BulkMutationResponse",
    ):
        pattern = r"\b%s\b" % name
        assert not re.search(pattern, source), f"路由仍在引用已拆除的 {name}"


def test_router_imports_the_split_models():
    source = _router_source()

    for name in (
        "SpuItem",
        "SkuItem",
        "SpuListResponse",
        "SkuListResponse",
        "SpuBulkMutationResponse",
        "SkuBulkMutationResponse",
    ):
        assert name in source, f"路由未导入 {name}"
