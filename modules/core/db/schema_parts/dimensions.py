from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

# SPU 经营状态与生命周期不变量的约束**从真源渲染**，不在这里手抄状态清单
# （律 1「真源只能一个，而且必须写在纸上」）。
#
# 真源：``backend/services/product_spu_lifecycle.py``
# ⇒ 状态全集、「能不能挂货」的口径、``active=false ⟹ biz_status='retired'``
#    的不变量，全部只在那一处定义。
# 守护测试：``backend/tests/test_product_spu_lifecycle_ssot_contract.py``
#
# ⚠️ 依赖方向说明: ``modules/core`` 引用 ``backend.services`` 在本仓库有先例
#    （``modules/core/db/schema_parts/collection.py`` → ``backend.services.collection_task_status``），
#    且本模块只依赖纯常量与渲染函数 ⇒ 无循环导入风险。
from backend.services.product_spu_lifecycle import (  # noqa: E402
    render_spu_biz_status_constraint,
    render_spu_lifecycle_constraint,
)

# SKU ↔ SPU **归属关系**的状态取值域**从真源渲染**，不在这里手抄状态清单。
#
# 真源：``backend/services/product_spu_binding.py``
# ⇒ active（当前有效）/ inactive（软删封存，可复活）/ historical（换款归档，历史证据）
#    三个值语义各不相同，任何一个都不能被悄悄替换成第四个。
# 守护测试：``backend/tests/test_product_center_binding_write_path_contract.py``
from backend.services.product_spu_binding import (  # noqa: E402
    CURRENT_BINDING_STATUS,
    render_binding_status_constraint,
    render_current_binding_index_predicate,
)


class DimPlatform(Base):
    __tablename__ = "dim_platforms"

    platform_code = Column(
        String(32), primary_key=True
    )  # e.g., 'shopee','miaoshou','tiktok'
    name = Column(String(64), nullable=False)  # display name
    default_fee_rate = Column(Float, nullable=True)
    fee_rate_source = Column(String(128), nullable=True)
    fee_rate_effective_from = Column(Date, nullable=True)
    fee_rate_version = Column(String(64), nullable=True)
    # 默认达人佣金率：SKU 未单独设置 creator_commission_rate 时的兜底值
    default_creator_commission_rate = Column(Numeric(12, 8), nullable=True)
    # 平台其他成本率：恒等式反推值，**已含平台佣金率**，不重复计入底线分母
    other_cost_rate = Column(Numeric(12, 8), nullable=True)
    # --- ROI 广告投放配置（阶段 1）---
    # 安全边际：建议 ROI = 保本ROI × (1 + roi_safety_margin)。
    # 业界实测 12%–25%，取下沿 20% 做保守默认（设计稿 §2.5⑨）。
    roi_safety_margin = Column(
        Numeric(6, 4), nullable=False, default=Decimal("0.20"), server_default="0.20"
    )
    # 平台后台可填的目标 ROI 上限（硬约束）。TikTok 20 / Shopee 50。
    # 建议 ROI 超过它就被截断（**只封顶不封底**）。
    target_roi_ceiling = Column(
        Numeric(10, 2), nullable=False, default=Decimal("50"), server_default="50"
    )
    # 平台可填下限：**当前不参与 clamp**，只记录平台允许的最小值（预留）
    target_roi_floor = Column(
        Numeric(10, 2), nullable=False, default=Decimal("1"), server_default="1"
    )
    platform_role = Column(
        String(16), nullable=False, default="source", server_default="source"
    )
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("name", name="uq_dim_platforms_name"),
        CheckConstraint(
            "platform_role IN ('sales', 'source', 'test')", name="ck_dim_platforms_role"
        ),
        CheckConstraint(
            "default_fee_rate IS NULL OR (default_fee_rate >= 0 AND default_fee_rate <= 1)",
            name="ck_dim_platforms_fee_rate_range",
        ),
        CheckConstraint(
            "default_creator_commission_rate IS NULL OR (default_creator_commission_rate >= 0 AND default_creator_commission_rate <= 1)",
            name="ck_dim_platforms_creator_commission_rate_range",
        ),
        CheckConstraint(
            "other_cost_rate IS NULL OR (other_cost_rate >= 0 AND other_cost_rate < 1)",
            name="ck_dim_platforms_other_cost_rate_range",
        ),
        CheckConstraint(
            "roi_safety_margin >= 0 AND roi_safety_margin < 1",
            name="ck_dim_platforms_roi_safety_margin_range",
        ),
        CheckConstraint(
            "target_roi_ceiling >= 1", name="ck_dim_platforms_target_roi_ceiling_range"
        ),
        CheckConstraint(
            "target_roi_floor >= 1", name="ck_dim_platforms_target_roi_floor_range"
        ),
        {"schema": "core"},
    )


