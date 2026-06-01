from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
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
    JSON,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base, JSON_COMPAT

class DataQuarantine(Base):
    """
    数据隔离表
    
    用于存储处理失败的数据行,便于问题排查和数据恢复。
    当ETL流程中某些数据行验证失败或入库失败时,将其隔离到此表。
    """
    __tablename__ = "data_quarantine"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 来源信息
    source_file = Column(String(500), nullable=False)
    catalog_file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True)
    row_number = Column(Integer, nullable=True)  # 原文件中的行号
    
    # 数据内容(JSON格式保存原始数据)
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
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_quarantine_source_file", "source_file"),
        Index("ix_quarantine_error_type", "error_type"),
        Index("ix_quarantine_platform_shop", "platform_code", "shop_id"),
        Index("ix_quarantine_created", "created_at"),
        Index("ix_quarantine_resolved", "is_resolved"),
        {"schema": "core"},
    )


# -------------------- Application Management Tables --------------------

class DataFile(Base):
    """数据文件表(旧版API兼容)"""
    __tablename__ = "data_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    platform = Column(String(50), nullable=False)
    data_type = Column(String(50), nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    discovery_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_data_files_platform", "platform"),
        Index("ix_data_files_status", "status"),
        {"schema": "core"},
    )

class DataRecord(Base):
    """通用数据记录表"""
    __tablename__ = "data_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    record_type = Column(String(50), nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_data_records_platform", "platform"),
        Index("ix_data_records_type", "record_type"),
        {"schema": "core"},
    )

class FieldMapping(Base):
    """
    字段映射表(方案B+增强版)
    
    方案B+改进:
    - 添加sub_domain字段(services的agent/ai_assistant)
    - 支持更精确的模板匹配
    """
    __tablename__ = "field_mappings"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey("core.data_files.id", ondelete="CASCADE"), nullable=True)
    platform = Column(String(50), nullable=True)  # source_platform(数据来源)
    original_field = Column(String(100), nullable=False)
    standard_field = Column(String(100), nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    is_manual = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    domain = Column(String(50), nullable=True)
    granularity = Column(String(50), nullable=True)
    sheet_name = Column(String(100), nullable=True)
    
    # 方案B+新字段
    sub_domain = Column(String(64), nullable=True, default='')  # 子数据域(agent/ai_assistant等)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_field_mappings_platform", "platform"),
        Index("ix_field_mappings_domain", "domain"),
        Index("ix_field_mappings_version", "version"),
        # 方案B+新索引(精确模板匹配)
        Index("ix_field_mappings_template_key", "platform", "domain", "sub_domain", "granularity"),
        {"schema": "core"},
    )

class MappingSession(Base):
    """字段映射会话表"""
    __tablename__ = "mapping_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=True)
    domain = Column(String(50), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_mapping_sessions_session_id"),
        {"schema": "core"},
    )


# -------------------- Staging Tables (ETL Layer) --------------------

class StagingOrders(Base):
    """订单数据暂存表(ETL中间层)
    
    v4.11.4增强:
    - 添加ingest_task_id字段(关联同步任务)
    - 添加file_id字段(关联文件记录)
    - 保留order_data JSON字段作为兜底
    """
    __tablename__ = "staging_orders"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    order_id = Column(String(128), nullable=True)
    order_data = Column(JSON, nullable=False)  # 原始数据JSON(兜底)
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_staging_orders_platform", "platform_code"),
        Index("ix_staging_orders_task", "ingest_task_id"),
        Index("ix_staging_orders_file", "file_id"),
        {"schema": "core"},
    )

class StagingProductMetrics(Base):
    """产品指标暂存表(ETL中间层)
    
    v4.11.4增强:
    - 添加ingest_task_id字段(关联同步任务)
    - 添加file_id字段(关联文件记录)
    - 保留metric_data JSON字段作为兜底
    """
    __tablename__ = "staging_product_metrics"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform_code = Column(String(32), nullable=True)
    shop_id = Column(String(64), nullable=True)
    platform_sku = Column(String(64), nullable=True)
    metric_data = Column(JSON, nullable=False)  # 原始数据JSON(兜底)
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_staging_metrics_platform", "platform_code"),
        Index("ix_staging_metrics_task", "ingest_task_id"),
        Index("ix_staging_metrics_file", "file_id"),
        {"schema": "core"},
    )

