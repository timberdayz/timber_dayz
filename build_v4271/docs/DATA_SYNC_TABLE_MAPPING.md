# 数据同步表映射关系

**版本**: v4.17.0 DSS架构（按平台分表）  
**更新日期**: 2025-01-31  
**用途**: 说明数据同步后，各个数据域的文件会同步到哪个表中

---

## 📊 数据同步表映射规则

数据同步系统采用 **DSS架构（Decision Support System）**，所有数据同步到 **B类数据表（fact_raw_data_*）**，以JSONB格式存储原始数据。

### 映射规则

数据同步根据以下维度选择目标表：
1. **平台（platform）**：shopee、tiktok、miaoshou等（v4.17.0新增）
2. **数据域（data_domain）**：orders、products、analytics、services、inventory
3. **粒度（granularity）**：daily、weekly、monthly、snapshot
4. **子类型（sub_domain）**：可选，services域必须提供（ai_assistant或agent）

**表名格式**（v4.17.0+）：
- 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`（如`fact_shopee_orders_daily`）
- 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`（如`fact_shopee_services_ai_assistant_monthly`）

**Schema管理**（v4.17.0+）：
- 所有B类数据表存储在`b_class` schema中
- 查询时使用`b_class."{table_name}"`格式
- 或依赖`search_path`自动查找（向后兼容）

### ⚠️ v4.17.0架构调整（按平台分表）

1. **按平台分表**：
   - 所有B类数据表按平台分表，表名包含platform_code信息
   - 用户可以通过表名直接识别数据归属（平台-数据域-子类型-粒度）
   - 所有表创建在`b_class` schema中，便于Metabase中清晰区分

2. **动态表管理**：
   - 所有表通过`PlatformTableManager`动态创建（如果不存在）
   - 表结构统一：系统字段（id, platform_code, shop_id等）+ 动态列（根据模板字段）
   - 唯一约束：基于`platform_code + shop_id + data_domain + granularity + data_hash`

3. **历史架构调整**（v4.16.0）：
   - traffic域已迁移到analytics域
   - services域按sub_domain分表（ai_assistant/agent）

---

## 📋 完整表映射清单

### 订单数据（Orders）

| 平台 | 数据域 | 粒度 | 目标表 | 说明 |
|------|--------|------|--------|------|
| shopee | orders | daily | `b_class.fact_shopee_orders_daily` | Shopee日度订单数据 |
| shopee | orders | weekly | `b_class.fact_shopee_orders_weekly` | Shopee周度订单数据 |
| shopee | orders | monthly | `b_class.fact_shopee_orders_monthly` | Shopee月度订单数据 |
| tiktok | orders | daily | `b_class.fact_tiktok_orders_daily` | TikTok日度订单数据 |
| ... | ... | ... | ... | 其他平台类似 |

### 产品数据（Products）

| 数据域 | 粒度 | 目标表 | 说明 |
|--------|------|--------|------|
| products | daily | `fact_raw_data_products_daily` | 日度产品数据 |
| products | weekly | `fact_raw_data_products_weekly` | 周度产品数据 |
| products | monthly | `fact_raw_data_products_monthly` | 月度产品数据 |

### 分析数据（Analytics）⭐ v4.16.0更新

| 数据域 | 粒度 | 目标表 | 说明 |
|--------|------|--------|------|
| analytics | daily | `fact_raw_data_analytics_daily` | 日度分析数据 |
| analytics | weekly | `fact_raw_data_analytics_weekly` | 周度分析数据 |
| analytics | monthly | `fact_raw_data_analytics_monthly` | 月度分析数据 |

**注意**：traffic域已迁移到analytics域，`fact_raw_data_traffic_*` 表已废弃（保留用于兼容性）。

### 服务数据（Services）⭐ v4.16.0更新：按sub_domain分表

#### AI助手子类型（ai_assistant）

