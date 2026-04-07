# 后端数据库设计和字段映射需求总结

**文档版本**: v1.0  
**创建日期**: 2025-11-13  
**状态**: 待实施（前端已完成，等待后端开发）

---

## 📋 概述

本文档总结了前端页面开发完成后，需要设计和实现的后端数据库表和字段映射需求。根据"先前端后数据库"的开发策略，所有前端页面已使用Mock数据完成开发，现在需要设计真实的数据表结构来支撑这些功能。

---

## 🎯 需要新增的数据表

### 1. 销售战役管理表（sales_campaigns）

**用途**: 存储销售战役配置和达成情况

**表结构设计**:
```sql
CREATE TABLE sales_campaigns (
    id SERIAL PRIMARY KEY,
    campaign_name VARCHAR(200) NOT NULL,
    campaign_type VARCHAR(32) NOT NULL,  -- holiday/new_product/special_event
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    target_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    target_quantity INTEGER NOT NULL DEFAULT 0,
    actual_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    actual_quantity INTEGER NOT NULL DEFAULT 0,
    achievement_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.00,  -- 达成率百分比
    status VARCHAR(32) NOT NULL DEFAULT 'pending',  -- active/completed/pending/cancelled
    description TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_campaign_dates CHECK (end_date >= start_date),
    CONSTRAINT chk_campaign_amount CHECK (target_amount >= 0),
    CONSTRAINT chk_campaign_quantity CHECK (target_quantity >= 0)
);

CREATE INDEX ix_sales_campaigns_status ON sales_campaigns(status);
CREATE INDEX ix_sales_campaigns_dates ON sales_campaigns(start_date, end_date);
CREATE INDEX ix_sales_campaigns_type ON sales_campaigns(campaign_type);
```

**关联表**: `sales_campaign_shops`（战役参与店铺）

```sql
CREATE TABLE sales_campaign_shops (
    id SERIAL PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES sales_campaigns(id) ON DELETE CASCADE,
    platform_code VARCHAR(32),
    shop_id VARCHAR(64),
    target_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    target_quantity INTEGER NOT NULL DEFAULT 0,
    actual_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    actual_quantity INTEGER NOT NULL DEFAULT 0,
    achievement_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    rank INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_campaign_shop UNIQUE (campaign_id, platform_code, shop_id),
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id)
);

CREATE INDEX ix_campaign_shops_campaign ON sales_campaign_shops(campaign_id);
CREATE INDEX ix_campaign_shops_shop ON sales_campaign_shops(platform_code, shop_id);
```

---

### 2. 目标管理表（sales_targets）

**用途**: 存储销售目标配置（店铺/产品/战役级别）

**表结构设计**:
```sql
CREATE TABLE sales_targets (
    id SERIAL PRIMARY KEY,
    target_name VARCHAR(200) NOT NULL,
    target_type VARCHAR(32) NOT NULL,  -- shop/product/campaign
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    target_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    target_quantity INTEGER NOT NULL DEFAULT 0,
    achieved_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    achieved_quantity INTEGER NOT NULL DEFAULT 0,
    achievement_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- active/completed/cancelled
    description TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_target_dates CHECK (period_end >= period_start),
    CONSTRAINT chk_target_amount CHECK (target_amount >= 0),
    CONSTRAINT chk_target_quantity CHECK (target_quantity >= 0)
);

CREATE INDEX ix_sales_targets_type ON sales_targets(target_type);
CREATE INDEX ix_sales_targets_status ON sales_targets(status);
CREATE INDEX ix_sales_targets_period ON sales_targets(period_start, period_end);
```

**关联表**: `target_breakdown`（目标分解）

```sql
CREATE TABLE target_breakdown (
    id SERIAL PRIMARY KEY,
    target_id INTEGER NOT NULL REFERENCES sales_targets(id) ON DELETE CASCADE,
    breakdown_type VARCHAR(32) NOT NULL,  -- shop/time
    -- 店铺分解字段
    platform_code VARCHAR(32),
    shop_id VARCHAR(64),
    -- 时间分解字段
    period_start DATE,
    period_end DATE,
    period_label VARCHAR(64),  -- 如"第1周"、"2025-01"
    -- 目标值
    target_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    target_quantity INTEGER NOT NULL DEFAULT 0,
    achieved_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    achieved_quantity INTEGER NOT NULL DEFAULT 0,
    achievement_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_breakdown_type CHECK (breakdown_type IN ('shop', 'time')),
    CONSTRAINT chk_breakdown_shop CHECK (
        (breakdown_type = 'shop' AND platform_code IS NOT NULL AND shop_id IS NOT NULL) OR
        (breakdown_type = 'time' AND period_start IS NOT NULL AND period_end IS NOT NULL)
    ),
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id)
);

CREATE INDEX ix_target_breakdown_target ON target_breakdown(target_id);
CREATE INDEX ix_target_breakdown_shop ON target_breakdown(platform_code, shop_id);
CREATE INDEX ix_target_breakdown_period ON target_breakdown(period_start, period_end);
```