class DimWarehouse(Base):
    """Canonical receiving warehouse and its single-country destination."""

    __tablename__ = "dim_warehouses"

    warehouse_code = Column(String(128), primary_key=True)
    warehouse_name = Column(String(256), nullable=False)
    country_code = Column(String(16), nullable=False)
    country_name = Column(String(64), nullable=False)
    region = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default="active")
    source = Column(String(128), nullable=True)
    effective_from = Column(Date, nullable=False, server_default=func.current_date())
    effective_to = Column(Date, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')", name="ck_dim_warehouses_status"
        ),
        Index("ix_dim_warehouses_country_status", "country_code", "status"),
        {"schema": "core"},
    )


class DimWarehouseNameAlias(Base):
    """妙手原始仓名 → 规范仓代码 的对照表。

    为什么需要这张表
    ----------------
    库存采集侧写进 ``mart.inventory_state`` 的仓名是**妙手导出的原始字符串**
    （生产实测：``新加坡``、``马来仓``、``菲律宾1店-儿童书包``、``菲律宾仓库（维修工具）``、
    ``菲律宾3店-时尚箱包``），而经营域用的规范仓代码来自 ``core.dim_warehouses``
    （``SG-01``/``MY-01``/``PH-01-CHILD``/``PH-REPAIR``/``PH-03-FASHION``）。
    两边的**字符串本身就不一样**（规范仓名带「仓」字后缀，原始仓名不带），
    所以不能靠字符串拼接去猜 —— 猜错的后果是**把货算到别的仓**，
    而仓错 ⇒ 库龄错 ⇒ 底线错 ⇒ 定价错。

    所以这里把「原始仓名 → 规范仓代码」做成**显式登记**的一行行记录：
    采集侧查这张表归一，查不到就**留空并记日志**，绝不静默归到一个仓。

    为什么放 ``core`` 而不是 ``mart``
    --------------------------------
    这张表是**主数据性质的对照关系**（仓的名字与代码），不是聚合层的事实。
    ``mart`` 层只放「由采集算出来的事实」，``core`` 层放「人工/主数据维护的对照」。
    """

    __tablename__ = "dim_warehouse_name_aliases"

    #: 妙手原始仓名（``mart.inventory_state.warehouse_name`` 的取值）
    source_warehouse_name = Column(String(255), primary_key=True)
    #: 规范仓代码（对应 ``core.dim_warehouses.warehouse_code``）
    warehouse_code = Column(
        String(128),
        ForeignKey("core.dim_warehouses.warehouse_code", ondelete="CASCADE"),
        nullable=False,
    )
    #: 归一说明：这一行是人登记的，还是种子播种的（便于日后核对）
    source = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_dim_warehouse_name_aliases_code", "warehouse_code"),
        {"schema": "core"},
    )


class CollectionSourceIdentifier(Base):
    """采集方标识 —— 「这批数据来自哪个采集器」，**不是**店铺身份。

    权威定义
    --------
    ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS`` 是**唯一定义处**。
    本表的行由迁移 ``current_schema_20261223_collection_source_identifiers`` 从那份定义播种，
    再由 ``backend/tests/test_inventory_warehouse_identity_ssot.py`` 守护
    （表内容 == Python 常量 ⇒ 防漂移）。

    为什么要有这张表
    ----------------
    语义层的身份解析入口 ``semantic.resolve_shop_identity`` 读这张表，
    把采集方代号从候选集里**统一剔除**。

    以前这条规则写在**每条链路各自的 SQL** 里：
    ``orders_atomic.sql`` 有一份字面量、``inventory_snapshot.sql`` 干脆没有 ——
    属于**多处复制**的 SSOT 违规：新加一条链路就会漏掉一次，
    而且漏掉的表现是「采集方代号被当成店铺」。

    采集方代号一旦混进候选集, 就会被主数据候选池反查成一个**伪店铺**
    （``core.dim_shops`` 里确实注册了 ``miaoshou / miaoshou_real_001 / xihong`` 这一行）
    ⇒ 库存的 4,111 行全部挂在一个不存在的店上。
    """

    __tablename__ = "collection_source_identifiers"

    #: 采集方标识（小写形式，与语义层候选集的归一形态一致）
    identifier = Column(String(64), primary_key=True)
    #: 这个标识是什么（给人看的，避免再写一份解释散落在各处）
    description = Column(String(255), nullable=True)
    #: 停用后语义层不再剔除它（留作历史口径追溯）
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = ({"schema": "core"},)


