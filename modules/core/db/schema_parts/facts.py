from __future__ import annotations

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from .base import Base

class FactOrderAmount(Base):
    """
    订单金额维度表(v4.6.0核心设计)
    
    维度表设计:统一字段 + 多维度列
    - 优势:零字段爆炸,多货币支持,符合关系型范式
    - 用途:存储订单金额维度数据(销售额/退款 × 状态 × 货币)
    
    维度列:
    - metric_type: sales_amount(销售额)/ refund_amount(退款)
    - metric_subtype: completed/paid/placed/cancelled/pending_shipment/...
    - currency: BRL/SGD/CNY/USD/EUR/...
    
    示例:
    - 销售额(已付款订单)(BRL) -> {metric_type: sales_amount, metric_subtype: paid, currency: BRL}
    - 退款金额(SGD) -> {metric_type: refund_amount, metric_subtype: standard, currency: SGD}
    """
    __tablename__ = "fact_order_amounts"
    
    # 主键
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 关联字段(不使用外键约束,数据仓库设计模式)
    order_id = Column(String(128), nullable=False, index=True)
    
    # 维度列(关键设计)
    metric_type = Column(String(32), nullable=False, index=True)  # sales_amount/refund_amount
    metric_subtype = Column(String(32), nullable=False, index=True)  # completed/paid/placed/cancelled/...
    currency = Column(String(3), nullable=False, index=True)  # BRL/SGD/CNY/...
    
    # 金额列
    amount_original = Column(Float, nullable=False)  # 原币金额
    amount_cny = Column(Float, nullable=True)  # CNY金额(自动转换)
    exchange_rate = Column(Float, nullable=True)  # 汇率(审计)
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_order_amounts_order", "order_id"),
        Index("ix_order_amounts_metric", "metric_type", "metric_subtype"),
        Index("ix_order_amounts_currency", "currency", "created_at"),
        Index("ix_order_amounts_composite", "order_id", "metric_type", "metric_subtype", "currency"),
    )


class FactProductMetric(Base):
    """
    [WARN] v4.6.0 DSS架构重构:已废弃
    - 已被fact_raw_data_products_*表替代(按data_domain+granularity分表)
    - 表结构保留用于兼容性,但新数据应写入fact_raw_data_*表
    - 计划在Phase 6.1中删除(需要先迁移所有数据)
    
    原设计说明(方案B+ 扁平化设计):
    
    设计理念:
    - 宽表设计:直接存储所有指标字段,避免外键查询
    - 支持多粒度:daily/weekly/monthly在同一表
    - 完整业务标识:platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope
    
    主键设计:
    - 复合主键:platform_code + shop_id + platform_sku + metric_date + metric_type(初始设计)
    - 唯一索引:platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope(v4.10.0更新)
    """
    __tablename__ = "fact_product_metrics"
    
    # ========== 主键字段(业务标识) ==========
    platform_code = Column(String(32), nullable=False, primary_key=True, index=True)
    shop_id = Column(String(64), nullable=False, primary_key=True, index=True)
    platform_sku = Column(String(128), nullable=False, primary_key=True, index=True)
    metric_date = Column(Date, nullable=False, primary_key=True, index=True)
    metric_type = Column(String(64), nullable=False, primary_key=True)
    
    # ========== 粒度与层级字段 ==========
    granularity = Column(String(16), nullable=False, server_default='daily', index=True)
    sku_scope = Column(String(8), nullable=False, server_default='product', index=True, comment='SKU粒度:product(商品级) | variant(规格级)')
    data_domain = Column(String(50), nullable=True, index=True, comment='数据域:products/inventory等')
    parent_platform_sku = Column(String(128), nullable=True, index=True, comment='父级SKU(当sku_scope=variant时指向商品级SKU)')
    
    # ========== 数据血缘字段 ==========
    source_catalog_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment='来源文件ID')
    
    # ========== 商品基础信息 ==========
    product_name = Column(String(500), nullable=True)
    category = Column(String(200), nullable=True)
    brand = Column(String(100), nullable=True)
    specification = Column(String(500), nullable=True, comment='商品规格')
    
    # ========== 价格信息 ==========
    currency = Column(String(8), nullable=True)
    price = Column(Float, nullable=False, server_default='0.0', comment='商品价格(原币)')
    price_rmb = Column(Float, nullable=False, server_default='0.0', comment='商品价格(人民币)')
    
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
    sales_amount = Column(Float, nullable=False, server_default='0.0', comment='销售额(原币)')
    sales_amount_rmb = Column(Float, nullable=False, server_default='0.0', comment='销售额(人民币)')
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
    metric_date_utc = Column(Date, nullable=True, comment='UTC日期(按店铺时区换算)')
    
    # ========== 指标值字段(兼容旧设计) ==========
    metric_value = Column(Float, nullable=False, server_default='0', comment='指标值(兼容旧设计)')
    metric_value_rmb = Column(Float, nullable=False, server_default='0', comment='指标值(人民币,兼容旧设计)')
    
    # ========== 时间戳字段 ==========
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # ========== 表约束和索引 ==========
    __table_args__ = (
        # 唯一索引:platform_code + shop_id + platform_sku + metric_date + granularity + sku_scope
        UniqueConstraint(
            "platform_code", "shop_id", "platform_sku", "metric_date", "granularity", "sku_scope",
            name="ix_product_unique_with_scope"
        ),
        # 外键约束:source_catalog_id -> catalog_files.id
        ForeignKeyConstraint(
            ["source_catalog_id"],
            ["catalog_files.id"],
            ondelete="SET NULL"
        ),
        # 外键约束:platform_code + shop_id + platform_sku -> dim_products
        ForeignKeyConstraint(
            ["platform_code", "shop_id", "platform_sku"],
            ["core.dim_products.platform_code", "core.dim_products.shop_id", "core.dim_products.platform_sku"]
        ),
        # 索引:支持父SKU聚合查询
        Index("ix_product_parent_date", "platform_code", "shop_id", "parent_platform_sku", "metric_date"),
        # 索引:支持平台+店铺+日期+粒度查询
        Index("ix_metrics_plat_shop_date_gran", "platform_code", "shop_id", "metric_date", "granularity"),
        # 索引:支持平台+店铺+指标类型查询
        Index("ix_metrics_plat_shop_type", "platform_code", "shop_id", "metric_type"),
    )