| 数据域 | 子类型 | 粒度 | 目标表 | 说明 |
|--------|--------|------|--------|------|
| services | ai_assistant | daily | `fact_raw_data_services_ai_assistant_daily` | AI助手日度数据 |
| services | ai_assistant | weekly | `fact_raw_data_services_ai_assistant_weekly` | AI助手周度数据 |
| services | ai_assistant | monthly | `fact_raw_data_services_ai_assistant_monthly` | AI助手月度数据 |

**表头特点**：
- 日期字段：单个日期（"日期"）
- 数据行数：多行（逐日一行）
- 字段数量：约12列

#### 人工服务子类型（agent）

| 数据域 | 子类型 | 粒度 | 目标表 | 说明 |
|--------|--------|------|--------|------|
| services | agent | weekly | `fact_raw_data_services_agent_weekly` | 人工服务周度数据 |
| services | agent | monthly | `fact_raw_data_services_agent_monthly` | 人工服务月度数据 |

**表头特点**：
- 日期字段：时间区间（"日期期间"，如"18/09/2025 - 24/09/2025"）
- 数据行数：单行（整个期间一行）
- 字段数量：约16列

**注意**：`fact_raw_data_services_*` 表已废弃（保留用于兼容性），新数据应写入按sub_domain分表的表。

### 库存数据（Inventory）

| 平台 | 数据域 | 粒度 | 目标表 | 说明 |
|------|--------|------|--------|------|
| shopee | inventory | snapshot | `b_class.fact_shopee_inventory_snapshot` | Shopee库存快照数据 |
| tiktok | inventory | snapshot | `b_class.fact_tiktok_inventory_snapshot` | TikTok库存快照数据 |
| ... | ... | ... | ... | 其他平台类似 |


---

## 🔍 在Metabase中检查数据同步

### 步骤1：连接数据库

1. 登录Metabase：http://localhost:8080
2. 进入：设置 → 管理 → 数据库
3. 确认PostgreSQL数据库已连接

### 步骤2：查看B类数据表

在Metabase中，你可以看到以下表（v4.17.0+按平台分表）：

**b_class schema中的表**（按平台-数据域-子类型-粒度分表）：
```
b_class.fact_shopee_orders_daily
b_class.fact_shopee_orders_weekly
b_class.fact_shopee_orders_monthly
b_class.fact_shopee_products_daily
b_class.fact_shopee_inventory_snapshot
b_class.fact_shopee_services_ai_assistant_daily
b_class.fact_shopee_services_ai_assistant_weekly
b_class.fact_shopee_services_ai_assistant_monthly
b_class.fact_tiktok_orders_daily
b_class.fact_tiktok_orders_weekly
...（其他平台类似）
```

**表名格式**：
- 无sub_domain：`fact_{platform}_{data_domain}_{granularity}`
- 有sub_domain：`fact_{platform}_{data_domain}_{sub_domain}_{granularity}`

**优势**：
- ✅ 用户可以通过表名直接识别数据归属（平台-数据域-子类型-粒度）
- ✅ 一个模板一个表，便于管理维护
- ✅ Metabase中按schema分组显示，便于查看

### 步骤3：创建数据同步检查Question

#### 示例1：检查订单数据同步情况

```sql
-- 检查日度订单数据
SELECT 
    platform_code,
    shop_id,
    COUNT(*) as row_count,
    MIN(metric_date) as earliest_date,
    MAX(metric_date) as latest_date,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_orders_daily
GROUP BY platform_code, shop_id
ORDER BY row_count DESC;
```

#### 示例2：检查产品数据同步情况

```sql
-- 检查产品数据
SELECT 
    platform_code,
    shop_id,
    COUNT(*) as row_count,
    MIN(metric_date) as earliest_date,
    MAX(metric_date) as latest_date,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_products_daily
GROUP BY platform_code, shop_id
ORDER BY row_count DESC;
```

#### 示例3：检查所有数据域的同步统计