class DimShop(Base):
    __tablename__ = "dim_shops"

    platform_code = Column(
        String(32),
        ForeignKey("core.dim_platforms.platform_code", ondelete="CASCADE"),
        primary_key=True,
    )
    shop_id = Column(String(256), primary_key=True)  # v4.3.4: 扩展到256以支持长shop_id

    shop_slug = Column(String(128), nullable=True)  # human readable
    shop_name = Column(String(256), nullable=True)
    region = Column(String(16), nullable=True)
    currency = Column(String(8), nullable=True)
    timezone = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    platform = relationship("DimPlatform", lazy="joined")

    __table_args__ = (
        Index("ix_dim_shops_platform_shop", "platform_code", "shop_id"),
        Index("ix_dim_shops_platform_slug", "platform_code", "shop_slug"),
        {"schema": "core"},
    )


class DimProduct(Base):
    __tablename__ = "dim_products"

    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)

    product_title = Column(String(512), nullable=True)
    category = Column(String(128), nullable=True)
    status = Column(String(32), nullable=True)  # active/disabled/etc.

    # product images
    image_url = Column(String(1024), nullable=True)
    image_path = Column(String(512), nullable=True)
    image_last_fetched_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_dim_products_platform_shop", "platform_code", "shop_id"),
        {"schema": "core"},
    )


class DimProductCategory(Base):
    """Company-owned two-level product category contract."""

    __tablename__ = "dim_product_categories"

    category_code = Column(String(64), primary_key=True)
    parent_category_code = Column(
        String(64),
        ForeignKey("core.dim_product_categories.category_code", ondelete="RESTRICT"),
        nullable=True,
    )
    level = Column(Integer, nullable=False)
    name_zh = Column(String(128), nullable=False)
    name_en = Column(String(128), nullable=True)
    category_path = Column(String(512), nullable=True)
    status = Column(String(16), nullable=False, default="active")
    is_selectable = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    version = Column(String(32), nullable=False, default="v1")
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_dim_product_categories_parent_status", "parent_category_code", "status"
        ),
        Index("ix_dim_product_categories_level_status", "level", "status"),
        {"schema": "core"},
    )


class DimSpu(Base):
    """Company-wide SPU master data maintained by business users."""

    __tablename__ = "dim_spu"

    spu = Column(String(128), primary_key=True)
    spu_name = Column(String(512), nullable=False)
    category_l1 = Column(String(128), nullable=True)
    category_l2 = Column(String(128), nullable=True)
    # Stable company category codes. Legacy text columns remain for compatibility.
    category_l1_code = Column(
        String(64),
        ForeignKey("core.dim_product_categories.category_code", ondelete="RESTRICT"),
        nullable=True,
    )
    category_l2_code = Column(
        String(64),
        ForeignKey("core.dim_product_categories.category_code", ondelete="RESTRICT"),
        nullable=True,
    )
    logistics_damage_rate = Column(Float, nullable=True)
    return_loss_rate = Column(Float, nullable=True)
    main_image_url = Column(String(1024), nullable=True)
    biz_status = Column(String(32), nullable=False, default="candidate")
    owner_user_id = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("spu", name="uq_dim_spu_spu"),
        Index("ix_dim_spu_status_owner", "biz_status", "owner_user_id"),
        # 经营状态取值域 —— 表达式从真源渲染，不手抄清单。
        CheckConstraint(
            render_spu_biz_status_constraint(),
            name="chk_dim_spu_biz_status",
        ),
        # 建模 A 的不变量：active=false 必然是 retired
        # （淘汰不等于删除：active=true + retired 是合法的「逻辑淘汰」）。
        CheckConstraint(
            render_spu_lifecycle_constraint(),
            name="chk_dim_spu_lifecycle",
        ),
        {"schema": "core"},
    )


