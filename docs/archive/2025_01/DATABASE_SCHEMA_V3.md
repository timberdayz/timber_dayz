# 数据库Schema设计文档 v3.0

**创建日期**: 2025-10-16  
**Schema版本**: v3.0  
**数据库**: SQLite（开发）/ PostgreSQL（生产）  
**ORM**: SQLAlchemy  
**迁移工具**: Alembic  

---

## 🎯 设计概述

本数据库采用**星型模型（Star Schema）**设计，包含：
- **维度表（Dimension Tables）**: 平台、店铺、产品、汇率
- **事实表（Fact Tables）**: 订单、订单明细、产品指标
- **管理表（Management Tables）**: 文件清单、隔离数据

### 设计原则
- ✅ 主键策略：复合主键保证唯一性
- ✅ 幂等性：支持重复导入不产生重复数据
- ✅ 原币+RMB：保留原始货币和人民币归一化金额
- ✅ 时间戳：所有表包含created_at和updated_at

---

## 📊 ER图概览

```
┌─────────────────┐
│  DimPlatform    │
│  (平台维度表)    │
└────────┬────────┘
         │1
         │
         │*
┌────────▼────────┐
│    DimShop      │
│  (店铺维度表)    │
└─────────────────┘


┌─────────────────┐         ┌─────────────────┐
│  DimProduct     │         │ FactOrder       │
│  (产品维度表)    │         │ (订单事实表)     │
└────────┬────────┘         └────────┬────────┘
         │*                          │1
         │                           │
         │                           │*
┌────────▼────────┐         ┌────────▼─────────┐
│FactProductMetric│         │ FactOrderItem    │
│ (产品指标表)     │         │ (订单明细表)      │
└─────────────────┘         └──────────────────┘


┌─────────────────┐         ┌──────────────────┐
│ DimCurrencyRate │         │  CatalogFile     │
│   (汇率表)       │         │  (文件清单表)     │
└─────────────────┘         └──────────────────┘
```

---

## 📋 表结构详细说明

### 1. 维度表（Dimension Tables）

#### 1.1 dim_platforms（平台维度表）

**用途**: 存储支持的电商平台信息

**表结构**:
```sql
CREATE TABLE dim_platforms (
    platform_code VARCHAR(32) PRIMARY KEY,  -- 平台代码（shopee/miaoshou/tiktok）
    name VARCHAR(64) NOT NULL,              -- 显示名称（Shopee/妙手ERP/TikTok）
    is_active BOOLEAN DEFAULT TRUE,         -- 是否启用
    created_at TIMESTAMP NOT NULL,          -- 创建时间
    updated_at TIMESTAMP NOT NULL,          -- 更新时间
    
    UNIQUE(name)                            -- 显示名称唯一
);
```

**示例数据**:
| platform_code | name | is_active |
|---------------|------|-----------|
| shopee | Shopee | true |
| miaoshou | 妙手ERP | true |
| tiktok | TikTok Shop | true |

---

#### 1.2 dim_shops（店铺维度表）

**用途**: 存储店铺信息

**表结构**:
```sql
CREATE TABLE dim_shops (
    platform_code VARCHAR(32) NOT NULL,     -- 平台代码（外键）
    shop_id VARCHAR(64) NOT NULL,           -- 平台店铺ID
    
    shop_slug VARCHAR(128),                 -- 店铺slug（友好名称）
    shop_name VARCHAR(256),                 -- 店铺名称
    region VARCHAR(16),                     -- 地区（SG/MY/TH等）
    currency VARCHAR(8),                    -- 货币（SGD/MYR等）
    timezone VARCHAR(64),                   -- 时区
    
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (platform_code, shop_id),
    FOREIGN KEY (platform_code) REFERENCES dim_platforms(platform_code) ON DELETE CASCADE,
    
    INDEX ix_dim_shops_platform_shop (platform_code, shop_id),
    INDEX ix_dim_shops_platform_slug (platform_code, shop_slug)
);
```

**示例数据**:
| platform_code | shop_id | shop_slug | shop_name | region | currency |
|---------------|---------|-----------|-----------|--------|----------|
| shopee | 1407964586 | clicks.sg | 新加坡3C店 | SG | SGD |
| tiktok | 7123456789 | tiktok-shop-2 | TikTok 2店 | SG | SGD |

---

#### 1.3 dim_products（产品维度表）

**用途**: 存储产品基本信息（慢变维度）

