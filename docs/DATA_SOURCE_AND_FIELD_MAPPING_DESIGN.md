# 数据来源和字段映射设计（修订版）

**文档版本**: v2.0  
**创建日期**: 2025-11-13  
**状态**: 设计确认中

---

## 📋 设计原则

### 1. 数据来源分类

根据业务特性，我们将数据分为三类：

#### A类：用户配置数据（系统内设置，不需要Excel采集）
- **销售战役配置**：战役名称、类型、时间、目标等
- **目标管理配置**：月度/周度目标设置、目标分解等
- **绩效权重配置**：绩效计算规则、权重设置等

**特点**：
- 用户在系统中手动设置
- 不需要Excel采集
- 需要提供友好的配置界面

#### B类：业务数据（从Excel采集，需要字段映射）
- **订单数据**：订单号、订单日期、订单金额、订单状态等
- **产品销售数据**：SKU、销量、销售额、浏览量、转化率等
- **库存数据**：库存数量、库存价值、库存状态等
- **流量数据**：页面浏览量、访客数、点击率等

**特点**：
- 从电商平台导出的Excel文件中采集
- 需要字段映射系统支持
- 自动同步到数据库

#### C类：计算数据（系统自动计算，不需要字段映射）
- **达成率**：实际值 / 目标值
- **健康度评分**：基于多个指标的综合评分
- **排名**：基于某个指标的排序
- **预警**：基于规则自动生成的预警

**特点**：
- 基于A类和B类数据计算得出
- 不需要Excel采集
- 系统自动计算和更新

---

## 🎯 问题1：销售战役和目标管理的数据来源

### 原设计方案（❌ 不合理）

**原设计**：销售战役和目标管理的数据都从Excel采集

**问题**：
- 效率低：用户需要先导出Excel，再导入系统
- 不灵活：无法随时修改目标
- 不符合实际业务场景：目标应该是用户主动设置的

### 修订方案（✅ 合理）

#### 1. 销售战役管理

**数据来源**：
- **配置数据（A类）**：用户在系统中创建和编辑
  - 战役名称、类型、时间范围
  - 目标销售额、目标订单数
  - 参与店铺列表
- **达成数据（B类）**：从订单数据自动计算
  - 实际销售额：从`fact_orders`表聚合计算
  - 实际订单数：从`fact_orders`表统计
  - 达成率：系统自动计算

**实现方式**：
```sql
-- 用户创建战役（A类数据）
INSERT INTO sales_campaigns (campaign_name, start_date, end_date, target_amount, ...)
VALUES ('2025春节促销', '2025-01-20', '2025-02-10', 100000.00, ...);

-- 系统自动计算达成数据（B类数据）
UPDATE sales_campaigns 
SET actual_amount = (
    SELECT COALESCE(SUM(total_amount_rmb), 0)
    FROM fact_orders
    WHERE order_date_local BETWEEN campaigns.start_date AND campaigns.end_date
      AND (platform_code, shop_id) IN (
          SELECT platform_code, shop_id FROM sales_campaign_shops WHERE campaign_id = campaigns.id
      )
),
actual_quantity = (
    SELECT COUNT(*)
    FROM fact_orders
    WHERE order_date_local BETWEEN campaigns.start_date AND campaigns.end_date
      AND (platform_code, shop_id) IN (
          SELECT platform_code, shop_id FROM sales_campaign_shops WHERE campaign_id = campaigns.id
      )
),
achievement_rate = CASE 
    WHEN target_amount > 0 THEN (actual_amount / target_amount * 100)
    ELSE 0
END;
```

#### 2. 目标管理

**数据来源**：
- **配置数据（A类）**：用户在系统中设置
  - 目标名称、类型（店铺/产品/战役）
  - 时间周期（月度/周度）
  - 目标销售额、目标订单数
  - 目标分解（按店铺/按时间）
- **达成数据（B类）**：从订单数据自动计算
  - 实际销售额：从`fact_orders`表聚合计算
  - 实际订单数：从`fact_orders`表统计
  - 达成率：系统自动计算