class DimErpSku(Base):
    """Canonical ERP SKU identity independent of platform and shop."""

    __tablename__ = "dim_erp_sku"

    sku_id = Column(Integer, primary_key=True, autoincrement=True)
    sku_key = Column(String(255), nullable=False)
    erp_record_id = Column(String(255), nullable=True)
    sku_name = Column(String(512), nullable=True)
    specification = Column(String(512), nullable=True)
    weight_kg = Column(Float, nullable=True)
    package_length_cm = Column(Float, nullable=True)
    package_width_cm = Column(Float, nullable=True)
    package_height_cm = Column(Float, nullable=True)
    # Company-maintained per-unit packed volume.  Historical dimensions remain
    # available as a fallback for imported ERP records.
    unit_volume_cbm = Column(Numeric(18, 6), nullable=True)
    units_per_carton = Column(Integer, nullable=True)
    default_purchase_cost = Column(Float, nullable=True)
    purchase_cost_currency = Column(String(8), nullable=False, default="CNY")
    purchase_cost_source = Column(String(64), nullable=True)
    purchase_cost_confidence = Column(String(16), nullable=False, default="low")
    purchase_cost_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    expected_logistics_cost = Column(Float, nullable=True)
    expected_storage_cost = Column(Float, nullable=True)
    reference_selling_price = Column(Float, nullable=True)
    selling_price_currency = Column(String(8), nullable=False, default="CNY")
    # 「基准售价来源」是**枚举**，不是自由文本（阶段 4 工具 1）。
    # 取值：platform_listing（平台商品页）/ erp（ERP 主数据）/ manual（人工填写）。
    #
    # ⚠️ `platform_listing` 保留了枚举位但**当前没有可靠数据源**
    #    （平台 SKU 档案靠人工维护，覆盖率未知）⇒ 保留位置，不承诺可采集。
    selling_price_source = Column(String(64), nullable=True)
    # 「基准售价确认日期」：运营最后一次确认基准售价的时间（阶段 4 工具 2）。
    # 填基准售价时自动写当天；基准售价被清空时一并清空（价格没了，确认日期无意义）。
    selling_price_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    # 枚举清洗的时间戳（阶段 4 迁移 20261121）。
    # 历史自由文本被归一到枚举的那一刻 —— 只写一次，之后不再动。
    selling_price_source_cleaned_at = Column(DateTime(timezone=True), nullable=True)
    turnover_class = Column(String(16), nullable=True)
    # 该 SKU 的达人佣金率；NULL = 未单独设置，计算时取平台默认值兜底
    creator_commission_rate = Column(Numeric(12, 8), nullable=True)
    # ⚠️ 这里**不**放「人工覆盖的最低售价」，也不放最低售价变更通知的基线。
    #
    # 1) 最低售价的人工覆盖已经是 **SKU × 平台** 的量（底线按平台费率算），
    #    住在 `finance.sku_platform_pricing`（阶段 2.1b）。
    # 2) 商品中心的 SKU 主数据会被「采集机 → 云端」同步做 TRUNCATE + 全量重灌，
    #    住在这里的任何东西都会被每次同步抹掉 ——
    #    基线被抹 ⇒ 同步窗口内的真实变化被静默吞掉；
    #    人工覆盖被抹 ⇒ 运营刚设的最低售价上限人间蒸发。
    #    所以基线放 `ops.price_adjust_baselines`、人工覆盖放
    #    `finance.sku_platform_pricing`（两张表都不参与商品中心同步）。
    status = Column(String(32), nullable=False, default="active")
    source_file_id = Column(Integer, nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("sku_key", name="uq_dim_erp_sku_sku_key"),
        Index("ix_dim_erp_sku_status", "status"),
        Index("ix_dim_erp_sku_erp_record", "erp_record_id"),
        CheckConstraint(
            "turnover_class IS NULL OR turnover_class IN ('fast', 'normal', 'slow')",
            name="ck_dim_erp_sku_turnover_class",
        ),
        CheckConstraint(
            "unit_volume_cbm IS NULL OR unit_volume_cbm >= 0",
            name="ck_dim_erp_sku_unit_volume_cbm",
        ),
        Index("ix_dim_erp_sku_unit_volume_cbm", "unit_volume_cbm"),
        CheckConstraint(
            "creator_commission_rate IS NULL OR (creator_commission_rate >= 0 AND creator_commission_rate <= 1)",
            name="ck_dim_erp_sku_creator_commission_rate",
        ),
        # 阶段 4 工具 1：基准售价来源必须是枚举值。
        CheckConstraint(
            "selling_price_source IS NULL OR selling_price_source IN ('platform_listing', 'erp', 'manual')",
            name="ck_dim_erp_sku_selling_price_source",
        ),
        # 阶段 4 工具 2：有基准售价就必须有确认日期。
        # 用 CHECK 而不是 NOT NULL：历史数据有缺口（迁移会先回填，再加约束）。
        CheckConstraint(
            "reference_selling_price IS NULL OR selling_price_confirmed_at IS NOT NULL",
            name="ck_dim_erp_sku_selling_price_confirmed",
        ),
        {"schema": "core"},
    )


