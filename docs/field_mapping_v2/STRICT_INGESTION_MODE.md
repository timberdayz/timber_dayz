# 严格入库模式技术文档

**版本**: v1.0  
**更新日期**: 2025-01-28  
**适用系统**: 西虹ERP系统 v4.3.2+

---

## 概述

**严格入库模式**（Strict Ingestion Mode）确保：
- 仅入库"已映射且通过校验"的字段
- 未映射字段一律忽略，不污染事实表
- 缺少必填字段则阻断入库并提示

核心原则：**数据精确优先**，避免"无用数据"与"字段语义错配"。

---

## 工作模式

### 严格模式（默认，推荐）

- **仅写已映射字段**：未在模板中配置映射的列一律忽略
- **必填字段阻断**：缺少任一必填字段则拒绝入库
- **生成ingest_report**：记录忽略列清单、缺失必填、模板版本

### 宽松模式（可选）

- **允许缺少可选字段**：必填字段存在即可
- **未映射字段仍忽略**：与严格模式一致
- **适用场景**：数据质量参差不齐的历史文件补录

---

## 必填字段定义

### Products（商品域）

| 字段 | 说明 | 缺失后果 |
|------|------|---------|
| `shop_id` | 店铺归属 | 阻断，提示批量指派 |
| `platform_sku` | 产品SKU | 阻断，无法写入维表 |
| `metric_date_local` | 统计日期 | 阻断，无法按时间聚合 |
| 至少1个可加总指标 | `sales_volume` 或 `sales_amount` 或 `page_views` | 阻断，无意义记录 |

### Orders（订单域）

| 字段 | 说明 | 缺失后果 |
|------|------|---------|
| `shop_id` | 店铺归属 | 阻断 |
| `order_id` | 订单唯一标识 | 阻断，主键缺失 |
| `order_date_local` | 订单日期 | 阻断 |

**明细行额外要求**：
- `platform_sku`（商品SKU）
- `quantity`（数量）

### Traffic（流量域）

| 字段 | 说明 |
|------|------|
| `shop_id` | 店铺归属 |
| `metric_date_local` | 统计日期 |
| 至少1个指标 | `page_views` 或 `unique_visitors` 或 `order_count` |

### Services（服务域）

| 字段 | 说明 |
|------|------|
| `shop_id` | 店铺归属 |
| `metric_date_local` | 统计日期 |
| 至少1个指标 | 根据子类型（agent/ai_assistant）不同 |

---

## 字段白名单机制

### 生成流程

```python
# 1. 从模板读取映射配置
template = load_template(platform, domain, granularity, sub_domain)

# 2. 生成白名单
whitelist = {
    mapping['standard_field']: mapping['source_column']
    for mapping in template['mappings']
    if mapping['source_column']  # 已映射
}

# 3. 入库时仅据白名单构建数据
for _, row in df.iterrows():
    record = {}
    for std_field, src_col in whitelist.items():
        if src_col in df.columns:
            record[std_field] = row[src_col]
    
    # 校验必填字段
    if not all(k in record for k in required_fields):
        reject_row(row, reason="missing_required_fields")
        continue
    
    upsert_fact_table(record)
```

### 未映射字段处理

- **忽略策略**：完全不读取，不占用内存
- **记录报告**：
  ```json
  {
    "ignored_columns": ["无用列A", "临时备注", "内部编码"],
    "ignored_count": 3,
    "reason": "未在模板中配置映射"
  }
  ```

---

## Ingest Report结构

### 报告内容

```json
{
  "file_id": 123,
  "file_name": "shopee_products_daily_xxx.xlsx",
  "template_version": "shopee:products:daily:v2.3",
  "ingestion_mode": "strict",
  
  "field_whitelist": [
    "platform_sku", "product_name", "sales_volume", "sales_amount", 
    "page_views", "unique_visitors"
  ],
  
  "required_fields_check": {
    "passed": true,
    "missing": []
  },
  
  "ignored_columns": {
    "columns": ["内部备注", "临时字段"],
    "count": 2
  },
  
  "rows_processed": {
    "total": 100,
    "succeeded": 95,
    "skipped": 3,
    "quarantined": 2
  },
  
  "timestamp": "2025-01-28T10:30:00Z"
}
```

