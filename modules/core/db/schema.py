#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unified star schema ORM (SQLAlchemy) for ERP database.

Tables:
- dim_platforms
- dim_shops
- dim_products
- dim_currency_rates
- fact_orders
- fact_order_items
- fact_product_metrics
- catalog_files (ingestion authority)

Primary keys (confirmed):
- Orders: (platform_code, shop_id, order_id)
- Products: (platform_code, shop_id, platform_sku)
- Metrics: (platform_code, shop_id, platform_sku, metric_date, metric_type)

Notes:
- Keep original currency columns and *_rmb columns.
- Index for (platform_code, shop_id, date/granularity) as critical queries.
- Platform code canonicalization will be handled by ingestion layer; schema stores canonical code.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    JSON,
    Text,
    ForeignKey,
    UniqueConstraint,
    Index,
    ForeignKeyConstraint,
    CheckConstraint,  # v4.5.1新增
    text,  # v4.5.1新增
    BigInteger,  # v4.12.0新增：用户权限表
    Table,  # v4.12.0新增：用户权限表
    Numeric,  # v4.12.0新增：运营数据表
)
from sqlalchemy.dialects.postgresql import JSONB  # v4.12.0新增：运营数据表
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func  # v4.12.0新增：用户权限表

Base = declarative_base()

# -------------------- Dimension Tables --------------------

class DimPlatform(Base):
    __tablename__ = "dim_platforms"

    platform_code = Column(String(32), primary_key=True)  # e.g., 'shopee','miaoshou','tiktok'
    name = Column(String(64), nullable=False)             # display name
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("name", name="uq_dim_platforms_name"),
    )


class DimShop(Base):
    __tablename__ = "dim_shops"

    platform_code = Column(String(32), ForeignKey("dim_platforms.platform_code", ondelete="CASCADE"), primary_key=True)
    shop_id = Column(String(256), primary_key=True)  # v4.3.4: 扩展到256以支持长shop_id

    shop_slug = Column(String(128), nullable=True)  # human readable
    shop_name = Column(String(256), nullable=True)
    region = Column(String(16), nullable=True)
    currency = Column(String(8), nullable=True)
    timezone = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    platform = relationship("DimPlatform", lazy="joined")

    __table_args__ = (
        Index("ix_dim_shops_platform_shop", "platform_code", "shop_id"),
        Index("ix_dim_shops_platform_slug", "platform_code", "shop_slug"),
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
    image_last_fetched_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dim_products_platform_shop", "platform_code", "shop_id"),
    )

# ---- Master SKU mapping & bridge (统一SKU映射) ----
class DimProductMaster(Base):
    __tablename__ = "dim_product_master"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    # 公司侧统一SKU/款号，可作为对外展示与聚合主键
    company_sku = Column(String(128), unique=True, nullable=False)

    product_title = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BridgeProductKeys(Base):
    __tablename__ = "bridge_product_keys"

    product_id = Column(Integer, ForeignKey("dim_product_master.product_id", ondelete="CASCADE"), primary_key=True)
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)

    __table_args__ = (
        # 关联至平台侧产品维表，复合外键
        ForeignKeyConstraint(
            ["platform_code", "shop_id", "platform_sku"],
            ["dim_products.platform_code", "dim_products.shop_id", "dim_products.platform_sku"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("platform_code", "shop_id", "platform_sku", name="uq_bridge_platform_sku"),
        Index("ix_bridge_product_id", "product_id"),
    )


class DimExchangeRate(Base):
    """
    汇率维度表（v4.6.0新增）
    
    用途：存储和缓存汇率数据
    - 支持全球180+货币
    - 多源汇率API（Open Exchange Rates, ECB, BOC等）
    - 本地缓存策略（24小时TTL）
    
    CNY本位币设计：
    - 所有交易自动转换为CNY
    - 保留原币金额和汇率（审计追溯）
    """
    __tablename__ = "dim_exchange_rates"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 汇率维度
    from_currency = Column(String(3), nullable=False, index=True)  # BRL/SGD/USD/...
    to_currency = Column(String(3), nullable=False, index=True)    # CNY（默认）
    rate_date = Column(Date, nullable=False, index=True)           # 汇率日期
    
    # 汇率值
    rate = Column(Float, nullable=False)  # 汇率（精度6位小数）
    
    # 数据源信息
    source = Column(String(50), nullable=True)  # open_exchange_rates/ecb/boc
    priority = Column(Integer, default=99)      # 数据源优先级（1-99）
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='uq_exchange_rate'),
        Index('ix_exchange_rate_lookup', 'from_currency', 'to_currency', 'rate_date'),
        Index('ix_exchange_rate_date', 'rate_date'),
    )



class AccountAlias(Base):
    """
    账号别名映射表（v4.3.6）
    
    用途：将妙手(miaoshou)等ERP导出的口语化店铺名映射到统一账号ID
    示例：
    - platform=miaoshou, account=虾皮巴西, store_label_raw="菲律宾1店" -> target_id="shopee_ph_1"
    - platform=miaoshou, account=虾皮巴西, store_label_raw="3C店" -> target_id="shopee_sg_3c"
    """
    __tablename__ = "account_aliases"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 源标识（from）
    platform = Column(String(32), nullable=False)  # 如 'miaoshou'
    data_domain = Column(String(64), nullable=False, default='orders')  # 仅orders需要对齐
    account = Column(String(128), nullable=True)  # 采购账号（如"虾皮巴西_东朗照明主体"）
    site = Column(String(64), nullable=True)  # 站点（如"菲律宾"）
    store_label_raw = Column(String(256), nullable=False)  # 原始店铺名（如"菲律宾1店"）
    
    # 目标标识（to）
    target_type = Column(String(32), nullable=False, default='account')  # 'account' | 'shop'
    target_id = Column(String(128), nullable=False)  # 标准账号ID或店铺ID
    
    # 元数据
    confidence = Column(Float, default=1.0)  # 映射置信度（人工=1.0，自动建议<1.0）
    active = Column(Boolean, default=True)  # 是否生效
    notes = Column(Text, nullable=True)  # 备注
    
    # 审计
    created_by = Column(String(64), default='system')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        # 唯一约束：同一source组合只能映射到一个target
        Index(
            'uq_account_alias_source',
            'platform', 'data_domain', 'account', 'site', 'store_label_raw',
            unique=True
        ),
        # 查询索引
        Index('ix_account_alias_platform_domain', 'platform', 'data_domain'),
        Index('ix_account_alias_target', 'target_id', 'active'),
    )


class DimCurrencyRate(Base):
    __tablename__ = "dim_currency_rates"

    rate_date = Column(Date, primary_key=True)  # UTC date of rate
    base_currency = Column(String(8), primary_key=True)   # e.g., USD
    quote_currency = Column(String(8), primary_key=True)  # e.g., CNY

    rate = Column(Float, nullable=False)
    source = Column(String(64), nullable=True, default="exchangerate.host")
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_currency_base_quote", "base_currency", "quote_currency"),
    )


# -------------------- Fact Tables --------------------

class FactOrder(Base):
    """
    [WARN] v4.6.0 DSS架构重构：已废弃
    - 已被fact_raw_data_orders_*表替代（按data_domain+granularity分表）
    - 表结构保留用于兼容性，但新数据应写入fact_raw_data_*表
    - 计划在Phase 6.1中删除（需要先迁移所有数据）
    """
    __tablename__ = "fact_orders"

    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)

    # times
    order_time_utc = Column(DateTime, nullable=True)
    order_date_local = Column(Date, nullable=True)  # date bucket in shop timezone

    # currency & amounts (original + RMB)
    currency = Column(String(8), nullable=True)
    subtotal = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL
    subtotal_rmb = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL
    shipping_fee = Column(Float, default=0.0)
    shipping_fee_rmb = Column(Float, default=0.0)
    tax_amount = Column(Float, default=0.0)
    tax_amount_rmb = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    discount_amount_rmb = Column(Float, default=0.0)
    total_amount = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL
    total_amount_rmb = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL

    payment_method = Column(String(64), nullable=True)
    payment_status = Column(String(32), default="pending")

    # status
    order_status = Column(String(32), default="pending")
    shipping_status = Column(String(32), default="pending")
    delivery_status = Column(String(32), default="pending")
    is_cancelled = Column(Boolean, default=False)
    is_refunded = Column(Boolean, default=False)
    refund_amount = Column(Float, default=0.0)
    refund_amount_rmb = Column(Float, default=0.0)

    buyer_id = Column(String(128), nullable=True)
    buyer_name = Column(String(256), nullable=True)
    # 数据血缘
    file_id = Column(Integer, nullable=True)
    # 通用扩展属性：用于存放未晋升为标准列的长尾字段（入库兜底）
    attributes = Column(JSON, nullable=True)
    
    # v4.3.6: 妙手(miaoshou)订单账号级对齐字段
    store_label_raw = Column(String(256), nullable=True)  # 原始"店铺"列（如"菲律宾1店"）
    site = Column(String(64), nullable=True)  # 站点（如"菲律宾"）
    account = Column(String(128), nullable=True)  # 采购账号
    aligned_account_id = Column(String(128), nullable=True)  # 对齐后的标准账号ID

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fact_orders_plat_shop_date", "platform_code", "shop_id", "order_date_local"),
        Index("ix_fact_orders_status", "platform_code", "shop_id", "order_status"),
        Index("ix_fact_orders_file_id", "file_id"),
    )


class FactOrderItem(Base):
    """
    [WARN] v4.6.0 DSS架构重构：已废弃
    - 已被fact_raw_data_orders_*表替代（按data_domain+granularity分表）
    - 表结构保留用于兼容性，但新数据应写入fact_raw_data_*表
    - 计划在Phase 6.1中删除（需要先迁移所有数据）
    """
    __tablename__ = "fact_order_items"

    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    order_id = Column(String(128), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)

    # [*] v4.12.0新增：产品ID冗余字段（便于直接查询，无需通过BridgeProductKeys关联）
    product_id = Column(Integer, ForeignKey("dim_product_master.product_id", ondelete="SET NULL"), nullable=True, comment="产品ID（冗余字段，通过BridgeProductKeys自动关联）")

    product_title = Column(String(512), nullable=True)
    quantity = Column(Integer, default=1, nullable=False)  # [*] v4.12.0修复：NOT NULL

    currency = Column(String(8), nullable=True)
    unit_price = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL
    unit_price_rmb = Column(Float, default=0.0, nullable=False)  # [*] v4.12.0修复：NOT NULL
    line_amount = Column(Float, default=0.0)
    line_amount_rmb = Column(Float, default=0.0)
    # 通用扩展属性：用于存放未晋升为标准列的长尾字段（入库兜底）
    attributes = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_fact_items_plat_shop_order", "platform_code", "shop_id", "order_id"),
        Index("ix_fact_items_plat_shop_sku", "platform_code", "shop_id", "platform_sku"),
        Index("ix_fact_items_product_id", "product_id"),  # [*] v4.12.0新增：支持通过product_id高效查询
    )


class FactOrderAmount(Base):
    """
    订单金额维度表（v4.6.0核心设计）
    
    维度表设计：统一字段 + 多维度列
    - 优势：零字段爆炸，多货币支持，符合关系型范式
    - 用途：存储订单金额维度数据（销售额/退款 × 状态 × 货币）
    
    维度列：
    - metric_type: sales_amount（销售额）/ refund_amount（退款）
    - metric_subtype: completed/paid/placed/cancelled/pending_shipment/...
    - currency: BRL/SGD/CNY/USD/EUR/...
    
    示例：
    - 销售额（已付款订单）（BRL） -> {metric_type: sales_amount, metric_subtype: paid, currency: BRL}
    - 退款金额（SGD） -> {metric_type: refund_amount, metric_subtype: standard, currency: SGD}
    """
    __tablename__ = "fact_order_amounts"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段（不使用外键约束，数据仓库设计模式）
    order_id = Column(String(128), nullable=False, index=True)
    
    # 维度列（关键设计）
    metric_type = Column(String(32), nullable=False, index=True)  # sales_amount/refund_amount
    metric_subtype = Column(String(32), nullable=False, index=True)  # completed/paid/placed/cancelled/...
    currency = Column(String(3), nullable=False, index=True)  # BRL/SGD/CNY/...
    
    # 金额列
    amount_original = Column(Float, nullable=False)  # 原币金额
    amount_cny = Column(Float, nullable=True)  # CNY金额（自动转换）
    exchange_rate = Column(Float, nullable=True)  # 汇率（审计）
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_order_amounts_order", "order_id"),
        Index("ix_order_amounts_metric", "metric_type", "metric_subtype"),
        Index("ix_order_amounts_currency", "currency", "created_at"),
        Index("ix_order_amounts_composite", "order_id", "metric_type", "metric_subtype", "currency"),
    )