class StagingInventory(Base):
    """库存数据暂存表(ETL中间层)
    
    v4.11.4新增:
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
    inventory_data = Column(JSON, nullable=False)  # 原始数据JSON(兜底)
    ingest_task_id = Column(String(64), nullable=True, index=True, comment="同步任务ID")
    file_id = Column(Integer, ForeignKey("catalog_files.id", ondelete="SET NULL"), nullable=True, index=True, comment="文件ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_staging_inventory_platform", "platform_code"),
        Index("ix_staging_inventory_task", "ingest_task_id"),
        Index("ix_staging_inventory_file", "file_id"),
        Index("ix_staging_inventory_sku", "platform_code", "shop_id", "platform_sku"),
        {"schema": "core"},
    )

class ProductImage(Base):
    """
    产品图片表(v3.0新增)
    
    存储产品图片URL和元数据,支持SKU级图片管理
    """
    __tablename__ = "product_images"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 产品标识(三元组)
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
    
    # 质量评分(预留v4.0 AI识别)
    quality_score = Column(Float, nullable=True, comment="图片质量评分(0-100)")
    is_main_image = Column(Boolean, nullable=False, default=False, comment="是否主图")
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    __table_args__ = (
        Index("idx_product_images_sku", "platform_sku"),
        Index("idx_product_images_product", "platform_code", "shop_id", "platform_sku"),
        Index("idx_product_images_order", "platform_sku", "image_order"),
    )


# -------------------- Field Mapping Dictionary & Templates (v4.3.7) --------------------

from sqlalchemy import UniqueConstraint  # reuse imports for constraints

class FieldMappingDictionary(Base):
    """
    字段映射辞典表(标准字段元数据)

    单一数据源:运行时从数据库读取并缓存
    """
    __tablename__ = "field_mapping_dictionary"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 标准字段标识(唯一、稳定)
    # 支持中文或英文代码(PostgreSQL UTF-8完全支持)
    # 中文示例:field_code="订单号", cn_name="订单号"
    # 英文示例:field_code="order_id", cn_name="订单号"
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

    # 审计与版本(v4.4.0新增)
    active = Column(Boolean, default=True)
    version = Column(Integer, default=1, nullable=False)  # 版本号(SCD2支持)
    status = Column(String(32), default="active", nullable=False)  # draft/active/deprecated
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    notes = Column(Text, nullable=True)
    
    # v4.6.0新增:Pattern-based Mapping(配置驱动)
    is_pattern_based = Column(Boolean, default=False, nullable=False, comment="是否启用模式匹配")
    field_pattern = Column(Text, nullable=True, comment="字段匹配正则表达式(支持命名组)")
    dimension_config = Column(JSON, nullable=True, comment="维度提取配置(如订单状态、货币映射)")
    target_table = Column(String(64), nullable=True, comment="目标表名(如fact_order_amounts)")
    target_columns = Column(JSON, nullable=True, comment="目标列映射配置(如metric_type/metric_subtype)")

    # v4.10.2新增:物化视图显示标识
    is_mv_display = Column(Boolean, default=False, nullable=False, comment="是否需要在物化视图中显示(true=核心字段,false=辅助字段)")
    
    # C类数据核心字段优化计划(Phase 3):货币策略字段
    currency_policy = Column(String(32), nullable=True, comment="货币策略(CNY/无货币/多币种)")
    source_priority = Column(JSON, nullable=True, comment="数据源优先级(JSON数组,如[\"miaoshou\", \"shopee\"])")

    __table_args__ = (
        UniqueConstraint("cn_name", name="uq_dictionary_cn_name"),  # 确保一对一映射:每个中文名称只对应一个标准字段
        Index("ix_dictionary_domain_group", "data_domain", "field_group"),
        Index("ix_dictionary_required", "is_required", "data_domain"),
        Index("ix_dictionary_status", "status", "data_domain"),
        Index("ix_dictionary_mv_display", "is_mv_display", "data_domain"),  # v4.10.2新增:物化视图显示字段索引
        Index("ix_dictionary_currency_policy", "currency_policy"),  # C类数据核心字段优化计划:货币策略索引
        {"schema": "core"},
    )

class FieldMappingTemplate(Base):
    """
    字段映射模板表(头)
    
    v4.5.1增强:
    - 新增header_row: 支持非0行表头
    - 新增sub_domain: 支持子数据类型识别(ai_assistant/agent等)
    - 新增sheet_name: 支持多工作表Excel
    - 新增encoding: 支持非UTF-8编码
    
    维度:platform × data_domain × sub_domain × granularity × account
    """
    __tablename__ = "field_mapping_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 模板维度
    platform = Column(String(32), nullable=False, index=True)
    data_domain = Column(String(64), nullable=False, index=True)
    granularity = Column(String(32), nullable=True)
    account = Column(String(128), nullable=True)
    
    # v4.5.1新增:数据解析配置
    sub_domain = Column(String(64), nullable=True, comment="子数据类型(如ai_assistant/agent)")
    header_row = Column(Integer, default=0, nullable=False, comment="表头行索引(0-based,默认0)")
    sheet_name = Column(String(128), nullable=True, comment="Excel工作表名称")
    encoding = Column(String(32), default='utf-8', nullable=False, comment="文件编码(默认utf-8)")

    # v4.6.0新增:原始表头字段列表(替代FieldMappingTemplateItem)
    header_columns = Column(JSONB, nullable=True, comment="原始表头字段列表(JSONB数组)")
    
    # v4.14.0新增:核心去重字段列表(用于data_hash计算)
    deduplication_fields = Column(JSONB, nullable=True, comment="核心去重字段列表(JSONB数组),用于data_hash计算,不受表头变化影响")

    # v4.22.1新增:模板列语义绑定(用于脏表头/空表头场景的稳定重连)
    header_bindings = Column(JSONB, nullable=True, comment="模板列语义绑定(JSONB数组)")

    # v4.22.0新增:字段级解析规则(用于metric_date等严格解析)
    field_parse_rules = Column(JSONB, nullable=True, comment="字段解析规则(JSONB数组)")
    
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    notes = Column(Text, nullable=True)

    __table_args__ = (
        # v4.5.1更新:新增sub_domain到复合索引
        Index("ix_template_dimension_v2", "platform", "data_domain", "sub_domain", "granularity", "account"),
        Index("ix_template_status", "status", "platform"),
        # v4.5.1新增:header_row范围CHECK约束(企业级数据治理标准)
        CheckConstraint('header_row >= 0 AND header_row <= 100', name='ck_template_header_row_range'),
        {"schema": "core"},
    )

class FieldMappingTemplateFamily(Base):
    """逻辑模板族。"""
    __tablename__ = "field_mapping_template_families"

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(32), nullable=False)
    data_domain = Column(String(64), nullable=False)
    granularity = Column(String(32), nullable=True)
    account = Column(String(128), nullable=True)
    sub_domain = Column(String(64), nullable=True)
    governance_status = Column(String(32), nullable=False, server_default=text("'ready'"))
    display_name = Column(String(256), nullable=True)
    active_version_id = Column(Integer, nullable=True)
    source_mode = Column(String(32), nullable=False, server_default=text("'legacy_projection'"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "data_domain",
            "sub_domain",
            "granularity",
            "account",
            name="uq_template_family_dimension",
        ),
        Index(
            "ix_template_family_dimension",
            "platform",
            "data_domain",
            "sub_domain",
            "granularity",
            "account",
        ),
        {"schema": "core"},
    )


class FieldMappingTemplateVersion(Base):
    """模板族下的不可变版本。"""
    __tablename__ = "field_mapping_template_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    family_id = Column(Integer, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, server_default=text("'active'"))
    template_name = Column(String(256), nullable=True)
    deduplication_fields = Column(JSONB, nullable=True)
    header_bindings = Column(JSONB, nullable=True)
    notes = Column(Text, nullable=True)
    legacy_template_ids = Column(JSONB, nullable=True)
    created_by = Column(String(64), default="system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("family_id", "version_no", name="uq_template_version_family_version_no"),
        Index("ix_template_version_family_status", "family_id", "status"),
        {"schema": "core"},
    )


class FieldMappingTemplateVariant(Base):
    """模板版本下的文件格式变体。"""
    __tablename__ = "field_mapping_template_variants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    template_version_id = Column(Integer, nullable=False)
    variant_key = Column(String(128), nullable=False)
    match_priority = Column(Integer, nullable=False, default=100)
    header_row = Column(Integer, default=0, nullable=False)
    sheet_name_pattern = Column(String(128), nullable=True)
    required_headers = Column(JSONB, nullable=True)
    parse_profile = Column(JSONB, nullable=True)
    field_parse_rules = Column(JSONB, nullable=True)
    source_legacy_template_id = Column(Integer, nullable=True)
    template_name = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "template_version_id",
            "variant_key",
            name="uq_template_variant_version_key",
        ),
        Index("ix_template_variant_version_priority", "template_version_id", "match_priority"),
        Index("ix_template_variant_source_legacy_id", "source_legacy_template_id"),
        CheckConstraint('header_row >= 0 AND header_row <= 100', name='ck_template_variant_header_row_range'),
        {"schema": "core"},
    )


class FieldMappingTemplateItem(Base):
    """
    字段映射模板明细表
    
    [WARN] v4.6.0 DSS架构重构:已废弃
    - 已被FieldMappingTemplate.header_columns JSONB字段替代
    - 表结构保留用于兼容性,但不再使用
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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_template_item_template", "template_id"),
        UniqueConstraint("template_id", "original_column", name="uq_template_original_column"),
        {"schema": "core"},
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
    operated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(256), nullable=True)

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_operator", "operator", "operated_at"),
        {"schema": "core"},
    )