---

### 3. 店铺健康度评分表（shop_health_scores）

**用途**: 存储店铺健康度评分和各项指标得分

**表结构设计**:
```sql
CREATE TABLE shop_health_scores (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    metric_date DATE NOT NULL,
    granularity VARCHAR(16) NOT NULL DEFAULT 'daily',  -- daily/weekly/monthly
    
    -- 健康度总分（0-100）
    health_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    
    -- 各项得分（0-100）
    gmv_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    conversion_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    inventory_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    service_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    
    -- 基础指标（用于计算得分）
    gmv DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    conversion_rate DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    inventory_turnover DECIMAL(10, 2) NOT NULL DEFAULT 0.00,
    customer_satisfaction DECIMAL(3, 2) NOT NULL DEFAULT 0.00,  -- 0-5分
    
    -- 风险等级
    risk_level VARCHAR(16) NOT NULL DEFAULT 'low',  -- low/medium/high
    risk_factors JSONB,  -- 风险因素列表
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_shop_health UNIQUE (platform_code, shop_id, metric_date, granularity),
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id),
    CONSTRAINT chk_health_score CHECK (health_score >= 0 AND health_score <= 100),
    CONSTRAINT chk_risk_level CHECK (risk_level IN ('low', 'medium', 'high'))
);

CREATE INDEX ix_shop_health_shop ON shop_health_scores(platform_code, shop_id);
CREATE INDEX ix_shop_health_date ON shop_health_scores(metric_date);
CREATE INDEX ix_shop_health_score ON shop_health_scores(health_score DESC);
CREATE INDEX ix_shop_health_risk ON shop_health_scores(risk_level);
```

---

### 4. 店铺预警提醒表（shop_alerts）

**用途**: 存储店铺运营预警信息

**表结构设计**:
```sql
CREATE TABLE shop_alerts (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    alert_type VARCHAR(64) NOT NULL,  -- inventory_turnover/conversion_rate/gmv_drop/...
    alert_level VARCHAR(16) NOT NULL,  -- critical/warning/info
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    metric_value DECIMAL(15, 2),
    threshold DECIMAL(15, 2),
    metric_unit VARCHAR(32),  -- 指标单位
    is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id),
    CONSTRAINT chk_alert_level CHECK (alert_level IN ('critical', 'warning', 'info'))
);

CREATE INDEX ix_shop_alerts_shop ON shop_alerts(platform_code, shop_id);
CREATE INDEX ix_shop_alerts_level ON shop_alerts(alert_level);
CREATE INDEX ix_shop_alerts_resolved ON shop_alerts(is_resolved);
CREATE INDEX ix_shop_alerts_created ON shop_alerts(created_at DESC);
```

---

### 5. 绩效管理表（performance_scores）

**用途**: 存储店铺绩效评分和明细

**表结构设计**:
```sql
CREATE TABLE performance_scores (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    period VARCHAR(16) NOT NULL,  -- 如"2025-01"
    
    -- 总分（0-100）
    total_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    
    -- 各项得分（权重 × 达成率）
    sales_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,  -- 销售额得分（权重30%）
    profit_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,  -- 毛利得分（权重25%）
    key_product_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,  -- 重点产品得分（权重25%）
    operation_score DECIMAL(5, 2) NOT NULL DEFAULT 0.00,  -- 运营得分（权重20%）
    
    -- 得分明细（JSONB存储详细计算过程）
    score_details JSONB,
    
    -- 排名和系数
    rank INTEGER,
    performance_coefficient DECIMAL(5, 2) NOT NULL DEFAULT 1.00,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_performance_shop_period UNIQUE (platform_code, shop_id, period),
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id),
    CONSTRAINT chk_total_score CHECK (total_score >= 0 AND total_score <= 100)
);

CREATE INDEX ix_performance_shop ON performance_scores(platform_code, shop_id);
CREATE INDEX ix_performance_period ON performance_scores(period);
CREATE INDEX ix_performance_score ON performance_scores(total_score DESC);
CREATE INDEX ix_performance_rank ON performance_scores(rank);
```

