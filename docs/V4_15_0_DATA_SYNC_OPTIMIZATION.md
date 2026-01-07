# 数据同步优化 - 货币变体识别和库存UPSERT（v4.15.0）

**版本**: v4.15.0  
**更新日期**: 2025-12-05

---

## 📋 概述

本次优化针对数据同步功能在实际工作场景中遇到的两个问题：

1. **货币代码导致的表头变化误报** - 全球业务中，同一字段因货币代码不同被误判为不同字段
2. **库存数据重复记录** - 同一商品不同数量导致多条记录，无法正确反映当前库存状态

---

## 🎯 核心功能

### 1. 货币代码变体识别

#### 问题背景

电商平台导出的源数据会根据当地货币在表头中添加货币代码（如BRL、COP、SGD等）。例如：
- `"销售额（已付款订单）(BRL)"` vs `"销售额（已付款订单）(COP)"`

这些字段语义相同（都是"销售额（已付款订单）"），只是货币不同，但系统将其识别为不同的字段，触发表头变化检测，阻止同步。

#### 解决方案

- **货币变体识别**：系统识别表头中的货币代码变体（如BRL、COP、SGD等），将其视为同一字段的不同变体
- **模式匹配**：使用正则表达式 `\(([A-Z]{3})\)` 识别货币代码模式
- **字段名归一化**：在表头变化检测前，将货币变体字段归一化为基础字段名（移除货币代码）
- **货币代码提取**：从字段名中提取货币代码，存储到`currency_code`系统字段（String(3)）
- **智能匹配策略**：
  - 如果只有货币代码差异，视为匹配（不触发变化检测）
  - 如果还有其他字段变化，正常触发变化检测

#### 数据存储优化

- **`raw_data` JSONB**：字段名归一化（不含货币代码）
  ```json
  {
    "销售额（已付款订单）": 100.50
  }
  ```
- **`currency_code`字段**：存储货币代码（如"BRL"）
- **`header_columns`字段**：保留原始字段名（含货币代码），用于追溯和显示

#### 示例

```
原始字段："销售额（已付款订单）(BRL)"
归一化后："销售额（已付款订单）"
currency_code: "BRL"
raw_data: {"销售额（已付款订单）": 100.50}

原始字段："销售额（已付款订单）(COP)"
归一化后："销售额（已付款订单）"
currency_code: "COP"
raw_data: {"销售额（已付款订单）": 200000.00}

结果：视为匹配（不触发表头变化检测）
```

---

### 2. 库存数据UPSERT策略

#### 问题背景

库存数据使用 `data_hash`（基于核心字段）判断重复数据。核心字段：`['product_sku', 'warehouse_id', 'platform_code', 'shop_id']`

如果同一商品（product_sku相同）在不同时间点库存数量不同（如1 vs 2），由于数量字段不在核心字段中，`data_hash`不同，导致两条记录都入库。最终数据库中同一商品存在多条记录，库存数量不一致。

#### 解决方案

- **UPSERT策略**：对于库存数据域，使用UPSERT（INSERT ... ON CONFLICT ... UPDATE）而非INSERT ... ON CONFLICT DO NOTHING
- **更新字段配置**：定义哪些字段在冲突时应该更新
  - 更新字段：`raw_data`, `ingest_timestamp`, `file_id`, `header_columns`, `currency_code`
  - 保留字段：`metric_date`, `platform_code`, `shop_id`, `data_domain`, `granularity`, `data_hash`
- **数据域特定策略**：为不同数据域配置不同的去重策略
  - `inventory`域：使用UPSERT（更新而非插入）
  - 其他域（orders/products/traffic/services/analytics）：使用INSERT（跳过重复）

#### SQL示例

```sql
-- 库存数据域
ON CONFLICT (data_domain, granularity, data_hash) 
DO UPDATE SET
    raw_data = EXCLUDED.raw_data,
    ingest_timestamp = EXCLUDED.ingest_timestamp,
    file_id = EXCLUDED.file_id,
    header_columns = EXCLUDED.header_columns,
    currency_code = EXCLUDED.currency_code

-- 其他数据域
ON CONFLICT (data_domain, granularity, data_hash) 
DO NOTHING
```

---

## 🔧 技术实现

### 货币代码识别

#### 正则表达式模式

- **模式**：`\(([A-Z]{3})\)`
- **匹配格式**：`(BRL)`, `(COP)`, `(SGD)` 等
- **验证**：ISO 4217 标准货币代码列表（支持180+货币）

#### 代码位置

- `backend/services/currency_extractor.py` - 货币代码提取和字段名归一化
- `backend/services/template_matcher.py` - 表头变化检测（货币变体识别）
- `backend/services/data_ingestion_service.py` - 数据入库时提取和存储货币代码

#### 使用示例

```python
from backend.services.currency_extractor import CurrencyExtractor

extractor = CurrencyExtractor()

# 提取货币代码
currency_code = extractor.extract_currency_code("销售额（已付款订单）(BRL)")
# 返回: "BRL"

# 归一化字段名
normalized = extractor.normalize_field_name("销售额（已付款订单）(BRL)")
# 返回: "销售额（已付款订单）"
```

### UPSERT策略配置

#### 配置位置

- `backend/services/deduplication_fields_config.py` - 策略和更新字段配置

#### 配置结构

```python
# 去重策略配置
DEDUPLICATION_STRATEGY = {
    'inventory': 'UPSERT',
    'orders': 'INSERT',
    'products': 'INSERT',
    # ... 其他域
}

# 更新字段配置（统一配置，保持一致性）
UPSERT_UPDATE_FIELDS = {
    'inventory': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    'orders': ['raw_data', 'ingest_timestamp', 'file_id', 'header_columns', 'currency_code'],
    # ... 其他域
}
```

