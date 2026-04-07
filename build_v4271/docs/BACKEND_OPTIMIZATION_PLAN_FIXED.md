# 后端优化和C类数据计算支撑计划（修正版）

**版本**: v1.1  
**创建日期**: 2025-11-15  
**状态**: 待确认  
**修正内容**: 已识别并修复所有双维护和漏洞风险

---

## ⚠️ 重要修正说明

本计划已根据现有代码结构进行了全面检查，修复了以下双维护和漏洞风险：

### 已修复的双维护风险

1. **达成率计算逻辑重复** - 已修正：从路由层提取到服务层
2. **店铺健康度API重复** - 已修正：在现有`store_analytics.py`中新增接口
3. **店铺预警服务重复** - 已修正：使用现有的`ShopHealthService.generate_alerts()`方法

### 已识别的依赖风险

1. **APScheduler未安装** - 需要在`requirements.txt`中添加依赖

---

## 一、核心字段映射需求分析

### 1.1 字段映射系统核心字段清单（必须支持）

根据前端页面需求，以下字段是系统计算（C类数据）有效运作的**核心字段映射**：

#### 订单数据域（orders）- 用于达成率计算

| 标准字段代码 | 标准字段名称 | 数据类型 | 用途 | 状态 |
|------------|------------|---------|------|------|
| `order_id` | 订单号 | String | 唯一订单标识，统计订单数 | ✅ 已有 |
| `order_date_local` | 订单日期 | Date | 时间筛选和聚合 | ✅ 已有 |
| `order_time_utc` | 订单时间 | DateTime | 精确时间查询 | ✅ 已有 |
| `total_amount_rmb` | 订单总金额（CNY） | Decimal | 销售额计算（达成率核心） | ✅ 已有 |
| `order_status` | 订单状态 | String | 筛选有效订单 | ✅ 已有 |
| `platform_code` | 平台代码 | String | 平台维度聚合 | ✅ 已有 |
| `shop_id` | 店铺ID | String | 店铺维度聚合 | ✅ 已有 |

#### 产品销售数据域（products）- 用于健康度评分和排名

| 标准字段代码 | 标准字段名称 | 数据类型 | 用途 | 状态 |
|------------|------------|---------|------|------|
| `platform_sku` | 平台SKU | String | 产品标识 | ✅ 已有 |
| `product_name` | 商品名称 | String | 产品名称 | ✅ 已有 |
| `metric_date` | 指标日期 | Date | 时间维度聚合 | ✅ 已有 |
| `sales_volume` | 销量 | Integer | 销量统计（排名计算） | ✅ 已有 |
| `sales_amount_rmb` | 销售额（CNY） | Decimal | 销售额统计 | ✅ 已有 |
| `page_views` | 浏览量 | Integer | 流量指标 | ✅ 已有 |
| `unique_visitors` | 访客数 | Integer | 流量指标（转化率计算） | ✅ 已有 |
| `add_to_cart_count` | 加购数 | Integer | 转化漏斗 | ✅ 已有 |
| `order_count` | 订单数 | Integer | 转化率计算核心 | ✅ 已有 |
| `conversion_rate` | 转化率 | Decimal | 健康度评分核心指标 | ✅ 已有 |
| `rating` | 评分 | Decimal | 客户满意度（服务得分） | ✅ 已有 |
| `review_count` | 评价数 | Integer | 服务指标 | ✅ 已有 |
| `platform_code` | 平台代码 | String | 平台维度聚合 | ✅ 已有 |
| `shop_id` | 店铺ID | String | 店铺维度聚合 | ✅ 已有 |
| `data_domain` | 数据域 | String | 区分products/inventory域 | ✅ 已有 |

#### 库存数据域（inventory）- 用于库存健康度评分