**关联表**: `performance_config`（绩效权重配置）

```sql
CREATE TABLE performance_config (
    id SERIAL PRIMARY KEY,
    config_name VARCHAR(64) NOT NULL DEFAULT 'default',
    sales_weight INTEGER NOT NULL DEFAULT 30,  -- 销售额权重（%）
    profit_weight INTEGER NOT NULL DEFAULT 25,  -- 毛利权重（%）
    key_product_weight INTEGER NOT NULL DEFAULT 25,  -- 重点产品权重（%）
    operation_weight INTEGER NOT NULL DEFAULT 20,  -- 运营权重（%）
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    effective_from DATE NOT NULL,
    effective_to DATE,
    created_by VARCHAR(64),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT chk_weights_sum CHECK (sales_weight + profit_weight + key_product_weight + operation_weight = 100),
    CONSTRAINT chk_weights_range CHECK (
        sales_weight >= 0 AND sales_weight <= 100 AND
        profit_weight >= 0 AND profit_weight <= 100 AND
        key_product_weight >= 0 AND key_product_weight <= 100 AND
        operation_weight >= 0 AND operation_weight <= 100
    )
);

CREATE INDEX ix_performance_config_active ON performance_config(is_active, effective_from);
```

---

### 6. 滞销清理排名表（clearance_rankings）

**用途**: 存储店铺滞销清理排名数据

**表结构设计**:
```sql
CREATE TABLE clearance_rankings (
    id SERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    shop_id VARCHAR(64) NOT NULL,
    metric_date DATE NOT NULL,
    granularity VARCHAR(16) NOT NULL,  -- monthly/weekly
    
    -- 清理数据
    clearance_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    clearance_quantity INTEGER NOT NULL DEFAULT 0,
    
    -- 激励金额
    incentive_amount DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    total_incentive DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    
    -- 排名
    rank INTEGER,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uq_clearance_ranking UNIQUE (platform_code, shop_id, metric_date, granularity),
    FOREIGN KEY (platform_code, shop_id) REFERENCES dim_shops(platform_code, shop_id)
);

CREATE INDEX ix_clearance_ranking_date ON clearance_rankings(metric_date, granularity);
CREATE INDEX ix_clearance_ranking_rank ON clearance_rankings(rank);
CREATE INDEX ix_clearance_ranking_amount ON clearance_rankings(clearance_amount DESC);
```

---

## 📊 需要利用的现有表

### 1. fact_orders（订单事实表）
**用途**: 计算店铺GMV、订单数、客单价等指标

**关键字段**:
- `platform_code`, `shop_id`, `order_id`（主键）
- `order_date_local`（订单日期）
- `total_amount_rmb`（订单总金额CNY）
- `order_status`（订单状态）

**查询场景**:
- 店铺GMV趋势：按日期聚合 `total_amount_rmb`
- 店铺订单数：按日期统计订单数
- 店铺客单价：`SUM(total_amount_rmb) / COUNT(order_id)`

---

### 2. fact_product_metrics（产品指标表）
**用途**: 计算店铺转化率、浏览量、访客数等指标

**关键字段**:
- `platform_code`, `shop_id`, `platform_sku`（业务标识）
- `metric_date`（指标日期）
- `data_domain`（数据域：products/analytics）
- `page_views`（浏览量）
- `unique_visitors`（访客数）
- `sales_volume`（销量）
- `sales_amount_rmb`（销售额CNY）
- `conversion_rate`（转化率）

**查询场景**:
- 店铺转化率分析：按日期聚合 `conversion_rate`
- 店铺浏览量：按日期聚合 `page_views`
- 店铺访客数：按日期聚合 `unique_visitors`

---

### 3. dim_shops（店铺维度表）
**用途**: 店铺基本信息

**关键字段**:
- `platform_code`, `shop_id`（主键）
- `shop_name`（店铺名称）
- `region`（地区）
- `currency`（货币）

---

## 🔗 字段映射需求（修订版）

### ⚠️ 重要说明

**数据来源分类**：
- **A类（用户配置数据）**：用户在系统中设置，不需要Excel采集
- **B类（业务数据）**：从Excel采集，需要字段映射
- **C类（计算数据）**：系统自动计算，不需要字段映射

