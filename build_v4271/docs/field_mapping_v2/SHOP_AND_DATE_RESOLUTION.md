# 店铺归属与日期解析技术文档

**版本**: v1.0  
**更新日期**: 2025-01-28  
**适用系统**: 西虹ERP系统 v4.3.2+

---

## 概述

跨境电商数据文件普遍存在两大挑战：
1. **缺少店铺归属**：文件本身无店铺字段，需从路径/元数据推断
2. **多样日期格式**：不同平台/粒度（日/周/月）使用不同日期格式

本文档定义系统的智能解析策略与统一口径。

---

## 店铺归属解析（ShopResolver）

### 核心原则

- **零人工干预**：扫描阶段自动解析，高置信度直接入库
- **可追溯**：所有解析结果记录置信度与来源，便于审计
- **人工兜底**：无法解析时标记`needs_shop`，支持批量指派

### 解析优先级（6级策略）

| 优先级 | 策略 | 置信度 | 示例 |
|-------|------|-------|------|
| 1 | `.meta.json`伴生文件 | 0.95 | `business_metadata.shop_id` |
| 2 | 路径规则 | 0.85 | `profiles/shopee/account1/shop123/...` |
| 3 | `config/platform_accounts/*.json` | 0.80 | 别名映射 |
| 4 | `local_accounts.py` | 0.75 | 店铺列表匹配 |
| 5 | 文件名正则 | 0.60 | `shop_12345_...` |
| 6 | `config/shop_aliases.yaml` | 1.0 | 人工映射表 |

### 路径规则详解

**模式识别**：
```
profiles/<platform>/<account>/<shop_id>/<data_domain>/...
downloads/<platform>/<shop_id>_<date>.xlsx
data/raw/<year>/<platform>_<shop_id>_<domain>_<granularity>.xlsx
```

**提取逻辑**：
- 找到平台目录索引，向后取第2或第3个路径段
- 验证：至少6位数字 或 包含连字符/点号
- 排除：平台名、数据域名（orders/products/traffic）

### 文件名正则

**支持模式**：
- `shop_<id>` → shop_12345
- `<platform>_<shop_id>_...` → shopee_shop123_products
- 纯数字ID（≥8位）→ 20250128（排除日期后）

### 人工映射表（`config/shop_aliases.yaml`）

```yaml
shop_aliases:
  "shopee:shopee_traffic_weekly_xxx.xlsx": "shop_sg_001"
  "tiktok:my_sales_report.xlsx": "shop_my_002"
```

---

## 日期解析（SmartDateParser）

### 核心原则

- **多格式自适应**：dd/MM/yyyy、yyyy-MM-dd、Excel序列自动判定
- **统一口径**：weekly/monthly统一锚定`period_end`（区间结束日）
- **可追溯**：记录解析决策与偏好到元数据

### 格式检测策略

**抽样判定**：
- 读取前10行非空日期值
- 分别尝试`dayfirst=True`与`dayfirst=False`
- 判定逻辑：
  - 若首段>12且次段≤12 → `dayfirst=True`
  - 若次段>12且首段≤12 → `dayfirst=False`
  - 否则 → 回退文件名推断或平台默认

### 平台偏好配置（推荐）

| 平台 | 日期偏好 | 典型格式 |
|------|---------|---------|
| Shopee | dayfirst=True | 23/09/2025, 19/09/2025 |
| TikTok | dayfirst=False | 09/23/2025 |
| Amazon | dayfirst=False | 2025-09-23 |
| 妙手ERP | dayfirst=False | 2025-09-23 |

### 粒度语义与口径

#### Daily（日粒度）
- **来源**：`23/09/2025 00:00`
- **归一**：`metric_date_local = 2025-09-23`（丢弃时分秒）
- **period_start**: NULL

#### Weekly（周粒度）
- **来源**：`19/09/2025`（可能是周一或周日）
- **归一**：`metric_date_local = 2025-09-25`（取周结束日，周日）
- **period_start**: `2025-09-19`（周开始日，周一）
- **说明**：统一采用"周日为结束日"口径，便于跨平台对齐

