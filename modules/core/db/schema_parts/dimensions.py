from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base

class DimPlatform(Base):
    __tablename__ = "dim_platforms"

    platform_code = Column(String(32), primary_key=True)  # e.g., 'shopee','miaoshou','tiktok'
    name = Column(String(64), nullable=False)             # display name
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("name", name="uq_dim_platforms_name"),
        {"schema": "core"},
    )


class DimShop(Base):
    __tablename__ = "dim_shops"

    platform_code = Column(String(32), ForeignKey("core.dim_platforms.platform_code", ondelete="CASCADE"), primary_key=True)
    shop_id = Column(String(256), primary_key=True)  # v4.3.4: 扩展到256以支持长shop_id

    shop_slug = Column(String(128), nullable=True)  # human readable
    shop_name = Column(String(256), nullable=True)
    region = Column(String(16), nullable=True)
    currency = Column(String(8), nullable=True)
    timezone = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

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

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_dim_products_platform_shop", "platform_code", "shop_id"),
        {"schema": "core"},
    )

# ---- Master SKU mapping & bridge (统一SKU映射) ----
class DimProductMaster(Base):
    __tablename__ = "dim_product_master"

    product_id = Column(Integer, primary_key=True, autoincrement=True)
    # 公司侧统一SKU/款号,可作为对外展示与聚合主键
    company_sku = Column(String(128), unique=True, nullable=False)

    product_title = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        {"schema": "core"},
    )


class BridgeProductKeys(Base):
    __tablename__ = "bridge_product_keys"

    product_id = Column(Integer, ForeignKey("core.dim_product_master.product_id", ondelete="CASCADE"), primary_key=True)
    platform_code = Column(String(32), primary_key=True)
    shop_id = Column(String(64), primary_key=True)
    platform_sku = Column(String(128), primary_key=True)

    __table_args__ = (
        # 关联至平台侧产品维表,复合外键
        ForeignKeyConstraint(
            ["platform_code", "shop_id", "platform_sku"],
            ["core.dim_products.platform_code", "core.dim_products.shop_id", "core.dim_products.platform_sku"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("platform_code", "shop_id", "platform_sku", name="uq_bridge_platform_sku"),
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
    to_currency = Column(String(3), nullable=False, index=True)    # CNY(默认)
    rate_date = Column(Date, nullable=False, index=True)           # 汇率日期
    
    # 汇率值
    rate = Column(Float, nullable=False)  # 汇率(精度6位小数)
    
    # 数据源信息
    source = Column(String(50), nullable=True)  # open_exchange_rates/ecb/boc
    priority = Column(Integer, default=99)      # 数据源优先级(1-99)
    
    # 审计字段
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    __table_args__ = (
        UniqueConstraint('from_currency', 'to_currency', 'rate_date', name='uq_exchange_rate'),
        Index('ix_exchange_rate_lookup', 'from_currency', 'to_currency', 'rate_date'),
        Index('ix_exchange_rate_date', 'rate_date'),
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
    data_domain = Column(String(64), nullable=False, default='orders')  # 仅orders需要对齐
    account = Column(String(128), nullable=True)  # 采购账号(如"虾皮巴西_东朗照明主体")
    site = Column(String(64), nullable=True)  # 站点(如"菲律宾")
    store_label_raw = Column(String(256), nullable=False)  # 原始店铺名(如"菲律宾1店")
    
    # 目标标识(to)
    target_type = Column(String(32), nullable=False, default='account')  # 'account' | 'shop'
    target_id = Column(String(128), nullable=False)  # 标准账号ID或店铺ID
    
    # 元数据
    confidence = Column(Float, default=1.0)  # 映射置信度(人工=1.0,自动建议<1.0)
    active = Column(Boolean, default=True)  # 是否生效
    notes = Column(Text, nullable=True)  # 备注
    
    # 审计
    created_by = Column(String(64), default='system')
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        # 唯一约束:同一source组合只能映射到一个target
        Index(
            'uq_account_alias_source',
            'platform', 'data_domain', 'account', 'site', 'store_label_raw',
            unique=True
        ),
        # 查询索引
        Index('ix_account_alias_platform_domain', 'platform', 'data_domain'),
        Index('ix_account_alias_target', 'target_id', 'active'),
        {"schema": "core"},
    )


class DimCurrencyRate(Base):
    __tablename__ = "dim_currency_rates"

    rate_date = Column(Date, primary_key=True)  # UTC date of rate
    base_currency = Column(String(8), primary_key=True)   # e.g., USD
    quote_currency = Column(String(8), primary_key=True)  # e.g., CNY

    rate = Column(Float, nullable=False)
    source = Column(String(64), nullable=True, default="exchangerate.host")
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_currency_base_quote", "base_currency", "quote_currency"),
        {"schema": "core"},
    )


# -------------------- Fact Tables --------------------

# [DELETED] v4.19.0: FactOrder 和 FactOrderItem 已删除
# - 已被 b_class.fact_{platform}_orders_{granularity} 表替代(DSS架构)
# - 所有订单数据现在存储在 b_class schema 下的按平台分表中