### 销售战役管理字段映射

**数据来源分类**：
- **A类（用户配置）**：战役配置信息（用户在系统中设置）
- **B类（业务数据）**：订单数据（从Excel采集，已有字段映射）
- **C类（计算数据）**：达成数据（系统自动计算）

**A类字段（用户配置，不需要Excel采集）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `campaign_name` | 战役名称 | String | 如"2025春节促销" |
| `campaign_type` | 战役类型 | String | holiday/new_product/special_event |
| `start_date` | 开始日期 | Date | 战役开始时间 |
| `end_date` | 结束日期 | Date | 战役结束时间 |
| `target_amount` | 目标销售额 | Decimal | 目标金额（CNY） |
| `target_quantity` | 目标数量 | Integer | 目标订单数/销量 |
| `status` | 状态 | String | active/completed/pending |

**B类字段（从Excel采集，已有字段映射）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 | 是否已有 |
|------------|------------|---------|------|---------|
| `order_date_local` | 订单日期 | Date | 订单日期 | ✅ 已有 |
| `total_amount_rmb` | 订单总金额（CNY） | Decimal | 订单总金额 | ✅ 已有 |
| `order_status` | 订单状态 | String | 订单状态 | ✅ 已有 |

**C类字段（系统自动计算）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `actual_amount` | 实际销售额 | Decimal | 从订单数据聚合计算 |
| `actual_quantity` | 实际数量 | Integer | 从订单数据统计计算 |
| `achievement_rate` | 达成率 | Decimal | actual_amount / target_amount * 100 |

---

### 目标管理字段映射

**数据来源分类**：
- **A类（用户配置）**：目标配置信息（用户在系统中设置）
- **B类（业务数据）**：订单数据（从Excel采集，已有字段映射）
- **C类（计算数据）**：达成数据（系统自动计算）

**A类字段（用户配置，不需要Excel采集）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `target_name` | 目标名称 | String | 如"2025年1月店铺销售目标" |
| `target_type` | 目标类型 | String | shop/product/campaign |
| `period_start` | 开始时间 | Date | 目标周期开始 |
| `period_end` | 结束时间 | Date | 目标周期结束 |
| `target_amount` | 目标金额 | Decimal | 目标销售额（CNY） |
| `target_quantity` | 目标数量 | Integer | 目标订单数/销量 |
| `status` | 状态 | String | active/completed/cancelled |

**目标分解字段（A类，用户配置）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `breakdown_type` | 分解类型 | String | shop/time |
| `platform_code` | 平台代码 | String | 店铺分解时使用 |
| `shop_id` | 店铺ID | String | 店铺分解时使用 |
| `period_start` | 周期开始 | Date | 时间分解时使用 |
| `period_end` | 周期结束 | Date | 时间分解时使用 |
| `target_amount` | 目标金额 | Decimal | 分解后的目标金额 |
| `target_quantity` | 目标数量 | Integer | 分解后的目标数量 |

**B类字段（从Excel采集，已有字段映射）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 | 是否已有 |
|------------|------------|---------|------|---------|
| `order_date_local` | 订单日期 | Date | 订单日期 | ✅ 已有 |
| `total_amount_rmb` | 订单总金额（CNY） | Decimal | 订单总金额 | ✅ 已有 |

**C类字段（系统自动计算）**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `achieved_amount` | 达成金额 | Decimal | 从订单数据聚合计算 |
| `achieved_quantity` | 达成数量 | Integer | 从订单数据统计计算 |
| `achievement_rate` | 达成率 | Decimal | achieved_amount / target_amount * 100 |

---

### 店铺健康度评分字段映射

**数据来源**: 从现有表计算得出（fact_orders + fact_product_metrics）

**需要计算的标准字段**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 计算来源 |
|------------|------------|---------|---------|
| `health_score` | 健康度总分 | Decimal | 综合计算（0-100） |
| `gmv_score` | GMV得分 | Decimal | 基于GMV计算（0-100） |
| `conversion_score` | 转化得分 | Decimal | 基于转化率计算（0-100） |
| `inventory_score` | 库存得分 | Decimal | 基于库存周转率计算（0-100） |
| `service_score` | 服务得分 | Decimal | 基于客户满意度计算（0-100） |
| `gmv` | GMV | Decimal | 从fact_orders聚合 |
| `conversion_rate` | 转化率 | Decimal | 从fact_product_metrics聚合 |
| `inventory_turnover` | 库存周转率 | Decimal | 从fact_product_metrics计算 |
| `customer_satisfaction` | 客户满意度 | Decimal | 从fact_product_metrics.rating聚合 |
| `risk_level` | 风险等级 | String | 基于各项指标计算 |

