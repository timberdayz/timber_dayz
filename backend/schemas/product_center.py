from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


_CODE_PATTERN = r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"
_CATEGORY_CODE_PATTERN = r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$"

#: 「基准售价来源」的**枚举**取值（阶段 4 工具 1）。
#:
#: - ``platform_listing``：平台商品页价格。**保留枚举位，但当前没有可靠数据源**
#:   （平台 SKU 档案靠人工维护，覆盖率未知）⇒ 不承诺可采集。
#: - ``erp``：ERP 主数据带过来的。
#: - ``manual``：运营在商品中心手填的。
SELLING_PRICE_SOURCES = ("platform_listing", "erp", "manual")

#: 写入侧的取值校验。自由文本在这里**不再被接受** —— 枚举化是这一阶段的目的。
SELLING_PRICE_SOURCE_PATTERN = r"^(?:platform_listing|erp|manual)$"

#: 基准售价多久没被确认就算「过期」（阶段 4 工具 4）。
#: 90 天 = 一个季度的经营周期；超过它，纪律线用的价格就该重新看一眼。
SELLING_PRICE_STALE_DAYS = 90

#: 基准售价与历史成交价中位数的允许偏差（阶段 4 工具 4）。超过就提示。
SELLING_PRICE_DEVIATION_THRESHOLD = 0.30