# -------------------- Finance Domain Tables (v4.4.0 - Modern ERP) --------------------

class FieldUsageTracking(Base):
    """
    字段使用追踪表(v4.7.0新增)
    
    用于追踪数据库字段在API和前端的使用情况,支持数据治理和元数据管理。
    """
    __tablename__ = "field_usage_tracking"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # 字段标识(允许NULL:前端组件可能只知道API端点,不知道表/字段)
    table_name = Column(String(64), nullable=True, index=True, comment="数据库表名")
    field_name = Column(String(128), nullable=True, index=True, comment="数据库字段名")
    
    # API端点追踪
    api_endpoint = Column(String(256), nullable=True, comment="API端点(如/api/products/products)")
    api_param = Column(String(64), nullable=True, comment="API参数名(如keyword)")
    api_file = Column(String(256), nullable=True, comment="API路由文件路径")
    
    # 前端组件追踪
    frontend_component = Column(String(256), nullable=True, comment="前端组件(如ProductManagement.vue)")
    frontend_param = Column(String(128), nullable=True, comment="前端参数(如filters.keyword)")
    frontend_file = Column(String(256), nullable=True, comment="前端组件文件路径")
    
    # 使用方式
    usage_type = Column(String(32), nullable=False, comment="使用类型:query/filter/sort/return")
    source_type = Column(String(32), default="scanned", nullable=False, comment="来源类型:scanned/manual")
    
    # 代码上下文(可选)
    code_snippet = Column(Text, nullable=True, comment="代码片段(用于定位)")
    line_number = Column(Integer, nullable=True, comment="行号")
    
    # 审计
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(64), default="scanner", nullable=False)
    
    __table_args__ = (
        Index("idx_usage_field", "table_name", "field_name"),
        Index("idx_usage_api", "api_endpoint"),
        Index("idx_usage_frontend", "frontend_component"),
        Index("idx_usage_type", "usage_type"),
        UniqueConstraint("table_name", "field_name", "api_endpoint", "frontend_component", name="uq_field_usage"),
        {"schema": "core"},
    )


