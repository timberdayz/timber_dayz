# 时间范围字段处理方案（完整版 - 支持数据粒度）

## 问题分析

对于周数据/月数据这种时间范围的数据，即使拆分为start_time和end_time，这个数据本身代表的就是这个时间范围的整体指标（比如这周的GMV、访客数等），而不是某个具体的日期。

**示例**：
- 原始数据：`日期期间 = "18/09/2025 - 24/09/2025"`，`访客数 = 1000`
- 这表示：**这一周（9月18日到9月24日）的访客数总共是1000**
- 不是：每天1000访客

## 解决方案

### 核心字段设计

1. **时间范围字段**（用于时间范围查询）
   - `start_time`: 开始时间（datetime）
   - `end_time`: 结束时间（datetime）

2. **统计日期字段**（用于按日期聚合）
   - `metric_date`: 统计日期（date，通常使用开始日期）
   - 作用：用于按日期范围查询和聚合，例如：`WHERE metric_date BETWEEN '2025-09-18' AND '2025-09-24'`

3. **粒度标识**（用于区分数据粒度）
   - `granularity`: 数据粒度（daily/weekly/monthly/custom）
   - 自动检测：根据时间范围的天数判断
     - 1天 → `daily`
     - 2-7天 → `weekly`
     - 8-31天 → `monthly`
     - >31天 → `custom`

4. **区间起始日期**（用于weekly/monthly数据）
   - `period_start`: 区间起始日期（date）
   - 作用：用于标识这个周/月数据的起始日期

### 处理流程

```
1. 用户选择"时间范围"字段
   ↓
2. 数据标准化阶段：
   - 解析时间范围：18/09/2025 - 24/09/2025
   - 拆分为：start_time = 2025-09-18 00:00:00, end_time = 2025-09-24 23:59:59
   - 设置metric_date = 2025-09-18（用于按日期聚合）
   - 计算granularity = "weekly"（7天）
   - 设置period_start = 2025-09-18
   ↓
3. 入库：
   - start_time, end_time（用于时间范围查询）
   - metric_date（用于按日期聚合）
   - granularity（用于区分数据粒度）
   - period_start（用于标识区间起始）
```

### 查询示例

**按日期范围查询**：
```sql
SELECT * FROM fact_product_metrics
WHERE metric_date BETWEEN '2025-09-18' AND '2025-09-24'
  AND granularity = 'weekly'
```

**按时间范围查询**：
```sql
SELECT * FROM fact_product_metrics
WHERE start_time >= '2025-09-18 00:00:00'
  AND end_time <= '2025-09-24 23:59:59'
```

## 已实现的修改

✅ **数据标准化器**（`backend/services/data_standardizer.py`）：
- 当检测到`time_range`字段时，自动：
  1. 拆分为`start_time`和`end_time`
  2. 设置`metric_date`（使用开始日期）
  3. 自动检测`granularity`（daily/weekly/monthly）
  4. 设置`period_start`（区间起始日期）

✅ **字段列表扩展**：
- 添加`metric_date`到date_fields列表
- 添加`start_time`和`end_time`到datetime_fields列表

## 使用说明

1. **用户操作**：在字段映射中选择"时间范围"字段（`time_range`）
2. **后端自动处理**：
   - 自动解析时间范围格式（支持多种格式）
   - 自动设置`metric_date`、`granularity`、`period_start`
   - 拆分`start_time`和`end_time`
3. **数据入库**：所有字段都会正确入库，支持按日期聚合和时间范围查询

## 优势

1. **满足两种查询需求**：
   - 按日期聚合：使用`metric_date`
   - 时间范围查询：使用`start_time`和`end_time`

2. **自动粒度识别**：无需用户手动设置粒度

3. **数据完整性**：保留时间范围信息，同时支持按日期聚合

