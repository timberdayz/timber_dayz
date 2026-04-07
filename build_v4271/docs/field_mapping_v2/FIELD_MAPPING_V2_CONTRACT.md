# 字段映射系统 v2 API 契约与使用说明

**版本**: v2.3  
**更新日期**: 2025-10-27  
**状态**: 生产就绪

---

## 核心变更

### 从 file_name 迁移到 file_id

**背景**: v1 版本使用 `file_name` 作为文件标识，存在以下问题：
- 文件名可能重复或包含特殊字符
- 前端传递对象导致序列化为 `[object Object]`
- 查询性能依赖文件名模糊匹配

**解决方案**: v2 版本统一使用 `file_id`（catalog_files.id）作为唯一标识。

**影响范围**:
- ✅ 所有查询/预览/入库接口仅接受 `file_id`
- ❌ 不再支持 `file_name` 参数（返回 400）
- ✅ 前端选择器 value=id，label 显示可读信息

---

## API 契约（最终版）

### 1. GET /api/field-mapping/file-groups

**功能**: 获取文件分组信息（平台/数据域/文件列表）

**请求**: 无参数

**响应**:
```json
{
  "platforms": ["shopee", "tiktok", "miaoshou"],
  "domains": {
    "orders": ["daily", "weekly", "monthly"],
    "products": ["daily", "weekly", "monthly", "snapshot"]
  },
  "files": {
    "shopee": {
      "orders": [
        {
          "id": 1,
          "file_name": "shopee_orders_monthly_20250925.xlsx",
          "sub_domain": "",
          "granularity": "monthly",
          "date_from": "2025-09-01",
          "date_to": "2025-09-30"
        }
      ]
    }
  }
}
```

**关键变更**: `files` 列表项包含 `id` 字段（必选）。

---

### 2. GET /api/field-mapping/file-info?file_id=

**功能**: 获取文件详细信息

**请求参数**:
- `file_id` (int, required): catalog_files.id

**响应**:
```json
{
  "success": true,
  "file_name": "shopee_orders_monthly_20250925.xlsx",
  "actual_path": "F:/Vscode/python_programme/AI_code/xihong_erp/data/raw/2025/shopee_orders_monthly_20250925.xlsx",
  "file_exists": true,
  "file_size": 1048576,
  "parsed_metadata": {
    "platform": "shopee",
    "data_type": "orders",
    "granularity": "monthly",
    "date_range": "2025-09-01 到 2025-09-30"
  }
}
```

**错误响应**:
```json
{
  "success": false,
  "file_name": null,
  "error": "文件未注册，请点击'扫描采集文件'刷新"
}
```

---

### 3. POST /api/field-mapping/preview

**功能**: 预览文件数据（含合并单元格还原）

**请求**:
```json
{
  "file_id": 1,
  "header_row": 1
}
```

**参数说明**:
- `file_id` (int, required): catalog_files.id
- `header_row` (int, optional): 表头行号（0=无表头，≥1=人类行号）

**响应**:
```json
{
  "success": true,
  "file_path": "data/raw/2025/shopee_orders_monthly_20250925.xlsx",
  "file_name": "shopee_orders_monthly_20250925.xlsx",
  "columns": ["订单号", "商品名称", "数量", "金额", "状态"],
  "data": [
    {"订单号": "12345", "商品名称": "商品A", "数量": 1, "金额": 100, "状态": "已发货"},
    {"订单号": "12345", "商品名称": "商品B", "数量": 2, "金额": 200, "状态": "已发货"}
  ],
  "total_rows": 100,
  "preview_rows": 2,
  "normalization_report": {
    "filled_columns": ["订单号", "状态"],
    "filled_rows": 50,
    "strategy": "heuristic_ffill"
  }
}
```

**合并单元格还原**:
- 自动识别订单号、状态等维度列的合并单元格
- 使用前向填充（ffill）还原空白行
- 金额/数量等度量列永不填充
- 返回 `normalization_report` 记录填充详情

---

### 4. POST /api/field-mapping/generate-mapping

**功能**: 生成智能字段映射

**请求**:
```json
{
  "columns": ["订单号", "商品名称", "数量"],
  "domain": "orders"
}
```

**响应**:
```json
{
  "success": true,
  "mappings": [
    {
      "original": "订单号",
      "standard": "order_id",
      "confidence": 1.0,
      "method": "exact_match"
    },
    {
      "original": "商品名称",
      "standard": "product_name",
      "confidence": 0.8,
      "method": "fuzzy_match"
    }
  ]
}
```

---

### 5. POST /api/field-mapping/ingest

**功能**: 数据入库（验证 + 入库 + 更新状态）

**请求**:
```json
{
  "file_id": 1,
  "platform": "shopee",
  "domain": "orders",
  "mappings": {
    "订单号": "order_id",
    "数量": "quantity"
  },
  "rows": [
    {"order_id": "12345", "quantity": 1}
  ]
}
```

**响应**:
```json
{
  "success": true,
  "message": "入库完成",
  "staged": 100,
  "imported": 95,
  "quarantined": 5,
  "validation": {
    "total_rows": 100,
    "valid_rows": 95,
    "error_rows": 5
  }
}
```

