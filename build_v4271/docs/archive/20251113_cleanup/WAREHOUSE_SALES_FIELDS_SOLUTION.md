# 仓库和销量字段解决方案

**日期**: 2025-11-05  
**版本**: v4.6.3  
**状态**: ✅ 已完成  

## 📋 问题描述

用户发现妙手ERP产品数据域中，仓库和近期销量字段都在使用拼音命名映射，这不符合系统的标准命名规范。

### 发现的拼音映射

| 中文字段 | 拼音映射 | 说明 |
|---------|---------|------|
| 仓库 | `cang_ku` | 货物存放仓库位置 |
| 近7天销量数据 | `jin_7_tian_xiao_liang_shu_ju` | 近7天销售数量 |
| 近30天销量数据 | `jin_30_tian_xiao_liang_shu_ju` | 近30天销售数量 |
| 近60天销量数据 | `jin_60_tian_xiao_liang_shu_ju` | 近60天销售数量 |
| 近90天销量数据 | `jin_90_tian_xiao_liang_shu_ju` | 近90天销售数量 |

## 📊 字段说明

### 仓库字段

**用途**: 记录货物存放的仓库位置

**数据示例**:
- `新加坡+部分菲律宾` - 主要在新加坡，部分在菲律宾
- `菲律宾3店-时尚箱包` - 仅存放于菲律宾第3店

**特点**:
- 信息较为复杂，包含地理位置和店铺信息
- 只需完整存储即可，不需要像时间字段那样做分析处理
- 用于说明货物存放位置

### 近期销量字段

**用途**: 追踪产品在不同时间段的销售情况

**字段列表**:
1. **近7天销量数据** - 短期销售趋势
2. **近30天销量数据** - 月度销售情况
3. **近60天销量数据** - 季度销售趋势
4. **近90天销量数据** - 长期销售趋势

**重要性**:
- 对销售分析和库存管理非常重要
- 帮助识别热销产品和滞销产品
- 支持销售趋势预测

## ✅ 解决方案

### Step 1: 扩展数据库表

#### 1.1 更新`schema.py`

```python
# 仓库信息（v4.6.3扩展）
warehouse = Column(String(256), nullable=True, comment="货物存放仓库位置")

# 近期销量数据（v4.6.3新增 - 妙手ERP产品快照）
sales_volume_7d = Column(Integer, nullable=True, comment="近7天销量")
sales_volume_30d = Column(Integer, nullable=True, comment="近30天销量")
sales_volume_60d = Column(Integer, nullable=True, comment="近60天销量")
sales_volume_90d = Column(Integer, nullable=True, comment="近90天销量")
```

#### 1.2 添加数据库列

```sql
ALTER TABLE fact_product_metrics ADD COLUMN warehouse VARCHAR(256) NULL;
ALTER TABLE fact_product_metrics ADD COLUMN sales_volume_7d INTEGER NULL;
ALTER TABLE fact_product_metrics ADD COLUMN sales_volume_30d INTEGER NULL;
ALTER TABLE fact_product_metrics ADD COLUMN sales_volume_60d INTEGER NULL;
ALTER TABLE fact_product_metrics ADD COLUMN sales_volume_90d INTEGER NULL;
```

### Step 2: 添加标准字段映射

| field_code | cn_name | en_name | data_type | synonyms |
|------------|---------|---------|-----------|----------|
| `warehouse` | 仓库 | Warehouse | string | 仓库, warehouse, 仓库位置, 存放仓库 |
| `sales_volume_7d` | 近7天销量数据 | Sales Volume (7 days) | integer | 近7天销量数据, 近7天销量, 7天销量 |
| `sales_volume_30d` | 近30天销量数据 | Sales Volume (30 days) | integer | 近30天销量数据, 近30天销量, 30天销量 |
| `sales_volume_60d` | 近60天销量数据 | Sales Volume (60 days) | integer | 近60天销量数据, 近60天销量, 60天销量 |
| `sales_volume_90d` | 近90天销量数据 | Sales Volume (90 days) | integer | 近90天销量数据, 近90天销量, 90天销量 |

### Step 3: 删除拼音映射