---

### 绩效管理字段映射

**数据来源**: 从现有表计算得出（fact_orders + fact_product_metrics + sales_targets）

**需要计算的标准字段**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 计算来源 |
|------------|------------|---------|---------|
| `total_score` | 总分 | Decimal | 综合计算（0-100） |
| `sales_score` | 销售额得分 | Decimal | 销售额达成率 × 30% |
| `profit_score` | 毛利得分 | Decimal | 毛利达成率 × 25% |
| `key_product_score` | 重点产品得分 | Decimal | 重点产品达成率 × 25% |
| `operation_score` | 运营得分 | Decimal | 运营指标得分 × 20% |
| `rank` | 排名 | Integer | 按总分排序 |
| `performance_coefficient` | 绩效系数 | Decimal | 基于排名计算 |

**绩效配置字段**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 |
|------------|------------|---------|------|
| `sales_weight` | 销售额权重 | Integer | 百分比（0-100） |
| `profit_weight` | 毛利权重 | Integer | 百分比（0-100） |
| `key_product_weight` | 重点产品权重 | Integer | 百分比（0-100） |
| `operation_weight` | 运营权重 | Integer | 百分比（0-100） |

---

### 滞销清理排名字段映射

**数据来源**: 从现有表计算得出（fact_product_metrics + fact_inventory）

**需要计算的标准字段**:
| 标准字段代码 | 标准字段名称 | 数据类型 | 计算来源 |
|------------|------------|---------|---------|
| `clearance_amount` | 清理金额 | Decimal | 滞销产品清理金额（CNY） |
| `clearance_quantity` | 清理数量 | Integer | 滞销产品清理数量 |
| `incentive_amount` | 激励金额 | Decimal | 基于清理金额计算 |
| `total_incentive` | 总计激励 | Decimal | 累计激励金额 |
| `rank` | 排名 | Integer | 按清理金额排序 |

---

## 📈 物化视图需求

### 1. mv_shop_performance（店铺表现物化视图）

**用途**: 聚合店铺级别的销售和运营指标

**数据来源**: fact_orders + fact_product_metrics

**关键指标**:
- GMV（按日/周/月聚合）
- 订单数
- 客单价
- 转化率
- 浏览量
- 访客数
- 库存周转率
- 客户满意度

**刷新策略**: 每日刷新（T+1）

---

### 2. mv_shop_health_score（店铺健康度物化视图）

**用途**: 计算店铺健康度评分

**数据来源**: mv_shop_performance

**计算逻辑**:
- GMV得分：基于GMV排名和增长率
- 转化得分：基于转化率排名
- 库存得分：基于库存周转率
- 服务得分：基于客户满意度

**刷新策略**: 每日刷新（T+1）

---

### 3. mv_clearance_ranking（滞销清理排名物化视图）

**用途**: 计算店铺滞销清理排名

**数据来源**: fact_product_metrics（滞销产品） + fact_orders（清理订单）

**计算逻辑**:
- 识别滞销产品（90天无销售）
- 统计清理金额和数量
- 计算激励金额
- 按金额排序

**刷新策略**: 每日刷新（T+1）

---

## 🔄 数据更新策略

### 实时更新（T+0）
- 店铺预警提醒（基于实时数据计算）
- 店铺健康度评分（基于最新数据）

### 定时更新（T+1）
- 店铺GMV趋势（每日凌晨刷新）
- 店铺转化率分析（每日凌晨刷新）
- 店铺健康度评分（每日凌晨刷新）
- 滞销清理排名（每日凌晨刷新）

### 手动触发
- 销售战役数据（管理员手动创建/更新）
- 目标管理数据（管理员手动创建/更新）
- 绩效管理数据（管理员手动配置权重）

---

## 📝 字段映射辞典更新需求（修订版）

### ⚠️ 重要发现

经过详细分析，**前端页面需要的所有核心字段映射已经存在**！

这些字段都已经在现有的字段映射系统中支持：
- `fact_orders`表的字段映射（订单数据）
- `fact_product_metrics`表的字段映射（产品销售数据）
- `dim_shops`表的字段映射（店铺维度数据）

### 核心字段映射清单（已存在）