class FactTraffic(Base):
    """
    流量数据事实表(运营数据)
    
    设计规则:
    - 主键:自增ID(便于外键引用和性能优化)
    - 业务唯一索引:platform_code + shop_id + traffic_date + granularity + metric_type + data_domain
    - shop_id为核心字段(运营数据主键设计规则)
    - 当shop_id为NULL时,使用account作为替代
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint(
            "platform_code", "shop_id", "traffic_date", "granularity", "metric_type", "data_domain",
            name="uq_fact_traffic_business"
        ),
    )


class FactService(Base):
    """
    服务数据事实表(运营数据)
    
    设计规则:
    - 主键:自增ID(便于外键引用和性能优化)
    - 业务唯一索引:platform_code + shop_id + service_date + granularity + metric_type + data_domain
    - shop_id为核心字段(运营数据主键设计规则)
    - 当shop_id为NULL时,使用account作为替代
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        UniqueConstraint(
            "platform_code", "shop_id", "service_date", "granularity", "metric_type", "data_domain",
            name="uq_fact_service_business"
        ),
    )


class FactAnalytics(Base):
    """
    分析数据事实表(运营数据)
    
    设计规则:
    - 主键:自增ID(便于外键引用和性能优化)
    - 业务唯一索引:platform_code + shop_id + analytics_date + granularity + metric_type + data_domain
    - shop_id为核心字段(运营数据主键设计规则)
    - 当shop_id为NULL时,使用account作为替代
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
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
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
    source = Column(String(64), nullable=False, default="data/raw")  # 正式采集文件统一来自 data/raw，temp/outputs 仅保留 legacy 兼容

    file_size = Column(Integer, nullable=True)
    file_hash = Column(String(64), nullable=True)  # sha256 or md5

    platform_code = Column(String(32), nullable=True)
    account = Column(String(128), nullable=True)  # [*] 账号信息(从.meta.json提取)
    shop_id = Column(String(256), nullable=True)  # v4.3.4: 扩展到256以支持长shop_id
    data_domain = Column(String(64), nullable=True)  # orders/products/metrics
    granularity = Column(String(16), nullable=True)   # daily/weekly/monthly
    date_from = Column(Date, nullable=True)
    date_to = Column(Date, nullable=True)

    # 方案B+核心字段
    source_platform = Column(String(32), nullable=True)  # 数据来源平台(用于字段映射模板匹配)
    sub_domain = Column(String(64), nullable=True)  # 子数据域(如services下的agent/ai_assistant)
    
    # 方案B+数据治理字段
    storage_layer = Column(String(32), nullable=True, default="raw")  # raw/staging/curated/quarantine
    quality_score = Column(Float, nullable=True)  # 0-100数据质量评分
    validation_errors = Column(JSON, nullable=True)  # 验证错误列表
    meta_file_path = Column(String(1024), nullable=True)  # 伴生元数据文件路径

    file_metadata = Column(JSON, nullable=True)

    status = Column(String(64), nullable=False, default="pending")  # pending/validated/ingested/quarantined/failed/template_update_required
    error_message = Column(Text, nullable=True)

    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_processed_at = Column(DateTime(timezone=True), nullable=True)

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