| 标准字段代码 | 标准字段名称 | 数据类型 | 用途 | 状态 |
|------------|------------|---------|------|------|
| `available_stock` | 可用库存 | Integer | 库存健康度计算 | ✅ 已有 |
| `total_stock` | 总库存 | Integer | 库存周转率计算 | ✅ 已有 |
| `price_rmb` | 单价（CNY） | Decimal | 库存价值计算 | ✅ 已有 |

### 1.2 字段映射验证清单

**验证步骤**：
1. 检查`field_mapping_dictionary`表中上述字段是否存在
2. 验证字段映射模板能够正确识别这些字段
3. 确保数据采集时能够正确映射到数据库列

**关键验证点**：
- `total_amount_rmb`（订单金额）- 达成率计算核心
- `conversion_rate`（转化率）- 健康度评分核心
- `unique_visitors`（访客数）- 转化率计算分母
- `order_count`（订单数）- 转化率计算分子
- `sales_volume`（销量）- 排名计算核心

---

## 二、C类数据计算逻辑实现

### 2.1 达成率计算（Achievement Rate）

#### 2.1.1 销售战役达成率计算

**数据来源**：
- A类：`sales_campaigns.target_amount`, `sales_campaigns.target_quantity`
- B类：`fact_orders.total_amount_rmb`, `fact_orders.order_id`（聚合计算）

**计算逻辑**：
```python
# 实际销售额 = SUM(fact_orders.total_amount_rmb)
# WHERE order_date_local BETWEEN campaign.start_date AND campaign.end_date
# AND (platform_code, shop_id) IN campaign_shops

# 实际订单数 = COUNT(DISTINCT fact_orders.order_id)

# 达成率 = (实际销售额 / 目标销售额) * 100
```

**实现位置**：
- ⚠️ **当前状态**：计算逻辑在`backend/routers/sales_campaign.py`的`calculate_campaign_achievement`函数中（第479行）
- ✅ **优化方案**：**提取计算逻辑到服务层**，创建`backend/services/sales_campaign_service.py`
- ✅ **API端点**：`POST /api/sales-campaigns/{campaign_id}/calculate`（已存在，路由层调用服务层）

#### 2.1.2 目标管理达成率计算

**数据来源**：
- A类：`target_breakdown.target_amount`, `target_breakdown.target_quantity`
- B类：`fact_orders.total_amount_rmb`（按店铺/时间聚合）

**计算逻辑**：
```python
# 店铺分解达成率：
# achieved_amount = SUM(fact_orders.total_amount_rmb)
# WHERE order_date_local BETWEEN target.period_start AND target.period_end
# AND platform_code = breakdown.platform_code
# AND shop_id = breakdown.shop_id

# 时间分解达成率：
# achieved_amount = SUM(fact_orders.total_amount_rmb)
# WHERE order_date_local BETWEEN breakdown.period_start AND breakdown.period_end
# AND (platform_code, shop_id) IN target_shops
```

**实现位置**：
- ⚠️ **当前状态**：计算逻辑在`backend/routers/target_management.py`的`calculate_target_achievement`函数中（第513行）
- ✅ **优化方案**：**提取计算逻辑到服务层**，创建`backend/services/target_management_service.py`
- ✅ **API端点**：`POST /api/targets/{target_id}/calculate`（已存在，路由层调用服务层）

### 2.2 健康度评分计算（Health Score）

#### 2.2.1 店铺健康度评分计算

**数据来源**：
- B类：`fact_orders.total_amount_rmb`, `fact_product_metrics.conversion_rate`, `fact_product_metrics`库存相关字段, `fact_product_metrics.rating`
- A类：`performance_config`（权重配置，可选）