```sql
-- 统一检查所有B类数据表
SELECT 
    'orders_daily' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_orders_daily
UNION ALL
SELECT 
    'orders_weekly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_orders_weekly
UNION ALL
SELECT 
    'orders_monthly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_orders_monthly
UNION ALL
SELECT 
    'products_daily' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_products_daily
UNION ALL
SELECT 
    'products_weekly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_products_weekly
UNION ALL
SELECT 
    'products_monthly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_products_monthly
UNION ALL
SELECT 
    'traffic_daily' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_traffic_daily
UNION ALL
SELECT 
    'traffic_weekly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_traffic_weekly
UNION ALL
SELECT 
    'traffic_monthly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_traffic_monthly
UNION ALL
SELECT 
    'services_daily' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_services_daily
UNION ALL
SELECT 
    'services_weekly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_services_weekly
UNION ALL
SELECT 
    'services_monthly' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_services_monthly
UNION ALL
SELECT 
    'inventory_snapshot' as table_name,
    COUNT(*) as row_count,
    COUNT(DISTINCT file_id) as file_count
FROM fact_raw_data_inventory_snapshot
ORDER BY table_name;
```

### 步骤4：查看原始数据（JSONB格式）

B类数据表使用JSONB格式存储原始数据，字段名为`raw_data`：

```sql
-- 查看订单原始数据示例
SELECT 
    platform_code,
    shop_id,
    metric_date,
    raw_data  -- JSONB格式，包含原始中文表头字段
FROM fact_raw_data_orders_daily
LIMIT 10;
```

---

## 📝 数据表结构说明

### 通用字段

所有B类数据表都包含以下通用字段：

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BIGINT | 主键（自增） |
| file_id | INTEGER | 关联到catalog_files表 |
| platform_code | VARCHAR | 平台代码（shopee/tiktok/amazon/miaoshou） |
| shop_id | VARCHAR | 店铺ID |
| metric_date | DATE | 指标日期（用于聚合） |
| data_hash | VARCHAR | 数据哈希（用于去重） |
| raw_data | JSONB | 原始数据（JSONB格式，保留原始中文表头） |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

### 唯一约束

所有B类数据表都有唯一约束：
- 普通数据域：`(data_domain, granularity, data_hash)` - 防止重复数据
- Services域（按sub_domain分表）：`(data_domain, sub_domain, granularity, data_hash)` - 防止重复数据

### Services域表的sub_domain字段

Services域的表包含 `sub_domain` 字段：
- `ai_assistant`：AI助手子类型
- `agent`：人工服务子类型

---

## 🔧 数据同步检查工具

### 使用后端API检查

```bash
# 检查数据同步统计
curl http://localhost:8001/api/data-sync/stats

# 检查特定文件同步状态
curl http://localhost:8001/api/data-sync/file-status?file_id=123
```

### 使用Python脚本检查

```python
# scripts/verify_database_data.py
python scripts/verify_database_data.py
```

---

## ⚠️ 重要说明

1. **DSS架构**：数据同步只做采集和存储，不做字段映射、数据标准化、业务逻辑验证
2. **JSONB格式**：原始数据以JSONB格式存储，保留原始中文表头字段
3. **去重机制**：使用`data_hash`字段自动去重（ON CONFLICT DO NOTHING）
4. **Metabase查询**：所有数据查询和业务逻辑验证在Metabase中完成

---

## 🔄 数据迁移

### v4.16.0表结构迁移

如果您的数据库中有旧的traffic或services数据，需要运行迁移脚本：

```bash
python scripts/migrate_tables_v4_16_0.py
```

迁移脚本会：
1. 将 `fact_raw_data_traffic_*` 表的数据迁移到 `fact_raw_data_analytics_*` 表
2. 将 `fact_raw_data_services_*` 表的数据按sub_domain拆分到新表
   - ai_assistant子类型 -> `fact_raw_data_services_ai_assistant_*`
   - agent子类型 -> `fact_raw_data_services_agent_*`

---

## 📚 相关文档

- `docs/DATA_SYNC_PIPELINE_VALIDATION.md` - 数据同步管道验证文档
- `docs/METABASE_DASHBOARD_SETUP.md` - Metabase配置指南
- `backend/services/raw_data_importer.py` - 数据入库服务实现
- `scripts/migrate_tables_v4_16_0.py` - v4.16.0表结构迁移脚本