class FactProductMetric(Base):
    """
    [WARN] v4.6.0 DSS架构重构：已废弃
    - 已被fact_raw_data_products_*表替代（按data_domain+granularity分表）
    - 表结构保留用于兼容性，但新数据应写入fact_raw_data_*表
    - 计划在Phase 6.1中删除（需要先迁移所有数据）
    
    原设计说明（方案B+ 扁平化设计）：
    
    设计理念：
    - 宽表设计：直接存储所有指标字段，避免外键查询
    - 支持多粒度：daily/weekly/monthly在同一表
    - 完整业务标识：platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope
    
    主键设计：
    - 复合主键：platform_code + shop_id + platform_sku + metric_date + metric_type（初始设计）
    - 唯一索引：platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope（v4.10.0更新）
    """
    __tablename__ = "fact_product_metrics"
    
    # ========== 主键字段（业务标识） ==========
    platform_code = Column(String(32), nullable=False, primary_key=True, index=True)
    shop_id = Column(String(64), nullable=False, primary_key=True, index=True)
    platform_sku = Column(String(128), nullable=False, primary_key=True, index=True)
    metric_date = Column(Date, nullable=False, primary_key=True, index=True)
    metric_type = Column(String(64), nullable=False, primary_key=True)
    
    # ========== 粒度与层级字段 ==========
    granularity = Column(String(16), nullable=False, server_default='daily', index=True)
    sku_scope = Column(String(8), nullable=False, server_default='product', index=True, comment='SKU粒度：product(商品级) | variant(规格级)')
    data_domain = Column(String(50), nullable=True, index=True, comment='数据域：products/inventory等')
    parent_platform_sku = Column(String(128), nullable=True, index=True, comment='父级SKU（当sku_scope=variant时指向商品级SKU）')
    
    # ========== 数据血缘字段 ==========
    source_catalog_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment='来源文件ID')
    
    # ========== 商品基础信息 ==========
    product_name = Column(String(500), nullable=True)
    category = Column(String(200), nullable=True)
    brand = Column(String(100), nullable=True)
    specification = Column(String(500), nullable=True, comment='商品规格')
    
    # ========== 价格信息 ==========
    currency = Column(String(8), nullable=True)
    price = Column(Float, nullable=False, server_default='0.0', comment='商品价格（原币）')
    price_rmb = Column(Float, nullable=False, server_default='0.0', comment='商品价格（人民币）')
    
    # ========== 库存信息 ==========
    stock = Column(Integer, nullable=False, server_default='0', comment='当前库存')
    total_stock = Column(Integer, nullable=True, comment='总库存')
    available_stock = Column(Integer, nullable=True, comment='可用库存')
    reserved_stock = Column(Integer, nullable=True, comment='预留库存')
    in_transit_stock = Column(Integer, nullable=True, comment='在途库存')
    warehouse = Column(String(100), nullable=True, comment='仓库名称')
    
    # ========== 图片信息 ==========
    image_url = Column(String(500), nullable=True)
    
    # ========== 销售指标 ==========
    sales_volume = Column(Integer, nullable=False, server_default='0', comment='销量')
    sales_amount = Column(Float, nullable=False, server_default='0.0', comment='销售额（原币）')
    sales_amount_rmb = Column(Float, nullable=False, server_default='0.0', comment='销售额（人民币）')
    sales_volume_7d = Column(Integer, nullable=True, comment='7天销量')
    sales_volume_30d = Column(Integer, nullable=True, comment='30天销量')
    sales_volume_60d = Column(Integer, nullable=True, comment='60天销量')
    sales_volume_90d = Column(Integer, nullable=True, comment='90天销量')
    
    # ========== 流量指标 ==========
    page_views = Column(Integer, nullable=False, server_default='0', comment='页面浏览量')
    unique_visitors = Column(Integer, nullable=False, server_default='0', comment='独立访客数')
    click_through_rate = Column(Float, nullable=True, comment='点击率')
    order_count = Column(Integer, nullable=True, server_default='0', comment='订单数统计')
    
    # ========== 转化指标 ==========
    conversion_rate = Column(Float, nullable=True, comment='转化率')
    add_to_cart_count = Column(Integer, nullable=False, server_default='0', comment='加购数')
    
    # ========== 评价指标 ==========
    rating = Column(Float, nullable=True, comment='评分')
    review_count = Column(Integer, nullable=False, server_default='0', comment='评价数')
    
    # ========== 时间维度字段 ==========
    period_start = Column(Date, nullable=True, comment='周/月统计区间起始日')
    metric_date_utc = Column(Date, nullable=True, comment='UTC日期（按店铺时区换算）')
    
    # ========== 指标值字段（兼容旧设计） ==========
    metric_value = Column(Float, nullable=False, server_default='0', comment='指标值（兼容旧设计）')
    metric_value_rmb = Column(Float, nullable=False, server_default='0', comment='指标值（人民币，兼容旧设计）')
    
    # ========== 时间戳字段 ==========
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    # ========== 表约束和索引 ==========
    __table_args__ = (
        # 唯一索引：platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope
        UniqueConstraint(
            "platform_code", "shop_id", "platform_sku", "metric_date", "granularity", "sku_scope",
            name="ix_product_unique_with_scope"
        ),
        # 外键约束：source_catalog_id -> catalog_files.id
        ForeignKeyConstraint(
            ["source_catalog_id"],
            ["catalog_files.id"],
            ondelete="SET NULL"
        ),
        # 外键约束：platform_code + shop_id + platform_sku -> dim_products
        ForeignKeyConstraint(
            ["platform_code", "shop_id", "platform_sku"],
            ["dim_products.platform_code", "dim_products.shop_id", "dim_products.platform_sku"]
        ),
        # 索引：支持父SKU聚合查询
        Index("ix_product_parent_date", "platform_code", "shop_id", "parent_platform_sku", "metric_date"),
        # 索引：支持平台+店铺+日期+粒度查询
        Index("ix_metrics_plat_shop_date_gran", "platform_code", "shop_id", "metric_date", "granularity"),
        # 索引：支持平台+店铺+指标类型查询
        Index("ix_metrics_plat_shop_type", "platform_code", "shop_id", "metric_type"),
    )


class FactTraffic(Base):
    """
    流量数据事实表（运营数据）
    
    设计规则：
    - 主键：自增ID（便于外键引用和性能优化）
    - 业务唯一索引：platform_code + shop_id + traffic_date + granularity + metric_type + data_domain
    - shop_id为核心字段（运营数据主键设计规则）
    - 当shop_id为NULL时，使用account作为替代
    """
    __tablename__ = "fact_traffic"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(50), nullable=False, index=True)
    shop_id = Column(String(100), nullable=True, index=True)
    account = Column(String(100), nullable=True)
    traffic_date = Column(Date, nullable=False, index=True)
    granularity = Column(String(20), nullable=False)
    metric_type = Column(String(50), nullable=False)
    metric_value = Column(Numeric(15, 2), nullable=False, default=0.0)
    data_domain = Column(String(50), nullable=False, default="traffic")
    attributes = Column(JSONB, nullable=True)
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint(
            "platform_code", "shop_id", "traffic_date", "granularity", "metric_type", "data_domain",
            name="uq_fact_traffic_business"
        ),
    )


class FactService(Base):
    """
    服务数据事实表（运营数据）
    
    设计规则：
    - 主键：自增ID（便于外键引用和性能优化）
    - 业务唯一索引：platform_code + shop_id + service_date + granularity + metric_type + data_domain
    - shop_id为核心字段（运营数据主键设计规则）
    - 当shop_id为NULL时，使用account作为替代
    """
    __tablename__ = "fact_service"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(50), nullable=False, index=True)
    shop_id = Column(String(100), nullable=True, index=True)
    account = Column(String(100), nullable=True)
    service_date = Column(Date, nullable=False, index=True)
    granularity = Column(String(20), nullable=False)
    metric_type = Column(String(50), nullable=False)
    metric_value = Column(Numeric(15, 2), nullable=False, default=0.0)
    data_domain = Column(String(50), nullable=False, default="services")
    attributes = Column(JSONB, nullable=True)
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint(
            "platform_code", "shop_id", "service_date", "granularity", "metric_type", "data_domain",
            name="uq_fact_service_business"
        ),
    )


class FactAnalytics(Base):
    """
    分析数据事实表（运营数据）
    
    设计规则：
    - 主键：自增ID（便于外键引用和性能优化）
    - 业务唯一索引：platform_code + shop_id + analytics_date + granularity + metric_type + data_domain
    - shop_id为核心字段（运营数据主键设计规则）
    - 当shop_id为NULL时，使用account作为替代
    """
    __tablename__ = "fact_analytics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(50), nullable=False, index=True)
    shop_id = Column(String(100), nullable=True, index=True)
    account = Column(String(100), nullable=True)
    analytics_date = Column(Date, nullable=False, index=True)
    granularity = Column(String(20), nullable=False)
    metric_type = Column(String(50), nullable=False)
    metric_value = Column(Numeric(15, 2), nullable=False, default=0.0)
    data_domain = Column(String(50), nullable=False, default="analytics")
    attributes = Column(JSONB, nullable=True)
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint(
            "platform_code", "shop_id", "analytics_date", "granularity", "metric_type", "data_domain",
            name="uq_fact_analytics_business"
        ),
    )


# -------------------- Ingestion Authority --------------------

class CatalogFile(Base):
    __tablename__ = "catalog_files"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # source identification
    file_path = Column(String(1024), nullable=False)
    file_name = Column(String(255), nullable=False)
    source = Column(String(64), nullable=False, default="temp/outputs")  # temp/outputs or data/input/manual_uploads

    file_size = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True)  # sha256 or md5

    platform_code = Column(String(32), nullable=True)
    account = Column(String(128), nullable=True)  # [*] 账号信息（从.meta.json提取）
    shop_id = Column(String(256), nullable=True)  # v4.3.4: 扩展到256以支持长shop_id
    data_domain = Column(String(64), nullable=True)  # orders/products/metrics
    granularity = Column(String(16), nullable=True)   # daily/weekly/monthly
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)

    # 方案B+核心字段
    source_platform = Column(String(32), nullable=True)  # 数据来源平台（用于字段映射模板匹配）
    sub_domain = Column(String(64), nullable=True)  # 子数据域（如services下的agent/ai_assistant）
    
    # 方案B+数据治理字段
    storage_layer = Column(String(32), nullable=True, default="raw")  # raw/staging/curated/quarantine
    quality_score = Column(Float, nullable=True)  # 0-100数据质量评分
    validation_errors = Column(JSON, nullable=True)  # 验证错误列表
    meta_file_path = Column(String(1024), nullable=True)  # 伴生元数据文件路径

    file_metadata = Column(JSON, nullable=True)

    status = Column(String(32), nullable=False, default="pending")  # pending/validated/ingested/quarantined/failed
    error_message = Column(Text, nullable=True)

    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_catalog_files_status", "status"),
        Index("ix_catalog_files_platform_shop", "platform_code", "shop_id"),
        Index("ix_catalog_files_dates", "date_from", "date_to"),
        # 方案B+新索引
        Index("ix_catalog_source_domain", "source_platform", "data_domain"),  # 模板匹配加速
        Index("ix_catalog_sub_domain", "sub_domain"),  # 子域查询
        Index("ix_catalog_storage_layer", "storage_layer"),  # 分层查询
        Index("ix_catalog_quality_score", "quality_score"),  # 质量筛选
        UniqueConstraint("file_hash", name="uq_catalog_files_hash"),
    )


class DataQuarantine(Base):
    """
    数据隔离表
    
    用于存储处理失败的数据行，便于问题排查和数据恢复。
    当ETL流程中某些数据行验证失败或入库失败时，将其隔离到此表。
    """
    __tablename__ = "data_quarantine"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 来源信息
    source_file = Column(String(500), nullable=False)
    catalog_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    row_number = Column(Integer, nullable=True)  # 原文件中的行号
    
    # 数据内容（JSON格式保存原始数据）
    row_data = Column(Text, nullable=False)
    
    # 错误信息
    error_type = Column(String(100), nullable=False)  # ValueError/KeyError/IntegrityError等
    error_msg = Column(Text, nullable=True)  # 详细错误信息
    
    # 元数据
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    data_domain = Column(String(64), nullable=True)  # orders/products/metrics
    
    # 处理状态
    is_resolved = Column(Boolean, default=False)  # 是否已解决
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_quarantine_source_file", "source_file"),
        Index("ix_quarantine_error_type", "error_type"),
        Index("ix_quarantine_platform_shop", "platform_code", "shop_id"),
        Index("ix_quarantine_created", "created_at"),
        Index("ix_quarantine_resolved", "is_resolved"),
    )


# -------------------- Application Management Tables --------------------

class Account(Base):
    """账号管理表"""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    account_name = Column(String(100), nullable=False)
    account_id = Column(String(100), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_accounts_account_id"),
        Index("ix_accounts_platform", "platform"),
        Index("ix_accounts_status", "status"),
    )


class CollectionConfig(Base):
    """
    数据采集配置表
    
    存储采集任务的配置模板，支持：
    - 多账号批量采集
    - 多数据域选择
    - 定时调度
    - 日期范围配置
    
    v4.7.0 更新：
    - sub_domain -> sub_domains (改为数组，支持多选)
    - account_ids=[] 表示使用该平台所有活跃账号
    """
    __tablename__ = "collection_configs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)  # 配置名称
    platform = Column(String(50), nullable=False)  # 平台：shopee/tiktok/miaoshou
    account_ids = Column(JSON, nullable=False)  # 账号ID列表 ["acc1", "acc2"] 或 []（表示所有活跃账号）
    data_domains = Column(JSON, nullable=False)  # 数据域列表 ["orders", "products"]
    sub_domains = Column(JSON, nullable=True)  # 子域数组 ["agent", "ai_assistant"]（v4.7.0改为数组）
    granularity = Column(String(20), default="daily", nullable=False)  # 粒度：daily/weekly/monthly
    date_range_type = Column(String(20), default="yesterday", nullable=False)  # today/yesterday/last_7_days/custom
    custom_date_start = Column(Date, nullable=True)  # 自定义开始日期
    custom_date_end = Column(Date, nullable=True)  # 自定义结束日期
    schedule_enabled = Column(Boolean, default=False, nullable=False)  # 是否启用定时
    schedule_cron = Column(String(50), nullable=True)  # Cron表达式
    retry_count = Column(Integer, default=3, nullable=False)  # 重试次数
    is_active = Column(Boolean, default=True, nullable=False)  # 是否启用
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(String(100), nullable=True)  # 创建者
    
    # 关系
    tasks = relationship("CollectionTask", back_populates="config")
    
    __table_args__ = (
        UniqueConstraint("name", "platform", name="uq_collection_configs_name_platform"),
        Index("ix_collection_configs_platform", "platform"),
        Index("ix_collection_configs_active", "is_active"),
    )


