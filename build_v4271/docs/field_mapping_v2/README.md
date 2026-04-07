# 字段映射v2.3系统文档总览

**版本**: v2.3  
**更新日期**: 2025-01-28  
**系统**: 西虹ERP系统 v4.3.2+

---

## 文档导航

### 核心架构文档

| 文档 | 说明 | 适用人群 |
|------|------|---------|
| [字段映射v2合同](FIELD_MAPPING_V2_CONTRACT.md) | 技术规范与API接口 | 开发者 |
| [操作手册](FIELD_MAPPING_V2_OPERATIONS.md) | 使用指南与最佳实践 | 业务用户 |
| [变更日志](CHANGELOG_FIELD_MAPPING_V2.md) | 版本更新历史 | 全员 |

### 新增技术文档（v2.3）

| 文档 | 说明 | 解决问题 |
|------|------|---------|
| [层级报表处理](HIERARCHICAL_DATA_PROCESSING.md) | 商品级+规格级并存方案 | 避免重复计数 |
| [店铺归属与日期解析](SHOP_AND_DATE_RESOLUTION.md) | 智能解析shop_id与多格式日期 | 缺店铺/多日期格式 |
| [严格入库模式](STRICT_INGESTION_MODE.md) | 未映射字段不入库 | 数据精确性 |

---

## 快速开始

### 1. 首次使用（新平台）

```bash
# Step 1: 上传样例文件到 data/raw/2025/
# 命名规范：shopee_products_daily_20250128.xlsx

# Step 2: 扫描注册
python -c "from modules.services.catalog_scanner import scan_files; scan_files()"

# Step 3: 打开字段映射审核页
# 访问：http://localhost:5173/field-mapping

# Step 4: 配置映射
# - 选择平台/数据域/文件
# - 点击"生成字段映射"（智能建议）
# - 确认或调整映射
# - 保存为模板

# Step 5: 入库
python -c "from modules.services.ingestion_worker import run_once; run_once(limit=10)"
```

### 2. 日常使用（已有模板）

```bash
# 自动流程：扫描 → 套用模板 → 自动入库
python -c "from modules.services.catalog_scanner import scan_files; scan_files()"
python -c "from modules.services.ingestion_worker import run_once; run_once()"
```

### 3. 批量指派店铺（缺shop_id时）

前端操作：
1. 字段映射审核页 → 筛选`status='needs_shop'`
2. 勾选需要指派的文件
3. 下拉选择店铺（从`dim_shops`读取）
4. 点击"批量指派并重试入库"

---

## 新特性（v2.3）

### 产品层级支持

- **自动识别**：商品汇总行与规格明细行
- **智能判定**：summary优先，否则variants求和
- **双写存储**：商品级1行（`sku_scope='product'`）+ 规格级N行（`sku_scope='variant'`）
- **查询兜底**：默认读商品级，缺失时聚合规格级

详见：[层级报表处理](HIERARCHICAL_DATA_PROCESSING.md)

### 全域店铺解析

- **零人工干预**：6级策略自动解析（.meta.json → 路径 → 配置 → 文件名 → 人工映射）
- **置信度分级**：≥0.9直接入库，0.6-0.9提示确认，<0.6标记`needs_shop`
- **批量指派**：前端一键批量设定并重试入库

详见：[店铺归属与日期解析](SHOP_AND_DATE_RESOLUTION.md)

### 智能日期解析

- **多格式自适应**：dd/MM/yyyy、yyyy-MM-dd、Excel序列自动判定
- **平台偏好**：Shopee dayfirst=True，TikTok dayfirst=False
- **统一口径**：weekly/monthly取period_end（区间结束日）
- **跨时区**：按`dim_shops.timezone`转换为本地日与UTC日

详见：[店铺归属与日期解析](SHOP_AND_DATE_RESOLUTION.md)

### 严格入库

