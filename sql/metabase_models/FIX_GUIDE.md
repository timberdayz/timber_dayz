# Metabase Models SQL 修复指南

## 修复内容

### 1. 格式化字符串处理

#### 普通数值字段
- **问题**：数据中可能包含千分位（`,`）和空格
- **修复**：使用 `replace(replace(field, ',', ''), ' ', '')` 移除千分位和空格
- **示例**：
```sql
-- 修复前
coalesce(nullif(raw_data->>'销售额', '')::numeric, 0) as sales_amount

-- 修复后
coalesce(nullif(replace(replace(raw_data->>'销售额', ',', ''), ' ', ''), '')::numeric, 0) as sales_amount
```

#### 百分比字段
- **问题**：数据中可能包含百分号（`%`）、欧洲格式（逗号作为小数分隔符 `0,00`）、空格
- **修复**：移除百分号、替换逗号为点号、移除空格，并除以100（如果原始数据是百分比格式）
- **示例**：
```sql
-- 修复前
coalesce(nullif(raw_data->>'转化率', '')::numeric, 0) as conversion_rate

-- 修复后
coalesce(nullif(replace(replace(replace(raw_data->>'转化率', '%', ''), ',', '.'), ' ', ''), '')::numeric / 100.0, 0) as conversion_rate
```

### 2. 常见百分比字段列表

需要应用百分比处理的字段：
- `click_rate` - 点击率
- `conversion_rate` - 转化率
- `bounce_rate` - 跳出率
- `positive_rate` - 好评率

### 3. 表名修正

- **Analytics Model**：使用 `fact_*_analytics_*` 表（不是 `fact_*_traffic_*`）
- **原因**：traffic域已迁移到analytics域

## 修复后的完整 SQL

请查看以下文件：
- `analytics_model_fixed.sql` - Analytics Model（已修复）
- `products_model_fixed.sql` - Products Model（待创建）
- `orders_model_fixed.sql` - Orders Model（待创建）