class ProductCategoryCreateRequest(BaseModel):
    category_code: str = Field(
        min_length=1, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    parent_category_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    level: int = Field(ge=1, le=2)
    name_zh: str = Field(min_length=1, max_length=128)
    name_en: Optional[str] = Field(default=None, max_length=128)
    category_path: Optional[str] = Field(default=None, max_length=512)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    is_selectable: bool = True
    version: str = Field(default="v1", min_length=1, max_length=32)
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None
    description: Optional[str] = None

    @model_validator(mode="after")
    def validate_parent_by_level(self):
        if self.level == 1 and self.parent_category_code is not None:
            raise ValueError("level 1 category cannot have a parent")
        if self.level == 2 and not self.parent_category_code:
            raise ValueError("level 2 category requires a parent category")
        return self


class ProductCategoryUpdateRequest(BaseModel):
    name_zh: Optional[str] = Field(default=None, min_length=1, max_length=128)
    name_en: Optional[str] = Field(default=None, max_length=128)
    category_path: Optional[str] = Field(default=None, max_length=512)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    is_selectable: Optional[bool] = None
    effective_to: Optional[date] = None
    description: Optional[str] = None


class ProductCategoryResponse(ProductCategoryCreateRequest):
    model_config = {"from_attributes": True}


class SpuBulkItem(BaseModel):
    spu: str = Field(min_length=1, max_length=128, pattern=_CODE_PATTERN)
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l2: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    category_l2_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    biz_status: Optional[str] = Field(
        default=None, pattern=r"^(candidate|testing|promoted|retired)$"
    )
    owner_user_id: Optional[int] = None
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # ⚠️ **刻意没有 `active`**（2026-11-12 建模 A）。
    #
    # `active`（是否已删除）只能由**删除 / 恢复**这两个专用动作写：
    #   * `POST /api/spus/{spu}/soft-delete`
    #   * `POST /api/spus/{spu}/restore`
    #   * `POST /api/spus/batch-soft-delete`
    #
    # 原因：它与 `biz_status` 表达的是**同一个**业务事实的两面
    # （删掉的款必然是淘汰的），两者若能各自独立写，就能造出
    # `active=false + biz_status='candidate'` 这种自相矛盾的行 ⇒
    # 「这个款还在不在」就没有唯一答案了。
    #
    # 前端 `payloadSpu` 整行回写会带上 `active` ⇒ Pydantic 默认
    # `extra='ignore'` 会**忽略**它 ⇒ 运营在表格里改名称/状态不会顺手
    # 把 SPU 删掉。


class SpuBulkRequest(BaseModel):
    items: list[SpuBulkItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_single_spu_request_models(cls, value):
        if not isinstance(value, dict):
            return value
        items = value.get("items")
        if items is None:
            return value
        return {
            **value,
            "items": [
                (
                    item.model_dump(exclude_unset=True)
                    if isinstance(item, BaseModel)
                    else item
                )
                for item in items
            ],
        }


class SkuBulkItem(BaseModel):
    sku_id: Optional[int] = Field(default=None, gt=0)
    sku_key: str = Field(min_length=1, max_length=255)
    spu: Optional[str] = Field(default=None, max_length=128, pattern=_CODE_PATTERN)
    effective_from: Optional[date] = None
    erp_record_id: Optional[str] = None
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_tier_code: Optional[str] = Field(default=None, max_length=32)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    unit_volume_cbm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: Optional[str] = Field(
        default="CNY", min_length=3, max_length=8
    )
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: Optional[str] = Field(
        default="low", pattern=r"^(low|medium|high)$"
    )
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: Optional[str] = Field(
        default=None, min_length=3, max_length=8
    )
    selling_price_source: Optional[str] = Field(
        default=None, pattern=SELLING_PRICE_SOURCE_PATTERN
    )
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")
    creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # ⚠️ 这里**不再有** `min_selling_price_override`（阶段 2.1b）：
    # 人工覆盖是 **SKU × 平台** 的量，挂在 SKU 主数据的保存流程上既口径不对
    # （一个数套所有平台），又会被「采集机 → 云端」同步 TRUNCATE 抹掉。
    # 它改走 `PATCH /api/skus/{sku_id}/pricing-override`（平台级独立接口）。

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency != "CNY" or self.selling_price_currency not in (
            None,
            "CNY",
        ):
            raise ValueError("SKU product-center amounts must use CNY")
        return self


class SkuBulkRequest(BaseModel):
    items: list[SkuBulkItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def accept_single_sku_request_models(cls, value):
        if not isinstance(value, dict):
            return value
        items = value.get("items")
        if items is None:
            return value
        return {
            **value,
            "items": [
                (
                    item.model_dump(exclude_unset=True)
                    if isinstance(item, BaseModel)
                    else item
                )
                for item in items
            ],
        }


class SpuCreateRequest(BaseModel):
    spu: str = Field(min_length=1, max_length=128, pattern=_CODE_PATTERN)
    spu_name: str = Field(min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    category_l2_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    main_image_url: Optional[str] = None
    biz_status: str = Field(
        default="candidate", pattern=r"^(candidate|testing|promoted|retired)$"
    )
    owner_user_id: Optional[int] = None
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)


class SpuUpdateRequest(BaseModel):
    spu_name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    category_l2_code: Optional[str] = Field(
        default=None, max_length=64, pattern=_CATEGORY_CODE_PATTERN
    )
    main_image_url: Optional[str] = None
    biz_status: Optional[str] = Field(
        default=None, pattern=r"^(candidate|testing|promoted|retired)$"
    )
    owner_user_id: Optional[int] = None
    logistics_damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_loss_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # ⚠️ **刻意没有 `active`** —— 理由同 `SpuBulkItem`：
    # `active` 只能由删除 / 恢复这两个专用动作写（建模 A）。


class SkuCreateRequest(BaseModel):
    sku_key: str = Field(min_length=1, max_length=255)
    erp_record_id: Optional[str] = None
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_tier_code: Optional[str] = Field(default=None, max_length=32)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    unit_volume_cbm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: str = Field(default="CNY", min_length=3, max_length=8)
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: str = Field(default="low", pattern=r"^(low|medium|high)$")
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: str = Field(default="CNY", min_length=3, max_length=8)
    selling_price_source: Optional[str] = Field(
        default=None, pattern=SELLING_PRICE_SOURCE_PATTERN
    )
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")
    creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # ⚠️ 这里**不再有** `min_selling_price_override`（阶段 2.1b）：
    # 人工覆盖是 **SKU × 平台** 的量，挂在 SKU 主数据的保存流程上既口径不对
    # （一个数套所有平台），又会被「采集机 → 云端」同步 TRUNCATE 抹掉。
    # 它改走 `PATCH /api/skus/{sku_id}/pricing-override`（平台级独立接口）。

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency != "CNY" or self.selling_price_currency != "CNY":
            raise ValueError("SKU product-center amounts must use CNY")
        return self


class SkuUpdateRequest(BaseModel):
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    weight_tier_code: Optional[str] = Field(default=None, max_length=32)
    package_length_cm: Optional[float] = Field(default=None, ge=0)
    package_width_cm: Optional[float] = Field(default=None, ge=0)
    package_height_cm: Optional[float] = Field(default=None, ge=0)
    unit_volume_cbm: Optional[float] = Field(default=None, ge=0)
    units_per_carton: Optional[int] = Field(default=None, ge=1)
    default_purchase_cost: Optional[float] = Field(default=None, ge=0)
    purchase_cost_currency: Optional[str] = Field(
        default=None, min_length=3, max_length=8
    )
    purchase_cost_source: Optional[str] = Field(default=None, max_length=64)
    purchase_cost_confidence: Optional[str] = Field(
        default=None, pattern=r"^(low|medium|high)$"
    )
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    reference_selling_price: Optional[float] = Field(default=None, ge=0)
    selling_price_currency: Optional[str] = Field(
        default=None, min_length=3, max_length=8
    )
    selling_price_source: Optional[str] = Field(
        default=None, pattern=SELLING_PRICE_SOURCE_PATTERN
    )
    selling_price_confirmed_at: Optional[datetime] = None
    turnover_class: Optional[str] = Field(default=None, pattern=r"^(fast|normal|slow)$")
    creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # ⚠️ 这里**不再有** `min_selling_price_override`（阶段 2.1b）：
    # 人工覆盖是 **SKU × 平台** 的量，挂在 SKU 主数据的保存流程上既口径不对
    # （一个数套所有平台），又会被「采集机 → 云端」同步 TRUNCATE 抹掉。
    # 它改走 `PATCH /api/skus/{sku_id}/pricing-override`（平台级独立接口）。

    @model_validator(mode="after")
    def cny_only(self):
        if self.purchase_cost_currency not in (
            None,
            "CNY",
        ) or self.selling_price_currency not in (None, "CNY"):
            raise ValueError("SKU product-center amounts must use CNY")
        return self

    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")


class SpuSkuBindingRequest(BaseModel):
    sku_id: int = Field(gt=0)
    effective_from: date


class SkuPricingOverrideRequest(BaseModel):
    """**平台级**最低售价人工覆盖的设置 / 重置请求（阶段 2.1b）。

    - `platform_code`：**必填**。人工覆盖是 SKU × 平台的量，不传平台就说不清
      要覆盖谁 —— 与「底线按平台算」是同一件事的两面。
    - `min_selling_price_override`：**传 null 表示「重置为自动值」**；
      传数字表示设置该平台的人工覆盖上限（必须 > 0）。

    ⚠️ 不接受 0 或负数：0 不是「不设覆盖」，而是「把底线压到 0」= 把护栏关掉。
    """

    platform_code: str = Field(min_length=1, max_length=32)
    min_selling_price_override: Optional[float] = Field(default=None, gt=0)


class SkuPricingOverrideResponse(BaseModel):
    """平台级人工覆盖的写后回执。"""

    sku_id: int
    platform_code: str
    min_selling_price_override: Optional[float] = None
    min_selling_price_source: Optional[str] = None
    #: True = 已重置为自动值（该平台不再有人工覆盖）
    cleared: bool = False


# ==================== 阶段 4 · 基准售价工具 ====================


class SkuSellingPricePreviewRequest(BaseModel):
    """**基准售价即时影响预览**的请求（阶段 4 工具 3）。

    运营在 SKU 资料页改基准售价时调用：给一个「如果基准售价改成这个数」，
    服务端按**完全相同的定价口径**算一遍纪律线与底线，返回各平台会怎么变。

    ⚠️ 预览是**假设**，不写库；真正生效要等运营保存。
    """

    #: 待预览的基准售价。**必填**（可以是 null）。
    #: null = 预览「清空基准售价」的效果。
    #: ⚠️ 不能给默认值：默认值 None 会让「没传这个字段」和「预览清空」变成同一件事。
    reference_selling_price: Optional[float] = Field(..., ge=0)


class SkuSellingPricePreviewPlatform(BaseModel):
    """某个平台上的预览结果。"""

    platform_code: str
    #: 现在的最低售价（当前基准售价下算出来的）
    min_selling_price_current: Optional[float] = None
    #: 换成新基准售价后的最低售价
    min_selling_price_preview: Optional[float] = None
    #: 变化额（预览 − 现在）
    change: Optional[float] = None
    #: 变化幅度（相对现在的百分比）
    change_pct: Optional[float] = None
    #: 现在的底线来源（cost_floor / discount_guard / manual_override / unavailable）
    source_current: Optional[str] = None
    #: 预览后的底线来源
    source_preview: Optional[str] = None
    #: 该平台是否有人工覆盖。人工覆盖**直接替换**底线 ⇒ 纪律线改了也不生效。
    override_locked: bool = False
    #: 一句话说明（中文，直接给运营看）
    message: Optional[str] = None


class SkuSellingPricePreviewResponse(BaseModel):
    """基准售价即时影响预览的响应。"""

    sku_id: int
    sku_key: Optional[str] = None
    #: 现在库里存的基准售价
    reference_selling_price_current: Optional[float] = None
    #: 本次预览用的基准售价
    reference_selling_price_preview: Optional[float] = None
    #: 命中档位的显示名（纪律线用的让利率来自这里）
    pricing_tier_label: Optional[str] = None
    #: 命中档位的身份（库龄起点）
    pricing_tier_min_restock_days: Optional[int] = None
    platforms: list[SkuSellingPricePreviewPlatform] = Field(default_factory=list)
    #: 整体提示（例如「纪律线生效，最低售价被抬高 123%」）
    warnings: list[str] = Field(default_factory=list)


class SkuSellingPriceDeviation(BaseModel):
    """基准售价 vs 历史成交价中位数的偏差（阶段 4 工具 4 · 偏差校验）。

    ⚠️ `available = False` 表示**算不出来**（没有成交记录 / 样本太少 / 没有汇率），
    这时**不给任何结论** —— 缺输入宁可不算，不可乐观。
    """

    available: bool = False
    #: 算不出来的原因（available=False 时有值）
    reason: Optional[str] = None
    #: 历史成交价中位数（CNY）
    median_price: Optional[float] = None
    #: 参与中位数计算的成交行数
    sample_size: Optional[int] = None
    #: 统计窗口
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    #: 偏差（相对历史成交价中位数的百分比，正数 = 基准售价更高）
    deviation_pct: Optional[float] = None
    #: 是否超过阈值（默认 30%）
    exceeds_threshold: bool = False


class SkuSellingPriceCheck(BaseModel):
    """单个 SKU 的基准售价体检结果。"""

    sku_id: int
    sku_key: Optional[str] = None
    reference_selling_price: Optional[float] = None
    selling_price_source: Optional[str] = None
    selling_price_confirmed_at: Optional[datetime] = None
    #: 距上次确认多少天；从未确认 ⇒ None
    age_days: Optional[int] = None
    #: 是否超过过期阈值（默认 90 天）
    stale: bool = False
    deviation: SkuSellingPriceDeviation


class SkuSellingPriceCheckResponse(BaseModel):
    """基准售价体检（偏差 + 过期）的响应。"""

    items: list[SkuSellingPriceCheck] = Field(default_factory=list)
    #: 偏差超阈值的条数
    deviation_count: int = 0
    #: 过期未确认的条数
    stale_count: int = 0
    #: 有基准售价但**算不出**偏差的条数（缺输入，不是「没问题」）
    unverified_count: int = 0


class SpuItem(BaseModel):
    """**款**（SPU）行 —— ``spu`` 在这里是**标识**（主键）。

    ⚠️ 这里**刻意**不包含任何 SKU 的列：
       款是头、货是脚，二者不是同一张表，也不是同一行。
       （旧的 ``ProductCenterItem`` 两边都装 ⇒ ``spu`` 一会儿是标识、
       一会儿是引用，调用方分不清自己拿的是哪一种。）
    """

    model_config = {"from_attributes": True}

    # --- 标识 ---
    spu: str
    spu_name: Optional[str] = None
    # --- 品类 ---
    category_l1: Optional[str] = None
    category_l2: Optional[str] = None
    category_l1_code: Optional[str] = None
    category_l2_code: Optional[str] = None
    # --- 款级风控（会下发给挂在它下面的货）---
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    main_image_url: Optional[str] = None
    # --- 经营状态 ---
    biz_status: Optional[str] = None
    owner_user_id: Optional[int] = None
    #: 软删标记（``dim_spu.active``）。
    #:
    #: ⚠️ 这个字段以前根本不在响应里，而前端多处依赖它：
    #:   ``row.active === false`` 决定「恢复」按钮是否出现、「删除」按钮是否禁用、
    #:   批量软删选中项过滤、以及整行灰显。
    #:   字段缺失 ⇒ 这些判断全部恒为 false ⇒
    #:     * 已软删的 SPU 在 UI 上**看不出自己被删了**（不灰显）；
    #:     * 「恢复」按钮**永远不出现** ⇒ 软删成了不可逆操作；
    #:     * 已软删的 SPU 仍能被选中、仍能被再次软删。
    #:
    #: ⚠️ **只有款有** ``active`` —— 货用 ``status``（见 :class:`SkuItem`）。
    active: Optional[bool] = None
    updated_at: Optional[datetime] = None


class SkuItem(BaseModel):
    """**货**（SKU）行 —— ``spu`` 在这里是**引用**，不是标识。

    ⚠️ 「这个货挂在哪个款上」**不是货身上的一个字段**，
       而是「一段归属关系在今天的落点」⇒ 引用与生效日必须成对出现
       （见 ``spu`` / ``spu_effective_from``）。

    ⚠️ 这里**刻意没有** ``active`` —— 货的软删用 ``status``。
       （旧的 ``ProductCenterItem`` 把它放在两边，SKU 行上恒为 None。）
    """

    model_config = {"from_attributes": True}

    # --- 标识 ---
    sku_id: Optional[int] = None
    sku_key: Optional[str] = None
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    status: Optional[str] = None
    # --- 当前归属（引用 + 时态）---
    #: 当前归属的款编码。**引用**，不是标识 —— 没挂到任何款上时为 None。
    spu: Optional[str] = None
    #: 当前归属的款名称（从款表投影下来）。
    spu_name: Optional[str] = None
    #: 当前归属**从哪天起生效**（``core.bridge_spu_sku.effective_from``）。
    #:
    #: ⚠️ 归属是**一段有时效的关联**，不是货身上的一个字段 ——
    #:    只给编码，就等于把关联压扁成了字段，
    #:    运营看不到「这个货是什么时候挂到这个款上的」「换过几次款」。
    #:
    #: 没有当前归属 ⇒ None（**不是**今天）。
    spu_effective_from: Optional[date] = None
    # --- 物理与包装 ---
    #: 重量段编码（引用 ``core.dim_weight_tiers.tier_code``，**刻意不建外键**）。
    #: ⚠️ 批次 6 起**不再有** ``weight_kg``：承运商按重量段定价 ⇒ SKU 不称重，
    #:    只报「落在哪一段」。没有段 ⇒ 按最轻段估算（尾程标记为 estimated）。
    weight_tier_code: Optional[str] = None
    #: 重量段显示名（从段表投影下来），前端直接显示，省一次查询。
    weight_tier_label: Optional[str] = None
    package_length_cm: Optional[float] = None
    package_width_cm: Optional[float] = None
    package_height_cm: Optional[float] = None
    unit_volume_cbm: Optional[float] = None
    units_per_carton: Optional[int] = None
    # --- 成本 ---
    default_purchase_cost: Optional[float] = None
    purchase_cost_currency: Optional[str] = None
    purchase_cost_source: Optional[str] = None
    purchase_cost_confidence: Optional[str] = None
    purchase_cost_confirmed_at: Optional[datetime] = None
    expected_logistics_cost: Optional[float] = None
    expected_storage_cost: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    actual_storage_cost: Optional[float] = None
    # --- 基准售价 ---
    reference_selling_price: Optional[float] = None
    selling_price_currency: Optional[str] = None
    selling_price_source: Optional[str] = None
    selling_price_confirmed_at: Optional[datetime] = None
    #: 枚举清洗时间戳（阶段 4 迁移）。历史自由文本被归一到枚举的那一刻。
    selling_price_source_cleaned_at: Optional[datetime] = None
    #: 基准售价已过多少天没确认（阶段 4 工具 4 · 过期巡检）。
    #: 没有确认日期 ⇒ None（**不是 0**）：「从没确认过」和「今天刚确认」是两回事。
    selling_price_age_days: Optional[int] = None
    #: 确认日期是否已超过阈值（默认 90 天）⇒ 页面标黄「纪律线可能失真」。
    selling_price_stale: bool = False
    turnover_class: Optional[str] = None
    # --- 款级风控（从当前归属的款投影下来）---
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    # --- 完整度 ---
    data_completeness: Optional[str] = None
    updated_at: Optional[datetime] = None
    # --- SKU 定价底线（全部 Optional：SkuItem 会被用于校验裸 ORM 行）---
    creator_commission_rate: Optional[float] = None
    creator_commission_rate_fallback: Optional[float] = None
    current_discount_rate: Optional[float] = None
    clearance_max_discount_rate: Optional[float] = None
    min_selling_price: Optional[float] = None
    # 这条底线是按**哪个平台**的成本率算出来的（阶段 2.1：底线是 SKU × 平台的量）。
    # 不带它前端只能显示「默认平台」，运营不知道自己看的是 TikTok 还是 Shopee 的底线。
    min_selling_price_platform: Optional[str] = None
    min_selling_price_source: Optional[str] = None
    min_selling_price_is_override: Optional[bool] = None
    min_selling_price_override: Optional[float] = None
    min_selling_price_missing_reasons: list[str] = Field(default_factory=list)
    # --- 尾程配送费是否进了成本底线（批次 9 B 路线）---
    # ⚠️ 现在**不再成对**：尾程只要有值（且该 SKU 包邮）就直接进分子。
    delivery_cost_in_cost_floor: Optional[bool] = None
    cost_floor_delivery_cost: Optional[float] = None
    # --- 履约按件成本（批次 9 P2）：头程 / 仓储 / 贴单 ---
    # ⚠️ None = 该项**未计入**（缺 SKU 体积或缺仓规则），不是「这项不要钱」。
    cost_floor_logistics_cost: Optional[float] = None
    cost_floor_storage_cost: Optional[float] = None
    cost_floor_label_fee: Optional[float] = None
    pricing_tier_label: Optional[str] = None
    pricing_days_since_restock: Optional[int] = None
    pricing_tier_source: Optional[str] = None
    #: **各可定价平台**各自的底线与人工覆盖（阶段 2.1b）。
    #:
    #: 形如 ``{"tiktok": {"min_selling_price": 127.61, "min_selling_price_override": None,
    #: "min_selling_price_source": "cost_floor", "min_selling_price_is_override": False},
    #: "shopee": {...}}``。
    #:
    #: 为什么要有它：底线是 SKU × 平台的量，前端要「按平台分行」展示与编辑，
    #: 就必须一次拿到**所有**可定价平台的数 —— 而列表接口一次只传一个
    #: ``platform_code``，让前端发 N 次请求既慢又容易出不一致。
    min_selling_price_by_platform: Optional[dict[str, dict]] = None


class SpuListResponse(BaseModel):
    """款列表的响应。"""

    data: list[SpuItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class SkuListResponse(BaseModel):
    """货列表的响应。"""

    data: list[SkuItem]
    page: int
    page_size: int
    total: int
    total_pages: int


class SpuBulkMutationResponse(BaseModel):
    """批量保存**款**的结果。"""

    created: int
    updated: int
    items: list[SpuItem]


class SkuBulkMutationResponse(BaseModel):
    """批量保存**货**的结果。"""

    created: int
    updated: int
    items: list[SkuItem]


class ProductCenterBindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    spu: str
    sku_id: int
    effective_from: date
    effective_to: Optional[date]
    binding_status: str


class SpuOption(BaseModel):
    """值的域里一个 SPU 选项的形状。

    ⚠️ **只给编码与名称**，不给整个 SPU 管理行 ——
    值域是「可选的款有哪些」，不是「这个款的全部资料」。
    """

    spu: str
    spu_name: Optional[str] = None


class SpuOptionListResponse(BaseModel):
    """值的域查询的响应。

    ⚠️ 刻意**不带分页字段** —— 值域是候选集，不是管理列表。
    分页是「SPU 管理」tab 的概念，不该渗进值域。
    """

    data: list[SpuOption] = Field(default_factory=list)


class ProductWarehouseCreateRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=128)
    warehouse_name: str = Field(min_length=1, max_length=256)
    country_code: str = Field(min_length=2, max_length=16)
    country_name: str = Field(min_length=1, max_length=64)
    region: Optional[str] = Field(default=None, max_length=64)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None


class ProductWarehouseUpdateRequest(BaseModel):
    warehouse_name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    country_code: Optional[str] = Field(default=None, min_length=2, max_length=16)
    country_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    region: Optional[str] = Field(default=None, max_length=64)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class PlatformFeeRateUpdateRequest(BaseModel):
    default_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    fee_rate_effective_from: date = Field(default_factory=date.today)
    fee_rate_source: Optional[str] = Field(default=None, max_length=128)
    fee_rate_version: Optional[str] = Field(default=None, max_length=64)
    # 平台成本率：底线计算的成本基数来源
    default_creator_commission_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # 平台其他成本率（批次 9）：**只装「佣金与尾程之外」的平台侧按收入比例扣款**。
    # 平台佣金率（default_fee_rate）**单独进分母**；尾程按重量段单件计价**直接进分子**。
    other_cost_rate: Optional[float] = Field(default=None, ge=0, lt=1)


class PlatformFeeRateResponse(BaseModel):
    """平台成本率的读取形状（与 `PlatformFeeRateUpdateRequest` 对应）。

    声明 response_model 的意义：端点返回的字段集合被钉死，
    避免「加字段忘了加契约 → 前端永远拿到 null」。
    """

    model_config = ConfigDict(from_attributes=True)

    platform_code: str
    default_fee_rate: Optional[float] = None
    default_creator_commission_rate: Optional[float] = None
    other_cost_rate: Optional[float] = None
    fee_rate_effective_from: Optional[date] = None
    fee_rate_source: Optional[str] = None
    fee_rate_version: Optional[str] = None


class WarehouseStorageRuleCreateRequest(BaseModel):
    warehouse_code: str = Field(min_length=1, max_length=128)
    unit_rate_cny: float = Field(ge=0)
    label_fee: Optional[float] = Field(default=None, ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class WarehouseStorageRuleUpdateRequest(BaseModel):
    unit_rate_cny: Optional[float] = Field(default=None, ge=0)
    label_fee: Optional[float] = Field(default=None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class DeliveryRateRuleCreateRequest(BaseModel):
    """尾程配送费费率（平台 × 仓 × 重量段）。

    ⚠️ **重量段是全局一套**（批次 6，2026-11-17）：``weight_tier_code`` 引用
    ``core.dim_weight_tiers`` 里的段 ⇒ 同一个段在所有平台、所有仓含义相同。
    段的上下限**不在这里填** —— 手工填上下限迟早填出重叠段（选档歧义），
    而段表是唯一真源。
    """

    platform_code: str = Field(min_length=1, max_length=32)
    warehouse_code: str = Field(min_length=1, max_length=128)
    weight_tier_code: str = Field(min_length=1, max_length=32)
    unit_price: float = Field(ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not be earlier than effective_from")
        return self

    @model_validator(mode="after")
    def cny_only(self):
        """尾程单价**只认人民币等值**。

        ⚠️ 为什么这么严：平台价目表常是新币/马币（Shopee SG = SGD），
        而尾程计算链**不读汇率**（``currency`` 列存了但计算层没用它换算）。
        照抄新币数字当人民币存进去 ⇒ 尾程少算好几倍 ⇒ **成本底线偏低 ⇒ 直接漏钱**。

        外币请先按汇率折算成人民币等值再录，原币金额与汇率写进 ``notes`` 留档。
        """
        if (self.currency or "CNY").upper() != "CNY":
            raise ValueError(
                "尾程单价必须按人民币等值录入（外币请先按汇率折算，原币与汇率写进备注）"
            )
        self.currency = "CNY"
        return self


class DeliveryRateRuleUpdateRequest(BaseModel):
    """改一档尾程费率：**只允许改备注 / 生效日 / 版本 / 来源 / 状态**。

    ⚠️ **单价不能在这里改**：费率是**版本化只进不退**的 ——
    改价必须走 ``POST /api/delivery-rate-rules``（后端会把旧行**闭区间**、
    新行从今天起生效），历史才留得住痕。在这里改价 = 直接覆盖历史行
    ⇒ 事后对不上「当时按多少钱算的」。

    ⚠️ **身份字段（平台 / 仓 / 重量段）不能改**：改了等于换了一档费率
    —— 那种情况请「新开一行」。
    """

    # 下面这几个字段**只用于把「误用」的请求挡下来并说清为什么不行**。
    unit_price: Optional[float] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    platform_code: Optional[str] = Field(default=None, max_length=32)
    warehouse_code: Optional[str] = Field(default=None, max_length=128)
    weight_tier_code: Optional[str] = Field(default=None, max_length=32)

    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def reject_forbidden_updates(self):
        forbidden = [
            key
            for key in (
                "unit_price",
                "currency",
                "platform_code",
                "warehouse_code",
                "weight_tier_code",
            )
            if getattr(self, key) is not None
        ]
        if forbidden:
            raise ValueError(
                "不能修改 " + "、".join(forbidden) + "：费率版本化只进不退 —— "
                "改价请 POST 新建一档（旧行自动闭区间、新行今天起生效），"
                "平台/仓/重量段是这一行的身份，改身份也要新开一行。"
            )
        return self

    @model_validator(mode="after")
    def effective_window_is_valid(self):
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("effective_to must not be earlier than effective_from")
        return self


class DeliveryRateRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rule_id: int
    platform_code: str
    warehouse_code: str
    weight_tier_code: str
    #: 重量段显示名 + 上下限（从 ``core.dim_weight_tiers`` 投影下来）。
    #: ⚠️ 是**投影**，不是这一行的身份 —— 段的定义全局唯一。
    weight_tier_label: Optional[str] = None
    min_weight_kg: Optional[float] = None
    max_weight_kg: Optional[float] = None
    unit_price: float
    currency: str = "CNY"
    effective_from: date
    effective_to: Optional[date] = None
    status: str = "active"
    source: Optional[str] = None
    version: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ==================== 批次 6 · 重量段（全局一套） ====================


class WeightTierResponse(BaseModel):
    """重量段行（``core.dim_weight_tiers``）。"""

    model_config = ConfigDict(from_attributes=True)

    tier_code: str
    label: str
    #: 段下限（含）。区间左闭右开 ``[min_kg, max_kg)``。
    min_kg: float
    #: 段上限（不含）；None = 往上不封顶。
    max_kg: Optional[float] = None
    #: 轻 → 重 的顺序。
    sort_order: int = 0
    status: str = "active"


class WeightTierCreateRequest(BaseModel):
    """新建一个重量段。"""

    tier_code: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=64)
    min_kg: float = Field(ge=0)
    max_kg: Optional[float] = Field(default=None, ge=0)
    sort_order: int = Field(default=0, ge=0)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")

    @model_validator(mode="after")
    def weight_window_is_valid(self):
        if self.max_kg is not None and self.max_kg <= self.min_kg:
            raise ValueError("max_kg must be greater than min_kg")
        return self


class WeightTierUpdateRequest(BaseModel):
    """改重量段：**只允许改显示名 / 顺序 / 状态**。

    ⚠️ **上下限不能改**：段是全局唯一的，它的区间一旦改了，
    所有引用它的 SKU 与费率行的含义都会漂移（且历史费率对不上号）。
    要改区间请**新建一段**并把费率迁过去。
    """

    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sort_order: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    # 下面这两个只用于把误用挡下来并说清为什么不行。
    min_kg: Optional[float] = Field(default=None, ge=0)
    max_kg: Optional[float] = Field(default=None, ge=0)
    tier_code: Optional[str] = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def reject_forbidden_updates(self):
        forbidden = [
            key
            for key in ("min_kg", "max_kg", "tier_code")
            if getattr(self, key) is not None
        ]
        if forbidden:
            raise ValueError(
                "不能修改 " + "、".join(forbidden) + "：重量段是全局唯一的，"
                "改区间会让所有引用它的 SKU 与费率行含义漂移 —— 请新建一段并迁移费率。"
            )
        return self


# ==================== 批次 6 · 包邮开关（SKU × 平台） ====================


class SkuFreeShippingRequest(BaseModel):
    """设置某 SKU 在某平台的**包邮开关**（批次 6，2026-11-17）。

    业务前提：跨境电商**不是默认包邮**，而是**选择性包邮** ⇒
    「包不包邮」是 SKU × 平台的经营选择。

    - ``free_shipping=true`` ⇒ 商家承担尾程 ⇒ 尾程进成本底线、利润链扣尾程；
    - ``free_shipping=false`` ⇒ 买家付运费 ⇒ 商家不承担尾程
      ⇒ 尾程**不进**底线、也不报「缺尾程费率」、利润链尾程按 0 计。
    """

    platform_code: str = Field(min_length=1, max_length=32)
    free_shipping: bool


class SkuFreeShippingResponse(BaseModel):
    """包邮开关的写后回执。"""

    sku_id: int
    platform_code: str
    free_shipping: bool


class CostAssumptionCreateRequest(BaseModel):
    profile_name: str = Field(min_length=1, max_length=128)
    destination: Optional[str] = None
    transport_type: Optional[str] = None
    billing_basis: str = Field(default="volume", pattern=r"^(volume|weight|quantity)$")
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    customs_rate: Optional[float] = Field(default=None, ge=0)
    storage_unit_rate: Optional[float] = Field(default=None, ge=0)
    platform_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_rate: Optional[float] = Field(default=None, ge=0, le=1)
    damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    effective_from: date
    effective_to: Optional[date] = None
    assumption_source: Optional[str] = None
    confidence_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")


class CostAssumptionUpdateRequest(BaseModel):
    profile_name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    destination: Optional[str] = None
    transport_type: Optional[str] = None
    billing_basis: Optional[str] = Field(
        default=None, pattern=r"^(volume|weight|quantity)$"
    )
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    customs_rate: Optional[float] = Field(default=None, ge=0)
    storage_unit_rate: Optional[float] = Field(default=None, ge=0)
    platform_fee_rate: Optional[float] = Field(default=None, ge=0, le=1)
    return_rate: Optional[float] = Field(default=None, ge=0, le=1)
    damage_rate: Optional[float] = Field(default=None, ge=0, le=1)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    assumption_source: Optional[str] = None
    confidence_level: Optional[str] = Field(
        default=None, pattern=r"^(low|medium|high)$"
    )
    active: Optional[bool] = None


_LOGISTICS_BILLING_UNITS = {
    "volume": "CNY/CBM",
    "weight": "CNY/KG",
    "quantity": "CNY/unit",
    "fixed": "CNY",
}


class LogisticsBillCreateRequest(BaseModel):
    bill_no: str = Field(min_length=1, max_length=128)
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: date
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    currency: str = Field(default="CNY", min_length=3, max_length=8)
    total_amount: float = Field(ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency != "CNY":
            raise ValueError("product-center logistics bills must use CNY")
        return self


class LogisticsBillUpdateRequest(BaseModel):
    logistics_provider: Optional[str] = Field(default=None, max_length=128)
    bill_date: Optional[date] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    total_amount: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency is not None and self.currency != "CNY":
            raise ValueError("product-center logistics bills must use CNY")
        return self


class LogisticsBillSkuLineRequest(BaseModel):
    """Compatibility request for legacy one-SKU bill rows.

    Legacy rows were always volume-billed.  Keep that contract explicit so a
    request cannot reach persistence without a canonical CNY billing unit.
    """

    sku_id: int = Field(gt=0)
    warehouse_code: str = Field(min_length=1, max_length=128)
    shipped_qty: float = Field(gt=0)
    billing_basis: Literal["volume"] = "volume"
    billing_unit: Literal["CNY/CBM"] = "CNY/CBM"
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None


class LogisticsBillLineAllocationRequest(BaseModel):
    """A single purchase-order SKU share of a provider statement row."""

    sku_id: int = Field(gt=0)
    po_id: Optional[str] = Field(default=None, max_length=64)
    shipped_qty: float = Field(gt=0)


class LogisticsBillLineRequest(BaseModel):
    """Provider statement row; supports one or many SKU allocations."""

    sku_ids: list[int] = Field(min_length=1)
    allocations: list[LogisticsBillLineAllocationRequest] = Field(default_factory=list)
    po_id: Optional[str] = Field(default=None, max_length=64)
    warehouse_code: str = Field(min_length=1, max_length=128)
    shipped_qty: float = Field(default=0, ge=0)
    actual_total_weight_kg: Optional[float] = Field(default=None, ge=0)
    actual_total_volume_cbm: Optional[float] = Field(default=None, ge=0)
    billing_basis: str = Field(
        default="volume", pattern=r"^(volume|weight|quantity|fixed)$"
    )
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    billing_unit_rate: Optional[float] = Field(default=None, ge=0)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    line_total_amount: float = Field(default=0, ge=0)
    is_sensitive: bool = False
    sensitive_surcharge: float = Field(default=0, ge=0)
    headhaul_cost: float = Field(default=0, ge=0)
    handling_cost: float = Field(default=0, ge=0)
    last_mile_cost: float = Field(default=0, ge=0)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def normalize_legacy_rate(self):
        if self.billing_unit_rate is None and self.freight_unit_rate is not None:
            self.billing_unit_rate = self.freight_unit_rate
        return self

    @model_validator(mode="after")
    def derive_cny_billing_unit(self):
        expected_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        if self.billing_unit is not None and self.billing_unit != expected_unit:
            raise ValueError(
                f"billing_unit must be {expected_unit}; product-center logistics costs use CNY"
            )
        self.billing_unit = expected_unit
        return self

    @model_validator(mode="after")
    def validate_allocation_skus(self):
        if not self.allocations:
            return self
        allocation_sku_ids = [item.sku_id for item in self.allocations]
        if len(allocation_sku_ids) != len(set(allocation_sku_ids)):
            raise ValueError("a statement row can contain a SKU only once")
        if set(allocation_sku_ids) != set(self.sku_ids):
            raise ValueError("allocation SKU IDs must match sku_ids")
        return self


class LogisticsBillLinesReplaceRequest(BaseModel):
    lines: list[LogisticsBillLineRequest | LogisticsBillSkuLineRequest] = Field(
        min_length=1
    )

    @model_validator(mode="after")
    def reject_duplicate_skus(self):
        # Legacy one-SKU rows remain accepted; new rows may contain multiple SKUs.
        legacy_ids = [
            line.sku_id
            for line in self.lines
            if isinstance(line, LogisticsBillSkuLineRequest)
        ]
        if len(legacy_ids) != len(set(legacy_ids)):
            raise ValueError("a logistics bill can contain each SKU only once")
        return self


class LogisticsBillPurchaseOrdersReplaceRequest(BaseModel):
    po_ids: list[str] = Field(min_length=1)


class PurchaseOrderLineCostSupplementRequest(BaseModel):
    """Manual cost completion when an imported purchase order has no amount."""

    unit_price: float = Field(ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=8)
    purchase_cost_source: str = Field(default="manual", min_length=1, max_length=64)

    @model_validator(mode="after")
    def cny_only(self):
        if self.currency not in (None, "CNY"):
            raise ValueError("purchase-order product-center costs must use CNY")
        return self


class LogisticsProviderRuleCreateRequest(BaseModel):
    logistics_provider: str = Field(min_length=1, max_length=128)
    warehouse_code: Optional[str] = Field(default=None, max_length=128)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    cargo_class: Optional[str] = Field(default=None, max_length=64)
    is_sensitive: bool = False
    is_default: bool = False
    billing_basis: str = Field(
        default="volume", pattern=r"^(volume|weight|quantity|fixed)$"
    )
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    sensitive_surcharge_mode: str = Field(default="manual", max_length=32)
    sensitive_surcharge_rate: Optional[float] = Field(default=None, ge=0)
    effective_from: date
    effective_to: Optional[date] = None
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def derive_cny_billing_unit(self):
        expected_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        if self.billing_unit is not None and self.billing_unit != expected_unit:
            raise ValueError(
                f"billing_unit must be {expected_unit}; product-center logistics costs use CNY"
            )
        self.billing_unit = expected_unit
        return self


class LogisticsProviderRuleUpdateRequest(BaseModel):
    """Partial provider-rule update; never inherit create defaults into PATCHes."""

    logistics_provider: Optional[str] = Field(
        default=None, min_length=1, max_length=128
    )
    warehouse_code: Optional[str] = Field(default=None, max_length=128)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    cargo_class: Optional[str] = Field(default=None, max_length=64)
    is_sensitive: Optional[bool] = None
    is_default: Optional[bool] = None
    billing_basis: Optional[str] = Field(
        default=None, pattern=r"^(volume|weight|quantity|fixed)$"
    )
    billing_unit: Optional[str] = Field(default=None, max_length=32)
    freight_unit_rate: Optional[float] = Field(default=None, ge=0)
    sensitive_surcharge_mode: Optional[str] = Field(default=None, max_length=32)
    sensitive_surcharge_rate: Optional[float] = Field(default=None, ge=0)
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None

    @model_validator(mode="after")
    def derive_cny_billing_unit_when_basis_changes(self):
        if "billing_unit" in self.model_fields_set:
            raise ValueError("billing_unit is derived from billing_basis")
        if self.billing_basis is not None:
            self.billing_unit = _LOGISTICS_BILLING_UNITS[self.billing_basis]
        return self


class LogisticsBillVoidRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


class ProfitPreviewRequest(BaseModel):
    sku_id: int = Field(gt=0)
    platform_code: Optional[str] = Field(default=None, max_length=32)
    selling_price: float = Field(ge=0)
    warehouse_code: Optional[str] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")


class SkuOperatingProfileCreateRequest(BaseModel):
    sku_id: int = Field(gt=0)
    platform_code: str = Field(min_length=1, max_length=32)
    warehouse_code: str = Field(min_length=1, max_length=128)
    warehouse_name: Optional[str] = Field(default=None, max_length=256)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    effective_from: date = Field(default_factory=date.today)
    effective_to: Optional[date] = None


class SkuOperatingProfileUpdateRequest(BaseModel):
    warehouse_name: Optional[str] = Field(default=None, max_length=256)
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    expected_logistics_cost: Optional[float] = Field(default=None, ge=0)
    expected_storage_cost: Optional[float] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, pattern=r"^(active|inactive)$")
    effective_from: Optional[date] = None
    effective_to: Optional[date] = None


class SkuOperatingProfileBulkRequest(BaseModel):
    items: list[SkuOperatingProfileCreateRequest] = Field(default_factory=list)


class SkuOperatingProfileResponse(SkuOperatingProfileCreateRequest):
    profile_id: Optional[int] = None
    platform_fee_rate: Optional[float] = None
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    sku_key: Optional[str] = None
    sku_name: Optional[str] = None
    spu: Optional[str] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    purchase_cost: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    actual_storage_cost: Optional[float] = None
    cost_completeness: Optional[str] = None
    # --- ROI 投放输入（阶段 2.2）---
    # 目标 ROI：运营打算投到多少（商家实收 ÷ 广告费的口径，与平台标尺一致）。
    # NULL = 没填 ⇒ 不参与保本 ROI 护栏。
    target_roi: Optional[float] = None
    # 来源标记：'user_input'（运营自己填）/ 'migrated_from_legacy_rate'（阶段 3 反解）。
    # 两者在利润表里长得一样但可信度不同 ⇒ 必须留痕，不能事后靠猜。
    target_roi_source: Optional[str] = None
    confidence_level: Optional[str] = None
    latest_estimate_as_of: Optional[datetime] = None
    latest_estimate_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SkuOperatingProfitRequest(BaseModel):
    selling_price: Optional[float] = Field(default=None, ge=0)
    warehouse_code: Optional[str] = None
    transport_type: Optional[str] = Field(default=None, pattern=r"^(sea|air|rail)$")
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class SkuOperatingPlatformOption(BaseModel):
    platform_code: str
    name: Optional[str] = None
    default_fee_rate: Optional[float] = None
    fee_rate_effective_from: Optional[date] = None
    fee_rate_source: Optional[str] = None
    fee_rate_version: Optional[str] = None
    default_creator_commission_rate: Optional[float] = None
    other_cost_rate: Optional[float] = None


class SkuOperatingDimensionsResponse(BaseModel):
    platforms: list[SkuOperatingPlatformOption]
    spus: list[str] = []
    skus: list[dict] = []
    warehouses: list[dict]


class SkuOperatingProfitResponse(BaseModel):
    sku_id: int
    profile_id: int
    platform_code: str
    warehouse_code: str
    net_revenue: Optional[float] = None
    purchase_cost: Optional[float] = None
    logistics_cost: Optional[float] = None
    storage_cost: Optional[float] = None
    platform_fee: Optional[float] = None
    expected_return_loss: Optional[float] = None
    expected_damage_loss: Optional[float] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    logistics_cost_source: Optional[str] = None
    storage_cost_source: Optional[str] = None
    cost_completeness: Optional[str] = None
    confidence_level: Optional[str] = None


class SkuOperatingProfitSaveResponse(BaseModel):
    estimate_id: int
    profile_id: int
    sku_id: int
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None


class SkuOperatingProfitHistoryResponse(BaseModel):
    estimate_id: int
    profile_id: int
    sku_id: int
    platform_code: Optional[str] = None
    warehouse_code: Optional[str] = None
    estimate_as_of: Optional[datetime] = None
    estimated_contribution_profit: Optional[float] = None
    estimated_margin_rate: Optional[float] = None
    cost_completeness: str
    confidence_level: str


class PlatformSkuProfitPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_id: int = Field(gt=0)
    platform_code: str = Field(min_length=1, max_length=32)
    warehouse_code: str = Field(min_length=1, max_length=128)
    transport_type: str = Field(pattern=r"^(sea|air|rail)$")
    competitor_price: Optional[float] = Field(default=None, ge=0)
    expected_selling_price: Optional[float] = Field(default=None, gt=0)
    # 广告分成率（老口径逃生口）：**默认 None，不是 0**。
    # ⚠️ 0 会被当成「这个品不投广告」⇒ 广告费 0 ⇒ 利润看着很美；
    #    None 才会让系统如实说「广告费不可算，利润空白」（批次 2 P2）。
    expected_ad_rate: Optional[float] = Field(default=None, ge=0, le=1)
    # --- ROI 投放输入（阶段 2.2）---
    # 目标 ROI：运营打算投到多少。> 0 才有效；不填 = 不参与保本 ROI 护栏。
    target_roi: Optional[float] = Field(default=None, gt=0)
    # 平台报告 ROI：运营从平台后台抄回来的实际投放 ROI。
    # ⚠️ 它是**事实记录**，低于保本线只标红不拦（拦了就等于不许记录亏损投放）。
    actual_roi: Optional[float] = Field(default=None, gt=0)


class PlatformSkuProfitEstimateRequest(PlatformSkuProfitPreviewRequest):
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class PlatformSkuProfitDraftRequest(PlatformSkuProfitPreviewRequest):
    """Persist editable workbench parameters without creating a profit version."""

    pass


class PlatformSkuProfitCandidateResponse(BaseModel):
    sku_id: int
    sku_key: str
    sku_name: Optional[str] = None
    specification: Optional[str] = None
    spu: Optional[str] = None
    reference_selling_price: Optional[float] = None
    purchase_cost: Optional[float] = None
    platform_code: str
    warehouse_code: str
    transport_type: str
    expected_selling_price: Optional[float] = None
    # 测算售价来源（阶段 1）：'user_input' / 'sku_reference' / 'profile'
    expected_selling_price_source: Optional[str] = None
    competitor_price: Optional[float] = None
    expected_ad_rate: Optional[float] = None
    # --- ROI 投放输入（阶段 2.2）---
    # 目标 ROI：运营的当前意图，存经营档案 ⇒ 列表回带供前端预填。
    target_roi: Optional[float] = None
    # 来源标记：'user_input' / 'migrated_from_legacy_rate'（阶段 3 反解）。
    target_roi_source: Optional[str] = None
    # --- ROI 广告投放配置（阶段 1）---
    # 安全边际：建议 ROI = 保本ROI × (1 + roi_safety_margin)，默认 0.20
    roi_safety_margin: Optional[float] = None
    # 平台后台可填的目标 ROI 上限（TikTok 20 / Shopee 50），建议 ROI 超了会被截断
    target_roi_ceiling: Optional[float] = None
    actual_logistics_cost: Optional[float] = None
    # 实际仓储成本：**恒为 None**。系统里不存在仓储费账单（LogisticsBill 的费用构成
    # 全是运费），只有 WarehouseStorageRule 的规则预估。保留字段是为了不破坏契约，
    # 但**前端不应展示它**（展示恒空列只会误导），UI 上该列已删除。
    actual_storage_cost: Optional[float] = None
    platform_fee_rate: Optional[float] = None
    logistics_damage_rate: Optional[float] = None
    return_loss_rate: Optional[float] = None
    # ⚠️ 这里说的是「经营档案配没配」，**不是成本完整度**。
    # 以前前端把它当完整度的兜底值，导致「重估完整度」列在缺失时显示 configured/unconfigured
    # —— 两种不相干的语义混在一列。前端已改为不再使用它。
    configuration_status: str
    turnover_class: Optional[str] = None
    reference_storage_days: Optional[int] = None
    reference_logistics_cost: Optional[float] = None
    reference_storage_cost: Optional[float] = None
    # 贴单费：利润里会实扣这笔，缺了它前端那一列会显示 "-"
    reference_label_fee: Optional[float] = None
    reference_cost_status: str = "ready"
    reference_cost_missing_reasons: list[str] = Field(default_factory=list)
    reference_logistics_missing_reasons: list[str] = Field(default_factory=list)
    reference_storage_missing_reasons: list[str] = Field(default_factory=list)
    # --- 批次 2：输入缺失清单（P2 / P3 / P5）---
    # 「缺哪些**输入**」与上面的「缺哪些**成本规则**」是两回事，分开列：
    #   missing_operating_profile      没有经营档案（这一行还没配过）
    #   missing_target_roi             没填目标 ROI ⇒ 广告费不可算 ⇒ 利润空白
    #   missing_creator_commission_rate 达人佣金率没配（按 0 计，利润偏乐观）
    missing_input_reasons: list[str] = Field(default_factory=list)
    # 达人佣金率的来源：'sku' / 'platform_default' / 'assumed_zero'（按 0 计）
    creator_commission_source: Optional[str] = None
    # --- 尾程配送费（批次 3 只读展示；批次 4 才进利润与成本底线）---
    delivery_cost: Optional[float] = None
    # rate_table（按费率表） / estimated（保守估算） / unavailable（算不出来）
    delivery_cost_source: Optional[str] = None
    delivery_cost_estimated: bool = False
    delivery_cost_missing_reasons: list[str] = Field(default_factory=list)
    # 重量段（批次 6）：SKU 落在哪一段 + 这一段的显示名。
    delivery_cost_weight_tier_code: Optional[str] = None
    delivery_cost_weight_tier_label: Optional[str] = None
    # ⚠️ **包邮开关**（批次 6，2026-11-17）：这个 SKU 在该平台上要不要包邮。
    #    False（默认）⇒ 买家付运费 ⇒ 商家不承担尾程 ⇒ 尾程不计入成本底线。
    free_shipping: bool = False
    preview: Optional[dict] = None
    currency: str = "CNY"
    # --- SKU 定价底线 ---
    # ⚠️ 该模型被候选接口当作 response_model，Pydantic v2 默认 extra='ignore'：
    # 路由返回的字典里没在这里声明的字段，**序列化时会被全部丢弃**。
    creator_commission_rate: Optional[float] = None
    creator_commission_rate_fallback: Optional[float] = None
    current_discount_rate: Optional[float] = None
    clearance_max_discount_rate: Optional[float] = None
    min_selling_price: Optional[float] = None
    # 这条底线是按**哪个平台**的成本率算出来的（阶段 2.1：底线是 SKU × 平台的量）。
    # 不带它前端只能显示「默认平台」，运营不知道自己看的是 TikTok 还是 Shopee 的底线。
    min_selling_price_platform: Optional[str] = None
    min_selling_price_source: Optional[str] = None
    min_selling_price_is_override: Optional[bool] = None
    min_selling_price_override: Optional[float] = None
    min_selling_price_missing_reasons: list[str] = Field(default_factory=list)
    # --- 尾程配送费是否进了成本底线（批次 9 B 路线）---
    # ⚠️ 现在**不再成对**：尾程只要有值（且该 SKU 包邮）就直接进分子。
    delivery_cost_in_cost_floor: Optional[bool] = None
    cost_floor_delivery_cost: Optional[float] = None
    # --- 履约按件成本（批次 9 P2）：头程 / 仓储 / 贴单 ---
    # ⚠️ None = 该项**未计入**（缺 SKU 体积或缺仓规则），不是「这项不要钱」。
    cost_floor_logistics_cost: Optional[float] = None
    cost_floor_storage_cost: Optional[float] = None
    cost_floor_label_fee: Optional[float] = None
    pricing_tier_label: Optional[str] = None
    pricing_days_since_restock: Optional[int] = None
    pricing_tier_source: Optional[str] = None
    min_selling_price_below: Optional[bool] = None
    # --- 仓维度（阶段 6）---
    # 各仓自己的库龄：这个 SKU 在哪几个仓、各自多老。
    # 空列表 = 状态层里没有这个 SKU 的库存行。
    warehouse_restocks: list[dict] = Field(default_factory=list)
    # 跨仓差异：同一 SKU 在别的仓滞销、这个仓不滞销 ⇒ 建议「优先调拨而非降价」。
    # None = 没有差异。**只提示，不改价**。
    warehouse_divergence: Optional[dict] = None
    # --- 当前仓库存（阶段 7）---
    # 当前选中仓的**可用库存数量**。
    # ⚠️ **含零库存行** —— 零 = 这个仓已经清空这货，是事实，不是缺数据。
    # None = 状态层取不到（不是"没有货"，是"查不到"）。
    current_warehouse_available_stock: Optional[int] = None
    # 库存状态：'in_stock'（在卖）/ 'cleared'（已清仓）/ 'no_record'（这个仓没有它的货）
    # / 'unavailable'（状态层不可用，取不到）。
    current_warehouse_stock_status: Optional[str] = None


class PlatformSkuProfitCandidatePageResponse(BaseModel):
    data: list[PlatformSkuProfitCandidateResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


class ProfitEstimateSaveRequest(ProfitPreviewRequest):
    assumption_version: Optional[str] = Field(default=None, min_length=1, max_length=64)


class FeishuProjectionInitializeRequest(BaseModel):
    spu_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    sku_table_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    platform_sku_profit_table_id: Optional[str] = Field(
        default=None, min_length=1, max_length=64
    )
    # 调价记录表：ERP 只往这里**新增**行，行归档由飞书机器人负责
    price_adjust_table_id: Optional[str] = Field(
        default=None, min_length=1, max_length=64
    )
    # 调价记录表所在的**多维表格 token**。留空则回落到 FEISHU_PRODUCT_BASE_TOKEN。
    price_adjust_base_token: Optional[str] = Field(
        default=None, min_length=1, max_length=64
    )


class PriceAdjustSuppressedRecordResponse(BaseModel):
    """一条「被静默的调价变化」的留痕记录。

    2026-11-22 新口径：只有「库龄跨档」才推飞书；其余变化静默但留痕。
    这条记录就是留痕的对外形态——回答「哪天因为什么变过、为什么没通知」。
    """

    business_key: str = Field(description="SKU × 平台 × 仓 的去重键")
    sku_key: Optional[str] = None
    spu: Optional[str] = None
    sku_name: Optional[str] = None
    platform_code: Optional[str] = None
    warehouse_code: Optional[str] = None
    direction: Optional[str] = Field(default=None, description="上升 / 下降 / 保护失效")
    reason: Optional[str] = Field(default=None, description="变动原因（归因）")
    suppression_reason: Optional[str] = Field(default=None, description="静默原因")
    old_min_selling_price: Optional[float] = None
    new_min_selling_price: Optional[float] = None
    change_rate: Optional[float] = None
    pricing_tier_label: Optional[str] = None
    age_days: Optional[int] = None
    changed_at: Optional[str] = Field(default=None, description="这次变化被判定的时间")


class PriceAdjustSuppressedListResponse(BaseModel):
    """被静默的调价变化（留痕）列表。"""

    data: list[PriceAdjustSuppressedRecordResponse]
    count: int = Field(description="本次返回的条数")


class ProfitEstimateCreateRequest(BaseModel):
    sku_id: int = Field(gt=0)
    assumption_version: str = Field(min_length=1, max_length=64)
    scenario: str = Field(default="base", pattern=r"^base$")
    selling_price: Optional[float] = Field(default=None, ge=0)
    purchase_cost: Optional[float] = Field(default=None, ge=0)
    logistics_cost: Optional[float] = Field(default=None, ge=0)
    storage_cost: Optional[float] = Field(default=None, ge=0)
    platform_fee: Optional[float] = Field(default=None, ge=0)
    expected_return_loss: Optional[float] = Field(default=None, ge=0)
    expected_damage_loss: Optional[float] = Field(default=None, ge=0)
    cost_completeness: str = Field(
        default="incomplete", pattern=r"^(complete|partial|incomplete)$"
    )
    confidence_level: str = Field(default="medium", pattern=r"^(low|medium|high)$")


# ==================== SPU 删除向导 (M1: 软删最小可用) ====================


class SpuDeletionCheck(BaseModel):
    """单条校验结果。status=pass 通过 / fail 阻塞 / warn 软提示。"""

    code: str
    label: str
    status: Literal["pass", "fail", "warn"]
    detail: Optional[str] = None


class SpuDeletionPreviewResponse(BaseModel):
    """删除预览:返回 7 项校验明细 + 软删/硬删能力 + 影响预估。"""

    spu: str
    spu_name: Optional[str] = None
    can_soft_delete: bool
    can_hard_delete: bool = False  # M3 才启用
    checks: list[SpuDeletionCheck] = Field(default_factory=list)
    soft_delete_impact: dict[str, int] = Field(default_factory=dict)
    hard_delete_impact: dict[str, int] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)


class SpuSoftDeleteRequest(BaseModel):
    """软删请求体。reason 可选(不强制),confirm 必须 true(防误触)。"""

    reason: Optional[str] = Field(default=None, max_length=500)
    confirm: bool = False

    @model_validator(mode="after")
    def check_confirm(self):
        if not self.confirm:
            raise ValueError("confirm must be true to proceed with soft delete")
        return self


class SpuSoftDeleteResponse(BaseModel):
    """软删返回:告知影响范围 + 时间戳。"""

    spu: str
    spu_name: Optional[str] = None
    soft_deleted_at: datetime
    affected_bindings: int
    biz_status: str
    audit_recorded: bool = True


class SpuRestoreRequest(BaseModel):
    """SPU 恢复请求体(revive 已软删的 SPU)。reason 可选。"""

    reason: Optional[str] = Field(default=None, max_length=500)
    confirm: bool = False

    @model_validator(mode="after")
    def check_confirm(self):
        if not self.confirm:
            raise ValueError("confirm must be true to proceed with spu restore")
        return self


class SpuRestoreResponse(BaseModel):
    """SPU 恢复返回。"""

    spu: str
    spu_name: Optional[str] = None
    previous_biz_status: str  # 恢复前 biz_status(通常 'retired')
    new_biz_status: str  # 恢复后 biz_status(通常 'promoted')
    restored_bindings: int  # 复活的 binding 数量(0/1)
    restored_at: datetime
    audit_recorded: bool = True


# ==================== 批量软删 (M2) ====================


class BatchSpuSoftDeleteRequest(BaseModel):
    """批量软删请求:SPU 列表(1~100)+ 可选 reason + confirm。

    策略:任一 SPU fail 则整体回滚,保证事务原子性。
    """

    spus: list[str] = Field(min_length=1, max_length=100)
    reason: Optional[str] = Field(default=None, max_length=500)
    confirm: bool = False

    @model_validator(mode="after")
    def check_confirm(self):
        if not self.confirm:
            raise ValueError("confirm must be true to proceed with batch soft delete")
        if len(set(self.spus)) != len(self.spus):
            raise ValueError("spus contains duplicates")
        return self


class BatchSpuSoftDeleteItem(BaseModel):
    """批量处理中单个 SPU 的结果。"""

    spu: str
    spu_name: Optional[str] = None
    status: Literal["deleted", "blocked"]
    affected_bindings: int = 0
    blocked_reasons: list[str] = Field(default_factory=list)
    warn_checks: list[dict] = Field(default_factory=list)


class BatchSpuSoftDeleteResponse(BaseModel):
    """批量软删响应:汇总 + 每个 SPU 状态。"""

    total: int
    deleted: int
    blocked: int
    rolled_back: bool = False  # True 表示因 fail 整体回滚
    items: list[BatchSpuSoftDeleteItem]


# ==================== SKU 停用/恢复 (M5.1) ====================


class SkuDeletionCheck(BaseModel):
    """SKU 单条校验结果。复用 SPU 语义(fail=阻塞 / warn=软提示 / pass=无影响)。"""

    code: str
    label: str
    status: Literal["pass", "fail", "warn"]
    detail: Optional[str] = None


class SkuDeletionPreviewResponse(BaseModel):
    """SKU 删除预览。

    can_soft_delete: 当前 status='active' 时 True;已 inactive 时 False(可走恢复路径)。
    can_hard_delete: 仅当业务引用表全 0 时 True(M5.2 才真正启用,本阶段仅作 hint)。
    """

    sku_id: int
    sku_key: str
    sku_name: Optional[str] = None
    current_status: str
    can_soft_delete: bool
    can_hard_delete: bool = False  # M5.2 启用
    business_reference_count: int = 0  # 9 张关联表的引用总数(0 才能硬删)
    checks: list[SkuDeletionCheck] = Field(default_factory=list)
    soft_delete_impact: dict[str, int] = Field(default_factory=dict)
    blocked_reasons: list[str] = Field(default_factory=list)


class SkuSoftDeleteRequest(BaseModel):
    """SKU 停用请求体。reason 可选(不强制),confirm 必须 true。"""

    reason: Optional[str] = Field(default=None, max_length=500)
    confirm: bool = False

    @model_validator(mode="after")
    def check_confirm(self):
        if not self.confirm:
            raise ValueError("confirm must be true to proceed with sku soft delete")
        return self


class SkuSoftDeleteResponse(BaseModel):
    """SKU 停用返回。"""

    sku_id: int
    sku_key: str
    sku_name: Optional[str] = None
    previous_status: str
    new_status: str  # 'inactive'
    affected_bindings: int
    soft_deleted_at: datetime
    audit_recorded: bool = True


class SkuRestoreRequest(BaseModel):
    """SKU 恢复请求体。reason 可选。"""

    reason: Optional[str] = Field(default=None, max_length=500)
    confirm: bool = False

    @model_validator(mode="after")
    def check_confirm(self):
        if not self.confirm:
            raise ValueError("confirm must be true to proceed with sku restore")
        return self


class SkuRestoreResponse(BaseModel):
    """SKU 恢复返回。"""

    sku_id: int
    sku_key: str
    sku_name: Optional[str] = None
    previous_status: str
    new_status: str  # 'active'
    restored_bindings: int
    restored_at: datetime
    audit_recorded: bool = True


class SkuPricingPolicyBase(BaseModel):
    """库龄档位定价纪律规则（公司级）。"""

    tier_label: str = Field(min_length=1, max_length=32)
    discount_rate: float = Field(ge=0, le=1)
    target_margin_rate: float = Field(ge=0, lt=1)
    platform_basis: str = Field(min_length=1, max_length=32)
    effective_from: date
    status: str = Field(default="active", pattern=r"^(active|inactive)$")
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None


class SkuPricingPolicyCreateRequest(SkuPricingPolicyBase):
    min_restock_days: int = Field(ge=0)


class SkuPricingPolicyUpdateRequest(BaseModel):
    """更新档位规则。

    ⚠️ **刻意不含 `status`**：当前行谓词是
    `status='active' AND effective_to IS NULL`，一旦把当前行直接置成 `inactive`，
    这个库龄档位就会从「当前生效规则」里消失——等于**静默删掉一档**，
    且规则集合变空后所有 SKU 一起掉进 `missing_pricing_policy`、最低售价算不出来。
    停用请走版本化路径（`PUT` 改 `effective_from` → 关旧行 + 建新行），
    那条路径由 `resolve_policy_update` 统一裁决。
    """

    tier_label: str = Field(min_length=1, max_length=32)
    discount_rate: float = Field(ge=0, le=1)
    target_margin_rate: float = Field(ge=0, lt=1)
    platform_basis: str = Field(min_length=1, max_length=32)
    effective_from: date
    min_restock_days: int = Field(ge=0)
    source: Optional[str] = Field(default=None, max_length=128)
    version: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = None


class SkuPricingPolicyResponse(SkuPricingPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    policy_id: int
    min_restock_days: int
    effective_to: Optional[date] = None