#### Monthly（月粒度）
- **来源**：`25/08/2025` 或 `26-08-2025 - 24-09-2025`（区间）
- **归一**：`metric_date_local = 2025-09-30`（取月最后一日）
- **period_start**: `2025-09-01`
- **说明**：统一采用"月末为结束日"口径

### Excel序列值处理

```python
# Excel日期序列（1899-12-30为起点）
44818 → pd.to_datetime(44818, unit='D', origin='1899-12-30') → 2022-09-15
```

### 解析示例

```python
from modules.services.smart_date_parser import parse_date, detect_dayfirst

# 自动检测格式
samples = ["23/09/2025", "24/09/2025", "25/09/2025"]
dayfirst = detect_dayfirst(samples)  # → True

# 解析单个值
date1 = parse_date("23/09/2025 10:30", prefer_dayfirst=True)  # → 2025-09-23
date2 = parse_date(44818)  # Excel序列 → 自动识别
date3 = parse_date("2025-09-23")  # ISO格式 → 自动识别
```

---

## 跨时区处理

### 时区标准

- **local时区**：`dim_shops.timezone`（如`Asia/Singapore`）
- **UTC统一**：`metric_date_utc`（可选）

### 转换规则

```python
from pytz import timezone
import datetime

shop_tz = timezone('Asia/Singapore')  # UTC+8
local_date = datetime.date(2025, 9, 23)
local_dt = datetime.datetime.combine(local_date, datetime.time(0, 0))
utc_dt = shop_tz.localize(local_dt).astimezone(timezone('UTC'))
metric_date_utc = utc_dt.date()  # 可能是2025-09-22（若时区负偏移）
```

### 存储设计

```sql
fact_product_metrics:
  metric_date DATE NOT NULL,  -- 店铺本地日（主查询）
  metric_date_utc DATE,       -- UTC日（跨时区聚合）
  period_start DATE,          -- 周/月起始（追溯）
```

---

## 入库前强校验

### 校验规则

所有数据域入库前必须通过：
1. **shop_id非空** → 缺失则`return False, "missing shop_id (needs assignment)"`
2. **日期可解析** → 失败则隔离到`data_quarantine`
3. **必填字段存在** → 缺失则阻断并返回缺失列表

### 隔离与告警

```python
# orders/products/traffic 入口统一校验
if not cf.shop_id:
    return False, "missing shop_id (needs assignment)"

# 日期解析失败
if date_col and not parse_date(row[date_col]):
    quarantine_row(row, reason="unparseable_date", detail=str(row[date_col]))
    continue
```

---

## 前端批量指派

### API接口

```http
POST /api/field-mapping/assign-shop
Content-Type: application/json

{
  "file_ids": [1, 2, 3],
  "shop_id": "shop_sg_001",
  "auto_retry_ingest": true
}
```

**响应**：
```json
{
  "success": true,
  "message": "成功指派3个文件到店铺shop_sg_001",
  "data": {
    "updated_count": 3,
    "shop_id": "shop_sg_001",
    "retried_ingest": 2
  }
}
```

### 前端UI

字段映射审核页顶部：
- 筛选：`status='needs_shop'`
- 下拉选择：从`dim_shops`读取可用店铺列表
- 批量操作：勾选多个文件 → 选择店铺 → 点击"批量指派并重试入库"

---

## 最佳实践

### 采集阶段（推荐）

1. **规范文件命名**：`<platform>_<shop_id>_<domain>_<granularity>_<date>.xlsx`
2. **生成.meta.json**：包含`shop_id`、`date_from/to`、`timezone`
3. **按店铺分目录**：`data/raw/<year>/<platform>/<shop_id>/...`

### 手动上传（兜底）

1. 上传前在文件名加入`shop_<id>`标识
2. 或上传后在字段映射页批量指派
3. 保存为模板后，下次同平台自动沿用

### 质量监控

- 查看`catalog_files.file_metadata.shop_resolution`：
  - `confidence < 0.9` → 建议人工核查
  - `source='filename'` → 建议补充.meta.json或规范路径
- 定期审计`status='needs_shop'`文件，及时指派

---

## 更新日志

- **v1.0 (2025-01-28)**: 初始版本，定义ShopResolver与SmartDateParser规范