class CollectionTask(Base):
    """
    数据采集任务表
    
    记录每次采集任务的执行状态和结果，支持：
    - 任务进度跟踪
    - 错误信息记录
    - 验证码暂停
    - 任务恢复和重试
    
    v4.7.0 更新（任务粒度优化）：
    - 一个任务 = 一个账号 + 所有配置的数据域
    - 浏览器复用，一次登录采集所有域
    - 支持部分成功机制（单域失败不影响其他域）
    - 新增进度跟踪字段（total_domains, completed_domains, failed_domains, current_domain）
    - 新增 debug_mode 调试模式支持
    - 状态新增 partial_success（部分成功）
    """
    __tablename__ = "collection_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(100), nullable=False)  # UUID任务标识
    platform = Column(String(50), nullable=False)
    account = Column(String(100), nullable=False)  # 账号ID
    status = Column(String(20), default="pending", nullable=False)  # pending/queued/running/paused/completed/partial_success/failed/cancelled/interrupted
    
    # 关联配置（可选，快速采集时为空）
    config_id = Column(Integer, ForeignKey("collection_configs.id", ondelete="SET NULL"), nullable=True)
    
    # 进度跟踪
    progress = Column(Integer, default=0, nullable=False)  # 0-100
    current_step = Column(String(200), nullable=True)  # 当前执行步骤
    files_collected = Column(Integer, default=0, nullable=False)  # 采集文件数
    
    # 任务配置（冗余存储，便于查询）
    trigger_type = Column(String(20), default="manual", nullable=False)  # manual/scheduled/retry
    data_domains = Column(JSON, nullable=True)  # ["orders", "products"]
    sub_domains = Column(JSON, nullable=True)  # ["agent", "ai_assistant"]（v4.7.0改为数组）
    granularity = Column(String(20), nullable=True)
    date_range = Column(JSON, nullable=True)  # {"start": "2025-01-01", "end": "2025-01-31"}
    
    # v4.7.0 任务粒度优化字段
    total_domains = Column(Integer, default=0, nullable=False)  # 总数据域数量（含子域）
    completed_domains = Column(JSON, nullable=True)  # 已完成的数据域列表 ["orders", "products:agent"]
    failed_domains = Column(JSON, nullable=True)  # 失败的数据域及原因 [{"domain": "orders", "error": "..."}]
    current_domain = Column(String(100), nullable=True)  # 当前正在采集的数据域（含子域，如 "services:agent"）
    
    # 错误信息
    error_message = Column(Text, nullable=True)
    error_screenshot_path = Column(String(500), nullable=True)
    
    # 执行统计
    duration_seconds = Column(Integer, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)
    parent_task_id = Column(Integer, ForeignKey("collection_tasks.id", ondelete="SET NULL"), nullable=True)
    
    # 验证码状态
    verification_type = Column(String(50), nullable=True)  # sms_code/email_code/slider/image/2fa
    verification_screenshot = Column(String(500), nullable=True)
    
    # v4.7.0 调试模式
    debug_mode = Column(Boolean, default=False, nullable=False)  # 调试模式（生产环境临时有头模式）
    
    # 乐观锁版本号
    version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # 关系
    config = relationship("CollectionConfig", back_populates="tasks")
    logs = relationship("CollectionTaskLog", back_populates="task", cascade="all, delete-orphan")
    parent_task = relationship("CollectionTask", remote_side=[id], backref="retry_tasks")
    
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_collection_tasks_task_id"),
        Index("ix_collection_tasks_platform", "platform"),
        Index("ix_collection_tasks_status", "status"),
        Index("ix_collection_tasks_config", "config_id"),
        Index("ix_collection_tasks_created", "created_at"),
    )


class CollectionTaskLog(Base):
    """
    采集任务日志表
    
    记录任务执行过程中的详细日志，便于排查问题
    """
    __tablename__ = "collection_task_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("collection_tasks.id", ondelete="CASCADE"), nullable=False)
    level = Column(String(10), nullable=False)  # info/warning/error
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)  # 额外详情
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # 关系
    task = relationship("CollectionTask", back_populates="logs")
    
    __table_args__ = (
        Index("ix_collection_task_logs_task", "task_id"),
        Index("ix_collection_task_logs_level", "level"),
        Index("ix_collection_task_logs_time", "timestamp"),
    )


class CollectionSyncPoint(Base):
    """
    增量采集同步点表 (Phase 9.2 - 已取消，保留表结构)
    
    注意：增量采集功能已取消（不适用于UI模拟场景），但保留表结构以维护迁移历史
    """
    __tablename__ = "collection_sync_points"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 唯一标识（平台+账号+数据域）
    platform = Column(String(50), nullable=False, comment="平台代码")
    account_id = Column(String(100), nullable=False, comment="账号ID")
    data_domain = Column(String(50), nullable=False, comment="数据域: orders/products/inventory/traffic/services")
    
    # 同步点信息
    last_sync_at = Column(DateTime, nullable=False, comment="最后同步时间（UTC）")
    last_sync_value = Column(String(200), nullable=True, comment="最后同步值（如最大的updated_at时间戳）")
    
    # 统计信息
    total_synced_count = Column(Integer, default=0, comment="累计同步记录数")
    last_batch_count = Column(Integer, default=0, comment="最近一次同步记录数")
    
    # 元数据
    sync_mode = Column(String(20), default="incremental", comment="同步模式: full/incremental")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        # 唯一约束：一个账号+数据域只有一个同步点
        UniqueConstraint("platform", "account_id", "data_domain", name="uq_sync_point"),
        # 索引
        Index("ix_sync_points_platform_account", "platform", "account_id"),
        Index("ix_sync_points_last_sync", "last_sync_at"),
    )


class ComponentVersion(Base):
    """
    组件版本管理表 (Phase 9.4)
    
    用于管理组件版本、A/B测试和自动切换稳定版本
    
    使用场景：
    - 组件升级时保留旧版本
    - A/B测试新版本组件
    - 自动统计成功率
    - 快速回滚到稳定版本
    """
    __tablename__ = "component_versions"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 组件标识
    component_name = Column(String(100), nullable=False, comment="组件名称（不含版本号）: shopee/login")
    version = Column(String(20), nullable=False, comment="版本号: 1.0.0, 1.1.0")
    file_path = Column(String(200), nullable=False, comment="组件文件路径（相对路径）")
    
    # 状态标识
    is_stable = Column(Boolean, default=False, comment="是否为稳定版本")
    is_active = Column(Boolean, default=True, comment="是否启用（禁用的版本不会被加载）")
    is_testing = Column(Boolean, default=False, comment="是否在A/B测试中")
    
    # 统计信息
    usage_count = Column(Integer, default=0, comment="使用次数")
    success_count = Column(Integer, default=0, comment="成功次数")
    failure_count = Column(Integer, default=0, comment="失败次数")
    success_rate = Column(Float, default=0.0, comment="成功率（自动计算）")
    
    # A/B测试配置
    test_ratio = Column(Float, default=0.0, comment="测试流量比例（0.0-1.0）")
    test_start_at = Column(DateTime, nullable=True, comment="测试开始时间")
    test_end_at = Column(DateTime, nullable=True, comment="测试结束时间")
    
    # 元数据
    description = Column(Text, nullable=True, comment="版本说明")
    created_by = Column(String(100), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        # 唯一约束：组件名+版本号唯一
        UniqueConstraint("component_name", "version", name="uq_component_version"),
        # 索引
        Index("ix_component_versions_name", "component_name"),
        Index("ix_component_versions_stable", "is_stable"),
        Index("ix_component_versions_success_rate", "success_rate"),
    )


class ComponentTestHistory(Base):
    """
    组件测试历史记录表 (Phase 8.2 - 2025-12-17)
    
    用于存储组件测试的详细历史记录，包括每步执行情况
    
    使用场景：
    - 查看组件历史测试结果
    - 分析组件稳定性趋势
    - 定位失败原因和时间点
    - 支持测试结果对比
    """
    __tablename__ = "component_test_history"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    test_id = Column(String(36), unique=True, nullable=False, comment="测试唯一ID (UUID)")
    
    # 组件标识
    component_name = Column(String(100), nullable=False, comment="组件名称: shopee/login")
    component_version = Column(String(20), nullable=True, comment="组件版本号（如未指定则为临时组件）")
    version_id = Column(Integer, nullable=True, comment="关联的版本ID（外键）")
    
    # 测试配置
    platform = Column(String(50), nullable=False, comment="平台代码")
    account_id = Column(String(100), nullable=False, comment="测试账号ID")
    headless = Column(Boolean, default=False, comment="是否无头模式")
    
    # 测试结果
    status = Column(String(20), nullable=False, comment="测试状态: passed/failed/cancelled")
    duration_ms = Column(Integer, nullable=False, comment="总耗时（毫秒）")
    steps_total = Column(Integer, nullable=False, comment="总步骤数")
    steps_passed = Column(Integer, nullable=False, comment="成功步骤数")
    steps_failed = Column(Integer, nullable=False, comment="失败步骤数")
    success_rate = Column(Float, nullable=False, comment="成功率（0.0-1.0）")
    
    # 详细结果（JSON存储）
    step_results = Column(JSONB, nullable=False, comment="每步执行详情（action/status/duration/error）")
    error_message = Column(Text, nullable=True, comment="失败原因（如有）")
    
    # 环境信息
    browser_info = Column(JSONB, nullable=True, comment="浏览器信息（User-Agent等）")
    
    # 审计字段
    tested_by = Column(String(100), nullable=True, comment="测试人")
    tested_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="测试时间")
    
    __table_args__ = (
        # 外键约束（可选）
        ForeignKeyConstraint(
            ["version_id"],
            ["component_versions.id"],
            name="fk_test_history_version",
            ondelete="SET NULL"
        ),
        # 索引
        Index("ix_test_history_component", "component_name"),
        Index("ix_test_history_status", "status"),
        Index("ix_test_history_tested_at", "tested_at"),
        Index("ix_test_history_version", "version_id"),
    )


class PlatformAccount(Base):
    """
    平台账号管理表 (v4.7.0)
    
    替代手动编辑 local_accounts.py，提供前端GUI管理
    支持：
    - 多平台账号统一管理
    - 店铺级别配置（一个主账号多个店铺）
    - 密码加密存储
    - 能力配置（capabilities）
    """
    __tablename__ = "platform_accounts"
    
    # 主键和唯一标识
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(100), unique=True, nullable=False, comment="账号唯一标识")
    
    # 账号基本信息
    parent_account = Column(String(100), nullable=True, comment="主账号（多店铺共用时填写）")
    platform = Column(String(50), nullable=False, comment="平台代码: shopee/tiktok/miaoshou/amazon")
    account_alias = Column(String(200), nullable=True, comment="账号别名（用于关联导出数据中的自定义名称，如miaoshou ERP的订单数据）")
    store_name = Column(String(200), nullable=False, comment="店铺名称")
    
    # 店铺信息
    shop_type = Column(String(50), nullable=True, comment="店铺类型: local/global")
    shop_region = Column(String(50), nullable=True, comment="店铺区域: SG/MY/GLOBAL等")
    shop_id = Column(String(256), nullable=True, comment="店铺ID（用于关联数据同步中的shop_id，可编辑）")  # [*] v4.18.1新增
    
    # 登录信息（敏感）
    username = Column(String(200), nullable=False, comment="登录用户名")
    password_encrypted = Column(Text, nullable=False, comment="加密后的密码")
    login_url = Column(Text, nullable=True, comment="登录URL")
    
    # 联系信息
    email = Column(String(200), nullable=True, comment="邮箱")
    phone = Column(String(50), nullable=True, comment="手机号")
    region = Column(String(50), default="CN", comment="账号注册地区")
    currency = Column(String(10), default="CNY", comment="主货币")
    
    # 能力配置（JSONB）
    capabilities = Column(
        JSONB, 
        nullable=False,
        default={
            "orders": True,
            "products": True,
            "services": True,
            "analytics": True,
            "finance": True,
            "inventory": True
        },
        comment="账号支持的数据域能力"
    )
    
    # 状态和设置
    enabled = Column(Boolean, default=True, nullable=False, comment="是否启用")
    proxy_required = Column(Boolean, default=False, comment="是否需要代理")
    notes = Column(Text, nullable=True, comment="备注")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")
    created_by = Column(String(100), nullable=True, comment="创建人")
    updated_by = Column(String(100), nullable=True, comment="更新人")
    
    # 扩展字段
    extra_config = Column(JSONB, nullable=True, default={}, comment="扩展配置")
    
    __table_args__ = (
        Index("ix_platform_accounts_platform", "platform"),
        Index("ix_platform_accounts_parent", "parent_account"),
        Index("ix_platform_accounts_enabled", "enabled"),
        Index("ix_platform_accounts_shop_type", "shop_type"),
        Index("ix_platform_accounts_shop_id", "shop_id"),  # [*] v4.18.1新增
    )


class DataFile(Base):
    """数据文件表（旧版API兼容）"""
    __tablename__ = "data_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    platform = Column(String(50), nullable=False)
    data_type = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    discovery_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_data_files_platform", "platform"),
        Index("ix_data_files_status", "status"),
    )


class DataRecord(Base):
    """通用数据记录表"""
    __tablename__ = "data_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    record_type = Column(String(50), nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_data_records_platform", "platform"),
        Index("ix_data_records_type", "record_type"),
    )


class FieldMapping(Base):
    """
    字段映射表（方案B+增强版）
    
    方案B+改进：
    - 添加sub_domain字段（services的agent/ai_assistant）
    - 支持更精确的模板匹配
    """
    __tablename__ = "field_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("data_files.id", ondelete="CASCADE"), nullable=True)
    platform = Column(String(50), nullable=True)  # source_platform（数据来源）
    original_field = Column(String(100), nullable=False)
    standard_field = Column(String(100), nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    domain = Column(String(50), nullable=True)
    granularity = Column(String(50), nullable=True)
    sheet_name = Column(String(100), nullable=True)
    
    # 方案B+新字段
    sub_domain = Column(String(64), nullable=True, default='')  # 子数据域（agent/ai_assistant等）
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_field_mappings_platform", "platform"),
        Index("ix_field_mappings_domain", "domain"),
        Index("ix_field_mappings_version", "version"),
        # 方案B+新索引（精确模板匹配）
        Index("ix_field_mappings_template_key", "platform", "domain", "sub_domain", "granularity"),
    )


class MappingSession(Base):
    """字段映射会话表"""
    __tablename__ = "mapping_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=True)
    domain = Column(String(50), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_mapping_sessions_session_id"),
    )


# -------------------- Staging Tables (ETL Layer) --------------------

class StagingOrders(Base):
    """订单数据暂存表（ETL中间层）
    
    v4.11.4增强：
    - 添加ingest_task_id字段（关联同步任务）
    - 添加file_id字段（关联文件记录）
    - 保留order_data JSON字段作为兜底
    """
    __tablename__ = "staging_orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    order_id = Column(String(128), nullable=True)
    order_data = Column(JSON, nullable=False)  # 原始数据JSON（兜底）
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_staging_orders_platform", "platform_code"),
        Index("ix_staging_orders_task", "ingest_task_id"),
        Index("ix_staging_orders_file", "file_id"),
    )


class StagingProductMetrics(Base):
    """产品指标暂存表（ETL中间层）
    
    v4.11.4增强：
    - 添加ingest_task_id字段（关联同步任务）
    - 添加file_id字段（关联文件记录）
    - 保留metric_data JSON字段作为兜底
    """
    __tablename__ = "staging_product_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    platform_sku = Column(String(64), nullable=True)
    metric_data = Column(JSON, nullable=False)  # 原始数据JSON（兜底）
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_staging_metrics_platform", "platform_code"),
        Index("ix_staging_metrics_task", "ingest_task_id"),
        Index("ix_staging_metrics_file", "file_id"),
    )