**表结构**:
```sql
CREATE TABLE dim_products (
    platform_code VARCHAR(32) NOT NULL,     -- 平台代码
    shop_id VARCHAR(64) NOT NULL,           -- 店铺ID
    platform_sku VARCHAR(128) NOT NULL,     -- 平台SKU
    
    product_title VARCHAR(512),             -- 产品标题
    category VARCHAR(128),                  -- 产品类别
    status VARCHAR(32),                     -- 状态（active/disabled）
    
    image_url VARCHAR(1024),                -- 产品图片URL
    image_path VARCHAR(512),                -- 本地图片路径
    image_last_fetched_at TIMESTAMP,        -- 图片最后抓取时间
    
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (platform_code, shop_id, platform_sku),
    
    INDEX ix_dim_products_platform_shop (platform_code, shop_id)
);
```

---

#### 1.4 dim_currency_rates（汇率表）

**用途**: 存储每日汇率数据

**表结构**:
```sql
CREATE TABLE dim_currency_rates (
    rate_date DATE NOT NULL,                -- 汇率日期
    base_currency VARCHAR(8) NOT NULL,      -- 基础货币（USD）
    quote_currency VARCHAR(8) NOT NULL,     -- 目标货币（CNY）
    
    rate FLOAT NOT NULL,                    -- 汇率
    source VARCHAR(64) DEFAULT 'exchangerate.host',  -- 数据源
    fetched_at TIMESTAMP NOT NULL,          -- 获取时间
    
    PRIMARY KEY (rate_date, base_currency, quote_currency),
    
    INDEX ix_currency_base_quote (base_currency, quote_currency)
);
```

**示例数据**:
| rate_date | base_currency | quote_currency | rate | source |
|-----------|---------------|----------------|------|--------|
| 2024-01-01 | USD | CNY | 7.1234 | exchangerate.host |
| 2024-01-01 | SGD | CNY | 5.3456 | exchangerate.host |

---

### 2. 事实表（Fact Tables）

#### 2.1 fact_orders（订单事实表）

**用途**: 存储订单级别的数据

**主键**: (platform_code, shop_id, order_id)

**表结构**:
```sql
CREATE TABLE fact_orders (
    -- 主键
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(128) NOT NULL,
    
    -- 时间维度
    order_time_utc TIMESTAMP,               -- 订单时间（UTC）
    order_date_local DATE,                  -- 订单日期（店铺时区）
    
    -- 金额信息（原币）
    currency VARCHAR(8),                    -- 货币代码
    subtotal FLOAT DEFAULT 0.0,             -- 小计
    shipping_fee FLOAT DEFAULT 0.0,         -- 运费
    tax_amount FLOAT DEFAULT 0.0,           -- 税费
    discount_amount FLOAT DEFAULT 0.0,      -- 折扣
    total_amount FLOAT DEFAULT 0.0,         -- 总金额
    
    -- 金额信息（人民币）
    subtotal_rmb FLOAT DEFAULT 0.0,
    shipping_fee_rmb FLOAT DEFAULT 0.0,
    tax_amount_rmb FLOAT DEFAULT 0.0,
    discount_amount_rmb FLOAT DEFAULT 0.0,
    total_amount_rmb FLOAT DEFAULT 0.0,
    
    -- 支付信息
    payment_method VARCHAR(64),             -- 支付方式
    payment_status VARCHAR(32) DEFAULT 'pending',
    
    -- 状态信息
    order_status VARCHAR(32) DEFAULT 'pending',
    shipping_status VARCHAR(32) DEFAULT 'pending',
    delivery_status VARCHAR(32) DEFAULT 'pending',
    is_cancelled BOOLEAN DEFAULT FALSE,
    is_refunded BOOLEAN DEFAULT FALSE,
    refund_amount FLOAT DEFAULT 0.0,
    refund_amount_rmb FLOAT DEFAULT 0.0,
    
    -- 买家信息
    buyer_id VARCHAR(128),
    buyer_name VARCHAR(256),
    
    -- 元数据
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (platform_code, shop_id, order_id),
    
    INDEX ix_fact_orders_plat_shop_date (platform_code, shop_id, order_date_local),
    INDEX ix_fact_orders_status (platform_code, shop_id, order_status)
);
```

**示例数据**:
| platform_code | shop_id | order_id | order_date_local | total_amount | currency | total_amount_rmb |
|---------------|---------|----------|------------------|--------------|----------|------------------|
| shopee | 1407964586 | ORDER001 | 2024-01-15 | 100.00 | SGD | 534.56 |

---

#### 2.2 fact_order_items（订单明细表）

**用途**: 存储订单的商品明细（一个订单多个商品）

**主键**: (platform_code, shop_id, order_id, platform_sku)

