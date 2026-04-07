# 层级报表处理规则与实现指南

**版本**: v1.0  
**更新日期**: 2025-01-28  
**适用系统**: 西虹ERP系统 v4.3.2+

---

## 概述

跨境电商平台（如Shopee、TikTok）的产品报表经常包含"商品汇总行+规格明细行"的混合结构。本文档定义了系统如何自动识别、解析并入库这类层级数据，确保：
- **不重复计数**：商品级与规格级数据并存，查询默认不重复
- **完整性**：既保留商品级汇总，也保留规格级明细
- **可追溯**：明确记录判定依据与置信度

---

## 数据结构示例

### Shopee产品报表典型结构

| 商品编号 | 规格编号 | 规格名称 | 商品 | 成交件数 | 商品交易总额(SGD) | 页面浏览次数 | 独立访客 |
|---------|---------|---------|------|----------|------------------|--------------|---------|
| 24742609432 | (空) | (空) | 商品A | 56 | 1,203.60 | 1361 | 800 |
| 24742609432 | 178777528153 | Gray | 商品A | 32 | 635.82 | 80 | - |
| 24742609432 | 178777528154 | Pink | 商品A | 8 | 176.17 | 23 | - |
| 24742609432 | 178777528155 | Black | 商品A | 14 | 303.09 | 41 | - |
| 24742609432 | 178777528156 | White | 商品A | 4 | 88.72 | 14 | - |

**解读**：
- 第1行：商品级汇总（`规格编号`为空），销量=56，浏览=1361
- 第2-5行：规格级明细，各规格分别统计
- 特点：
  - 可加总指标（销量/销售额）：summary与variants接近一致（32+8+14+4=54≈56）
  - 流量指标（浏览/访客）：部分仅在summary有值，部分在variants有值

---

## 自动识别规则

### 列识别

系统自动识别以下关键列（基于`config/field_mappings_v2.yaml`）：

| 标准字段 | 中文同义词 | 英文同义词 |
|---------|----------|-----------|
| `product_id` | 商品编号、商品ID | Item ID, Product ID |
| `variant_id` | 规格编号、型号 | Model ID, Variation ID |
| `sales_volume` | 成交件数、销量 | Sold Count, Sales |
| `sales_amount` | 商品交易总额、销售额 | GMV, Revenue |
| `page_views` | 页面浏览次数、浏览量 | Page Views |
| `unique_visitors` | 独立访客、去重浏览 | Unique Visitors, UV |

### 行分类逻辑

按`product_id`分组后，对组内每行判定：
- **summary行（商品汇总）**：`variant_id`为空 且 属性列（颜色/尺码/规格名等）为空
- **variant行（规格明细）**：`variant_id`非空 或 属性列非空

### 一致性阈值校验

对于每个`product_id`组，计算：
- `S` = summary行的指标值
- `V` = 所有variant行的求和值
- `偏差% = |S - V| / max(S, V)`

**阈值规则**：
- 可加总指标（销量/GMV）：偏差≤5%
- 流量指标（PV/UV）：偏差≤10%（因平台统计口径差异）

**判定**：
- 若任一核心指标偏差≤阈值 → 判定"存在汇总行"
- 否则 → 判定"无汇总行"（可能是纯变体报表或数据质量问题）

---

## 入库策略

### 商品级（`sku_scope='product'`）

- **有汇总行且一致性通过** → 直接写入summary行数据
- **无汇总行** → 对所有variant行求和/加权平均后写入
  - 可加总指标：求和（sales_volume, sales_amount, page_views等）
  - 比率指标：加权平均（conversion_rate = 总订单数/总访客数）

### 规格级（`sku_scope='variant'`）

- 对每个variant行分别写入
- `platform_sku` = `{product_id}::{variant_id}`（避免与商品级冲突）
- `parent_platform_sku` = `product_id`（建立主从关系）

### 数据模型

```sql
CREATE TABLE fact_product_metrics (
    platform_code VARCHAR(32),
    shop_id VARCHAR(64),
    platform_sku VARCHAR(128),
    metric_date DATE,
    granularity VARCHAR(16),
    sku_scope VARCHAR(8) DEFAULT 'product',  -- product | variant
    parent_platform_sku VARCHAR(128),  -- 规格级指向商品级
    
    sales_volume INTEGER,
    sales_amount FLOAT,
    page_views INTEGER,
    unique_visitors INTEGER,
    -- ... 更多指标
    
    UNIQUE (platform_code, shop_id, platform_sku, metric_date, granularity, sku_scope)
);
```

---

## 查询不重复计数

### 默认查询（推荐）

```python
# 仅读取商品级，避免重复计数
SELECT * FROM fact_product_metrics
WHERE sku_scope = 'product'
  AND platform_code = 'shopee'
  AND metric_date >= '2025-01-01';
```

### 兜底聚合（商品级缺失时）