- **字段白名单**：仅入库已映射字段，未映射列完全忽略
- **必填阻断**：缺少shop_id/sku/date等必填字段则拒绝入库
- **Ingest Report**：详细记录忽略列、缺失字段、处理统计

详见：[严格入库模式](STRICT_INGESTION_MODE.md)

---

## 数据质量保障

### 入库前校验（3道防线）

1. **必填字段**：shop_id、platform_sku、metric_date_local + 至少1个指标
2. **数据类型**：数值类/日期类/枚举类严格校验
3. **业务规则**：销量≥0、转化率0-1、日期合理范围

### 入库后监控

- **冲突检测**：orders vs products GMV差异>5%触发告警
- **质量评分**：`catalog_files.quality_score`（0-100）
- **隔离机制**：失败行进入`data_quarantine`，不污染事实表

### 可追溯性

```
文件 → catalog_files.id
  ↓
  fact_product_metrics.source_catalog_id
  ↓
  查询：哪个文件导入了这条记录？
```

---

## 性能优化

### 索引策略

```sql
-- 商品级查询（局部索引，PostgreSQL）
CREATE INDEX ix_product_product_only 
ON fact_product_metrics (platform_code, shop_id, metric_date)
WHERE sku_scope = 'product';

-- 规格级聚合
CREATE INDEX ix_product_parent_date 
ON fact_product_metrics (platform_code, shop_id, parent_platform_sku, metric_date);
```

### 物化视图

```sql
-- Top商品榜（5-15分钟刷新）
CREATE MATERIALIZED VIEW mv_top_products AS ...
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_products;
```

### 查询优化

- 榜单/趋势直读物化视图
- 明细查询限制时间范围（≤90天）
- 大表启用BRIN索引或按月分区

---

## 运维指南

### 日常检查

```bash
# 1. 查看待处理文件
python -c "from modules.services.catalog_scanner import scan_files; scan_files()"

# 2. 查看需要指派店铺的文件
# 前端：字段映射审核页 → 筛选status='needs_shop'

# 3. 批量入库
python -c "from modules.services.ingestion_worker import run_once; run_once(limit=100)"

# 4. 查看隔离数据
# 后端：SELECT * FROM data_quarantine WHERE is_resolved = false;
```

### 质量监控

```sql
-- 查看最近1周质量评分<60的文件
SELECT file_name, quality_score, status, error_message
FROM catalog_files
WHERE quality_score < 60
  AND first_seen_at >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY quality_score ASC;
```

### 问题排查

1. **预览失败**：
   - 查看结构化错误：`{code, message, tried_strategies, next_action}`
   - 尝试在Excel中重新导出为标准.xlsx

2. **入库失败**：
   - 检查`catalog_files.error_message`
   - 检查`data_quarantine`表
   - 查看后端日志

3. **数据偏差**：
   - 查看`quality_reports`表
   - 比对orders与products的GMV差异
   - 人工核查来源文件

---

## 扩展路径

### Phase 4规划（待实施）

- [ ] AI驱动的字段映射建议（GPT-4o）
- [ ] 跨平台SKU主数据管理（`dim_product_master`）
- [ ] 实时数据流接入（WebSocket/SSE）
- [ ] 移动端审核与批量操作

### 社区贡献

欢迎提交：
- 新平台字段映射模板（PR到`config/field_mappings_v2.yaml`）
- 改进建议（Issue）
- 最佳实践案例

---

## 技术支持

- 📧 技术邮箱：support@xihong-erp.com
- 📚 在线文档：https://docs.xihong-erp.com
- 💬 技术论坛：https://community.xihong-erp.com

---

## 版本历史

- **v2.3 (2025-01-28)**: 产品层级、全域店铺解析、智能日期、严格入库
- **v2.2 (2025-01-26)**: 方案B+升级（子类型、质量评分）
- **v2.1 (2025-01-20)**: 合并单元格还原、异步图片提取
- **v2.0 (2025-01-15)**: 粒度感知字段映射