**表结构**:
```sql
CREATE TABLE fact_order_items (
    -- 主键
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(128) NOT NULL,
    platform_sku VARCHAR(128) NOT NULL,
    
    -- 产品信息
    product_title VARCHAR(512),             -- 产品标题
    quantity INTEGER DEFAULT 1,             -- 数量
    
    -- 金额信息
    currency VARCHAR(8),
    unit_price FLOAT DEFAULT 0.0,           -- 单价
    unit_price_rmb FLOAT DEFAULT 0.0,
    line_amount FLOAT DEFAULT 0.0,          -- 行金额
    line_amount_rmb FLOAT DEFAULT 0.0,
    
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (platform_code, shop_id, order_id, platform_sku),
    
    INDEX ix_fact_items_plat_shop_order (platform_code, shop_id, order_id),
    INDEX ix_fact_items_plat_shop_sku (platform_code, shop_id, platform_sku)
);
```

---

#### 2.3 fact_product_metrics（产品指标表）

**用途**: 存储产品的各种指标数据（点击量、销量、GMV等）

**主键**: (platform_code, shop_id, platform_sku, metric_date, metric_type)

**表结构**:
```sql
CREATE TABLE fact_product_metrics (
    -- 主键
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    platform_sku VARCHAR(128) NOT NULL,
    metric_date DATE NOT NULL,              -- 指标日期
    metric_type VARCHAR(64) NOT NULL,       -- 指标类型
    
    -- 指标数据
    granularity VARCHAR(16) DEFAULT 'daily' NOT NULL,  -- 粒度（daily/weekly/monthly）
    metric_value FLOAT DEFAULT 0.0,         -- 指标值
    
    currency VARCHAR(8),                    -- 货币（如果是金额类指标）
    metric_value_rmb FLOAT DEFAULT 0.0,     -- 人民币值
    
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    
    PRIMARY KEY (platform_code, shop_id, platform_sku, metric_date, metric_type),
    
    INDEX ix_metrics_plat_shop_date_gran (platform_code, shop_id, metric_date, granularity),
    INDEX ix_metrics_plat_shop_type (platform_code, shop_id, metric_type)
);
```

**常见metric_type**:
- clicks: 点击量
- views: 浏览量
- orders: 订单数
- units_sold: 销售件数
- gmv: 成交金额（Gross Merchandise Value）
- conversion_rate: 转化率

---

### 3. 管理表（Management Tables）

#### 3.1 catalog_files（文件清单表）

**用途**: 作为ETL的**权威清单**，记录所有处理过的文件

**主键**: id（自增）  
**唯一约束**: file_hash（避免重复处理同一文件）

**表结构**:
```sql
CREATE TABLE catalog_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- 文件标识
    file_path VARCHAR(1024) NOT NULL,       -- 文件完整路径
    file_name VARCHAR(255) NOT NULL,        -- 文件名
    source VARCHAR(64) DEFAULT 'temp/outputs',  -- 来源目录
    
    file_size INTEGER,                      -- 文件大小（字节）
    file_hash VARCHAR(64) UNIQUE,           -- 文件hash（用于去重）
    
    -- 元数据（从路径或旁文件提取）
    platform_code VARCHAR(32),              -- 平台代码
    shop_id VARCHAR(64),                    -- 店铺ID
    data_domain VARCHAR(64),                -- 数据域（orders/products/metrics）
    granularity VARCHAR(16),                -- 粒度（daily/weekly/monthly）
    date_from DATE,                         -- 数据起始日期
    date_to DATE,                           -- 数据结束日期
    
    file_metadata JSON,                     -- 其他元数据（JSON格式）
    
    -- 处理状态
    status VARCHAR(32) DEFAULT 'pending',   -- pending/ingested/failed
    error_message TEXT,                     -- 错误信息
    
    -- 时间戳
    first_seen_at TIMESTAMP NOT NULL,       -- 首次发现时间
    last_processed_at TIMESTAMP,            -- 最后处理时间
    
    INDEX ix_catalog_files_status (status),
    INDEX ix_catalog_files_platform_shop (platform_code, shop_id),
    INDEX ix_catalog_files_dates (date_from, date_to)
);
```

**状态说明**:
- pending: 待处理
- ingested: 已入库
- failed: 处理失败

**示例数据**:
| id | file_name | platform_code | data_domain | status | first_seen_at |
|----|-----------|---------------|-------------|--------|---------------|
| 1 | orders_20240115.xlsx | shopee | orders | ingested | 2024-01-15 10:00:00 |
| 2 | products_20240115.xlsx | shopee | products | pending | 2024-01-15 10:05:00 |

---

#### 3.2 data_quarantine（隔离数据表）❌需要添加

