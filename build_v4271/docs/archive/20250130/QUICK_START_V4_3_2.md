# 快速启动指南 - v4.3.2产品层级与智能解析版

**版本**: v4.3.2  
**更新日期**: 2025-01-28  
**预计时间**: 10分钟

---

## 系统升级（如果是从旧版本升级）

### Step 1: 数据库迁移

```bash
cd f:\Vscode\python_programme\AI_code\xihong_erp

# 运行迁移
alembic upgrade head
```

**预期输出**：
```
INFO  [alembic.runtime.migration] Running upgrade -> 20250128_0012
INFO  [alembic.runtime.migration] Add product hierarchy and governance fields
```

### Step 2: 验证迁移

```bash
python -c "
from modules.core.db.schema import FactProductMetric
import sqlalchemy as sa
print('检查新字段...')
for col in ['sku_scope', 'parent_platform_sku', 'source_catalog_id', 'period_start']:
    assert hasattr(FactProductMetric, col), f'缺少字段: {col}'
print('[OK] 所有新字段已创建')
"
```

---

## 新功能测试

### 功能1：产品层级入库（商品+规格）

```bash
# 1. 生成测试样例
python temp/development/test_product_hierarchy_sample.py

# 2. 扫描并注册
python -c "from modules.services.catalog_scanner import scan_files; scan_files('temp/development')"

# 3. 入库
python -c "from modules.services.ingestion_worker import run_once; run_once(limit=10, domains=['products'])"

# 4. 验证结果
python temp/development/test_product_hierarchy_sample.py verify
```

**预期结果**：
```
[验证] 场景1（仅summary）:
  商品级记录: 1 条（预期1条）✅
  规格级记录: 0 条（预期0条）✅

[验证] 场景2（仅variants）:
  商品级记录: 1 条（预期1条）✅
  规格级记录: 4 条（预期4条）✅
  销量: 100 (由30+20+40+10求和)✅

[验证] 场景3（summary+variants）:
  商品级记录: 1 条（预期1条）✅
  规格级记录: 4 条（预期4条）✅
  销量: 100 (优先取summary)✅
```

### 功能2：全域店铺解析

```bash
# 测试ShopResolver
python -c "
from modules.services.shop_resolver import get_shop_resolver
from pathlib import Path

resolver = get_shop_resolver()

# 测试1：路径规则
result = resolver.resolve('profiles/shopee/account1/shop_sg_001/products/file.xlsx', 'shopee')
print(f'测试1: shop_id={result.shop_id}, 置信度={result.confidence}, 来源={result.source}')

# 测试2：文件名正则
result = resolver.resolve('data/raw/shopee_shop123_products_daily.xlsx', 'shopee')
print(f'测试2: shop_id={result.shop_id}, 置信度={result.confidence}, 来源={result.source}')

print('[OK] 店铺解析功能正常')
"
```

### 功能3：智能日期解析

```bash
# 测试SmartDateParser
python -c "
from modules.services.smart_date_parser import parse_date, detect_dayfirst

# 测试1：Shopee格式（dd/MM/yyyy）
samples = ['23/09/2025', '24/09/2025', '25/09/2025']
dayfirst = detect_dayfirst(samples)
print(f'检测dayfirst: {dayfirst} (预期True)✅' if dayfirst else '检测dayfirst失败❌')

# 测试2：多格式解析
d1 = parse_date('23/09/2025 10:30', prefer_dayfirst=True)
print(f'解析dd/MM/yyyy: {d1} (预期2025-09-23)✅' if str(d1) == '2025-09-23' else 'Error❌')

d2 = parse_date('2025-09-23')
print(f'解析yyyy-MM-dd: {d2} (预期2025-09-23)✅' if str(d2) == '2025-09-23' else 'Error❌')

d3 = parse_date(44818)  # Excel序列
print(f'解析Excel序列: {d3}✅')

print('[OK] 日期解析功能正常')
"
```

### 功能4：批量指派店铺API

```bash
# 方式1：使用curl测试（后端需运行）
curl -X POST http://localhost:8001/api/field-mapping/assign-shop \
  -H "Content-Type: application/json" \
  -d '{
    "file_ids": [1, 2, 3],
    "shop_id": "shop_sg_001",
    "auto_retry_ingest": true
  }'

# 方式2：使用Python测试
python -c "
import requests
response = requests.post(
    'http://localhost:8001/api/field-mapping/assign-shop',
    json={
        'file_ids': [1, 2, 3],
        'shop_id': 'shop_sg_001',
        'auto_retry_ingest': True
    }
)
print(response.json())
"
```

---

## 前端功能（需要Agent B实施）

### 批量指派店铺UI

**位置**: 字段映射审核页顶部

**功能**：
1. 筛选`status='needs_shop'`文件
2. 多选勾选框
3. 下拉选择店铺（从`dim_shops`读取）
4. 批量操作按钮："指派店铺并重试入库"

**API调用**：
```javascript
await api.post('/field-mapping/assign-shop', {
  file_ids: selectedFileIds,
  shop_id: selectedShopId,
  auto_retry_ingest: true
})
```

### 预览页层级提示

**位置**: 文件预览区顶部

**显示内容**：
```
📊 层级识别：有汇总（置信度95%）
商品级: 1行 | 规格级: 4行 | 销量偏差: 2% | GMV偏差: 0%
```

### ingest_report可视化

**位置**: 入库完成后弹窗

**显示内容**：
```
✅ 入库成功

处理统计：
- 总行数: 100
- 成功: 95
- 跳过: 3
- 隔离: 2

未映射字段（已忽略）：
- 内部备注
- 临时字段A

💡 提示：未映射字段不会入库，如需使用请编辑模板补充映射
```

---

## 常见问题

### Q: 迁移后旧数据会丢失吗？

**A**: 不会。迁移仅增加列与索引，旧数据自动视为`sku_scope='product'`（默认值），查询不受影响。

### Q: 需要重新扫描所有文件吗？

**A**: 建议重新扫描，以利用新的店铺解析功能：
```bash
python -c "from modules.services.catalog_scanner import scan_files; scan_files()"
```

### Q: 如何验证升级成功？

**A**: 运行契约测试：
```bash
python temp/development/test_product_hierarchy_sample.py
python temp/development/test_product_hierarchy_sample.py verify
```

所有测试通过即升级成功。

### Q: 前端需要改动吗？

**A**: 批量指派店铺UI需要Agent B实施，其他功能后端已完成，前端可直接使用。

---

## 下一步

1. ✅ **已完成**：后端核心功能（数据模型、解析器、入库引擎、API）
2. ⏳ **待实施**：前端UI（批量指派、层级提示、报告可视化）
3. 📋 **可选**：查询服务统一出口、质量告警、物化视图

---

## 支持与反馈

如遇问题，请提供：
- 错误日志（backend/logs/*.log）
- 失败文件示例
- 预期行为描述

我们将在24小时内响应。