**实现方式**：
```sql
-- 用户设置月度目标（A类数据）
INSERT INTO sales_targets (target_name, target_type, period_start, period_end, target_amount, ...)
VALUES ('2025年1月店铺销售目标', 'shop', '2025-01-01', '2025-01-31', 500000.00, ...);

-- 用户设置目标分解（A类数据）
INSERT INTO target_breakdown (target_id, breakdown_type, platform_code, shop_id, target_amount, ...)
VALUES (1, 'shop', 'shopee', 'sg_001', 100000.00, ...);

-- 系统自动计算达成数据（B类数据）
UPDATE target_breakdown
SET achieved_amount = (
    SELECT COALESCE(SUM(total_amount_rmb), 0)
    FROM fact_orders
    WHERE order_date_local BETWEEN target.period_start AND target.period_end
      AND platform_code = breakdown.platform_code
      AND shop_id = breakdown.shop_id
),
achieved_quantity = (
    SELECT COUNT(*)
    FROM fact_orders
    WHERE order_date_local BETWEEN target.period_start AND target.period_end
      AND platform_code = breakdown.platform_code
      AND shop_id = breakdown.shop_id
),
achievement_rate = CASE 
    WHEN target_amount > 0 THEN (achieved_amount / target_amount * 100)
    ELSE 0
END
FROM sales_targets target
WHERE target.id = breakdown.target_id;
```

### 总结

**不需要Excel采集的字段**（A类 - 用户配置）：
- `campaign_name`（战役名称）
- `campaign_type`（战役类型）
- `start_date`（开始日期）
- `end_date`（结束日期）
- `target_amount`（目标销售额）
- `target_quantity`（目标订单数）
- `target_name`（目标名称）
- `target_type`（目标类型）
- `period_start`（周期开始）
- `period_end`（周期结束）

**需要从Excel采集的字段**（B类 - 业务数据）：
- 订单数据：`order_id`, `order_date_local`, `total_amount_rmb`, `order_status`等
- 这些字段已经存在于`fact_orders`表中，不需要新增字段映射

**系统自动计算的字段**（C类 - 计算数据）：
- `actual_amount`（实际销售额）
- `actual_quantity`（实际订单数）
- `achievement_rate`（达成率）

---

## 🎯 问题2：前端表格需要的字段映射

### 分析前端页面实际需要的数据

#### 1. 销售看板页面（SalesDashboard.vue）

**店铺销售表现表格**需要：
| 显示字段 | 数据来源 | 是否需要字段映射 |
|---------|---------|----------------|
| 店铺地区 | `dim_shops.region` | ❌ 已有 |
| 店铺名称 | `dim_shops.shop_name` | ❌ 已有 |
| 销售数量（目标） | `sales_targets.target_quantity` | ❌ A类数据 |
| 销售数量（达成） | `fact_orders`聚合计算 | ❌ 计算字段 |
| 销售额（目标） | `sales_targets.target_amount` | ❌ A类数据 |
| 销售额（达成） | `fact_orders.total_amount_rmb`聚合 | ✅ **需要** |
| 利润 | `fact_orders`计算（销售额-成本） | ❌ 计算字段 |
| 提成 | 基于利润计算 | ❌ 计算字段 |

**需要的字段映射**（从Excel采集）：
- `total_amount_rmb`（订单总金额CNY）- **已有字段映射**
- `order_date_local`（订单日期）- **已有字段映射**
- `order_status`（订单状态）- **已有字段映射**

#### 2. 店铺分析页面（StoreAnalytics.vue）

**店铺健康度评分表格**需要：
| 显示字段 | 数据来源 | 是否需要字段映射 |
|---------|---------|----------------|
| 店铺名称 | `dim_shops.shop_name` | ❌ 已有 |
| 健康度总分 | `shop_health_scores.health_score` | ❌ 计算字段 |
| GMV得分 | `shop_health_scores.gmv_score` | ❌ 计算字段 |
| 转化得分 | `shop_health_scores.conversion_score` | ❌ 计算字段 |
| GMV | `fact_orders.total_amount_rmb`聚合 | ✅ **需要** |
| 转化率 | `fact_product_metrics.conversion_rate` | ✅ **需要** |
| 库存周转率 | `fact_product_metrics`计算 | ❌ 计算字段 |
| 客户满意度 | `fact_product_metrics.rating` | ✅ **需要** |

**GMV趋势图表**需要：
| 显示字段 | 数据来源 | 是否需要字段映射 |
|---------|---------|----------------|
| 日期 | `fact_orders.order_date_local` | ✅ **需要** |
| GMV | `fact_orders.total_amount_rmb`聚合 | ✅ **需要** |
| 订单数 | `fact_orders`统计 | ❌ 计算字段 |