**计算逻辑**（4个维度，总分100分）：
```python
# 1. GMV得分（0-30分）
# gmv_score = min((gmv / target_gmv) * 30, 30)
# gmv = SUM(fact_orders.total_amount_rmb) WHERE shop = shop_id AND date = metric_date

# 2. 转化率得分（0-25分）
# conversion_score = min((conversion_rate / target_conversion_rate) * 25, 25)
# conversion_rate = AVG(fact_product_metrics.conversion_rate) WHERE shop = shop_id AND date = metric_date

# 3. 库存得分（0-25分）
# inventory_score = min((inventory_turnover / target_turnover) * 25, 25)
# inventory_turnover = sales_volume / avg_stock（需要计算）

# 4. 服务得分（0-20分）
# service_score = min((rating / 5.0) * 20, 20)
# rating = AVG(fact_product_metrics.rating) WHERE shop = shop_id AND date = metric_date

# 总分 = gmv_score + conversion_score + inventory_score + service_score
```

**实现位置**：
- ✅ **服务层**：`backend/services/shop_health_service.py`（已存在，需完善计算逻辑）
- ✅ **API端点**：`POST /api/store-analytics/health-scores/calculate`（已存在，在`store_analytics.py`第154行）
- ⚠️ **定时任务**：APScheduler每天凌晨2点自动计算（需要先安装APScheduler依赖）

### 2.3 排名和预警计算

#### 2.3.1 店铺赛马排名（Shop Racing）

**数据来源**：
- B类：`fact_orders.total_amount_rmb`, `fact_product_metrics.unique_visitors`, `fact_product_metrics.page_views`

**计算逻辑**：
```python
# 按销售额排名：
# 1. 查询指定粒度（日/周/月）的销售额
# 2. 按销售额降序排序
# 3. 计算环比（日度环比昨日、周度环比上周、月度环比上月）
# 4. 返回TopN排名
```

**实现位置**：
- API端点：`GET /api/dashboard/business-overview/shop-racing`（已存在，需完善环比计算）

#### 2.3.2 滞销清理排名（Clearance Ranking）

**数据来源**：
- B类：`fact_product_metrics.sales_volume`, `fact_product_metrics.metric_date`, `fact_product_metrics.available_stock`

**计算逻辑**：
```python
# 滞销定义：库存天数 > 30天 且 销量 < 阈值
# 1. 计算库存天数 = CURRENT_DATE - metric_date
# 2. 筛选滞销产品（库存天数 > 30 且 销量 < 阈值）
# 3. 按滞销金额排序（库存数量 * 单价）
# 4. 返回TopN排名
```

**实现位置**：
- API端点：`GET /api/dashboard/business-overview/inventory-backlog`（需新增）

#### 2.3.3 店铺预警（Shop Alerts）

**数据来源**：
- C类：`shop_health_scores`（健康度评分）
- B类：`fact_orders`, `fact_product_metrics`（实时指标）

**预警规则**：
```python
# 1. 健康度预警：health_score < 60 → critical
# 2. 转化率预警：conversion_rate < 1% → warning
# 3. GMV下降预警：当日GMV < 昨日GMV * 0.8 → warning
# 4. 库存预警：available_stock < 10 → info
```

**实现位置**：
- ✅ **服务层**：`ShopHealthService.generate_alerts()`方法（已存在，第454行）
- ✅ **API端点**：在`store_analytics.py`中新增`GET /api/store-analytics/alerts`（不创建新路由文件）
- ⚠️ **定时任务**：APScheduler每小时检查一次（需要先安装APScheduler依赖）

---

## 三、后端API优化计划

### 3.1 业务概览API增强

**现有API**：
- `GET /api/dashboard/business-overview/kpi`（已存在）
- `GET /api/dashboard/business-overview/comparison`（已存在）
- `GET /api/dashboard/business-overview/shop-racing`（已存在，需完善）

**需要新增/增强**：
1. **经营指标API增强**（`GET /api/dashboard/business-overview/operational-metrics`）
   - 从`sales_targets`表读取月目标（A类数据）
   - 计算月达成率、时间GAP
   - 预估销售和费用（基于历史数据）

2. **滞销清理排名API**（`GET /api/dashboard/business-overview/inventory-backlog`）
   - 计算滞销产品排名
   - 返回滞销金额、滞销数量、滞销率