```python
# 若某商品无product行，则聚合variant行
WITH product_level AS (
  SELECT * FROM fact_product_metrics WHERE sku_scope = 'product'
),
variant_agg AS (
  SELECT 
    parent_platform_sku AS platform_sku,
    metric_date,
    SUM(sales_volume) AS sales_volume,
    SUM(sales_amount) AS sales_amount,
    SUM(page_views) AS page_views
  FROM fact_product_metrics
  WHERE sku_scope = 'variant'
    AND parent_platform_sku NOT IN (SELECT platform_sku FROM product_level)
  GROUP BY parent_platform_sku, metric_date
)
SELECT * FROM product_level
UNION ALL
SELECT * FROM variant_agg;
```

### 规格明细查询

```python
# 需要规格级分析时，显式过滤
SELECT * FROM fact_product_metrics
WHERE sku_scope = 'variant'
  AND parent_platform_sku = 'PROD003';
```

---

## 可解释性与审计

### 判定决策记录

系统将层级判定结果写入`catalog_files.file_metadata.ingest_decision`：

```json
{
  "has_summary": true,
  "summary_row_count": 1,
  "variant_row_count": 4,
  "deviation": {
    "sales_volume": 0.02,  // 2%偏差
    "sales_amount": 0.00,
    "page_views": 0.10     // 10%偏差
  },
  "strategy": "prefer_summary",
  "confidence": 0.95
}
```

### 前端提示

字段映射审核页顶部显示：
- "识别为：有汇总（置信度95%）| 商品级1行，规格级4行"
- "销量偏差2%，GMV偏差0%，浏览量偏差10%"

---

## 平台差异与扩展

### 已支持平台

| 平台 | 商品ID列 | 规格ID列 | 属性列 |
|------|---------|---------|--------|
| Shopee | 商品编号 | 规格编号、Model ID | 规格名称、颜色分类 |
| TikTok | 商品ID | 型号 | 颜色、尺码 |
| 妙手ERP | 商品编号 | 款号 | 属性 |

### 扩展新平台

在`config/field_mappings_v2.yaml`补充同义词：

```yaml
<platform>:
  products:
    common:
      product_id:
        - "<你的商品ID列名>"
      variant_id:
        - "<你的规格ID列名>"
      # ... 其他指标
```

---

## 常见问题

### Q1: summary与variants偏差>5%怎么办？
**A**: 系统会保守处理：
- 仍写入商品级与规格级两类数据
- 降低置信度，标记文件为`needs_review`
- 前端提示"数据偏差较大（xx%），建议检查来源文件"
- 用户可选"强制商品级=变体求和"或人工指派

### Q2: 没有summary行，只有variants，怎么处理？
**A**: 系统自动对variants求和，生成商品级记录，并标注来源为"aggregated_from_variants"。

### Q3: 没有variant_id列，但有颜色/尺码等属性列？
**A**: 系统自动组合属性列生成临时`variant_id`（如"红色+L"），视为规格级处理。

### Q4: 查询时如何避免重复计数？
**A**: 
- 榜单/看板默认`WHERE sku_scope='product'`
- 后端查询服务提供`prefer_scope='auto'`参数，自动选择商品级或聚合规格级
- 前端显示"数据来源：商品级/规格级聚合"

---

## 回滚与兼容

### 回滚策略
- 数据库迁移可逆：删除新增列与索引，恢复旧唯一索引
- Feature Flag: `PRODUCT_VARIANT_SCOPE_ENABLED=false` 可关闭variant行写入，仅保留商品级

### 向后兼容
- 旧数据自动视为`sku_scope='product'`（默认值）
- 现有查询不受影响（索引调整不破坏读取）

---

## 性能优化建议

### 局部索引（PostgreSQL）

```sql
CREATE INDEX CONCURRENTLY ix_product_product_only 
ON fact_product_metrics (platform_code, shop_id, metric_date)
WHERE sku_scope = 'product';
```

### 物化视图（Top商品榜）

```sql
CREATE MATERIALIZED VIEW mv_top_products AS
SELECT 
  platform_code,
  shop_id,
  platform_sku,
  SUM(sales_amount_rmb) AS total_gmv,
  SUM(sales_volume) AS total_units
FROM fact_product_metrics
WHERE sku_scope = 'product'
  AND metric_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY platform_code, shop_id, platform_sku
ORDER BY total_gmv DESC
LIMIT 100;

-- 定时刷新（每15分钟）
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_products;
```

---

## 附录：契约测试样例

详见：`temp/development/test_product_hierarchy_sample.py`

运行方式：
```bash
# 1. 生成样例文件
python temp/development/test_product_hierarchy_sample.py

# 2. 扫描并入库
python -c "from modules.services.catalog_scanner import scan_files; scan_files('temp/development')"
python -c "from modules.services.ingestion_worker import run_once; run_once(limit=10, domains=['products'])"

# 3. 验证结果
python temp/development/test_product_hierarchy_sample.py verify
```

预期结果：
- 场景1（仅summary）: 1条商品级，0条规格级
- 场景2（仅variants）: 1条商品级（求和），4条规格级
- 场景3（summary+variants）: 1条商品级（summary），4条规格级

---

## 更多资源

- [字段映射v2总览](FIELD_MAPPING_V2_CONTRACT.md)
- [字段映射v2操作手册](FIELD_MAPPING_V2_OPERATIONS.md)
- [店铺归属与日期解析](SHOP_AND_DATE_RESOLUTION.md)