#### 订单数据域（orders）- ✅ 已有
1. `order_id` - 订单号
2. `order_date_local` - 订单日期
3. `order_time_utc` - 订单时间
4. `total_amount_rmb` - 订单总金额（CNY）
5. `order_status` - 订单状态
6. `payment_status` - 支付状态

#### 产品销售数据域（products）- ✅ 已有
1. `platform_sku` - 平台SKU
2. `product_name` - 商品名称
3. `metric_date` - 指标日期
4. `sales_volume` - 销量
5. `sales_amount_rmb` - 销售额（CNY）
6. `page_views` - 浏览量
7. `unique_visitors` - 访客数
8. `add_to_cart_count` - 加购数
9. `order_count` - 订单数
10. `conversion_rate` - 转化率
11. `rating` - 评分
12. `review_count` - 评价数

#### 库存数据域（inventory）- ✅ 已有
1. `available_stock` - 可用库存
2. `total_stock` - 总库存
3. `price_rmb` - 单价（CNY）

### 不需要添加到字段映射辞典的字段

以下字段是**用户配置数据（A类）**或**计算数据（C类）**，不需要字段映射：

#### 用户配置字段（A类）- 不需要字段映射
- `campaign_name`, `campaign_type`, `start_date`, `end_date`, `target_amount`, `target_quantity`
- `target_name`, `target_type`, `period_start`, `period_end`
- `sales_weight`, `profit_weight`, `key_product_weight`, `operation_weight`

#### 计算字段（C类）- 不需要字段映射
- `actual_amount`, `actual_quantity`, `achievement_rate`
- `health_score`, `gmv_score`, `conversion_score`, `inventory_score`, `service_score`
- `total_score`, `sales_score`, `profit_score`, `key_product_score`, `operation_score`
- `rank`, `performance_coefficient`, `clearance_amount`, `clearance_quantity`

### 结论

**不需要新增字段映射**，只需要：
1. ✅ 确保现有字段映射正常工作
2. ✅ 验证数据采集时能够正确识别和映射这些字段
3. ✅ 确保字段映射模板能够正确识别这些字段

**总计**: 0个新字段需要添加到字段映射辞典（所有核心字段已存在）

---

## 🎯 实施优先级

### Phase 1: 核心表设计（高优先级）
1. ✅ `sales_campaigns` + `sales_campaign_shops`（销售战役管理）
2. ✅ `sales_targets` + `target_breakdown`（目标管理）
3. ✅ `shop_health_scores`（店铺健康度评分）

### Phase 2: 计算表设计（中优先级）
4. ✅ `performance_scores` + `performance_config`（绩效管理）
5. ✅ `clearance_rankings`（滞销清理排名）
6. ✅ `shop_alerts`（店铺预警提醒）

### Phase 3: 物化视图设计（中优先级）
7. ✅ `mv_shop_performance`（店铺表现物化视图）
8. ✅ `mv_shop_health_score`（店铺健康度物化视图）
9. ✅ `mv_clearance_ranking`（滞销清理排名物化视图）

### Phase 4: 字段映射更新（高优先级）
10. ✅ 更新`field_mapping_dictionary`表，添加43个新标准字段

---

## 📋 总结

### 新增表数量
- **主表**: 6张（sales_campaigns, sales_targets, shop_health_scores, performance_scores, clearance_rankings, shop_alerts）
- **关联表**: 3张（sales_campaign_shops, target_breakdown, performance_config）
- **物化视图**: 3个（mv_shop_performance, mv_shop_health_score, mv_clearance_ranking）
- **总计**: 9张表 + 3个物化视图

### 新增字段映射
- **标准字段**: 43个新字段需要添加到字段映射辞典
- **数据域**: 新增`campaigns`（销售战役）、`targets`（目标管理）、`shop_health`（店铺健康度）数据域

### 利用现有表
- `fact_orders`（订单数据）
- `fact_product_metrics`（产品指标数据）
- `dim_shops`（店铺维度数据）
- `fact_order_amounts`（订单金额维度数据）

---

## ✅ 下一步行动

1. **数据库设计**: 在`modules/core/db/schema.py`中添加新表定义
2. **Alembic迁移**: 创建数据库迁移脚本
3. **字段映射更新**: 更新`field_mapping_dictionary`表，添加43个新标准字段
4. **后端API开发**: 实现CRUD API和计算逻辑
5. **物化视图创建**: 创建3个物化视图并设置刷新策略

---

**文档状态**: ✅ 已完成前端开发，等待后端实施

