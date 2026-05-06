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

class Account(Base):
    """账号管理表"""
    __tablename__ = "accounts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False)
    account_name = Column(String(100), nullable=False)
    account_id = Column(String(100), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_accounts_account_id"),
        Index("ix_accounts_platform", "platform"),
        Index("ix_accounts_status", "status"),
        {"schema": "core"},
    )

class PlatformAccount(Base):
    """
    平台账号管理表 (v4.7.0)
    
    替代手动编辑 local_accounts.py,提供前端GUI管理
    支持:
    - 多平台账号统一管理
    - 店铺级别配置(一个主账号多个店铺)
    - 密码加密存储
    - 能力配置(capabilities)
    
    表位于 core schema(core.platform_accounts),与 search_path 中 public 优先时
    须显式指定 schema 以免查到 public 下空表导致账号列表为空。
    """
    __tablename__ = "platform_accounts"
    __table_args__ = (
        Index("ix_platform_accounts_platform", "platform"),
        Index("ix_platform_accounts_parent", "parent_account"),
        Index("ix_platform_accounts_enabled", "enabled"),
        Index("ix_platform_accounts_shop_type", "shop_type"),
        Index("ix_platform_accounts_shop_id", "shop_id"),  # [*] v4.18.1新增
        Index("ix_platform_accounts_platform_store_name", "platform", "store_name"),  # Orders 模型店铺别称→shop_id JOIN
        Index("ix_platform_accounts_platform_account_alias", "platform", "account_alias"),  # Orders 模型店铺别称→shop_id JOIN
        {"schema": "core"},
    )
    
    # 主键和唯一标识
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(100), unique=True, nullable=False, comment="账号唯一标识")
    
    # 账号基本信息
    parent_account = Column(String(100), nullable=True, comment="主账号(多店铺共用时填写)")
    platform = Column(String(50), nullable=False, comment="平台代码: shopee/tiktok/miaoshou/amazon")
    account_alias = Column(String(200), nullable=True, comment="账号别名(用于关联导出数据中的自定义名称,如miaoshou ERP的订单数据)")
    store_name = Column(String(200), nullable=False, comment="店铺名称")
    
    # 店铺信息
    shop_type = Column(String(50), nullable=True, comment="店铺类型: local/global")
    shop_region = Column(String(50), nullable=True, comment="店铺区域: SG/MY/GLOBAL等")
    shop_id = Column(String(256), nullable=True, comment="店铺ID(用于关联数据同步中的shop_id,可编辑)")  # [*] v4.18.1新增
    
    # 登录信息(敏感)
    username = Column(String(200), nullable=False, comment="登录用户名")
    password_encrypted = Column(Text, nullable=False, comment="加密后的密码")
    login_url = Column(Text, nullable=True, comment="登录URL")
    
    # 联系信息
    email = Column(String(200), nullable=True, comment="邮箱")
    phone = Column(String(50), nullable=True, comment="手机号")
    region = Column(String(50), default="CN", comment="账号注册地区")
    currency = Column(String(10), default="CNY", comment="主货币")
    
    # 能力配置(JSONB)
    capabilities = Column(
        JSON_COMPAT,
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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="创建时间")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False, comment="更新时间")
    created_by = Column(String(100), nullable=True, comment="创建人")
    updated_by = Column(String(100), nullable=True, comment="更新人")
    
    # 扩展字段
    extra_config = Column(JSONB, nullable=True, default={}, comment="扩展配置")

class MainAccount(Base):
    """Canonical login owner for shared persistent collection sessions."""

    __tablename__ = "main_accounts"

    __table_args__ = (
        Index("ix_main_accounts_platform", "platform"),
        Index("ix_main_accounts_enabled", "enabled"),
        {"schema": "core"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False, comment="平台代码")
    main_account_id = Column(String(100), unique=True, nullable=False, comment="主账号ID")
    main_account_name = Column(String(200), nullable=True, comment="主账号名称")
    username = Column(String(200), nullable=False, comment="登录用户名")
    password_encrypted = Column(Text, nullable=False, comment="加密后的密码")
    login_url = Column(Text, nullable=True, comment="登录URL")
    enabled = Column(Boolean, default=True, nullable=False, comment="是否启用")
    notes = Column(Text, nullable=True, comment="备注")
    extra_config = Column(JSON_COMPAT, nullable=True, default={}, comment="扩展配置")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)