class StagingInventory(Base):
    """库存数据暂存表（ETL中间层）
    
    v4.11.4新增：
    - inventory域数据暂存表
    - 支持原始数据JSON存储
    - 关联同步任务和文件记录
    """
    __tablename__ = "staging_inventory"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    platform_sku = Column(String(128), nullable=True)
    warehouse_id = Column(String(64), nullable=True, comment="仓库ID")
    inventory_data = Column(JSON, nullable=False)  # 原始数据JSON（兜底）
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_staging_inventory_platform", "platform_code"),
        Index("ix_staging_inventory_task", "ingest_task_id"),
        Index("ix_staging_inventory_file", "file_id"),
        Index("ix_staging_inventory_sku", "platform_code", "shop_id", "platform_sku"),
    )


class ProductImage(Base):
    """
    产品图片表（v3.0新增）
    
    存储产品图片URL和元数据，支持SKU级图片管理
    """
    __tablename__ = "product_images"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 产品标识（三元组）
    platform_code = Column(String(32), nullable=False, comment="平台编码")
    shop_id = Column(String(64), nullable=False, comment="店铺ID")
    platform_sku = Column(String(128), nullable=False, comment="平台SKU")
    
    # 图片URL
    image_url = Column(String(1024), nullable=False, comment="原图URL")
    thumbnail_url = Column(String(1024), nullable=False, comment="缩略图URL")
    
    # 图片类型和顺序
    image_type = Column(String(20), nullable=False, default='main', comment="图片类型: main/detail/spec")
    image_order = Column(Integer, nullable=False, default=0, comment="显示顺序")
    
    # 图片元数据
    file_size = Column(Integer, nullable=True, comment="文件大小(bytes)")
    width = Column(Integer, nullable=True, comment="图片宽度(px)")
    height = Column(Integer, nullable=True, comment="图片高度(px)")
    format = Column(String(10), nullable=True, comment="图片格式: JPEG/PNG/GIF")
    
    # 质量评分（预留v4.0 AI识别）
    quality_score = Column(Float, nullable=True, comment="图片质量评分(0-100)")
    is_main_image = Column(Boolean, nullable=False, default=False, comment="是否主图")
    
    # 时间戳
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    __table_args__ = (
        Index("idx_product_images_sku", "platform_sku"),
        Index("idx_product_images_product", "platform_code", "shop_id", "platform_sku"),
        Index("idx_product_images_order", "platform_sku", "image_order"),
    )


# -------------------- Field Mapping Dictionary & Templates (v4.3.7) --------------------

from sqlalchemy import UniqueConstraint  # reuse imports for constraints


class FieldMappingDictionary(Base):
    """
    字段映射辞典表（标准字段元数据）

    单一数据源：运行时从数据库读取并缓存
    """
    __tablename__ = "field_mapping_dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 标准字段标识（唯一、稳定）
    # 支持中文或英文代码（PostgreSQL UTF-8完全支持）
    # 中文示例：field_code="订单号", cn_name="订单号"
    # 英文示例：field_code="order_id", cn_name="订单号"
    field_code = Column(String(128), nullable=False, unique=True, index=True)

    # 中文友好信息
    cn_name = Column(String(128), nullable=False)
    en_name = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)

    # 数据域与分组
    data_domain = Column(String(64), nullable=False, index=True)  # orders/products/traffic/services/general
    field_group = Column(String(64), nullable=True)  # dimension/amount/quantity/ratio/text/datetime

    # 约束与验证
    is_required = Column(Boolean, default=False)
    data_type = Column(String(32), nullable=True)  # string/integer/float/date/datetime/currency/ratio
    value_range = Column(String(256), nullable=True)

    # 同义词与平台特定同义词
    synonyms = Column(JSON, nullable=True)
    platform_synonyms = Column(JSON, nullable=True)  # {"shopee": ["xxx"]}

    # 示例值
    example_values = Column(JSON, nullable=True)

    # 排序与权重
    display_order = Column(Integer, default=999)
    match_weight = Column(Float, default=1.0)

    # 审计与版本（v4.4.0新增）
    active = Column(Boolean, default=True)
    version = Column(Integer, default=1, nullable=False)  # 版本号（SCD2支持）
    status = Column(String(32), default="active", nullable=False)  # draft/active/deprecated
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)
    
    # v4.6.0新增：Pattern-based Mapping（配置驱动）
    is_pattern_based = Column(Boolean, default=False, nullable=False, comment="是否启用模式匹配")
    field_pattern = Column(Text, nullable=True, comment="字段匹配正则表达式（支持命名组）")
    dimension_config = Column(JSON, nullable=True, comment="维度提取配置（如订单状态、货币映射）")
    target_table = Column(String(64), nullable=True, comment="目标表名（如fact_order_amounts）")
    target_columns = Column(JSON, nullable=True, comment="目标列映射配置（如metric_type/metric_subtype）")

    # v4.10.2新增：物化视图显示标识
    is_mv_display = Column(Boolean, default=False, nullable=False, comment="是否需要在物化视图中显示（true=核心字段，false=辅助字段）")
    
    # C类数据核心字段优化计划（Phase 3）：货币策略字段
    currency_policy = Column(String(32), nullable=True, comment="货币策略（CNY/无货币/多币种）")
    source_priority = Column(JSON, nullable=True, comment="数据源优先级（JSON数组，如[\"miaoshou\", \"shopee\"]）")

    __table_args__ = (
        UniqueConstraint("cn_name", name="uq_dictionary_cn_name"),  # 确保一对一映射：每个中文名称只对应一个标准字段
        Index("ix_dictionary_domain_group", "data_domain", "field_group"),
        Index("ix_dictionary_required", "is_required", "data_domain"),
        Index("ix_dictionary_status", "status", "data_domain"),
        Index("ix_dictionary_mv_display", "is_mv_display", "data_domain"),  # v4.10.2新增：物化视图显示字段索引
        Index("ix_dictionary_currency_policy", "currency_policy"),  # C类数据核心字段优化计划：货币策略索引
    )


class FieldMappingTemplate(Base):
    """
    字段映射模板表（头）
    
    v4.5.1增强：
    - 新增header_row: 支持非0行表头
    - 新增sub_domain: 支持子数据类型识别（ai_assistant/agent等）
    - 新增sheet_name: 支持多工作表Excel
    - 新增encoding: 支持非UTF-8编码
    
    维度：platform × data_domain × sub_domain × granularity × account
    """
    __tablename__ = "field_mapping_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 模板维度
    platform = Column(String(32), nullable=False, index=True)
    data_domain = Column(String(64), nullable=False, index=True)
    granularity = Column(String(32), nullable=True)
    account = Column(String(128), nullable=True)
    
    # v4.5.1新增：数据解析配置
    sub_domain = Column(String(64), nullable=True, comment="子数据类型（如ai_assistant/agent）")
    header_row = Column(Integer, default=0, nullable=False, comment="表头行索引（0-based，默认0）")
    sheet_name = Column(String(128), nullable=True, comment="Excel工作表名称")
    encoding = Column(String(32), default='utf-8', nullable=False, comment="文件编码（默认utf-8）")

    # v4.6.0新增：原始表头字段列表（替代FieldMappingTemplateItem）
    header_columns = Column(JSONB, nullable=True, comment="原始表头字段列表（JSONB数组）")
    
    # v4.14.0新增：核心去重字段列表（用于data_hash计算）
    deduplication_fields = Column(JSONB, nullable=True, comment="核心去重字段列表（JSONB数组），用于data_hash计算，不受表头变化影响")
    
    # 元信息
    template_name = Column(String(256), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="draft")  # draft/published/archived

    # 统计
    field_count = Column(Integer, default=0)
    usage_count = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)

    # 审计
    created_by = Column(String(64), default="user")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        # v4.5.1更新：新增sub_domain到复合索引
        Index("ix_template_dimension_v2", "platform", "data_domain", "sub_domain", "granularity", "account"),
        Index("ix_template_status", "status", "platform"),
        # v4.5.1新增：header_row范围CHECK约束（企业级数据治理标准）
        CheckConstraint('header_row >= 0 AND header_row <= 100', name='ck_template_header_row_range'),
    )


class FieldMappingTemplateItem(Base):
    """
    字段映射模板明细表
    
    [WARN] v4.6.0 DSS架构重构：已废弃
    - 已被FieldMappingTemplate.header_columns JSONB字段替代
    - 表结构保留用于兼容性，但不再使用
    - 新代码应使用header_columns字段
    """
    __tablename__ = "field_mapping_template_items"

    id = Column(Integer, primary_key=True, autoincrement=True)

    template_id = Column(Integer, nullable=False, index=True)
    original_column = Column(String(256), nullable=False)
    standard_field = Column(String(128), nullable=False)

    confidence = Column(Float, default=1.0)
    match_method = Column(String(64), nullable=True)
    match_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_template_item_template", "template_id"),
        UniqueConstraint("template_id", "original_column", name="uq_template_original_column"),
    )


class FieldMappingAudit(Base):
    """字段映射审计日志表"""
    __tablename__ = "field_mapping_audit"

    id = Column(Integer, primary_key=True, autoincrement=True)

    action = Column(String(64), nullable=False)  # create/update/apply_template
    entity_type = Column(String(64), nullable=False)  # dictionary/template/mapping
    entity_id = Column(Integer, nullable=True)

    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)

    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    operator = Column(String(64), nullable=False)
    operated_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_operator", "operator", "operated_at"),
    )


# -------------------- Finance Domain Tables (v4.4.0 - Modern ERP) --------------------

class DimMetricFormula(Base):
    """
    计算指标公式辞典（自动计算指标）
    
    存储计算类指标的SQL表达式和依赖关系，如：
    - CTR = clicks / NULLIF(impressions, 0)
    - conversion_rate = orders / NULLIF(sessions, 0)
    """
    __tablename__ = "dim_metric_formulas"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 指标标识
    metric_code = Column(String(128), nullable=False, unique=True, index=True)
    cn_name = Column(String(128), nullable=False)
    en_name = Column(String(128), nullable=True)
    description = Column(Text, nullable=True)
    
    # 数据域与分组
    data_domain = Column(String(64), nullable=False, index=True)  # sales/traffic/inventory
    metric_type = Column(String(32), nullable=False)  # ratio/amount/count
    
    # 计算公式
    sql_expr = Column(Text, nullable=False)  # SQL表达式
    depends_on = Column(JSON, nullable=True)  # 依赖的原子字段列表 ["clicks", "impressions"]
    aggregator = Column(String(32), nullable=True)  # SUM/AVG/MAX/MIN/CUSTOM
    
    # 元数据
    unit = Column(String(32), nullable=True)  # %/CNY/count
    display_format = Column(String(64), nullable=True)  # 0.00%/0.00
    
    # 审计
    active = Column(Boolean, default=True)
    version = Column(Integer, default=1, nullable=False)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_metric_formula_domain", "data_domain", "active"),
    )


class DimCurrency(Base):
    """货币维度表"""
    __tablename__ = "dim_currencies"
    
    currency_code = Column(String(8), primary_key=True)  # CNY/USD/SGD
    currency_name = Column(String(64), nullable=False)
    symbol = Column(String(8), nullable=True)
    is_base = Column(Boolean, default=False)  # CNY为基准货币
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class FxRate(Base):
    """汇率表（CNY基准）"""
    __tablename__ = "fx_rates"
    
    rate_date = Column(Date, primary_key=True)
    from_currency = Column(String(8), primary_key=True)
    to_currency = Column(String(8), primary_key=True)
    
    rate = Column(Float, nullable=False)  # Decimal(18,6) precision
    source = Column(String(64), nullable=True, default="manual")  # manual/ecb/api
    version = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_fx_rates_date_from", "rate_date", "from_currency"),
    )


class DimFiscalCalendar(Base):
    """会计期间日历表"""
    __tablename__ = "dim_fiscal_calendar"
    
    period_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)  # 1-12
    period_code = Column(String(16), nullable=False, unique=True)  # 2025-01
    
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    status = Column(String(32), default="open", nullable=False)  # open/closed
    closed_by = Column(String(64), nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_fiscal_calendar_year_month", "period_year", "period_month"),
        Index("ix_fiscal_calendar_status", "status"),
        UniqueConstraint("period_year", "period_month", name="uq_fiscal_period"),
    )


class DimVendor(Base):
    """供应商维度表"""
    __tablename__ = "dim_vendors"
    
    vendor_code = Column(String(64), primary_key=True)
    vendor_name = Column(String(256), nullable=False)
    
    country = Column(String(64), nullable=True)
    tax_id = Column(String(128), nullable=True)
    payment_terms = Column(String(64), nullable=True)  # NET30/NET60
    credit_limit = Column(Float, default=0.0)
    
    status = Column(String(32), default="active", nullable=False)  # active/suspended/blocked
    
    contact_person = Column(String(128), nullable=True)
    contact_phone = Column(String(64), nullable=True)
    contact_email = Column(String(128), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_vendors_status", "status"),
    )


class POHeader(Base):
    """采购订单头表"""
    __tablename__ = "po_headers"
    
    po_id = Column(String(64), primary_key=True)
    
    vendor_code = Column(String(64), ForeignKey("dim_vendors.vendor_code"), nullable=False)
    po_date = Column(Date, nullable=False)
    expected_date = Column(Date, nullable=True)
    
    currency = Column(String(8), nullable=False)
    total_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    status = Column(String(32), default="draft", nullable=False)  # draft/pending_approval/approved/closed
    approval_threshold = Column(Float, nullable=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_po_headers_vendor_date", "vendor_code", "po_date"),
        Index("ix_po_headers_status", "status"),
    )


class POLine(Base):
    """采购订单行表"""
    __tablename__ = "po_lines"
    
    po_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    po_id = Column(String(64), ForeignKey("po_headers.po_id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    
    platform_sku = Column(String(128), nullable=False)  # 关联到BridgeProductKeys
    product_title = Column(String(512), nullable=True)
    
    qty_ordered = Column(Integer, default=0)
    qty_received = Column(Integer, default=0)
    
    unit_price = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    line_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_po_lines_po_id", "po_id"),
        Index("ix_po_lines_sku", "platform_sku"),
        UniqueConstraint("po_id", "line_number", name="uq_po_line"),
    )


class GRNHeader(Base):
    """入库单头表（Goods Receipt Note）"""
    __tablename__ = "grn_headers"
    
    grn_id = Column(String(64), primary_key=True)
    
    po_id = Column(String(64), ForeignKey("po_headers.po_id"), nullable=False)
    receipt_date = Column(Date, nullable=False)
    warehouse = Column(String(64), nullable=True)
    
    status = Column(String(32), default="pending", nullable=False)  # pending/completed/cancelled
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_grn_headers_po_id", "po_id"),
        Index("ix_grn_headers_date", "receipt_date"),
    )