# -------------------- Sales Campaign & Target Management (v4.11.0) --------------------

class SyncProgressTask(Base):
    """
    数据同步进度任务表
    
    v4.12.0新增:
    - 用于持久化存储数据同步任务的进度信息
    - 支持服务重启后恢复进度
    - 替代内存存储的ProgressTracker(用于数据同步场景)
    """
    __tablename__ = "sync_progress_tasks"
    
    task_id = Column(String(100), primary_key=True, index=True, comment="任务ID")
    
    # 任务基本信息
    task_type = Column(String(50), nullable=False, default="bulk_ingest", comment="任务类型:bulk_ingest/single_file")
    total_files = Column(Integer, default=0, nullable=False, comment="总文件数")
    processed_files = Column(Integer, default=0, nullable=False, comment="已处理文件数")
    current_file = Column(String(500), nullable=True, comment="当前处理文件")
    
    # 任务状态
    status = Column(String(20), default="pending", nullable=False, index=True, comment="状态:pending/processing/completed/failed")
    
    # 数据统计
    total_rows = Column(Integer, default=0, nullable=False, comment="总行数")
    processed_rows = Column(Integer, default=0, nullable=False, comment="已处理行数")
    valid_rows = Column(Integer, default=0, nullable=False, comment="有效行数")
    error_rows = Column(Integer, default=0, nullable=False, comment="错误行数")
    quarantined_rows = Column(Integer, default=0, nullable=False, comment="隔离行数")
    
    # 进度百分比(计算字段,冗余存储便于查询)
    file_progress = Column(Float, default=0.0, nullable=False, comment="文件进度百分比")
    row_progress = Column(Float, default=0.0, nullable=False, comment="行进度百分比")
    
    # 时间戳
    start_time = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True, comment="开始时间")
    end_time = Column(DateTime(timezone=True), nullable=True, comment="结束时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    
    # 错误和警告(JSON格式)
    errors = Column(JSON, nullable=True, comment="错误列表")
    warnings = Column(JSON, nullable=True, comment="警告列表")
    
    # 任务详情(JSON格式,存储额外信息)
    task_details = Column(JSON, nullable=True, comment="任务详情")
    
    __table_args__ = (
        Index("ix_sync_progress_status", "status", "start_time"),
        Index("ix_sync_progress_updated", "updated_at"),
        CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name="chk_sync_progress_status"),
        {"schema": "core"},
    )