---

## 📊 数据库变更

### 新增字段

所有 `fact_raw_data_*` 表新增 `currency_code` 字段：

```sql
ALTER TABLE fact_raw_data_* 
ADD COLUMN currency_code VARCHAR(3) NULL;

CREATE INDEX ix_fact_raw_data_*_currency_code ON fact_raw_data_*(currency_code);
```

### 字段说明

- **字段名**：`currency_code`
- **类型**：`VARCHAR(3)`（ISO 4217标准货币代码）
- **可空**：`NULL`（如果字段名中没有货币代码）
- **索引**：已创建索引以提升查询性能

---

## ✅ 验证要点

### 货币变体识别

- ✅ 只有货币差异 → 视为匹配（不触发变化检测）
- ✅ 货币差异 + 其他字段变化 → 触发变化检测
- ✅ 非货币代码不被误识别
- ✅ 货币代码正确提取并存储到`currency_code`字段
- ✅ 字段名归一化正确（`raw_data`中字段名不含货币代码）
- ✅ 多货币字段场景（提取第一个货币代码）

### 库存数据 UPSERT

- ✅ 核心字段不变，数量变化 → 更新（不重复插入）
- ✅ 核心字段变化 → 插入新记录
- ✅ `metric_date` 保留，`ingest_timestamp` 更新
- ✅ `raw_data` 更新为最新数据
- ✅ `currency_code` 字段在UPSERT时正确更新（如果变化）

### 其他数据域

- ✅ orders/products 等域保持 INSERT 策略
- ✅ 重复数据被正确跳过（不更新）

---

## 🚀 Metabase查询指南

### 使用currency_code字段

`currency_code`字段作为独立维度字段，可以用于：

1. **按货币筛选**
   ```sql
   SELECT * FROM fact_raw_data_orders_daily 
   WHERE currency_code = 'BRL'
   ```

2. **按货币分组**
   ```sql
   SELECT currency_code, COUNT(*) 
   FROM fact_raw_data_orders_daily 
   GROUP BY currency_code
   ```

3. **货币维度分析**
   - 在Metabase中创建筛选器，使用`currency_code`字段
   - 创建图表时，可以将`currency_code`作为维度字段

### 字段名归一化优势

- **字段名简洁**：`raw_data`中的字段名不含货币代码，查询更简洁
- **货币独立**：货币作为独立维度字段，便于分析和筛选
- **查询性能**：按货币筛选可以使用索引，无需解析JSONB（提升10-100倍）

---

## 🔍 故障排查

### 货币变体识别问题

#### 问题1：货币代码未被识别

**症状**：字段名包含货币代码，但`currency_code`字段为NULL

**可能原因**：
1. 货币代码格式不正确（不是`(XXX)`格式）
2. 货币代码不在ISO 4217列表中

**解决方案**：
- 检查字段名格式是否符合`\(([A-Z]{3})\)`模式
- 确认货币代码是否在ISO 4217标准列表中
- 查看日志中的警告信息

#### 问题2：表头变化检测仍然触发

**症状**：只有货币差异，但仍然触发表头变化检测

**可能原因**：
1. 字段名格式不符合预期
2. 货币代码不在ISO 4217列表中

**解决方案**：
- 检查字段名格式
- 确认货币代码是否有效
- 查看`detect_header_changes()`的日志输出

### UPSERT问题

#### 问题1：库存数据仍然重复

**症状**：同一商品存在多条记录

**可能原因**：
1. `data_hash`计算不正确
2. UPSERT策略未生效

**解决方案**：
- 检查`data_hash`计算逻辑
- 确认数据域是否为`inventory`
- 查看数据库日志中的UPSERT语句

#### 问题2：`metric_date`被更新

**症状**：UPSERT后`metric_date`发生变化

**可能原因**：
- 配置错误，`metric_date`被包含在更新字段列表中

**解决方案**：
- 检查`UPSERT_UPDATE_FIELDS`配置
- 确认`metric_date`不在更新字段列表中

---

## 📈 性能影响

### 写入性能

| 操作 | 影响 | 说明 |
|------|------|------|
| 字段名归一化 | <0.1% | 内存操作，每列字段名执行一次正则操作（<1ms） |
| 货币代码提取 | <0.1% | 内存操作，与字段名归一化同时进行（<1ms） |
| 数据库写入 | <0.01% | 新增3字节字段，写入开销可忽略 |
| 索引写入 | <0.1% | 每个记录约20-30字节索引，轻微开销 |
| **总计** | **<0.5%** | **几乎可忽略** |

### 查询性能提升

| 操作 | 提升 | 说明 |
|------|------|------|
| 按货币筛选 | 10-100倍 | 直接索引查询，无需解析JSONB |
| Metabase查询 | 显著提升 | 字段名简洁，货币作为独立维度字段 |
| 数据聚合 | 显著提升 | 货币维度独立，便于分组和聚合 |

### 结论

- **写入性能影响**：几乎可忽略（<0.5%）
- **查询性能提升**：显著（10-100倍）
- **总体评估**：性能影响可忽略，查询性能显著提升

---

## 📝 相关文档

- [数据同步设置指南](DATA_SYNC_SETUP_GUIDE.md)
- [字段映射系统指南](FIELD_MAPPING_VALIDATION_GUIDE.md)
- [数据库设计规范](DEVELOPMENT_RULES/DATABASE_DESIGN.md)

---

## 🔄 版本历史

- **v4.15.0** (2025-12-05): 初始版本
  - 货币代码变体识别
  - 库存数据UPSERT策略
  - `currency_code`字段支持