class GRNLine(Base):
    """入库单行表"""
    __tablename__ = "grn_lines"
    
    grn_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    grn_id = Column(String(64), ForeignKey("grn_headers.grn_id", ondelete="CASCADE"), nullable=False)
    po_line_id = Column(Integer, ForeignKey("po_lines.po_line_id"), nullable=False)
    
    platform_sku = Column(String(128), nullable=False)
    qty_received = Column(Integer, default=0)
    
    unit_cost = Column(Float, nullable=False)
    currency = Column(String(8), nullable=False)
    ext_value = Column(Float, default=0.0)  # 原币
    base_ext_value = Column(Float, default=0.0)  # CNY
    
    weight_kg = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_grn_lines_grn_id", "grn_id"),
        Index("ix_grn_lines_po_line", "po_line_id"),
        Index("ix_grn_lines_sku", "platform_sku"),
    )


class InventoryLedger(Base):
    """
    库存流水账表（Universal Journal模式）
    
    唯一库存真源，记录所有出入库事务：
    - receipt: 采购入库
    - sale: 销售出库
    - return: 退货入库
    - adjustment: 盘点调整
    
    支持移动加权平均成本计算
    """
    __tablename__ = "inventory_ledger"
    
    ledger_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    
    # 交易日期与类型
    transaction_date = Column(Date, nullable=False)
    movement_type = Column(String(32), nullable=False)  # receipt/sale/return/adjustment
    
    # 数量与成本
    qty_in = Column(Integer, default=0)
    qty_out = Column(Integer, default=0)
    unit_cost_wac = Column(Float, nullable=False)  # 移动加权平均成本
    ext_value = Column(Float, default=0.0)
    base_ext_value = Column(Float, default=0.0)  # CNY
    
    # 成本计算辅助（移动加权平均）
    qty_before = Column(Integer, default=0)
    avg_cost_before = Column(Float, default=0.0)
    qty_after = Column(Integer, default=0)
    avg_cost_after = Column(Float, default=0.0)
    
    # 来源追踪
    link_grn_id = Column(String(64), nullable=True)  # 关联入库单
    link_order_id = Column(String(128), nullable=True)  # 关联销售订单
    original_sale_line_id = Column(Integer, nullable=True)  # 退货关联原销售行
    return_reason = Column(String(256), nullable=True)
    
    # 审计
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_inventory_ledger_sku_date", "platform_code", "shop_id", "platform_sku", "transaction_date"),
        Index("ix_inventory_ledger_type", "movement_type", "transaction_date"),
        Index("ix_inventory_ledger_grn", "link_grn_id"),
        Index("ix_inventory_ledger_order", "link_order_id"),
    )


class InvoiceHeader(Base):
    """发票头表"""
    __tablename__ = "invoice_headers"
    
    invoice_id = Column(Integer, primary_key=True, autoincrement=True)
    
    vendor_code = Column(String(64), ForeignKey("dim_vendors.vendor_code"), nullable=False)
    invoice_no = Column(String(128), nullable=False, unique=True)
    invoice_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    
    currency = Column(String(8), nullable=False)
    total_amt = Column(Float, default=0.0)
    tax_amt = Column(Float, default=0.0)
    base_total_amt = Column(Float, default=0.0)  # CNY
    
    status = Column(String(32), default="pending", nullable=False)  # pending/matched/paid
    
    # OCR结果
    source_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    ocr_result = Column(JSON, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_invoice_headers_vendor_date", "vendor_code", "invoice_date"),
        Index("ix_invoice_headers_status", "status"),
    )


class InvoiceLine(Base):
    """发票行表"""
    __tablename__ = "invoice_lines"
    
    invoice_line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    invoice_id = Column(Integer, ForeignKey("invoice_headers.invoice_id", ondelete="CASCADE"), nullable=False)
    po_line_id = Column(Integer, ForeignKey("po_lines.po_line_id"), nullable=True)
    grn_line_id = Column(Integer, ForeignKey("grn_lines.grn_line_id"), nullable=True)
    
    platform_sku = Column(String(128), nullable=False)
    qty = Column(Integer, default=0)
    
    unit_price = Column(Float, nullable=False)
    line_amt = Column(Float, default=0.0)
    tax_amt = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_invoice_lines_invoice", "invoice_id"),
        Index("ix_invoice_lines_po_line", "po_line_id"),
        Index("ix_invoice_lines_grn_line", "grn_line_id"),
    )


class InvoiceAttachment(Base):
    """发票附件表（扫描件）"""
    __tablename__ = "invoice_attachments"
    
    attachment_id = Column(Integer, primary_key=True, autoincrement=True)
    
    invoice_id = Column(Integer, ForeignKey("invoice_headers.invoice_id", ondelete="CASCADE"), nullable=False)
    
    file_path = Column(String(1024), nullable=False)
    file_type = Column(String(32), nullable=True)  # pdf/jpg/png
    file_size = Column(Integer, nullable=True)
    
    ocr_text = Column(Text, nullable=True)
    ocr_fields = Column(JSON, nullable=True)  # 提取的结构化字段
    
    uploaded_by = Column(String(64), default="system")
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_invoice_attachments_invoice", "invoice_id"),
    )


class ThreeWayMatchLog(Base):
    """三单匹配日志表（PO-GRN-Invoice）"""
    __tablename__ = "three_way_match_log"
    
    match_id = Column(Integer, primary_key=True, autoincrement=True)
    
    po_line_id = Column(Integer, ForeignKey("po_lines.po_line_id"), nullable=False)
    grn_line_id = Column(Integer, ForeignKey("grn_lines.grn_line_id"), nullable=True)
    invoice_line_id = Column(Integer, ForeignKey("invoice_lines.invoice_line_id"), nullable=True)
    
    match_status = Column(String(32), default="unmatched", nullable=False)  # matched/variance/unmatched
    
    variance_qty = Column(Integer, default=0)
    variance_amt = Column(Float, default=0.0)
    variance_reason = Column(Text, nullable=True)
    
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_three_way_match_po", "po_line_id"),
        Index("ix_three_way_match_status", "match_status"),
    )


class FactExpensesMonth(Base):
    """月度运营费用事实表"""
    __tablename__ = "fact_expenses_month"
    
    expense_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("dim_fiscal_calendar.period_code"), nullable=False)
    
    cost_center = Column(String(64), nullable=True)  # 成本中心
    expense_type = Column(String(128), nullable=False)  # 从FieldMappingDictionary
    vendor = Column(String(256), nullable=True)
    
    currency = Column(String(8), nullable=False)
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    tax_amt = Column(Float, default=0.0)
    
    # 可选：指定店铺（不指定则需分摊）
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    source_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    memo = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_expenses_month_period", "period_month"),
        Index("ix_expenses_month_type", "expense_type"),
        Index("ix_expenses_month_shop", "platform_code", "shop_id"),
    )


class AllocationRule(Base):
    """分摊规则表"""
    __tablename__ = "allocation_rules"
    
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    
    rule_name = Column(String(256), nullable=False)
    scope = Column(String(64), nullable=False)  # expense/logistics
    driver = Column(String(64), nullable=False)  # revenue_share/orders_share/units_share/weight/volume/manual
    
    # 权重配置（JSON格式）
    weights = Column(JSON, nullable=True)  # {"shop_a": 0.4, "shop_b": 0.6}
    
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    
    active = Column(Boolean, default=True)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_allocation_rules_scope", "scope", "active"),
    )


class FactExpensesAllocated(Base):
    """费用分摊结果表（日-店铺-SKU粒度）"""
    __tablename__ = "fact_expenses_allocated_day_shop_sku"
    
    allocation_id = Column(Integer, primary_key=True, autoincrement=True)
    
    expense_id = Column(Integer, ForeignKey("fact_expenses_month.expense_id"), nullable=False)
    allocation_date = Column(Date, nullable=False)
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=True)  # NULL表示店铺级
    
    allocated_amt = Column(Float, default=0.0)  # CNY
    allocation_driver = Column(String(64), nullable=True)
    allocation_weight = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_expenses_allocated_date", "allocation_date"),
        Index("ix_expenses_allocated_shop", "platform_code", "shop_id", "allocation_date"),
        Index("ix_expenses_allocated_sku", "platform_code", "shop_id", "platform_sku", "allocation_date"),
    )


class LogisticsCost(Base):
    """物流成本表"""
    __tablename__ = "logistics_costs"
    
    logistics_id = Column(Integer, primary_key=True, autoincrement=True)
    
    grn_id = Column(String(64), ForeignKey("grn_headers.grn_id"), nullable=True)  # 入库物流
    order_id = Column(String(128), nullable=True)  # 销售物流
    
    logistics_provider = Column(String(128), nullable=True)
    tracking_no = Column(String(128), nullable=True)
    cost_type = Column(String(64), nullable=False)  # freight/customs/insurance
    
    currency = Column(String(8), nullable=False)
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    weight_kg = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    
    invoice_id = Column(Integer, ForeignKey("invoice_headers.invoice_id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_logistics_costs_grn", "grn_id"),
        Index("ix_logistics_costs_order", "order_id"),
        Index("ix_logistics_costs_invoice", "invoice_id"),
    )


class LogisticsAllocationRule(Base):
    """物流成本分摊规则表"""
    __tablename__ = "logistics_allocation_rules"
    
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    
    rule_name = Column(String(256), nullable=False)
    scope = Column(String(64), nullable=False)  # domestic/international
    driver = Column(String(64), nullable=False)  # weight/volume/revenue/order
    
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_logistics_alloc_rules_scope", "scope", "active"),
    )


class TaxVoucher(Base):
    """税务凭证表"""
    __tablename__ = "tax_vouchers"
    
    voucher_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("dim_fiscal_calendar.period_code"), nullable=False)
    voucher_type = Column(String(32), nullable=False)  # input_tax/output_tax
    
    invoice_id = Column(Integer, ForeignKey("invoice_headers.invoice_id"), nullable=True)
    
    tax_amt = Column(Float, default=0.0)
    deductible_amt = Column(Float, default=0.0)  # 可抵扣金额
    
    status = Column(String(32), default="pending", nullable=False)  # pending/filed/rejected
    filing_status = Column(String(64), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_tax_vouchers_period", "period_month"),
        Index("ix_tax_vouchers_type", "voucher_type", "status"),
    )


class TaxReport(Base):
    """报税清单表"""
    __tablename__ = "tax_reports"
    
    report_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period_month = Column(String(16), ForeignKey("dim_fiscal_calendar.period_code"), nullable=False)
    report_type = Column(String(64), nullable=False)  # vat/export_refund
    
    status = Column(String(32), default="draft", nullable=False)  # draft/submitted
    export_file_path = Column(String(1024), nullable=True)
    
    generated_by = Column(String(64), default="system")
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    submitted_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_tax_reports_period", "period_month"),
        Index("ix_tax_reports_status", "status"),
    )


class GLAccount(Base):
    """总账科目表"""
    __tablename__ = "gl_accounts"
    
    account_code = Column(String(64), primary_key=True)
    account_name = Column(String(256), nullable=False)
    account_type = Column(String(64), nullable=False)  # asset/liability/equity/revenue/expense
    parent_account = Column(String(64), nullable=True)
    
    is_debit_normal = Column(Boolean, default=True)  # 借方为正常余额
    active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_gl_accounts_type", "account_type", "active"),
    )


class JournalEntry(Base):
    """总账凭证头表"""
    __tablename__ = "journal_entries"
    
    entry_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entry_no = Column(String(64), nullable=False, unique=True)
    entry_date = Column(Date, nullable=False)
    period_month = Column(String(16), ForeignKey("dim_fiscal_calendar.period_code"), nullable=False)
    
    entry_type = Column(String(64), nullable=False)  # revenue/expense/asset/adjustment
    description = Column(Text, nullable=True)
    
    status = Column(String(32), default="draft", nullable=False)  # draft/posted/reversed
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    posted_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index("ix_journal_entries_date", "entry_date"),
        Index("ix_journal_entries_period", "period_month"),
        Index("ix_journal_entries_status", "status"),
    )


class JournalEntryLine(Base):
    """总账凭证行表（双分录）"""
    __tablename__ = "journal_entry_lines"
    
    line_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entry_id = Column(Integer, ForeignKey("journal_entries.entry_id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    
    account_code = Column(String(64), ForeignKey("gl_accounts.account_code"), nullable=False)
    
    debit_amt = Column(Float, default=0.0)
    credit_amt = Column(Float, default=0.0)
    
    currency = Column(String(8), default="CNY")
    currency_amt = Column(Float, default=0.0)
    base_amt = Column(Float, default=0.0)  # CNY
    
    # 来源追踪
    link_order_id = Column(String(128), nullable=True)
    link_expense_id = Column(Integer, nullable=True)
    link_invoice_id = Column(Integer, nullable=True)
    
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_journal_lines_entry", "entry_id"),
        Index("ix_journal_lines_account", "account_code"),
        UniqueConstraint("entry_id", "line_number", name="uq_journal_line"),
    )


class OpeningBalance(Base):
    """期初余额表（数据迁移用）"""
    __tablename__ = "opening_balances"
    
    balance_id = Column(Integer, primary_key=True, autoincrement=True)
    
    period = Column(String(16), nullable=False)  # 期初期间 2025-01
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    
    opening_qty = Column(Integer, default=0)
    opening_cost = Column(Float, default=0.0)  # 单位成本
    opening_value = Column(Float, default=0.0)  # 总价值 CNY
    
    source = Column(String(64), default="migration")  # migration/manual
    migration_batch_id = Column(String(64), nullable=True)
    
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_opening_balances_period", "period"),
        Index("ix_opening_balances_sku", "platform_code", "shop_id", "platform_sku"),
        UniqueConstraint("period", "platform_code", "shop_id", "platform_sku", name="uq_opening_balance"),
    )


class ApprovalLog(Base):
    """审批日志表（PO/费用审批）"""
    __tablename__ = "approval_logs"
    
    log_id = Column(Integer, primary_key=True, autoincrement=True)
    
    entity_type = Column(String(64), nullable=False)  # PO/expense
    entity_id = Column(String(128), nullable=False)
    
    approver = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)  # pending/approved/rejected
    comment = Column(Text, nullable=True)
    
    approved_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_approval_logs_entity", "entity_type", "entity_id"),
        Index("ix_approval_logs_approver", "approver", "status"),
    )