# -------------------- DSS Architecture Tables (v4.6.0+) --------------------

# B-Class Data Tables (按平台-数据域-子类型-粒度分表,动态创建)
# [WARN] v4.17.0+ 架构调整:旧的固定表类已删除,所有B类数据表通过PlatformTableManager动态创建
# 表名格式:fact_{platform}_{data_domain}_{sub_domain}_{granularity}
# 所有表创建在b_class schema中

# 以下旧的固定表类定义已删除(v4.17.0+):
# - FactRawDataOrdersDaily, FactRawDataOrdersWeekly, FactRawDataOrdersMonthly
# - FactRawDataProductsDaily, FactRawDataProductsWeekly, FactRawDataProductsMonthly
# - FactRawDataTrafficDaily, FactRawDataTrafficWeekly, FactRawDataTrafficMonthly
# - FactRawDataAnalyticsDaily, FactRawDataAnalyticsWeekly, FactRawDataAnalyticsMonthly
# - FactRawDataServicesDaily, FactRawDataServicesWeekly, FactRawDataServicesMonthly
# - FactRawDataServicesAiAssistantDaily, FactRawDataServicesAiAssistantWeekly, FactRawDataServicesAiAssistantMonthly
# - FactRawDataServicesAgentWeekly, FactRawDataServicesAgentMonthly
# - FactRawDataInventorySnapshot
# 
# 所有B类数据表现在通过PlatformTableManager动态创建,表名格式:
# - 无sub_domain:fact_{platform}_{data_domain}_{granularity}(如fact_shopee_orders_daily)
# - 有sub_domain:fact_{platform}_{data_domain}_{sub_domain}_{granularity}(如fact_shopee_services_ai_assistant_monthly)
# 所有表创建在b_class schema中

# 所有旧的固定表类定义已删除(v4.17.0+)
# 所有B类数据表通过PlatformTableManager动态创建


# 统一对齐表(替代dim_shops和account_aliases)

class EntityAlias(Base):
    """
    统一实体别名表(v4.6.0+)
    
    替代dim_shops和account_aliases两张表,统一管理所有账号和店铺的别名映射
    """
    __tablename__ = "entity_aliases"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 源标识(from)
    source_platform = Column(String(32), nullable=False, index=True)
    source_type = Column(String(32), nullable=False, index=True)  # 'account' | 'shop' | 'store'
    source_name = Column(String(256), nullable=False, index=True)
    source_account = Column(String(128), nullable=True)
    source_site = Column(String(64), nullable=True)
    data_domain = Column(String(64), nullable=True)
    
    # 目标标识(to)
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("source_platform", "source_type", "source_name", "source_account", "source_site", name="uq_entity_alias_source"),
        Index("ix_entity_aliases_source", "source_platform", "source_type", "source_name"),
        Index("ix_entity_aliases_target", "target_type", "target_id", "active"),
        {"schema": "b_class"},
    )


# 以下所有旧的固定表类定义已删除(v4.17.0+)
# 所有B类数据表通过PlatformTableManager动态创建
# 表名格式:fact_{platform}_{data_domain}_{sub_domain}_{granularity}
# 所有表创建在b_class schema中

# 统一对齐表(替代dim_shops和account_aliases)


# Staging表(临时表,用于数据清洗)

class StagingRawData(Base):
    """
    Staging原始数据表(ETL中间层)
    
    存储原始数据(JSONB格式),用于数据清洗和验证
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index("ix_staging_raw_data_file", "file_id", "status"),
        Index("ix_staging_raw_data_domain_gran", "data_domain", "granularity"),
        {"schema": "b_class"},
    )


# A类数据表(使用中文字段名)

# A类数据表(使用中文字段名)
# 注意:中文字段名将在Alembic迁移脚本中使用text()函数实现
# 这里先使用英文字段名定义表结构,迁移脚本中会重命名为中文