删除的旧映射：
- ❌ `cang_ku`
- ❌ `jin_7_tian_xiao_liang_shu_ju`
- ❌ `jin_30_tian_xiao_liang_shu_ju`
- ❌ `jin_60_tian_xiao_liang_shu_ju`
- ❌ `jin_90_tian_xiao_liang_shu_ju`

## 🎯 映射效果

### Before（清理前）
```
仓库 → cang_ku ❌ (拼音)
近7天销量数据 → jin_7_tian_xiao_liang_shu_ju ❌ (拼音)
近30天销量数据 → jin_30_tian_xiao_liang_shu_ju ❌ (拼音)
近60天销量数据 → jin_60_tian_xiao_liang_shu_ju ❌ (拼音)
近90天销量数据 → jin_90_tian_xiao_liang_shu_ju ❌ (拼音)
```

### After（清理后）
```
仓库 → warehouse ✅ (标准英文)
近7天销量数据 → sales_volume_7d ✅ (标准英文)
近30天销量数据 → sales_volume_30d ✅ (标准英文)
近60天销量数据 → sales_volume_60d ✅ (标准英文)
近90天销量数据 → sales_volume_90d ✅ (标准英文)
```

## 📊 数据使用场景

### 仓库字段使用

```sql
-- 查询特定仓库的库存
SELECT product_name, warehouse, total_stock, available_stock
FROM fact_product_metrics
WHERE warehouse LIKE '%新加坡%'
ORDER BY total_stock DESC;

-- 按仓库统计库存
SELECT 
    warehouse,
    COUNT(*) as product_count,
    SUM(total_stock) as total_inventory
FROM fact_product_metrics
GROUP BY warehouse;
```

### 销量字段使用

```sql
-- 查询热销产品（近30天销量大于100）
SELECT 
    product_name, 
    warehouse,
    sales_volume_7d,
    sales_volume_30d,
    sales_volume_90d
FROM fact_product_metrics
WHERE sales_volume_30d > 100
ORDER BY sales_volume_30d DESC;

-- 分析销售趋势
SELECT 
    product_name,
    sales_volume_7d,
    sales_volume_30d,
    sales_volume_60d,
    sales_volume_90d,
    CASE 
        WHEN sales_volume_7d > sales_volume_30d/4 THEN '上升趋势'
        WHEN sales_volume_7d < sales_volume_30d/4 THEN '下降趋势'
        ELSE '稳定'
    END as trend
FROM fact_product_metrics
WHERE sales_volume_90d > 0;

-- 识别滞销产品
SELECT 
    product_name,
    warehouse,
    total_stock,
    sales_volume_90d
FROM fact_product_metrics
WHERE total_stock > 100 
    AND sales_volume_90d < 10
ORDER BY total_stock DESC;
```

## 🔍 验证方法

### 方法1: 检查表结构

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'fact_product_metrics'
    AND (column_name = 'warehouse'
         OR column_name LIKE 'sales_volume_%d')
ORDER BY ordinal_position;
```

**期望输出**:
```
warehouse       | character varying(256)
sales_volume_7d | integer
sales_volume_30d | integer
sales_volume_60d | integer
sales_volume_90d | integer
```

### 方法2: 检查字段映射

```sql
SELECT field_code, cn_name, en_name
FROM field_mapping_dictionary
WHERE data_domain = 'products'
    AND (field_code = 'warehouse'
         OR field_code LIKE 'sales_volume_%d')