class ShopAccount(Base):
    """Shop-level collection target bound to a main login account."""

    __tablename__ = "shop_accounts"

    __table_args__ = (
        UniqueConstraint("platform", "platform_shop_id", name="uq_shop_accounts_platform_shop_id"),
        Index("ix_shop_accounts_main_account_id", "main_account_id"),
        Index("ix_shop_accounts_platform_shop_id", "platform_shop_id"),
        Index("ix_shop_accounts_enabled", "enabled"),
        {"schema": "core"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False, comment="平台代码")
    shop_account_id = Column(String(100), unique=True, nullable=False, comment="店铺账号ID")
    main_account_id = Column(
        String(100),
        ForeignKey("core.main_accounts.main_account_id", ondelete="CASCADE"),
        nullable=False,
        comment="归属主账号ID",
    )
    store_name = Column(String(200), nullable=False, comment="店铺名称")
    platform_shop_id = Column(String(256), nullable=True, comment="平台店铺ID")
    platform_shop_id_status = Column(
        String(32),
        nullable=False,
        default="missing",
        server_default=text("'missing'"),
        comment="平台店铺ID状态",
    )
    shop_region = Column(String(50), nullable=True, comment="店铺区域")
    shop_type = Column(String(50), nullable=True, comment="店铺类型")
    enabled = Column(Boolean, default=True, nullable=False, comment="是否启用")
    notes = Column(Text, nullable=True, comment="备注")
    extra_config = Column(JSON_COMPAT, nullable=True, default={}, comment="扩展配置")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)

class ShopAccountAlias(Base):
    """Alias mapping from raw shop labels to canonical shop accounts."""

    __tablename__ = "shop_account_aliases"

    __table_args__ = (
        UniqueConstraint("platform", "alias_normalized", "is_active", name="uq_shop_account_aliases_active_alias"),
        Index("ix_shop_account_aliases_shop_account_id", "shop_account_id"),
        Index("ix_shop_account_aliases_platform_alias_normalized", "platform", "alias_normalized"),
        {"schema": "core"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_account_id = Column(
        Integer,
        ForeignKey("core.shop_accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="归属店铺账号",
    )
    platform = Column(String(50), nullable=False, comment="平台代码")
    alias_value = Column(String(256), nullable=False, comment="别名原值")
    alias_normalized = Column(String(256), nullable=False, comment="标准化别名")
    alias_type = Column(String(32), nullable=True, comment="别名类型")
    source = Column(String(64), nullable=True, comment="来源")
    is_primary = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class ShopAccountCapability(Base):
    """Final enabled data domains for a shop account."""

    __tablename__ = "shop_account_capabilities"

    __table_args__ = (
        UniqueConstraint("shop_account_id", "data_domain", name="uq_shop_account_capabilities_domain"),
        Index("ix_shop_account_capabilities_shop_account_id", "shop_account_id"),
        {"schema": "core"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    shop_account_id = Column(
        Integer,
        ForeignKey("core.shop_accounts.id", ondelete="CASCADE"),
        nullable=False,
        comment="归属店铺账号",
    )
    data_domain = Column(String(64), nullable=False, comment="数据域")
    enabled = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class PlatformShopDiscovery(Base):
    """Auto-discovered platform shop identifiers awaiting confirmation or binding."""

    __tablename__ = "platform_shop_discoveries"

    __table_args__ = (
        Index("ix_platform_shop_discoveries_main_account_id", "main_account_id"),
        Index("ix_platform_shop_discoveries_status", "status"),
        {"schema": "core"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(50), nullable=False, comment="平台代码")
    main_account_id = Column(
        String(100),
        ForeignKey("core.main_accounts.main_account_id", ondelete="CASCADE"),
        nullable=False,
        comment="归属主账号ID",
    )
    detected_store_name = Column(String(256), nullable=True, comment="识别到的店铺名")
    detected_platform_shop_id = Column(String(256), nullable=True, comment="识别到的平台店铺ID")
    detected_region = Column(String(50), nullable=True, comment="识别到的区域")
    candidate_shop_account_ids = Column(JSON_COMPAT, nullable=True, default=list, comment="候选店铺账号ID列表")
    status = Column(
        String(32),
        nullable=False,
        default="detected_failed",
        server_default=text("'detected_failed'"),
        comment="发现状态",
    )
    raw_payload = Column(JSON_COMPAT, nullable=True, default=dict, comment="原始识别载荷")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