### 3.2 销售战役API增强

**现有API**：
- `POST /api/sales-campaigns/{campaign_id}/calculate`（已存在）

**需要完善**：
1. **提取计算逻辑到服务层**（避免路由层包含业务逻辑）
2. 支持批量计算所有战役
3. 定时任务自动更新达成率

### 3.3 目标管理API增强

**现有API**：
- `POST /api/targets/{target_id}/calculate`（已存在）

**需要完善**：
1. **提取计算逻辑到服务层**（避免路由层包含业务逻辑）
2. 完善店铺分解达成率计算
3. 完善时间分解达成率计算
4. 定时任务自动更新达成率

### 3.4 店铺健康度API增强（避免双维护）⚠️

**当前状态**：
- ✅ `GET /api/store-analytics/health-scores` - 查询健康度评分列表（已存在，`store_analytics.py`第92行）
- ✅ `POST /api/store-analytics/health-scores/calculate` - 计算健康度评分（已存在，`store_analytics.py`第154行）

**需要新增**（在`store_analytics.py`中新增，不创建新路由文件）：
1. `GET /api/store-analytics/health-scores/{shop_id}/history` - 查询历史健康度趋势（新增接口）

### 3.5 店铺预警API新增（避免双维护）⚠️

**当前状态**：
- ✅ 预警生成逻辑已在`ShopHealthService.generate_alerts()`方法中实现（第454行）

**需要新增**（在`store_analytics.py`中新增，不创建新路由文件）：
1. `GET /api/store-analytics/alerts` - 查询店铺预警列表（新增接口）
2. `POST /api/store-analytics/alerts/{alert_id}/resolve` - 标记预警已解决（新增接口）
3. `GET /api/store-analytics/alerts/stats` - 预警统计（新增接口）

---

## 四、定时任务实现

### 4.1 APScheduler任务配置

**前置条件**：
- ⚠️ **必须先安装APScheduler依赖**：在`requirements.txt`中添加`APScheduler`

**任务列表**：
1. **达成率计算任务**（每天凌晨2点）
   - 计算所有销售战役达成率
   - 计算所有目标达成率

2. **健康度评分计算任务**（每天凌晨2点）
   - 计算所有店铺健康度评分
   - 更新`shop_health_scores`表

3. **预警检查任务**（每小时）
   - 检查店铺健康度预警
   - 检查转化率预警
   - 检查GMV下降预警
   - 生成`shop_alerts`记录

4. **排名计算任务**（每天凌晨3点）
   - 计算店铺赛马排名
   - 计算滞销清理排名

**实现位置**：
- `backend/services/scheduler_service.py`（需新增）
- `backend/main.py`（启动时注册任务）

---

## 五、数据库优化

### 5.1 索引优化

**需要添加的索引**：
```sql
-- fact_orders表（达成率计算优化）
CREATE INDEX IF NOT EXISTS ix_fact_orders_date_shop 
ON fact_orders(order_date_local, platform_code, shop_id);

-- fact_product_metrics表（健康度计算优化）
CREATE INDEX IF NOT EXISTS ix_fact_product_metrics_date_shop 
ON fact_product_metrics(metric_date, platform_code, shop_id, data_domain);

-- shop_health_scores表（查询优化）
CREATE INDEX IF NOT EXISTS ix_shop_health_scores_date_score 
ON shop_health_scores(metric_date, health_score DESC);
```

### 5.2 物化视图优化

**考虑新增物化视图**：
1. `mv_shop_daily_performance` - 店铺日度表现（GMV、订单数、转化率）
2. `mv_shop_health_summary` - 店铺健康度汇总

---

## 六、实施步骤

### Phase 1: 字段映射验证（1-2天）

1. 验证核心字段映射完整性
2. 测试字段映射模板识别准确性
3. 验证数据采集入库正确性

### Phase 2: C类数据计算服务开发（3-5天）