class ReturnOrder(Base):
    """退货单表"""
    __tablename__ = "return_orders"
    
    return_id = Column(Integer, primary_key=True, autoincrement=True)
    
    original_order_id = Column(String(128), nullable=False)
    return_type = Column(String(32), nullable=False)  # customer/vendor
    
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    platform_sku = Column(String(128), nullable=False)
    
    qty = Column(Integer, default=0)
    refund_amt = Column(Float, default=0.0)
    restocking_fee = Column(Float, default=0.0)
    
    reason = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_return_orders_original", "original_order_id"),
        Index("ix_return_orders_shop", "platform_code", "shop_id"),
    )


class FieldUsageTracking(Base):
    """
    字段使用追踪表（v4.7.0新增）
    
    用于追踪数据库字段在API和前端的使用情况，支持数据治理和元数据管理。
    """
    __tablename__ = "field_usage_tracking"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 字段标识（允许NULL：前端组件可能只知道API端点，不知道表/字段）
    table_name = Column(String(64), nullable=True, index=True, comment="数据库表名")
    field_name = Column(String(128), nullable=True, index=True, comment="数据库字段名")
    
    # API端点追踪
    api_endpoint = Column(String(256), nullable=True, comment="API端点（如/api/products/products）")
    api_param = Column(String(64), nullable=True, comment="API参数名（如keyword）")
    api_file = Column(String(256), nullable=True, comment="API路由文件路径")
    
    # 前端组件追踪
    frontend_component = Column(String(256), nullable=True, comment="前端组件（如ProductManagement.vue）")
    frontend_param = Column(String(128), nullable=True, comment="前端参数（如filters.keyword）")
    frontend_file = Column(String(256), nullable=True, comment="前端组件文件路径")
    
    # 使用方式
    usage_type = Column(String(32), nullable=False, comment="使用类型：query/filter/sort/return")
    source_type = Column(String(32), default="scanned", nullable=False, comment="来源类型：scanned/manual")
    
    # 代码上下文（可选）
    code_snippet = Column(Text, nullable=True, comment="代码片段（用于定位）")
    line_number = Column(Integer, nullable=True, comment="行号")
    
    # 审计
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String(64), default="scanner", nullable=False)
    
    __table_args__ = (
        Index("idx_usage_field", "table_name", "field_name"),
        Index("idx_usage_api", "api_endpoint"),
        Index("idx_usage_frontend", "frontend_component"),
        Index("idx_usage_type", "usage_type"),
        UniqueConstraint("table_name", "field_name", "api_endpoint", "frontend_component", name="uq_field_usage"),
    )


# -------------------- Sales Campaign & Target Management (v4.11.0) --------------------

class SalesCampaign(Base):
    """
    销售战役管理表（A类数据：用户配置）
    
    用途：存储销售战役配置信息，用户在系统中创建和编辑
    达成数据：从fact_orders表自动计算（C类数据）
    """
    __tablename__ = "sales_campaigns"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 战役基本信息
    campaign_name = Column(String(200), nullable=False, comment="战役名称")
    campaign_type = Column(String(32), nullable=False, comment="战役类型：holiday/new_product/special_event")
    start_date = Column(Date, nullable=False, comment="开始日期")
    end_date = Column(Date, nullable=False, comment="结束日期")
    
    # 目标值（A类：用户配置）
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额（CNY）")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值（C类：系统自动计算）
    actual_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额（CNY）")
    actual_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率（百分比）")
    
    # 状态
    status = Column(String(32), nullable=False, default="pending", comment="状态：active/completed/pending/cancelled")
    description = Column(Text, nullable=True, comment="战役描述")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_campaign_dates"),
        CheckConstraint("target_amount >= 0", name="chk_campaign_amount"),
        CheckConstraint("target_quantity >= 0", name="chk_campaign_quantity"),
        Index("ix_sales_campaigns_status", "status"),
        Index("ix_sales_campaigns_dates", "start_date", "end_date"),
        Index("ix_sales_campaigns_type", "campaign_type"),
    )


class SalesCampaignShop(Base):
    """
    销售战役参与店铺表（A类数据：用户配置）
    
    用途：存储战役参与店铺及其目标配置
    达成数据：从fact_orders表自动计算（C类数据）
    """
    __tablename__ = "sales_campaign_shops"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段
    campaign_id = Column(Integer, ForeignKey("sales_campaigns.id", ondelete="CASCADE"), nullable=False)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    # 目标值（A类：用户配置）
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额（CNY）")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值（C类：系统自动计算）
    actual_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额（CNY）")
    actual_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率（百分比）")
    
    # 排名
    rank = Column(Integer, nullable=True, comment="排名")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("campaign_id", "platform_code", "shop_id", name="uq_campaign_shop"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_campaign_shop"
        ),
        Index("ix_campaign_shops_campaign", "campaign_id"),
        Index("ix_campaign_shops_shop", "platform_code", "shop_id"),
    )


class SalesTarget(Base):
    """
    目标管理表（A类数据：用户配置）
    
    用途：存储销售目标配置（店铺/产品/战役级别）
    达成数据：从fact_orders表自动计算（C类数据）
    """
    __tablename__ = "sales_targets"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 目标基本信息
    target_name = Column(String(200), nullable=False, comment="目标名称")
    target_type = Column(String(32), nullable=False, comment="目标类型：shop/product/campaign")
    period_start = Column(Date, nullable=False, comment="开始时间")
    period_end = Column(Date, nullable=False, comment="结束时间")
    
    # 目标值（A类：用户配置）
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额（CNY）")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值（C类：系统自动计算）
    achieved_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额（CNY）")
    achieved_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率（百分比）")
    
    # 状态
    status = Column(String(32), nullable=False, default="active", comment="状态：active/completed/cancelled")
    description = Column(Text, nullable=True, comment="目标描述")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="chk_target_dates"),
        CheckConstraint("target_amount >= 0", name="chk_target_amount"),
        CheckConstraint("target_quantity >= 0", name="chk_target_quantity"),
        Index("ix_sales_targets_type", "target_type"),
        Index("ix_sales_targets_status", "status"),
        Index("ix_sales_targets_period", "period_start", "period_end"),
    )


class TargetBreakdown(Base):
    """
    目标分解表（A类数据：用户配置）
    
    用途：存储目标分解配置（按店铺/按时间）
    达成数据：从fact_orders表自动计算（C类数据）
    """
    __tablename__ = "target_breakdown"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段
    target_id = Column(Integer, ForeignKey("sales_targets.id", ondelete="CASCADE"), nullable=False)
    
    # 分解类型
    breakdown_type = Column(String(32), nullable=False, comment="分解类型：shop/time")
    
    # 店铺分解字段（breakdown_type='shop'时使用）
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    
    # 时间分解字段（breakdown_type='time'时使用）
    period_start = Column(Date, nullable=True, comment="周期开始")
    period_end = Column(Date, nullable=True, comment="周期结束")
    period_label = Column(String(64), nullable=True, comment="周期标签，如'第1周'、'2025-01'")
    
    # 目标值（A类：用户配置）
    target_amount = Column(Float, nullable=False, default=0.0, comment="目标销售额（CNY）")
    target_quantity = Column(Integer, nullable=False, default=0, comment="目标订单数/销量")
    
    # 达成值（C类：系统自动计算）
    achieved_amount = Column(Float, nullable=False, default=0.0, comment="实际销售额（CNY）")
    achieved_quantity = Column(Integer, nullable=False, default=0, comment="实际订单数/销量")
    achievement_rate = Column(Float, nullable=False, default=0.0, comment="达成率（百分比）")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        CheckConstraint("breakdown_type IN ('shop', 'time')", name="chk_breakdown_type"),
        # 注意：PostgreSQL的CHECK约束不支持复杂的条件逻辑，这里用Python代码验证
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_breakdown_shop"
        ),
        Index("ix_target_breakdown_target", "target_id"),
        Index("ix_target_breakdown_shop", "platform_code", "shop_id"),
        Index("ix_target_breakdown_period", "period_start", "period_end"),
    )


class ShopHealthScore(Base):
    """
    店铺健康度评分表（C类数据：系统自动计算）
    
    用途：存储店铺健康度评分和各项指标得分
    数据来源：基于fact_orders和fact_product_metrics计算得出
    """
    __tablename__ = "shop_health_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    metric_date = Column(Date, nullable=False)
    granularity = Column(String(16), nullable=False, default="daily", comment="粒度：daily/weekly/monthly")
    
    # 健康度总分（0-100）
    health_score = Column(Float, nullable=False, default=0.0, comment="健康度总分（0-100）")
    
    # 各项得分（0-100）
    gmv_score = Column(Float, nullable=False, default=0.0, comment="GMV得分")
    conversion_score = Column(Float, nullable=False, default=0.0, comment="转化得分")
    inventory_score = Column(Float, nullable=False, default=0.0, comment="库存得分")
    service_score = Column(Float, nullable=False, default=0.0, comment="服务得分")
    
    # 基础指标（用于计算得分）
    gmv = Column(Float, nullable=False, default=0.0, comment="GMV（CNY）")
    conversion_rate = Column(Float, nullable=False, default=0.0, comment="转化率（百分比）")
    inventory_turnover = Column(Float, nullable=False, default=0.0, comment="库存周转率")
    customer_satisfaction = Column(Float, nullable=False, default=0.0, comment="客户满意度（0-5分）")
    
    # 风险等级
    risk_level = Column(String(16), nullable=False, default="low", comment="风险等级：low/medium/high")
    risk_factors = Column(JSON, nullable=True, comment="风险因素列表")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "metric_date", "granularity", name="uq_shop_health"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_shop_health"
        ),
        CheckConstraint("health_score >= 0 AND health_score <= 100", name="chk_health_score"),
        CheckConstraint("risk_level IN ('low', 'medium', 'high')", name="chk_risk_level"),
        Index("ix_shop_health_shop", "platform_code", "shop_id"),
        Index("ix_shop_health_date", "metric_date"),
        Index("ix_shop_health_score", "health_score"),
        Index("ix_shop_health_risk", "risk_level"),
    )


class ShopAlert(Base):
    """
    店铺预警提醒表（C类数据：系统自动计算）
    
    用途：存储店铺运营预警信息
    数据来源：基于shop_health_scores和业务规则自动生成
    """
    __tablename__ = "shop_alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    
    # 预警信息
    alert_type = Column(String(64), nullable=False, comment="预警类型：inventory_turnover/conversion_rate/gmv_drop/...")
    alert_level = Column(String(16), nullable=False, comment="预警级别：critical/warning/info")
    title = Column(String(200), nullable=False, comment="预警标题")
    message = Column(Text, nullable=False, comment="预警内容")
    
    # 指标值
    metric_value = Column(Float, nullable=True, comment="当前指标值")
    threshold = Column(Float, nullable=True, comment="阈值")
    metric_unit = Column(String(32), nullable=True, comment="指标单位")
    
    # 处理状态
    is_resolved = Column(Boolean, nullable=False, default=False, comment="是否已解决")
    resolved_at = Column(DateTime, nullable=True, comment="解决时间")
    resolved_by = Column(String(64), nullable=True, comment="解决人")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_shop_alert"
        ),
        CheckConstraint("alert_level IN ('critical', 'warning', 'info')", name="chk_alert_level"),
        Index("ix_shop_alerts_shop", "platform_code", "shop_id"),
        Index("ix_shop_alerts_level", "alert_level"),
        Index("ix_shop_alerts_resolved", "is_resolved"),
        Index("ix_shop_alerts_created", "created_at"),
    )


class PerformanceScore(Base):
    """
    绩效评分表（C类数据：系统自动计算）
    
    用途：存储店铺绩效评分和明细
    数据来源：基于fact_orders、fact_product_metrics和sales_targets计算得出
    """
    __tablename__ = "performance_scores"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    period = Column(String(16), nullable=False, comment="考核周期，如'2025-01'")
    
    # 总分（0-100）
    total_score = Column(Float, nullable=False, default=0.0, comment="总分（0-100）")
    
    # 各项得分（权重 × 达成率）
    sales_score = Column(Float, nullable=False, default=0.0, comment="销售额得分（权重30%）")
    profit_score = Column(Float, nullable=False, default=0.0, comment="毛利得分（权重25%）")
    key_product_score = Column(Float, nullable=False, default=0.0, comment="重点产品得分（权重25%）")
    operation_score = Column(Float, nullable=False, default=0.0, comment="运营得分（权重20%）")
    
    # 得分明细（JSONB存储详细计算过程）
    score_details = Column(JSON, nullable=True, comment="得分明细（JSON格式）")
    
    # 排名和系数
    rank = Column(Integer, nullable=True, comment="排名")
    performance_coefficient = Column(Float, nullable=False, default=1.0, comment="绩效系数")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "period", name="uq_performance_shop_period"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_performance_shop"
        ),
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="chk_total_score"),
        Index("ix_performance_shop", "platform_code", "shop_id"),
        Index("ix_performance_period", "period"),
        Index("ix_performance_score", "total_score"),
        Index("ix_performance_rank", "rank"),
    )


class PerformanceConfig(Base):
    """
    绩效权重配置表（A类数据：用户配置）
    
    用途：存储绩效计算规则和权重配置
    """
    __tablename__ = "performance_config"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 配置信息
    config_name = Column(String(64), nullable=False, default="default", comment="配置名称")
    
    # 权重配置（百分比，总和必须为100）
    sales_weight = Column(Integer, nullable=False, default=30, comment="销售额权重（%）")
    profit_weight = Column(Integer, nullable=False, default=25, comment="毛利权重（%）")
    key_product_weight = Column(Integer, nullable=False, default=25, comment="重点产品权重（%）")
    operation_weight = Column(Integer, nullable=False, default=20, comment="运营权重（%）")
    
    # 生效时间
    is_active = Column(Boolean, nullable=False, default=True, comment="是否启用")
    effective_from = Column(Date, nullable=False, comment="生效开始日期")
    effective_to = Column(Date, nullable=True, comment="生效结束日期（NULL表示永久有效）")
    
    # 审计字段
    created_by = Column(String(64), nullable=True, comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        CheckConstraint(
            "sales_weight + profit_weight + key_product_weight + operation_weight = 100",
            name="chk_weights_sum"
        ),
        CheckConstraint(
            "sales_weight >= 0 AND sales_weight <= 100 AND "
            "profit_weight >= 0 AND profit_weight <= 100 AND "
            "key_product_weight >= 0 AND key_product_weight <= 100 AND "
            "operation_weight >= 0 AND operation_weight <= 100",
            name="chk_weights_range"
        ),
        Index("ix_performance_config_active", "is_active", "effective_from"),
    )