ORDER BY field_code;
```

**期望输出**:
```
sales_volume_30d | 近30天销量数据 | Sales Volume (30 days)
sales_volume_60d | 近60天销量数据 | Sales Volume (60 days)
sales_volume_7d  | 近7天销量数据  | Sales Volume (7 days)
sales_volume_90d | 近90天销量数据 | Sales Volume (90 days)
warehouse        | 仓库          | Warehouse
```

### 方法3: 验证无重复映射

```bash
python scripts/check_duplicate_mappings.py
```

**期望输出**:
```
[OK] No duplicate Chinese names found in 'products' domain.
[OK] No duplicate field codes found in 'products' domain.
[OK] No duplicates found across all data domains.
```

## 📝 字段映射配置

### 导入时的映射

当您重新导入妙手产品数据时，应该看到：

| Excel列名 | 映射到 | 字段代码 | 状态 |
|-----------|-------|---------|------|
| 仓库 | 仓库 | `warehouse` | ✅ 自动映射，高置信度 |
| 近7天销量数据 | 近7天销量数据 | `sales_volume_7d` | ✅ 自动映射，高置信度 |
| 近30天销量数据 | 近30天销量数据 | `sales_volume_30d` | ✅ 自动映射，高置信度 |
| 近60天销量数据 | 近60天销量数据 | `sales_volume_60d` | ✅ 自动映射，高置信度 |
| 近90天销量数据 | 近90天销量数据 | `sales_volume_90d` | ✅ 自动映射，高置信度 |

**重要**: 每个字段的下拉菜单现在只有**1个**选项！

## 🎓 应用场景

### 场景1: 库存管理

利用仓库字段和库存字段，实现多仓库库存管理：

```sql
SELECT 
    warehouse,
    COUNT(*) as sku_count,
    SUM(total_stock) as total_inventory,
    SUM(available_stock) as available_inventory,
    SUM(in_transit_stock) as in_transit_inventory
FROM fact_product_metrics
WHERE platform_code = 'miaoshou'
GROUP BY warehouse
ORDER BY total_inventory DESC;
```

### 场景2: 销售分析

利用近期销量字段，分析销售趋势：

```sql
-- 计算销售加速度（7天销量 vs 30天平均日销量）
SELECT 
    product_name,
    warehouse,
    sales_volume_7d,
    sales_volume_30d,
    ROUND(sales_volume_7d::numeric / 7, 2) as avg_daily_7d,
    ROUND(sales_volume_30d::numeric / 30, 2) as avg_daily_30d,
    CASE 
        WHEN sales_volume_7d / 7.0 > sales_volume_30d / 30.0 * 1.2 THEN '快速增长'
        WHEN sales_volume_7d / 7.0 < sales_volume_30d / 30.0 * 0.8 THEN '销量下降'
        ELSE '稳定'
    END as trend
FROM fact_product_metrics
WHERE sales_volume_30d > 0
ORDER BY (sales_volume_7d / 7.0) / (sales_volume_30d / 30.0) DESC;
```

### 场景3: 补货建议

结合库存和销量数据，生成补货建议：

```sql
-- 补货优先级分析
SELECT 
    product_name,
    warehouse,
    available_stock,
    sales_volume_30d,
    ROUND(available_stock::numeric / (sales_volume_30d::numeric / 30), 1) as days_of_stock,
    CASE 
        WHEN available_stock < sales_volume_30d / 30 * 7 THEN '紧急补货'
        WHEN available_stock < sales_volume_30d / 30 * 14 THEN '需要补货'
        WHEN available_stock < sales_volume_30d / 30 * 30 THEN '考虑补货'
        ELSE '库存充足'
    END as restock_priority
FROM fact_product_metrics
WHERE sales_volume_30d > 0
    AND platform_code = 'miaoshou'
ORDER BY days_of_stock ASC, sales_volume_30d DESC;
```

## 📚 相关文档

- **库存价格映射方案**: `docs/INVENTORY_PRICE_MAPPING_SOLUTION.md`
- **重复映射解决报告**: `docs/DUPLICATE_MAPPING_RESOLUTION_REPORT.md`
- **导入操作指南**: `docs/HOW_TO_IMPORT_MIAOSHOU_PRODUCTS.md`

## ✅ 总结

### 完成的工作

- ✅ 扩展`fact_product_metrics`表，添加5个新字段
- ✅ 更新`schema.py`添加字段定义
- ✅ 添加5个标准英文命名的字段映射
- ✅ 删除5个拼音命名的旧映射
- ✅ 验证所有映射唯一性

### 清理统计

| 项目 | 数量 |
|------|------|
| 新增字段 | 5个 |
| 新增映射 | 5个 |
| 删除拼音映射 | 5个 |
| 映射冲突 | 0个 ✅ |

### 系统改进

1. **标准化命名** - 所有字段使用英文命名
2. **数据完整性** - 支持完整的仓库和销量数据
3. **唯一映射** - 每个字段只有一个映射选项
4. **业务支持** - 支持库存管理和销售分析

---

**文档版本**: v1.0  
**最后更新**: 2025-11-05  
**作者**: AI Agent  
**状态**: ✅ 已完成并验证