**入库后状态更新**:
- 全部成功: `catalog_files.status = 'ingested'`
- 部分成功: `catalog_files.status = 'partial_success'`（有隔离行）
- 失败: `catalog_files.status = 'failed'`
- 同时更新 `catalog_files.last_processed_at`

---

### 6. GET /api/field-mapping/catalog-status

**功能**: 获取 Catalog 状态统计

**响应**:
```json
{
  "total": 407,
  "by_status": [
    {"status": "pending", "count": 405},
    {"status": "ingested", "count": 2},
    {"status": "failed", "count": 0}
  ]
}
```

---

### 7. POST /api/field-mapping/cleanup

**功能**: 清理无效文件记录（文件不存在的孤儿记录）

**响应**:
```json
{
  "success": true,
  "message": "清理完成，删除了 10 个无效文件记录",
  "data": {
    "total_checked": 407,
    "orphaned_removed": 10,
    "valid_remaining": 397
  }
}
```

---

## 前端使用指南

### 文件选择器配置

```vue
<el-select v-model="dataStore.selectedFile">
  <el-option
    v-for="file in dataStore.files"
    :key="file.id"
    :label="file.file_name"
    :value="file.id"
  />
</el-select>
```

**关键点**:
- `value` 必须为 `file.id`（整数）
- `label` 可自定义展示（如 `file_name + platform + granularity`）

### API 调用示例

```javascript
// 预览文件
const response = await api.previewFile({
  fileId: dataStore.selectedFile, // 整数 ID
  headerRow: 1
})

// 入库文件
const result = await api.ingestFile({
  fileId: dataStore.selectedFile,
  platform: 'shopee',
  domain: 'orders',
  mappings: dataStore.fieldMappings,
  rows: mappedRows
})
```

---

## 安全与约束

### 路径安全校验

**允许的根目录**:
- `<project>/data/raw`
- `<project>/downloads`

**拒绝访问**:
- 任何路径穿越（`../`）
- 项目外绝对路径
- 返回 400 错误

### 数据库约束

**catalog_files 表约束**:
```sql
-- 日期范围约束
CHECK (date_from IS NULL OR date_to IS NULL OR date_from <= date_to)

-- 状态枚举约束
CHECK (status IN ('pending','validated','ingested','partial_success','failed','quarantined'))
```

**索引**:
- B-Tree: `file_name`（精确查询）
- GIN: `file_metadata`, `validation_errors`（JSONB 搜索）
- 复合索引: `(source_platform, data_domain)`, `(date_from, date_to)`

---

## 性能指标

| 操作 | 性能目标 | 实际性能 |
|------|---------|---------|
| 文件路径查询 | <10ms | 2ms（PostgreSQL 索引） |
| 预览文件（100行） | <5s | 1-3s（ExcelParser） |
| 生成字段映射 | <2s | 200ms（智能算法） |
| 入库（1000行） | <10s | 5-8s（批量 upsert） |

---

## 故障排查

### 问题1: 文件未找到

**错误信息**: `文件未注册: id=123`

**解决方案**:
1. 点击"扫描采集文件"刷新清单
2. 检查文件是否在 `data/raw/` 目录
3. 查看 `catalog_files` 表是否有记录

### 问题2: 预览失败

**错误信息**: `文件不存在: /path/to/file.xlsx`

**解决方案**:
1. 检查文件路径是否正确
2. 运行"清理无效文件"删除孤儿记录
3. 重新扫描文件

### 问题3: 入库失败

**错误信息**: `文件记录不存在`

**解决方案**:
1. 确认 `file_id` 参数正确
2. 检查 `catalog_files` 表中是否有对应记录
3. 查看后端日志获取详细错误

---

## 迁移指南

### 从 v1 迁移到 v2

**后端代码**:
```python
# ❌ v1（不再支持）
file_name = request.get("file_name")
catalog = db.query(CatalogFile).filter(CatalogFile.file_name == file_name).first()

# ✅ v2（推荐）
file_id = int(request.get("file_id"))
catalog = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
```

**前端代码**:
```javascript
// ❌ v1（不再支持）
await api.previewFile({
  filePath: fileName,
  platform: 'shopee',
  dataDomain: 'orders'
})

// ✅ v2（推荐）
await api.previewFile({
  fileId: fileId,
  headerRow: 1
})
```

---

## 后续优化（第二、三阶段）

### 第二阶段（本周内）
- COPY → staging → 并发 upsert 流水线
- 连接池与超时参数优化
- 物化视图并发刷新

### 第三阶段（两周内）
- 事实表按月 RANGE 分区
- dim_date 维表（周/月/季度编码）
- 监控与慢 SQL 优化
- 字段类型与约束收敛

---

## 联系支持

遇到问题请查看：
- 后端日志: `backend/logs/`
- 前端控制台: 浏览器开发者工具
- 数据库日志: PostgreSQL logs

技术文档:
- `docs/guides/USER_MANUAL.md` - 用户手册
- `docs/guides/TROUBLESHOOTING.md` - 故障排查
- `README.md` - 项目概览