class BridgeSpuSku(Base):
    """Effective-dated manual assignment of an ERP SKU to an SPU."""

    __tablename__ = "bridge_spu_sku"

    id = Column(Integer, primary_key=True, autoincrement=True)
    spu = Column(
        String(128), ForeignKey("core.dim_spu.spu", ondelete="RESTRICT"), nullable=False
    )
    sku_id = Column(
        Integer,
        ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    binding_status = Column(String(32), nullable=False, default=CURRENT_BINDING_STATUS)
    created_by = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_bridge_spu_sku_current",
            "sku_id",
            unique=True,
            # ⚠️ 部分索引谓词也**从真源渲染** ——
            #    「一个 SKU 只有一条当前归属」这条规则不该在 ORM 里再抄一遍。
            postgresql_where=text(render_current_binding_index_predicate()),
        ),
        Index("ix_bridge_spu_sku_spu", "spu", "effective_to"),
        # ⚠️ 归属状态的取值域兜底 —— 从真源渲染，不手抄。
        #    没有它，第四个状态值会**静默**写进库：
        #    三个值的语义各不相同（当前有效 / 软删封存可复活 / 换款归档不可复活），
        #    一旦漂移，恢复端点就会复活一条本该留作历史的关系。
        CheckConstraint(
            render_binding_status_constraint(),
            name="chk_bridge_spu_sku_binding_status",
        ),
        {"schema": "core"},
    )


class BridgeErpSkuKey(Base):
    """Maps source-specific identifiers to the canonical ERP SKU."""

    __tablename__ = "bridge_erp_sku_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_system = Column(String(64), nullable=False)
    source_platform = Column(String(64), nullable=True)
    source_shop_id = Column(String(256), nullable=True)
    source_key_type = Column(String(64), nullable=False)
    source_key = Column(String(255), nullable=False)
    sku_id = Column(
        Integer,
        ForeignKey("core.dim_erp_sku.sku_id", ondelete="CASCADE"),
        nullable=False,
    )
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    source_file_id = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_bridge_erp_sku_key_current",
            "source_system",
            "source_platform",
            "source_shop_id",
            "source_key_type",
            "source_key",
            unique=True,
            postgresql_where=text("effective_to IS NULL AND active = true"),
        ),
        Index("ix_bridge_erp_sku_key_sku", "sku_id"),
        {"schema": "core"},
    )