**用途**: 隔离处理失败的数据行，便于排查问题

**表结构**:
```sql
CREATE TABLE data_quarantine (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    source_file VARCHAR(500) NOT NULL,      -- 来源文件
    row_number INTEGER,                     -- 行号
    row_data TEXT NOT NULL,                 -- 行数据（JSON格式）
    
    error_type VARCHAR(100) NOT NULL,       -- 错误类型
    error_msg TEXT,                         -- 错误详细信息
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX ix_quarantine_file (source_file),
    INDEX ix_quarantine_error_type (error_type),
    INDEX ix_quarantine_created (created_at)
);
```

**示例数据**:
| id | source_file | error_type | error_msg | created_at |
|----|-------------|------------|-----------|------------|
| 1 | orders.xlsx | ValueError | 订单金额为负数 | 2024-01-15 10:10:00 |

---

## 🔑 主键策略

### 订单（Orders）
```python
主键: (platform_code, shop_id, order_id)

理由: 
- 同一平台、同一店铺下，订单ID唯一
- 支持多平台、多店铺
- 保证幂等性（重复导入不会创建重复数据）
```

### 产品（Products）
```python
主键: (platform_code, shop_id, platform_sku)

理由:
- 同一平台、同一店铺下，SKU唯一
- 不同平台可能有相同SKU，需要区分
```

### 产品指标（Product Metrics）
```python
主键: (platform_code, shop_id, platform_sku, metric_date, metric_type)

理由:
- 支持多种指标类型（clicks/views/sales等）
- 支持每日、每周、每月数据
- 同一天同一产品可以有多个指标类型
```

---

## 💰 货币策略

### 双币种设计

**原则**: 保留原始货币和人民币归一化金额

**示例**:
```sql
-- 订单表
total_amount FLOAT,         -- 原币金额（如100.00 SGD）
currency VARCHAR(8),        -- 货币代码（SGD）
total_amount_rmb FLOAT,     -- 人民币金额（如534.56 CNY）
```

**优势**:
- ✅ 保留原始数据（可追溯）
- ✅ 统一归一化（便于聚合分析）
- ✅ 支持多货币查询

**汇率转换**:
```python
# 使用currency_service
from services.currency_service import convert_to_rmb

total_amount_rmb = convert_to_rmb(
    amount=100.00,
    currency='SGD',
    date='2024-01-15'
)
# 返回: 534.56
```

---

## 🔍 索引策略

### 关键索引

#### 订单表索引
```sql
-- 按日期查询（最常用）
CREATE INDEX ix_fact_orders_plat_shop_date 
ON fact_orders(platform_code, shop_id, order_date_local);

-- 按状态查询
CREATE INDEX ix_fact_orders_status 
ON fact_orders(platform_code, shop_id, order_status);
```

#### 产品指标索引
```sql
-- 按日期和粒度查询
CREATE INDEX ix_metrics_plat_shop_date_gran 
ON fact_product_metrics(platform_code, shop_id, metric_date, granularity);

-- 按指标类型查询
CREATE INDEX ix_metrics_plat_shop_type 
ON fact_product_metrics(platform_code, shop_id, metric_type);
```

#### 文件清单索引
```sql
-- 按状态查询（pending）
CREATE INDEX ix_catalog_files_status ON catalog_files(status);

-- 按平台店铺查询
CREATE INDEX ix_catalog_files_platform_shop 
ON catalog_files(platform_code, shop_id);
```

---

## 🔄 数据流转流程

### ETL Pipeline数据流

```
1. 采集模块导出文件
   ↓
   temp/outputs/{platform}/{account}/{shop}/{data_domain}/{granularity}/*.xlsx

2. catalog_scanner扫描文件
   ↓
   INSERT INTO catalog_files (status='pending')

3. ingestion_worker处理文件
   ↓
   读取Excel → 字段映射 → 数据验证
   ↓
   ├─ 成功 → UPSERT到dim/fact表
   │          UPDATE catalog_files SET status='ingested'
   │
   └─ 失败 → INSERT INTO data_quarantine
              UPDATE catalog_files SET status='failed'

4. 前端查询展示
   ↓
   data_query_service.get_orders/products/metrics
   ↓
   显示在Streamlit页面
```

---

## 📝 ORM模型映射

### Python类 ↔ 数据库表