**转化率分析图表**需要：
| 显示字段 | 数据来源 | 是否需要字段映射 |
|---------|---------|----------------|
| 日期 | `fact_product_metrics.metric_date` | ✅ **需要** |
| 浏览量 | `fact_product_metrics.page_views` | ✅ **需要** |
| 访客数 | `fact_product_metrics.unique_visitors` | ✅ **需要** |
| 加购数 | `fact_product_metrics.add_to_cart_count` | ✅ **需要** |
| 订单数 | `fact_product_metrics.order_count` | ✅ **需要** |
| 转化率 | `fact_product_metrics.conversion_rate` | ✅ **需要** |

**需要的字段映射**（从Excel采集）：
- `order_date_local`（订单日期）- **已有字段映射**
- `total_amount_rmb`（订单总金额CNY）- **已有字段映射**
- `metric_date`（指标日期）- **已有字段映射**
- `page_views`（浏览量）- **已有字段映射**
- `unique_visitors`（访客数）- **已有字段映射**
- `add_to_cart_count`（加购数）- **已有字段映射**
- `order_count`（订单数）- **已有字段映射**
- `conversion_rate`（转化率）- **已有字段映射**
- `rating`（评分）- **已有字段映射**

#### 3. 业务概览页面（BusinessOverview.vue）

**滞销清理排名**需要：
| 显示字段 | 数据来源 | 是否需要字段映射 |
|---------|---------|----------------|
| 店铺名称 | `dim_shops.shop_name` | ❌ 已有 |
| 清理金额 | `fact_orders` + `fact_product_metrics`计算 | ❌ 计算字段 |
| 清理数量 | `fact_product_metrics.sales_volume`聚合 | ✅ **需要** |

**需要的字段映射**（从Excel采集）：
- `sales_volume`（销量）- **已有字段映射**
- `sales_amount_rmb`（销售额CNY）- **已有字段映射**

---

## 📊 字段映射需求总结

### 核心字段映射（必须支持）

这些字段是前端页面显示的核心数据，**必须**在字段映射系统中支持：

#### 订单数据域（orders）

| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 | 是否已有 |
|------------|------------|---------|------|---------|
| `order_id` | 订单号 | String | 唯一订单标识 | ✅ 已有 |
| `order_date_local` | 订单日期 | Date | 订单日期（本地时区） | ✅ 已有 |
| `order_time_utc` | 订单时间 | DateTime | 订单时间（UTC） | ✅ 已有 |
| `total_amount_rmb` | 订单总金额（CNY） | Decimal | 订单总金额（人民币） | ✅ 已有 |
| `order_status` | 订单状态 | String | pending/completed/cancelled | ✅ 已有 |
| `payment_status` | 支付状态 | String | paid/unpaid/refunded | ✅ 已有 |

#### 产品销售数据域（products）

| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 | 是否已有 |
|------------|------------|---------|------|---------|
| `platform_sku` | 平台SKU | String | 平台商品SKU | ✅ 已有 |
| `product_name` | 商品名称 | String | 商品名称 | ✅ 已有 |
| `metric_date` | 指标日期 | Date | 指标统计日期 | ✅ 已有 |
| `sales_volume` | 销量 | Integer | 销售数量 | ✅ 已有 |
| `sales_amount_rmb` | 销售额（CNY） | Decimal | 销售额（人民币） | ✅ 已有 |
| `page_views` | 浏览量 | Integer | 页面浏览量 | ✅ 已有 |
| `unique_visitors` | 访客数 | Integer | 独立访客数 | ✅ 已有 |
| `add_to_cart_count` | 加购数 | Integer | 加入购物车数量 | ✅ 已有 |
| `order_count` | 订单数 | Integer | 订单数量 | ✅ 已有 |
| `conversion_rate` | 转化率 | Decimal | 转化率（百分比） | ✅ 已有 |
| `rating` | 评分 | Decimal | 商品评分（0-5） | ✅ 已有 |
| `review_count` | 评价数 | Integer | 评价数量 | ✅ 已有 |

#### 库存数据域（inventory）

| 标准字段代码 | 标准字段名称 | 数据类型 | 说明 | 是否已有 |
|------------|------------|---------|------|---------|
| `available_stock` | 可用库存 | Integer | 可售库存数量 | ✅ 已有 |
| `total_stock` | 总库存 | Integer | 总库存数量 | ✅ 已有 |
| `price_rmb` | 单价（CNY） | Decimal | 商品单价（人民币） | ✅ 已有 |

### 结论

**好消息**：前端页面需要的所有核心字段映射**已经存在**！