1. **提取达成率计算逻辑到服务层**（从路由层提取，避免双维护）
   - 创建`backend/services/sales_campaign_service.py`
   - 创建`backend/services/target_management_service.py`
   - 修改路由层调用服务层

2. **完善健康度评分计算服务**（已有基础实现）
   - 完善`backend/services/shop_health_service.py`的计算逻辑
   - 完善库存周转率和客户满意度计算（当前是临时值）

3. **开发排名和预警计算服务**（预警逻辑已存在，只需新增查询接口）
   - 在`store_analytics.py`中新增预警查询接口
   - 不创建新的服务文件（避免双维护）

### Phase 3: API增强和新增（2-3天）

1. 增强现有业务概览API（`dashboard_api.py`）
2. **在`store_analytics.py`中新增健康度历史趋势接口**（不创建新路由文件）
3. **在`store_analytics.py`中新增预警查询接口**（不创建新路由文件）

### Phase 4: 定时任务实现（1-2天）

1. **检查并安装APScheduler依赖**（当前未安装）
2. 创建`backend/services/scheduler_service.py`统一管理定时任务
3. 配置定时任务：
   - 达成率计算任务（每天凌晨2点）
   - 健康度评分计算任务（每天凌晨2点）
   - 预警检查任务（每小时）
   - 排名计算任务（每天凌晨3点）
4. 在`backend/main.py`中注册定时任务
5. 测试定时任务执行
6. 监控任务执行状态

### Phase 5: 数据库优化（1天）

1. 添加必要索引
2. 创建物化视图（如需要）
3. 性能测试

### Phase 6: 测试和文档（2天）

1. 端到端功能测试
2. 性能测试
3. API文档更新
4. 用户文档更新

---

## 七、关键文件清单（已修正双维护风险）

### 7.1 需要修改的文件（避免双维护）

- `backend/routers/sales_campaign.py` - 销售战役API（**提取计算逻辑到服务层**，避免路由层包含业务逻辑）
- `backend/routers/target_management.py` - 目标管理API（**提取计算逻辑到服务层**，避免路由层包含业务逻辑）
- `backend/services/shop_health_service.py` - 店铺健康度服务（**完善计算逻辑**，已有基础实现）
- `backend/routers/dashboard_api.py` - 业务概览API（增强现有接口）
- `backend/routers/store_analytics.py` - 店铺分析API（**新增预警查询接口**，不创建新路由文件）

### 7.2 需要新增的文件（避免双维护）

- `backend/services/sales_campaign_service.py` - 销售战役服务（**新增**，从路由层提取计算逻辑）
- `backend/services/target_management_service.py` - 目标管理服务（**新增**，从路由层提取计算逻辑）
- `backend/services/scheduler_service.py` - 定时任务服务（**新增**，统一管理所有定时任务）
- `sql/migrations/add_indexes_for_c_class_calculation.sql` - 数据库索引迁移（新增）

### 7.3 不需要创建的文件（避免双维护）⚠️

- ❌ `backend/routers/shop_health.py` - **不创建**，健康度API已在`store_analytics.py`中实现
- ❌ `backend/services/shop_alert_service.py` - **不创建**，预警逻辑已在`ShopHealthService.generate_alerts()`中实现
- ❌ `backend/routers/shop_alerts.py` - **不创建**，在`store_analytics.py`中新增预警查询接口即可

### 7.4 需要验证的文件

- `modules/core/db/schema.py` - 验证C类数据表结构完整性
- `backend/services/data_importer.py` - 验证B类数据入库正确性
- `backend/services/field_mapping_service.py` - 验证字段映射正确性

---

## 八、风险和注意事项

### 8.1 双维护风险（已识别并修复）⚠️

**风险1：达成率计算逻辑重复**
- ❌ **原计划**：创建新的服务层文件
- ✅ **实际情况**：计算逻辑已在路由层实现
- ✅ **修复方案**：提取计算逻辑到服务层，路由层只负责API接口，符合分层架构