### 存储位置

- **实时**：`catalog_files.validation_errors`（JSON字段）
- **历史**：可选建立`ingest_runs`表（便于长期审计）

---

## 字段组（Field Groups）

### 快捷选择

为提升用户体验，前端提供"字段组"快捷选择：

| 字段组 | 包含字段 | 适用场景 |
|--------|---------|---------|
| 核心 | SKU, 销量, GMV | 最小可用集 |
| 流量 | PV, UV, 点击率, 转化率 | 流量分析 |
| 互动 | 加购, 收藏, 分享 | 用户行为分析 |
| 评价 | 评分, 评论数, 好评率 | 商品质量监控 |
| 全部 | 所有标准字段 | 完整数据集 |

### 配置示例（`config/field_groups.yaml`）

```yaml
products:
  core:
    - platform_sku
    - product_name
    - sales_volume
    - sales_amount
  
  traffic:
    - page_views
    - unique_visitors
    - click_through_rate
    - conversion_rate
  
  engagement:
    - add_to_cart_count
    - favorites_count  # 预留
    - shares_count     # 预留
  
  reviews:
    - rating
    - review_count
```

---

## 中文用户使用指南

### 5步安全配置法

#### 步骤1：选择文件
- 平台：Shopee
- 数据域：products
- 粒度：daily

#### 步骤2：查看智能建议
- 系统自动匹配中文列名到标准字段
- 绿色：高置信度（≥90%）
- 黄色：中等置信度（60-89%）
- 灰色：未映射

#### 步骤3：确认或调整映射
- **不要改标准字段名**（保持英文小写+下划线）
- 仅调整"来源列"（下拉选择你的中文列名）
- 勾选"必填/可选"（系统已预设）

#### 步骤4：选择字段组（可选）
- 快速选择"核心"或"流量"字段组
- 未勾选字段将被忽略，不入库

#### 步骤5：校验与入库
- 点击"校验与预览入库"
- 系统显示：
  - ✅ 必填字段满足
  - ⚠️ 将忽略3列（未映射）
  - 📊 预览前10行转换结果
- 确认后保存为模板

### 6条安全规则

1. **不改英文标准名**：`order_id`、`sales_volume`保持不变
2. **一域一口径**：同一指标只在一个数据域标注为"权威"
3. **分类配置**：维度（SKU）、可加总（销量）、比率（转化率）
4. **中文同义词全**：为每个字段补充常见别名
5. **日期交给解析器**：不手工改格式
6. **保存即版本化**：每次保存模板加版本号

---

## 权威来源与冲突检测

### 权威口径（推荐）

| 指标 | 权威来源 | 兜底来源 | 说明 |
|------|---------|---------|------|
| `units_sold`（SKU级） | `fact_order_items` | `fact_product_metrics` | 订单明细最准 |
| `gmv` | `fact_orders` | `fact_product_metrics` | 订单表最准 |
| `pv/uv/加购/转化` | `fact_product_metrics` | - | 仅流量报表有 |

### 冲突监测

```sql
-- 检测orders与products报表的GMV差异
SELECT 
  o.platform_sku,
  o.metric_date,
  SUM(o.total_amount_rmb) AS gmv_from_orders,
  p.sales_amount_rmb AS gmv_from_products,
  ABS(SUM(o.total_amount_rmb) - p.sales_amount_rmb) / 
    NULLIF(GREATEST(SUM(o.total_amount_rmb), p.sales_amount_rmb), 0) AS deviation
FROM fact_orders o
JOIN fact_product_metrics p 
  ON o.platform_sku = p.platform_sku 
  AND o.metric_date = p.metric_date
WHERE p.sku_scope = 'product'
GROUP BY o.platform_sku, o.metric_date, p.sales_amount_rmb
HAVING deviation > 0.10  -- 偏差>10%
```

**告警策略**：
- 偏差5-10%：写入`quality_reports`，前端黄色标识
- 偏差>10%：写入`quality_reports`，前端红色告警，建议人工核查

---

## 前端显示规范

### 数据来源标识

所有看板/榜单显示：
```
GMV: ¥1,234,567
数据来源: orders (权威) | 最后更新: 2025-01-28 10:30
```