# ---- Master SKU mapping & bridge (统一SKU映射) ----
class DimProductMaster(Base):
    __tablename__ = "dim_product_master"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    # 公司侧统一SKU/款号,可作为对外展示与聚合主键
    company_sku = Column(String(128), unique=True, nullable=False)

    product_title = Column(String(512), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = ({"schema": "core"},)


class BridgeProductKeys(Base):
    __tablename__ = "bridge_product_keys"

    product_id = Column(
        Integer,
        ForeignKey("core.dim_product_master.product_id", ondelete="CASCADE"),
        primary_key=True,
    )
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)

    __table_args__ = (
        # 关联至平台侧产品维表,复合外键
        ForeignKeyConstraint(
            ["platform_code", "shop_id", "platform_sku"],
            [
                "core.dim_products.platform_code",
                "core.dim_products.shop_id",
                "core.dim_products.platform_sku",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "platform_code", "shop_id", "platform_sku", name="uq_bridge_platform_sku"
        ),
        Index("ix_bridge_product_id", "product_id"),
        {"schema": "core"},
    )


class DimExchangeRate(Base):
    """
    汇率维度表(v4.6.0新增)

    用途:存储和缓存汇率数据
    - 支持全球180+货币
    - 多源汇率API(Open Exchange Rates, ECB, BOC等)
    - 本地缓存策略(24小时TTL)

    CNY本位币设计:
    - 所有交易自动转换为CNY
    - 保留原币金额和汇率(审计追溯)
    """

    __tablename__ = "dim_exchange_rates"

    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 汇率维度
    from_currency = Column(String(3), nullable=False, index=True)  # BRL/SGD/USD/...
    to_currency = Column(String(3), nullable=False, index=True)  # CNY(默认)
    rate_date = Column(Date, nullable=False, index=True)  # 汇率日期

    # 汇率值
    rate = Column(Float, nullable=False)  # 汇率(精度6位小数)

    # 数据源信息
    source = Column(String(50), nullable=True)  # open_exchange_rates/ecb/boc
    priority = Column(Integer, default=99)  # 数据源优先级(1-99)

    # 审计字段
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "from_currency", "to_currency", "rate_date", name="uq_exchange_rate"
        ),
        Index("ix_exchange_rate_lookup", "from_currency", "to_currency", "rate_date"),
        Index("ix_exchange_rate_date", "rate_date"),
        {"schema": "core"},
    )


class AccountAlias(Base):
    """
    账号别名映射表(v4.3.6)

    用途:将妙手(miaoshou)等ERP导出的口语化店铺名映射到统一账号ID
    示例:
    - platform=miaoshou, account=虾皮巴西, store_label_raw="菲律宾1店" -> target_id="shopee_ph_1"
    - platform=miaoshou, account=虾皮巴西, store_label_raw="3C店" -> target_id="shopee_sg_3c"
    """

    __tablename__ = "account_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 源标识(from)
    platform = Column(String(32), nullable=False)  # 如 'miaoshou'
    data_domain = Column(
        String(64), nullable=False, default="orders"
    )  # 仅orders需要对齐
    account = Column(String(128), nullable=True)  # 采购账号(如"虾皮巴西_东朗照明主体")
    site = Column(String(64), nullable=True)  # 站点(如"菲律宾")
    store_label_raw = Column(String(256), nullable=False)  # 原始店铺名(如"菲律宾1店")

    # 目标标识(to)
    target_type = Column(
        String(32), nullable=False, default="account"
    )  # 'account' | 'shop'
    target_id = Column(String(128), nullable=False)  # 标准账号ID或店铺ID

    # 元数据
    confidence = Column(Float, default=1.0)  # 映射置信度(人工=1.0,自动建议<1.0)
    active = Column(Boolean, default=True)  # 是否生效
    notes = Column(Text, nullable=True)  # 备注

    # 审计
    created_by = Column(String(64), default="system")
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        # 唯一约束:同一source组合只能映射到一个target
        Index(
            "uq_account_alias_source",
            "platform",
            "data_domain",
            "account",
            "site",
            "store_label_raw",
            unique=True,
        ),
        # 查询索引
        Index("ix_account_alias_platform_domain", "platform", "data_domain"),
        Index("ix_account_alias_target", "target_id", "active"),
        {"schema": "core"},
    )


class DimCurrencyRate(Base):
    __tablename__ = "dim_currency_rates"

    rate_date = Column(Date, primary_key=True)  # UTC date of rate
    base_currency = Column(String(8), primary_key=True)  # e.g., USD
    quote_currency = Column(String(8), primary_key=True)  # e.g., CNY

    rate = Column(Float, nullable=False)
    source = Column(String(64), nullable=True, default="exchangerate.host")
    fetched_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_currency_base_quote", "base_currency", "quote_currency"),
        {"schema": "core"},
    )


# -------------------- Fact Tables --------------------

# [DELETED] v4.19.0: FactOrder 和 FactOrderItem 已删除
# - 已被 b_class.fact_{platform}_orders_{granularity} 表替代(DSS架构)
# - 所有订单数据现在存储在 b_class schema 下的按平台分表中