class ClearanceRanking(Base):
    """
    滞销清理排名表（C类数据：系统自动计算）
    
    用途：存储店铺滞销清理排名数据
    数据来源：基于fact_product_metrics和fact_orders计算得出
    """
    __tablename__ = "clearance_rankings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 业务标识
    platform_code = Column(String(32), nullable=False)
    shop_id = Column(String(64), nullable=False)
    metric_date = Column(Date, nullable=False)
    granularity = Column(String(16), nullable=False, comment="粒度：monthly/weekly")
    
    # 清理数据
    clearance_amount = Column(Float, nullable=False, default=0.0, comment="清理金额（CNY）")
    clearance_quantity = Column(Integer, nullable=False, default=0, comment="清理数量")
    
    # 激励金额
    incentive_amount = Column(Float, nullable=False, default=0.0, comment="激励金额（CNY）")
    total_incentive = Column(Float, nullable=False, default=0.0, comment="总计激励（CNY）")
    
    # 排名
    rank = Column(Integer, nullable=True, comment="排名")
    
    # 审计字段
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("platform_code", "shop_id", "metric_date", "granularity", name="uq_clearance_ranking"),
        ForeignKeyConstraint(
            ["platform_code", "shop_id"],
            ["dim_shops.platform_code", "dim_shops.shop_id"],
            name="fk_clearance_ranking"
        ),
        Index("ix_clearance_ranking_date", "metric_date", "granularity"),
        Index("ix_clearance_ranking_rank", "rank"),
        Index("ix_clearance_ranking_amount", "clearance_amount"),
    )


# -------------------- Materialized View Management --------------------

class MaterializedViewRefreshLog(Base):
    """物化视图刷新日志表
    
    v4.11.4新增：
    - 记录每次物化视图刷新的详细信息
    - 用于监控刷新性能和审计追踪
    - 与MaterializedViewService中的使用保持一致
    """
    __tablename__ = "mv_refresh_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    view_name = Column(String(128), nullable=False, index=True, comment="物化视图名称")
    refresh_started_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="刷新开始时间")
    refresh_completed_at = Column(DateTime, nullable=True, comment="刷新完成时间")
    duration_seconds = Column(Float, nullable=True, comment="刷新耗时（秒）")
    row_count = Column(Integer, nullable=True, comment="刷新后行数")
    status = Column(String(20), default="running", nullable=False, comment="状态：running/success/failed")
    error_message = Column(Text, nullable=True, comment="错误信息（如果失败）")
    triggered_by = Column(String(64), default="scheduler", nullable=False, comment="触发方式：scheduler/manual/api")
    
    __table_args__ = (
        CheckConstraint("status IN ('running', 'success', 'failed')", name="chk_mv_refresh_status"),
        Index("ix_mv_refresh_log_view", "view_name", "refresh_started_at"),
        Index("ix_mv_refresh_log_status", "status", "refresh_started_at"),
    )


# -------------------- User and Permission Tables (v4.12.0 SSOT Migration) --------------------

# 用户-角色关联表（多对多）
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', BigInteger, ForeignKey('dim_users.user_id'), primary_key=True),
    Column('role_id', BigInteger, ForeignKey('dim_roles.role_id'), primary_key=True),
    Column('assigned_at', DateTime, server_default=func.now()),
    Column('assigned_by', String(100))
)


class DimUser(Base):
    """
    用户表
    
    v4.12.0迁移：从backend/models/users.py迁移到schema.py（SSOT合规性）
    """
    __tablename__ = "dim_users"
    
    user_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)  # 存储hash后的密码
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
        comment="用户状态: pending/active/rejected/suspended/deleted"
    )
    
    # 审批信息
    approved_at = Column(DateTime, nullable=True, comment="审批时间")
    approved_by = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=True,
        comment="审批人ID"
    )
    rejection_reason = Column(Text, nullable=True, comment="拒绝原因")
    
    # 数据权限（可见的平台和店铺）
    allowed_platforms = Column(Text)  # JSON数组，如：["shopee", "tiktok"]
    allowed_shops = Column(Text)  # JSON数组，如：["shop1", "shop2"]
    
    # 联系信息
    phone = Column(String(50))
    department = Column(String(100))
    position = Column(String(100))
    
    # 登录信息
    last_login = Column(DateTime)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True, comment="账户锁定到期时间")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_users_active", "is_active"),
        Index("idx_users_email_active", "email", "is_active"),
    )
    
    # 关系
    roles = relationship(
        "DimRole",
        secondary=user_roles,
        back_populates="users"
    )
    audit_logs = relationship(
        "FactAuditLog",
        back_populates="user",
        cascade="all, delete-orphan"
    )


class DimRole(Base):
    """
    角色表
    
    v4.12.0迁移：从backend/models/users.py迁移到schema.py（SSOT合规性）
    """
    __tablename__ = "dim_roles"
    
    role_id = Column(BigInteger, primary_key=True, index=True)
    
    # 角色信息
    role_name = Column(String(100), unique=True, nullable=False, index=True)
    role_code = Column(String(50), unique=True, nullable=False)  # 角色代码，如：admin, finance, warehouse
    description = Column(Text)
    
    # 权限（JSON格式）
    permissions = Column(Text, nullable=False)  # JSON数组，如：["view_sales", "edit_inventory"]
    
    # 数据权限范围
    data_scope = Column(String(50), default='all')  # all/platform/shop/self
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False)
    is_system = Column(Boolean, default=False)  # 是否系统角色（不可删除）
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index("idx_roles_active", "is_active"),
    )
    
    # 关系
    users = relationship(
        "DimUser",
        secondary=user_roles,
        back_populates="roles"
    )


class UserSession(Base):
    """
    用户会话表（用于会话管理）
    
    v4.19.0新增：会话管理功能
    用于跟踪和管理用户的活跃会话，支持强制登出其他设备
    """
    __tablename__ = "user_sessions"
    
    session_id = Column(String(64), primary_key=True, index=True, comment="会话ID（Token的哈希值）")
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        index=True
    )
    
    # 会话信息
    device_info = Column(String(255), nullable=True, comment="设备信息（User-Agent）")
    ip_address = Column(String(45), nullable=True, comment="IP地址")
    location = Column(String(100), nullable=True, comment="登录位置（可选）")
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间（登录时间）"
    )
    expires_at = Column(
        DateTime,
        nullable=False,
        comment="过期时间"
    )
    last_active_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后活跃时间"
    )
    
    # 状态
    is_active = Column(Boolean, default=True, nullable=False, comment="是否有效")
    revoked_at = Column(DateTime, nullable=True, comment="撤销时间")
    revoked_reason = Column(String(100), nullable=True, comment="撤销原因")
    
    __table_args__ = (
        Index("idx_session_user_active", "user_id", "is_active"),
        Index("idx_session_expires", "expires_at"),
    )
    
    # 关系
    user = relationship("DimUser", backref="sessions")


class UserApprovalLog(Base):
    """
    用户审批记录表（用于审计）
    
    v4.19.0新增：用户注册和审批流程
    用于记录所有用户审批操作，支持审计追踪
    """
    __tablename__ = "user_approval_logs"
    
    log_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        index=True
    )
    
    # 审批信息
    action = Column(
        String(20),
        nullable=False,
        index=True,
        comment="操作类型: approve/reject/suspend"
    )
    approved_by = Column(
        BigInteger,
        ForeignKey('dim_users.user_id'),
        nullable=False,
        comment="操作人ID"
    )
    reason = Column(
        Text,
        nullable=True,
        comment="操作原因/备注"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True
    )
    
    __table_args__ = (
        Index("idx_approval_user_time", "user_id", "created_at"),
        Index("idx_approval_action_time", "action", "created_at"),
    )


class FactAuditLog(Base):
    """
    操作审计日志表
    
    v4.12.0迁移：从backend/models/users.py迁移到schema.py（SSOT合规性）
    
    用于记录所有用户操作，支持企业级ERP的审计追溯要求。
    """
    __tablename__ = "fact_audit_logs"
    
    log_id = Column(BigInteger, primary_key=True, index=True)
    
    # 用户信息
    user_id = Column(BigInteger, ForeignKey("dim_users.user_id"), nullable=False)
    username = Column(String(100), nullable=False)  # 冗余字段，便于查询
    
    # 操作信息
    action_type = Column(String(50), nullable=False, index=True)  # create/update/delete/view/export
    resource_type = Column(String(100), nullable=False)  # order/product/inventory/finance
    resource_id = Column(String(150))  # 资源ID
    
    # 详细信息
    action_description = Column(Text)  # 操作描述
    changes_json = Column(Text)  # JSON格式的变更详情（before/after）
    
    # IP和设备信息
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    
    # 结果
    is_success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    __table_args__ = (
        Index("idx_audit_user_time", "user_id", "created_at"),
        Index("idx_audit_action_time", "action_type", "created_at"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
        Index(
            "idx_audit_recent",
            "created_at",
            postgresql_using='btree',
            postgresql_ops={'created_at': 'DESC'}
        ),
    )
    
    # 关系
    user = relationship("DimUser", back_populates="audit_logs")


class SyncProgressTask(Base):
    """
    数据同步进度任务表
    
    v4.12.0新增：
    - 用于持久化存储数据同步任务的进度信息
    - 支持服务重启后恢复进度
    - 替代内存存储的ProgressTracker（用于数据同步场景）
    """
    __tablename__ = "sync_progress_tasks"
    
    task_id = Column(String(100), primary_key=True, index=True, comment="任务ID")
    
    # 任务基本信息
    task_type = Column(String(50), nullable=False, default="bulk_ingest", comment="任务类型：bulk_ingest/single_file")
    total_files = Column(Integer, default=0, nullable=False, comment="总文件数")
    processed_files = Column(Integer, default=0, nullable=False, comment="已处理文件数")
    current_file = Column(String(500), nullable=True, comment="当前处理文件")
    
    # 任务状态
    status = Column(String(20), default="pending", nullable=False, index=True, comment="状态：pending/processing/completed/failed")
    
    # 数据统计
    total_rows = Column(Integer, default=0, nullable=False, comment="总行数")
    processed_rows = Column(Integer, default=0, nullable=False, comment="已处理行数")
    valid_rows = Column(Integer, default=0, nullable=False, comment="有效行数")
    error_rows = Column(Integer, default=0, nullable=False, comment="错误行数")
    quarantined_rows = Column(Integer, default=0, nullable=False, comment="隔离行数")
    
    # 进度百分比（计算字段，冗余存储便于查询）
    file_progress = Column(Float, default=0.0, nullable=False, comment="文件进度百分比")
    row_progress = Column(Float, default=0.0, nullable=False, comment="行进度百分比")
    
    # 时间戳
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False, index=True, comment="开始时间")
    end_time = Column(DateTime, nullable=True, comment="结束时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False, comment="更新时间")
    
    # 错误和警告（JSON格式）
    errors = Column(JSON, nullable=True, comment="错误列表")
    warnings = Column(JSON, nullable=True, comment="警告列表")
    
    # 任务详情（JSON格式，存储额外信息）
    task_details = Column(JSON, nullable=True, comment="任务详情")
    
    __table_args__ = (
        Index("ix_sync_progress_status", "status", "start_time"),
        Index("ix_sync_progress_updated", "updated_at"),
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="chk_sync_progress_status"),
    )


# -------------------- DSS Architecture Tables (v4.6.0+) --------------------

# B-Class Data Tables (按平台-数据域-子类型-粒度分表，动态创建)
# [WARN] v4.17.0+ 架构调整：旧的固定表类已删除，所有B类数据表通过PlatformTableManager动态创建
# 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
# 所有表创建在b_class schema中

# 以下旧的固定表类定义已删除（v4.17.0+）：
# - FactRawDataOrdersDaily, FactRawDataOrdersWeekly, FactRawDataOrdersMonthly
# - FactRawDataProductsDaily, FactRawDataProductsWeekly, FactRawDataProductsMonthly
# - FactRawDataTrafficDaily, FactRawDataTrafficWeekly, FactRawDataTrafficMonthly
# - FactRawDataAnalyticsDaily, FactRawDataAnalyticsWeekly, FactRawDataAnalyticsMonthly
# - FactRawDataServicesDaily, FactRawDataServicesWeekly, FactRawDataServicesMonthly
# - FactRawDataServicesAiAssistantDaily, FactRawDataServicesAiAssistantWeekly, FactRawDataServicesAiAssistantMonthly
# - FactRawDataServicesAgentWeekly, FactRawDataServicesAgentMonthly
# - FactRawDataInventorySnapshot
# 
# 所有B类数据表现在通过PlatformTableManager动态创建，表名格式：
# - 无sub_domain：fact_{platform}_{data_domain}_{granularity}（如fact_shopee_orders_daily）
# - 有sub_domain：fact_{platform}_{data_domain}_{sub_domain}_{granularity}（如fact_shopee_services_ai_assistant_monthly）
# 所有表创建在b_class schema中

# 所有旧的固定表类定义已删除（v4.17.0+）
# 所有B类数据表通过PlatformTableManager动态创建


# 统一对齐表（替代dim_shops和account_aliases）

class EntityAlias(Base):
    """
    统一实体别名表（v4.6.0+）
    
    替代dim_shops和account_aliases两张表，统一管理所有账号和店铺的别名映射
    """
    __tablename__ = "entity_aliases"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 源标识（from）
    source_platform = Column(String(32), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)  # 'account' | 'shop' | 'store'
    source_name = Column(String(256), nullable=False, index=True)
    source_account = Column(String(128), nullable=True)
    source_site = Column(String(64), nullable=True)
    data_domain = Column(String(64), nullable=True)
    
    # 目标标识（to）
    target_type = Column(String(32), nullable=False, index=True)  # 'account' | 'shop'
    target_id = Column(String(256), nullable=False, index=True)
    target_name = Column(String(256), nullable=True)
    target_platform_code = Column(String(32), nullable=True)
    
    # 元数据
    confidence = Column(Float, default=1.0)
    active = Column(Boolean, default=True, nullable=False, index=True)
    notes = Column(Text, nullable=True)
    
    # 审计
    created_by = Column(String(64), default='system')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("source_platform", "source_type", "source_name", "source_account", "source_site", name="uq_entity_alias_source"),
        Index("ix_entity_aliases_source", "source_platform", "source_type", "source_name"),
        Index("ix_entity_aliases_target", "target_type", "target_id", "active"),
    )


# 以下所有旧的固定表类定义已删除（v4.17.0+）
# 所有B类数据表通过PlatformTableManager动态创建
# 表名格式：fact_{platform}_{data_domain}_{sub_domain}_{granularity}
# 所有表创建在b_class schema中

# 统一对齐表（替代dim_shops和account_aliases）


# Staging表（临时表，用于数据清洗）