| Python类 | 数据库表 | 文件位置 |
|----------|----------|----------|
| DimPlatform | dim_platforms | modules/core/db/schema.py |
| DimShop | dim_shops | modules/core/db/schema.py |
| DimProduct | dim_products | modules/core/db/schema.py |
| DimCurrencyRate | dim_currency_rates | modules/core/db/schema.py |
| FactOrder | fact_orders | modules/core/db/schema.py |
| FactOrderItem | fact_order_items | modules/core/db/schema.py |
| FactProductMetric | fact_product_metrics | modules/core/db/schema.py |
| CatalogFile | catalog_files | modules/core/db/schema.py |
| DataQuarantine | data_quarantine | 🆕需要添加 |

---

## 🆕 需要补充的内容

### 1. 添加data_quarantine表

```python
# 添加到modules/core/db/schema.py

class DataQuarantine(Base):
    """隔离数据表"""
    __tablename__ = "data_quarantine"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    source_file = Column(String(500), nullable=False)
    row_number = Column(Integer)
    row_data = Column(Text, nullable=False)  # JSON格式
    
    error_type = Column(String(100), nullable=False)
    error_msg = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    __table_args__ = (
        Index("ix_quarantine_file", "source_file"),
        Index("ix_quarantine_error_type", "error_type"),
        Index("ix_quarantine_created", "created_at"),
    )
```

---

## 🔧 使用示例

### 查询订单
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from modules.core.db.schema import FactOrder

engine = create_engine('sqlite:///data/unified_erp_system.db')
Session = sessionmaker(bind=engine)
session = Session()

# 查询Shopee订单
orders = session.query(FactOrder).filter(
    FactOrder.platform_code == 'shopee',
    FactOrder.order_date_local >= '2024-01-01'
).limit(100).all()

for order in orders:
    print(f"{order.order_id}: ¥{order.total_amount_rmb}")
```

### Upsert订单
```python
from sqlalchemy.dialects.sqlite import insert

# SQLite: INSERT OR REPLACE
stmt = insert(FactOrder).values(
    platform_code='shopee',
    shop_id='1407964586',
    order_id='ORDER001',
    total_amount=100.00,
    currency='SGD',
    total_amount_rmb=534.56
)
stmt = stmt.on_conflict_do_update(
    index_elements=['platform_code', 'shop_id', 'order_id'],
    set_={'total_amount': 100.00, 'updated_at': datetime.utcnow()}
)
session.execute(stmt)
session.commit()
```

---

## 📊 数据库统计

### 表数量统计

| 类型 | 数量 | 状态 |
|------|------|------|
| 维度表 | 4 | ✅ 全部已存在 |
| 事实表 | 3 | ✅ 全部已存在 |
| 管理表 | 2 | ⚠️ 缺少data_quarantine |
| **总计** | **9** | **8/9已存在** |

### 现有vs计划对比

| 计划的表 | 现有状态 | 需要操作 |
|----------|---------|----------|
| dim_platforms | ✅ 已存在 | 无需操作 |
| dim_shops | ✅ 已存在 | 无需操作 |
| dim_products | ✅ 已存在 | 无需操作 |
| dim_currency_rates | ✅ 已存在 | 无需操作 |
| fact_orders | ✅ 已存在 | 无需操作 |
| fact_order_items | ✅ 已存在 | 无需操作 |
| fact_product_metrics | ✅ 已存在 | 无需操作 |
| catalog_files | ✅ 已存在 | 无需操作 |
| data_quarantine | ❌ 缺失 | 🆕需要添加 |

**完成度**: 88.9% (8/9)

---

## 🎯 Day 1下午任务调整

### 原计划 vs 实际
| 原计划 | 实际情况 | 调整后任务 |
|--------|---------|-----------|
| 创建完整Schema | 88.9%已存在 | 只需添加1个表 |
| 创建ORM模型 | 已存在 | 检查和文档化 |
| 工作量4小时 | 实际1小时 | 多出3小时 |

### 调整后的Day 1下午任务

**14:00-15:00（1小时）：补充data_quarantine表**
- 在modules/core/db/schema.py中添加DataQuarantine类
- 测试表创建
- 提交代码

**15:00-16:00（1小时）：创建Schema文档**
- 完善本文档（DATABASE_SCHEMA_V3.md）
- 添加使用示例
- 提交文档

**16:00-18:00（2小时）：提前开始Alembic工作**
- 检查现有迁移
- 创建新的迁移（如果需要）
- 测试迁移执行

---

## ✅ 验收标准

### Day 1完成标准

- [x] **系统诊断完成** ✅
- [ ] **Schema文档完成** （本文档）
- [ ] data_quarantine表添加完成
- [ ] Alembic迁移测试通过

---

**文档版本**: v3.0  
**最后更新**: 2025-10-16 14:00  
**状态**: 诊断完成，Schema已存在88.9%，只需补充1个表