或：
```
GMV: ¥1,234,567
数据来源: products (回退) | 质量: 中 | 最后更新: 2025-01-28 10:30
```

### 未映射提示

字段映射页底部：
```
⚠️ 以下3列未映射，将不会入库：
  - 内部备注
  - 临时字段A
  - 无用列X

💡 提示：未映射字段不会占用数据库空间，不影响查询性能
```

---

## 性能优化

### 解析优化

- **抽样而非全表**：日期格式检测仅读前10行
- **早失败**：必填字段缺失时立即返回，不继续解析
- **缓存模板**：同批次文件共享模板，避免重复解析

### 写入优化

- **批量UPSERT**：每500行一次commit
- **索引利用**：白名单字段顺序对齐索引列
- **延迟外键**：`source_catalog_id`可为空，避免级联锁

---

## 回滚与兼容

### 切换模式

```python
# 环境变量控制
INGESTION_MODE=strict  # 默认
INGESTION_MODE=loose   # 宽松模式
```

### 模板版本控制

- 每次保存模板自动递增版本号
- `template_id = f"{platform}:{domain}:{granularity}:{sub_domain}:v{version}"`
- 支持回退到旧版本模板

---

## 最佳实践

### 首次配置（新平台）

1. 上传1个样例文件
2. 使用"智能建议"快速配置
3. 勾选"核心"字段组
4. 校验并预览
5. 保存为模板v1.0

### 模板优化（迭代）

1. 发现新列需要映射
2. 编辑模板，补充映射
3. 重新校验与预览
4. 保存为v1.1（自动递增）
5. 历史文件可选重跑

### 字段组推荐

| 业务场景 | 推荐字段组 | 说明 |
|---------|----------|------|
| 基础销售分析 | 核心 | SKU+销量+GMV |
| 营销效果评估 | 核心+流量 | 加上PV/UV/转化率 |
| 用户行为分析 | 核心+流量+互动 | 加上加购/收藏 |
| 商品质量监控 | 核心+评价 | 加上评分/评论数 |
| 完整数据集 | 全部 | 科研/深度分析 |

---

## 常见问题

### Q1: 如何知道哪些列被忽略了？

**A**: 入库后查看`ingest_report`：
- 前端：字段映射页底部显示"忽略列清单"
- 后端：`catalog_files.validation_errors.ignored_columns`

### Q2: 必填字段缺失怎么办？

**A**: 系统会阻断入库并返回：
```json
{
  "success": false,
  "reason": "missing_required_fields",
  "missing": ["shop_id", "metric_date_local"],
  "next_action": "请补充映射或使用批量指派功能"
}
```

### Q3: 能否临时关闭严格模式？

**A**: 可以，设置环境变量：
```bash
export INGESTION_MODE=loose
```
但不推荐长期使用，会降低数据质量。

### Q4: 未映射字段对性能有影响吗？

**A**: 完全没有。严格入库模式下，未映射列不会被读取、解析或存储，零性能开销。

---

## 实施检查清单

### 上线前

- [ ] 为核心业务域（orders/products/traffic）配置必填字段
- [ ] 补充中文同义词到`field_mappings_v2.yaml`
- [ ] 创建字段组配置（可选）
- [ ] 测试样例文件通过校验

### 日常运维

- [ ] 定期查看`status='needs_shop'`文件，及时指派
- [ ] 审查`ingest_report.ignored_columns`，评估是否需要补充映射
- [ ] 监控`quality_reports`，处理权威/兜底差异告警

---

## 附录：API示例

### 获取必填字段列表

```http
GET /api/field-mapping/required-fields?domain=products
```

**响应**：
```json
{
  "required_fields": ["shop_id", "platform_sku", "metric_date_local"],
  "at_least_one_of": ["sales_volume", "sales_amount", "page_views"]
}
```

### 入库前校验

```http
POST /api/field-mapping/validate
{
  "file_id": 123,
  "mappings": [...]
}
```

**响应**：
```json
{
  "success": false,
  "required_check": {
    "passed": false,
    "missing": ["shop_id"]
  },
  "next_action": "使用批量指派功能设定店铺"
}
```

---

## 更新日志

- **v1.0 (2025-01-28)**: 初始版本，定义严格入库规范与字段白名单机制