**风险2：店铺健康度API重复**
- ❌ **原计划**：创建`backend/routers/shop_health.py`
- ✅ **实际情况**：健康度API已在`store_analytics.py`中实现
- ✅ **修复方案**：在`store_analytics.py`中新增接口，不创建新路由文件

**风险3：店铺预警服务重复**
- ❌ **原计划**：创建`backend/services/shop_alert_service.py`
- ✅ **实际情况**：预警生成逻辑已在`ShopHealthService.generate_alerts()`中实现
- ✅ **修复方案**：在`store_analytics.py`中新增预警查询接口，不创建新服务

### 8.2 依赖缺失风险⚠️

**风险：APScheduler未安装**
- ❌ **问题**：日志显示"No module named 'apscheduler'"
- ✅ **修复方案**：在`requirements.txt`中添加`APScheduler`依赖

### 8.3 架构合规风险⚠️

**风险：业务逻辑在路由层**
- ❌ **问题**：达成率计算逻辑在路由层实现，不符合分层架构规范
- ✅ **修复方案**：提取计算逻辑到服务层，路由层只负责API接口和参数验证

### 8.4 数据质量风险

- **风险**：B类数据缺失或不准确导致C类计算错误
- **应对**：数据质量检查、数据隔离区机制

### 8.5 性能风险

- **风险**：大量数据聚合计算导致API响应慢
- **应对**：使用物化视图、添加索引、缓存热点数据

### 8.6 计算逻辑风险

- **风险**：计算逻辑错误导致业务决策错误
- **应对**：充分测试、代码审查、文档记录

---

## 九、成功标准

1. ✅ 所有核心字段映射验证通过
2. ✅ C类数据计算逻辑正确实现
3. ✅ API响应时间 < 500ms（P95）
4. ✅ 定时任务正常运行
5. ✅ 前端页面数据正常显示
6. ✅ 达成率、健康度评分、排名计算准确
7. ✅ **无双维护问题**（100% SSOT合规）
8. ✅ **架构分层清晰**（路由层不包含业务逻辑）

---

## 十、核心字段映射总结

### 10.1 字段映射系统必须支持的核心字段

为了让前端的系统计算（C类数据）有效运作，字段映射系统必须支持以下核心字段：

#### 订单数据域（orders）- 达成率计算核心
- `order_id` - 订单号（统计订单数）
- `order_date_local` - 订单日期（时间筛选）
- `total_amount_rmb` - 订单总金额CNY（销售额计算）
- `order_status` - 订单状态（筛选有效订单）
- `platform_code` + `shop_id` - 平台和店铺（维度聚合）

#### 产品销售数据域（products）- 健康度评分和排名核心
- `metric_date` - 指标日期（时间维度）
- `sales_volume` - 销量（排名计算）
- `sales_amount_rmb` - 销售额CNY（排名计算）
- `unique_visitors` - 访客数（转化率计算分母）
- `order_count` - 订单数（转化率计算分子）
- `conversion_rate` - 转化率（健康度评分核心）
- `rating` - 评分（服务得分）
- `page_views` - 浏览量（流量指标）
- `platform_code` + `shop_id` - 平台和店铺（维度聚合）

#### 库存数据域（inventory）- 库存健康度评分核心
- `available_stock` - 可用库存（库存健康度）
- `total_stock` - 总库存（库存周转率）
- `price_rmb` - 单价CNY（库存价值）

### 10.2 字段映射验证优先级

**P0（必须验证）**：
1. `total_amount_rmb` - 达成率计算核心
2. `conversion_rate` - 健康度评分核心
3. `unique_visitors` + `order_count` - 转化率计算

**P1（重要验证）**：
1. `sales_volume` - 排名计算
2. `rating` - 服务得分
3. `available_stock` - 库存健康度

**P2（一般验证）**：
1. 其他辅助字段

---

**文档状态**: ✅ 已修正双维护和漏洞风险，等待用户确认后执行