class StagingRawData(Base):
    """
    Staging原始数据表（ETL中间层）
    
    存储原始数据（JSONB格式），用于数据清洗和验证
    """
    __tablename__ = "staging_raw_data"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True)
    row_number = Column(Integer, nullable=False)
    platform_code = Column(String(32), nullable=True, index=True)
    shop_id = Column(String(256), nullable=True, index=True)
    data_domain = Column(String(64), nullable=True, index=True)
    granularity = Column(String(32), nullable=True)
    metric_date = Column(Date, nullable=True)
    raw_data = Column(JSONB, nullable=False)
    header_columns = Column(JSONB, nullable=True)
    status = Column(String(32), default='pending', nullable=False, index=True)  # pending/validated/ingested/failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_staging_raw_data_file", "file_id", "status"),
        Index("ix_staging_raw_data_domain_gran", "data_domain", "granularity"),
    )


# A类数据表（使用中文字段名）

# A类数据表（使用中文字段名）
# 注意：中文字段名将在Alembic迁移脚本中使用text()函数实现
# 这里先使用英文字段名定义表结构，迁移脚本中会重命名为中文

class SalesTargetA(Base):
    """
    A类数据表：销售目标（中文字段名）
    
    注意：字段名在Alembic迁移脚本中将使用中文（如"店铺ID", "年月"等）
    注意：此表将替代旧的SalesTarget表（v4.11.0），使用中文字段名
    """
    __tablename__ = "sales_targets_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"，格式：'2025-01'
    target_sales_amount = Column(Numeric(15, 2), nullable=False)  # 迁移时将重命名为"目标销售额"
    target_quantity = Column(Integer, nullable=False)  # 迁移时将重命名为"目标订单数"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 迁移时将重命名为"创建时间"
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)  # 迁移时将重命名为"更新时间"
    
    __table_args__ = (
        UniqueConstraint("shop_id", "year_month", name="uq_sales_targets_shop_month"),
        Index("ix_sales_targets_shop", "shop_id"),
        Index("ix_sales_targets_month", "year_month"),
    )


class SalesCampaignA(Base):
    """
    A类数据表：销售战役（中文字段名）
    
    注意：此表将替代旧的SalesCampaign表（v4.11.0），使用中文字段名
    """
    __tablename__ = "sales_campaigns_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    campaign_name = Column(String(200), nullable=False)  # 迁移时将重命名为"战役名称"
    campaign_type = Column(String(32), nullable=False)  # 迁移时将重命名为"战役类型"
    start_date = Column(Date, nullable=False)  # 迁移时将重命名为"开始日期"
    end_date = Column(Date, nullable=False)  # 迁移时将重命名为"结束日期"
    target_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"目标销售额"
    target_quantity = Column(Integer, nullable=False, default=0)  # 迁移时将重命名为"目标订单数"
    status = Column(String(32), nullable=False, default="pending")  # 迁移时将重命名为"状态"
    description = Column(Text, nullable=True)  # 迁移时将重命名为"描述"
    created_by = Column(String(64), nullable=True)  # 迁移时将重命名为"创建人"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_campaign_dates"),
        Index("ix_sales_campaigns_type", "campaign_type"),
        Index("ix_sales_campaigns_status", "status"),
    )


class OperatingCost(Base):
    """A类数据表：运营成本（中文字段名）"""
    __tablename__ = "operating_costs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    rent = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"租金"
    salary = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"工资"
    utilities = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"水电费"
    other_costs = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"其他成本"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("shop_id", "year_month", name="uq_operating_costs_shop_month"),
        Index("ix_operating_costs_shop", "shop_id"),
        Index("ix_operating_costs_month", "year_month"),
    )


class Employee(Base):
    """A类数据表：员工档案（中文字段名）"""
    __tablename__ = "employees"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False, unique=True)  # 迁移时将重命名为"员工编号"
    name = Column(String(128), nullable=False)  # 迁移时将重命名为"姓名"
    department = Column(String(128), nullable=True)  # 迁移时将重命名为"部门"
    position = Column(String(128), nullable=True)  # 迁移时将重命名为"职位"
    hire_date = Column(Date, nullable=True)  # 迁移时将重命名为"入职日期"
    status = Column(String(32), nullable=False, default="active")  # 迁移时将重命名为"状态"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_employees_code", "employee_code"),
        Index("ix_employees_department", "department"),
    )


class EmployeeTarget(Base):
    """A类数据表：员工目标（中文字段名）"""
    __tablename__ = "employee_targets"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    target_type = Column(String(32), nullable=False)  # 迁移时将重命名为"目标类型"
    target_value = Column(Numeric(15, 2), nullable=False)  # 迁移时将重命名为"目标值"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", "target_type", name="uq_employee_targets"),
        Index("ix_employee_targets_employee", "employee_code"),
        Index("ix_employee_targets_month", "year_month"),
    )


class AttendanceRecord(Base):
    """A类数据表：考勤记录（中文字段名）"""
    __tablename__ = "attendance_records"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    attendance_date = Column(Date, nullable=False)  # 迁移时将重命名为"考勤日期"
    clock_in_time = Column(DateTime, nullable=True)  # 迁移时将重命名为"上班时间"
    clock_out_time = Column(DateTime, nullable=True)  # 迁移时将重命名为"下班时间"
    work_hours = Column(Float, nullable=True)  # 迁移时将重命名为"工作时长"
    status = Column(String(32), nullable=False, default="normal")  # 迁移时将重命名为"状态"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("employee_code", "attendance_date", name="uq_attendance_records"),
        Index("ix_attendance_records_employee", "employee_code"),
        Index("ix_attendance_records_date", "attendance_date"),
    )


class PerformanceConfigA(Base):
    """
    A类数据表：绩效权重配置（中文字段名）
    
    注意：此表将替代旧的PerformanceConfig表（v4.11.0），使用中文字段名
    """
    __tablename__ = "performance_config_a"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    config_name = Column(String(128), nullable=False)  # 迁移时将重命名为"配置名称"
    sales_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"销售额权重"
    quantity_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"订单数权重"
    quality_weight = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"质量权重"
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        UniqueConstraint("config_name", name="uq_performance_config_name"),
        Index("ix_performance_config_active", "active"),
    )


# C类数据表（使用中文字段名，由Metabase定时计算更新）

class EmployeePerformance(Base):
    """C类数据表：员工绩效（中文字段名，Metabase每20分钟更新）"""
    __tablename__ = "employee_performance"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    actual_sales = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"实际销售额"
    achievement_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"达成率"
    performance_score = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"绩效得分"
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", name="uq_employee_performance"),
        Index("ix_employee_performance_employee", "employee_code"),
        Index("ix_employee_performance_month", "year_month"),
    )


class EmployeeCommission(Base):
    """C类数据表：员工提成（中文字段名，Metabase每20分钟更新）"""
    __tablename__ = "employee_commissions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    employee_code = Column(String(64), nullable=False)  # 迁移时将重命名为"员工编号"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    sales_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"销售额"
    commission_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"提成金额"
    commission_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"提成比例"
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("employee_code", "year_month", name="uq_employee_commissions"),
        Index("ix_employee_commissions_employee", "employee_code"),
        Index("ix_employee_commissions_month", "year_month"),
    )


class ShopCommission(Base):
    """C类数据表：店铺提成（中文字段名，Metabase每20分钟更新）"""
    __tablename__ = "shop_commissions"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    year_month = Column(String(7), nullable=False)  # 迁移时将重命名为"年月"
    sales_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"销售额"
    commission_amount = Column(Numeric(15, 2), nullable=False, default=0.0)  # 迁移时将重命名为"提成金额"
    commission_rate = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"提成比例"
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("shop_id", "year_month", name="uq_shop_commissions"),
        Index("ix_shop_commissions_shop", "shop_id"),
        Index("ix_shop_commissions_month", "year_month"),
    )


class PerformanceScoreC(Base):
    """
    C类数据表：店铺绩效（中文字段名，Metabase每20分钟更新）
    
    注意：此表将替代旧的PerformanceScore表（v4.11.0），使用中文字段名
    """
    __tablename__ = "performance_scores_c"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    shop_id = Column(String(256), nullable=False)  # 迁移时将重命名为"店铺ID"
    period = Column(String(32), nullable=False)  # 迁移时将重命名为"考核周期"
    total_score = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"总分"
    sales_score = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"销售得分"
    quality_score = Column(Float, nullable=False, default=0.0)  # 迁移时将重命名为"质量得分"
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # 迁移时将重命名为"计算时间"
    
    __table_args__ = (
        UniqueConstraint("shop_id", "period", name="uq_performance_scores"),
        Index("ix_performance_scores_shop", "shop_id"),
        Index("ix_performance_scores_period", "period"),
    )


# v4.19.0: 系统通知表

class Notification(Base):
    """
    系统通知表 (v4.19.0)
    
    用于存储系统内部通知，如：
    - 新用户注册通知（发给管理员）
    - 审批结果通知（发给用户）
    - 系统告警通知
    """
    __tablename__ = "notifications"
    
    notification_id = Column(BigInteger, primary_key=True, autoincrement=True)
    recipient_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="接收者用户ID"
    )
    
    # 通知内容
    notification_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="通知类型：user_registered, user_approved, user_rejected, system_alert"
    )
    title = Column(String(200), nullable=False, comment="通知标题")
    content = Column(Text, nullable=False, comment="通知内容")
    extra_data = Column(JSON, nullable=True, comment="扩展数据（JSON格式）")
    
    # 关联数据
    related_user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id', ondelete='SET NULL'),
        nullable=True,
        comment="关联用户ID（如被审批的用户）"
    )
    
    # v4.19.0: 优先级
    priority = Column(
        String(10),
        default="medium",
        nullable=False,
        index=True,
        comment="优先级：high, medium, low"
    )
    
    # 状态
    is_read = Column(Boolean, default=False, nullable=False, index=True, comment="是否已读")
    read_at = Column(DateTime, nullable=True, comment="阅读时间")
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="创建时间"
    )
    
    # 关系
    recipient = relationship(
        "DimUser",
        foreign_keys=[recipient_id],
        backref="notifications"
    )
    
    __table_args__ = (
        Index("idx_notification_user_unread", "recipient_id", "is_read"),
        Index("idx_notification_type_created", "notification_type", "created_at"),
    )


# v4.19.0: 用户通知偏好表

class UserNotificationPreference(Base):
    """
    用户通知偏好表 (v4.19.0)
    
    用于存储用户对不同类型通知的偏好设置，如：
    - 是否启用通知
    - 是否启用桌面通知
    """
    __tablename__ = "user_notification_preferences"
    
    preference_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        BigInteger,
        ForeignKey('dim_users.user_id', ondelete='CASCADE'),
        nullable=False,
        index=True,
        comment="用户ID"
    )
    notification_type = Column(
        String(50),
        nullable=False,
        comment="通知类型：user_registered, user_approved, user_rejected, system_alert等"
    )
    enabled = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用通知（应用内通知）"
    )
    desktop_enabled = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否启用桌面通知（浏览器原生通知）"
    )
    
    # 时间戳
    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间"
    )
    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间"
    )
    
    # 关系
    user = relationship(
        "DimUser",
        foreign_keys=[user_id],
        backref="notification_preferences"
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_preference"),
        Index("idx_user_notification_user", "user_id"),
    )


# [*] v4.19.4 新增：限流配置表（Phase 3）
class DimRateLimitConfig(Base):
    """
    限流配置维度表
    
    用途：存储基于角色的限流配置，支持运行时动态调整
    - 支持多角色、多端点类型配置
    - 支持配置启用/禁用
    - 支持配置版本管理
    
    v4.19.4 新增：Phase 3 数据库配置支持
    """
    __tablename__ = "dim_rate_limit_config"
    
    config_id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 配置维度
    role_code = Column(String(50), nullable=False, index=True)  # admin/manager/finance/operator/normal/anonymous
    endpoint_type = Column(String(50), nullable=False, index=True)  # default/data_sync/auth
    
    # 限流值
    limit_value = Column(String(50), nullable=False)  # "200/minute", "100/minute"
    
    # 配置状态
    is_active = Column(Boolean, default=True, nullable=False, index=True)  # 是否启用
    
    # 配置描述
    description = Column(Text, nullable=True)  # 配置说明
    
    # 审计字段
    created_by = Column(String(100), nullable=True)  # 创建者
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    updated_by = Column(String(100), nullable=True)  # 最后更新者
    
    __table_args__ = (
        UniqueConstraint("role_code", "endpoint_type", name="uq_rate_limit_config_role_endpoint"),
        Index("ix_rate_limit_config_active", "is_active", "role_code"),
        Index("ix_rate_limit_config_role", "role_code", "endpoint_type"),
    )


# [*] v4.19.4 新增：限流配置审计日志表（Phase 3）
class FactRateLimitConfigAudit(Base):
    """
    限流配置变更审计日志表
    
    用途：记录所有限流配置的变更历史，支持审计追溯
    - 记录配置创建、更新、删除操作
    - 记录变更前后的值
    - 记录操作人和操作时间
    
    v4.19.4 新增：Phase 3 配置变更审计
    """
    __tablename__ = "fact_rate_limit_config_audit"
    
    audit_id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    
    # 配置信息
    config_id = Column(Integer, ForeignKey("dim_rate_limit_config.config_id"), nullable=True)  # 配置ID（删除时为NULL）
    role_code = Column(String(50), nullable=False, index=True)  # 角色代码
    endpoint_type = Column(String(50), nullable=False, index=True)  # 端点类型
    
    # 操作信息
    action_type = Column(String(50), nullable=False, index=True)  # create/update/delete
    old_limit_value = Column(String(50), nullable=True)  # 变更前的限流值
    new_limit_value = Column(String(50), nullable=True)  # 变更后的限流值
    old_is_active = Column(Boolean, nullable=True)  # 变更前的启用状态
    new_is_active = Column(Boolean, nullable=True)  # 变更后的启用状态
    
    # 操作人信息
    operator_id = Column(BigInteger, ForeignKey("dim_users.user_id"), nullable=True)  # 操作人ID
    operator_username = Column(String(100), nullable=False)  # 操作人用户名（冗余字段）
    
    # IP和设备信息
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # 操作结果
    is_success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)  # 错误信息（如果操作失败）
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    
    __table_args__ = (
        Index("idx_rate_limit_audit_config", "config_id", "created_at"),
        Index("idx_rate_limit_audit_role", "role_code", "endpoint_type", "created_at"),
        Index("idx_rate_limit_audit_operator", "operator_id", "created_at"),
        Index("idx_rate_limit_audit_action", "action_type", "created_at"),
    )