这些字段都已经在现有的字段映射系统中支持：
- `fact_orders`表的字段映射（订单数据）
- `fact_product_metrics`表的字段映射（产品销售数据）
- `dim_shops`表的字段映射（店铺维度数据）

**不需要新增字段映射**，只需要：
1. 确保这些字段在`field_mapping_dictionary`表中存在
2. 确保字段映射模板能够正确识别这些字段
3. 确保数据采集时能够正确映射这些字段

---

## 🔄 数据流程设计

### 完整数据流程

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 用户配置（A类数据）                                        │
│    - 在系统中创建销售战役                                      │
│    - 在系统中设置月度目标                                      │
│    - 在系统中配置绩效权重                                      │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. 数据采集（B类数据）                                        │
│    - 从电商平台导出Excel文件                                  │
│    - 通过字段映射系统识别字段                                  │
│    - 自动入库到fact_orders/fact_product_metrics表            │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. 系统计算（C类数据）                                        │
│    - 自动计算达成率（实际值/目标值）                          │
│    - 自动计算健康度评分                                        │
│    - 自动计算排名和预警                                        │
│    - 更新sales_campaigns/sales_targets/shop_health_scores表  │
└─────────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. 前端展示                                                  │
│    - 销售看板显示店铺销售表现                                  │
│    - 店铺分析显示健康度评分                                    │
│    - 业务概览显示滞销清理排名                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ 修订后的数据库设计

### 不需要Excel采集的表（A类数据）

这些表的数据完全由用户在系统中设置：

1. **sales_campaigns**（销售战役配置）
2. **sales_campaign_shops**（战役参与店铺）
3. **sales_targets**（目标配置）
4. **target_breakdown**（目标分解）
5. **performance_config**（绩效权重配置）

### 需要Excel采集的表（B类数据）

这些表的数据从Excel文件采集，通过字段映射系统自动入库：

1. **fact_orders**（订单数据）- ✅ 已有
2. **fact_order_items**（订单明细）- ✅ 已有
3. **fact_product_metrics**（产品指标）- ✅ 已有
4. **dim_shops**（店铺维度）- ✅ 已有

### 系统自动计算的表（C类数据）

这些表的数据由系统自动计算和更新：

1. **shop_health_scores**（店铺健康度评分）
2. **performance_scores**（绩效评分）
3. **clearance_rankings**（滞销清理排名）
4. **shop_alerts**（店铺预警）

---

## 📝 实施建议

### Phase 1: 用户配置功能（A类数据）

1. **目标管理页面开发**
   - 创建/编辑月度目标
   - 目标分解（按店铺/按时间）
   - 目标达成情况查看

2. **销售战役管理页面开发**
   - 创建/编辑销售战役
   - 选择参与店铺
   - 战役达成情况查看

3. **绩效配置页面开发**
   - 配置绩效权重
   - 查看绩效计算规则

### Phase 2: 数据采集验证（B类数据）

1. **验证字段映射**
   - 确认所有核心字段在`field_mapping_dictionary`表中存在
   - 测试字段映射模板识别准确性
   - 验证数据采集入库正确性

2. **数据质量检查**
   - 检查订单数据完整性
   - 检查产品指标数据完整性
   - 建立数据质量监控

### Phase 3: 计算逻辑开发（C类数据）

1. **达成率计算**
   - 销售战役达成率计算
   - 目标达成率计算
   - 定时任务自动更新

2. **健康度评分计算**
   - GMV得分计算
   - 转化得分计算
   - 库存得分计算
   - 服务得分计算
   - 综合评分计算

3. **排名和预警**
   - 滞销清理排名计算
   - 店铺预警规则引擎
   - 定时任务自动更新

---

## 🎯 总结

### 问题1的答案

**销售战役和目标管理的数据来源**：
- ✅ **配置数据**：用户在系统中设置（不需要Excel采集）
- ✅ **达成数据**：从订单数据自动计算（不需要新增字段映射）
- ✅ **更灵活**：用户可以随时修改目标，系统自动计算达成情况

### 问题2的答案

**字段映射需求**：
- ✅ **所有核心字段映射已存在**：订单数据、产品销售数据、库存数据的字段映射都已经在系统中支持
- ✅ **不需要新增字段映射**：只需要确保现有字段映射正常工作
- ✅ **重点**：确保数据采集时能够正确识别和映射这些字段

---

**文档状态**: ✅ 设计确认中，等待用户确认后实施

