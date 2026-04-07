# 📊 数据同步核心流程详解

**版本**: v4.10.0  
**更新时间**: 2025-11-09  
**目的**: 完整梳理数据同步流程，识别潜在问题

---

## 🎯 流程概览

数据同步包含以下核心流程：

1. **文件扫描与注册** → 2. **批量同步触发** → 3. **单文件处理** → 4. **数据入库**

```
文件扫描 → 注册到catalog_files → 批量同步 → 单文件处理 → 数据入库
```

---

## 📋 详细流程

### 阶段1: 文件扫描与注册

**触发方式**:
- 手动触发: `POST /api/field-mapping/scan`
- 定时任务: Celery Beat（可选）

**流程步骤**:

```
┌─────────────────────────────────────────────────────────────┐
│              阶段1: 文件扫描与注册                          │
└─────────────────────────────────────────────────────────────┘

开始（POST /api/field-mapping/scan）
  │
  ▼
┌─────────────────┐
│ 1. 扫描data/raw目录│
│ • 递归扫描      │
│ • 过滤Excel文件 │
│ • 目录白名单: YYYY/│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 解析文件元数据│
│ • 文件名解析    │
│   - platform_code│
│   - data_domain │
│   - granularity │
│ • .meta.json读取│
│   - shop_id     │
│   - date_from/to│
│ • file_hash计算 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 检查文件是否已注册│
│ • 查询catalog_files│
│ • WHERE file_hash = ?│
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  已存在    新文件
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │ 4. 创建CatalogFile记录│
    │    │ • status='pending'│
    │    │ • platform_code  │
    │    │ • source_platform│
    │    │ • data_domain    │
    │    │ • granularity    │
    │    │ • shop_id        │
    │    │ • file_hash      │
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 5. 可选：触发自动入库│
    │    │ • 仅新文件（前20个）│
    │    │ • 查找模板        │
    │    │ • 自动入库        │
    │    └────────┬──────────┘
    │             │
    └─────────────┘
         │
         ▼
    完成
```

**关键代码位置**:
- `modules/services/catalog_scanner.py::scan_and_register()`
- `backend/routers/field_mapping.py::scan_files()`

**状态流转**:
- 新文件: `status='pending'`
- 已存在: 保持原状态

---

### 阶段2: 批量同步触发

**触发方式**:
- 前端: 用户点击"开始同步"按钮
- API: `POST /api/field-mapping/auto-ingest/batch`

**流程步骤**:

```
┌─────────────────────────────────────────────────────────────┐
│              阶段2: 批量同步触发                            │
└─────────────────────────────────────────────────────────────┘

开始（用户点击"开始同步"）
  │
  ▼
┌─────────────────┐
│ 1. 前端准备参数   │
│ • platform: '*' │
│ • domains: []   │
│ • granularities: []│
│ • limit: 100    │
│ • only_with_template: true│
│ • allow_quarantine: true│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. POST /api/field-mapping/auto-ingest/batch│
│ • 发送同步请求   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. AutoIngestOrchestrator.batch_ingest()│
│ • 查询待入库文件 │
│   - WHERE status='pending'│
│   - AND platform IN (...)│
│   - AND data_domain IN (...)│
│   - AND granularity IN (...)│
│   - LIMIT 100    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 检查文件数量   │
│ • total_files=0?│
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  无文件     有文件
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │ 5. 创建进度任务   │
    │    │ • task_id = uuid│
    │    │ • ProgressTracker│
    │    │ • 初始化进度状态  │
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 6. 循环处理每个文件│
    │    │ • ingest_single_file()│
    │    │ • 更新进度        │
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 7. 返回汇总统计   │
    │    │ • total_files    │
    │    │ • succeeded      │
    │    │ • failed         │
    │    │ • quarantined    │
    │    └────────┬──────────┘
    │             │
    └─────────────┘
         │
         ▼
    完成
```

**关键代码位置**:
- `backend/services/auto_ingest_orchestrator.py::batch_ingest()`
- `backend/routers/auto_ingest.py::auto_ingest_batch()`

**筛选条件**:
```python
# 查询条件
stmt = select(CatalogFile).where(
    CatalogFile.status == 'pending',
    # 平台筛选（支持platform_code或source_platform）
    or_(
        func.lower(CatalogFile.platform_code) == platform.lower(),
        func.lower(CatalogFile.source_platform) == platform.lower()
    ),
    # 数据域筛选（可选）
    CatalogFile.data_domain.in_(domains) if domains else True,
    # 粒度筛选（可选）
    CatalogFile.granularity.in_(granularities) if granularities else True
).limit(limit)
```

---

### 阶段3: 单文件处理

**流程步骤**:

```
┌─────────────────────────────────────────────────────────────┐
│              阶段3: 单文件处理                              │
└─────────────────────────────────────────────────────────────┘

开始（ingest_single_file(file_id)）
  │
  ▼
┌─────────────────┐
│ 1. 获取文件信息   │
│ • 查询CatalogFile│
│ • WHERE id = file_id│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 检查文件状态   │ ⚠️ 状态检查
│ • status='processing'?│
│   → 跳过（防止并发）│
│ • status='ingested'?│
│   → 跳过（已处理）│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 查找模板       │ ⚠️ 模板匹配
│ • TemplateMatcher│
│ • find_best_template()│
│   - platform     │
│   - data_domain  │
│   - granularity  │
│   - sub_domain   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  无模板     有模板
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │ 4. 设置processing状态│
    │    │ • status='processing'│
    │    │ • 防止并发处理    │
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 5. 预览文件      │ ⚠️ 表头处理
    │    │ • ExcelParser.read_excel()│
    │    │ • header_row = template.header_row│
    │    │ • 自动检测表头行  │
    │    │   - 如果匹配失败  │
    │    │   - 尝试0-5行    │
    │    │   - 选择匹配率最高的│
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 6. 应用模板映射   │
    │    │ • apply_template_to_columns()│
    │    │ • 匹配列名        │
    │    │ • 生成field_mapping│
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 7. 检查映射结果   │
    │    │ • field_mapping为空?│
    │    │   → 跳过（无映射）│
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 8. 调用ingest API│
    │    │ • POST /api/field-mapping/ingest│
    │    │ • 传递file_id   │
    │    │ • 传递mappings   │
    │    │ • 传递header_row│
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 9. 更新文件状态   │
    │    │ • success → 'ingested'│
    │    │ • quarantined → 'quarantined'│
    │    │ • failed → 'failed'│
    │    └────────┬──────────┘
    │             │
    └─────────────┘
         │
         ▼
    完成
```

**关键代码位置**:
- `backend/services/auto_ingest_orchestrator.py::ingest_single_file()`

**状态流转**:
```
pending → processing → ingested/quarantined/failed
```

**表头行处理逻辑**:
```python
# ⭐ v4.10.0修复：如果用户已设置表头行，严格使用用户设置的值，不进行自动检测

# 1. 判断用户是否已设置表头行
user_defined_header = template.header_row if template else None

if user_defined_header is not None:
    # 用户已设置表头行，严格使用用户设置的值
    header_row = user_defined_header
    # 不进行自动检测，即使匹配失败也使用用户设置的值
    if 匹配失败:
        记录警告日志，但不自动检测
else:
    # 用户未设置表头行，使用默认值0，并允许自动检测（兜底机制）
    header_row = 0
    if 匹配失败:
        # 尝试表头行0-5，选择匹配率最高的
        for test_header in [0, 1, 2, 3, 4, 5]:
            if 匹配成功:
                header_row = test_header
                break
```

---

### 阶段4: 数据入库

**流程步骤**:

```
┌─────────────────────────────────────────────────────────────┐
│              阶段4: 数据入库                                 │
└─────────────────────────────────────────────────────────────┘

开始（POST /api/field-mapping/ingest）
  │
  ▼
┌─────────────────┐
│ 1. 验证请求参数   │
│ • file_id       │
│ • mappings      │
│ • header_row    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 2. 读取完整Excel文件│ ⚠️ 重新读取
│ • ExcelParser.read_excel()│
│ • 使用header_row│
│ • 不限制行数    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 3. 应用字段映射   │
│ • 将原始列名映射到标准字段│
│ • 生成标准化的数据行│
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 4. 数据验证       │ ⚠️ 验证逻辑
│ • validate_orders()│
│ • validate_inventory()│
│ • validate_product_metrics()│
│ • 检查必填字段    │
│ • 检查数据格式    │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
  验证失败    验证通过
    │         │
    │         ▼
    │    ┌─────────────────┐
    │    │ 5. 数据入库       │
    │    │ • upsert_product_metrics()│
    │    │ • upsert_orders()│
    │    │ • 批量插入       │
    │    └────────┬──────────┘
    │             │
    │             ▼
    │    ┌─────────────────┐
    │    │ 6. 更新文件状态   │
    │    │ • imported > 0 → 'ingested'│
    │    │ • quarantined > 0 → 'quarantined'│
    │    │ • imported = 0 → 'failed'│
    │    └────────┬──────────┘
    │             │
    └─────────────┘
         │
         ▼
    完成
```

**关键代码位置**:
- `backend/routers/field_mapping.py::ingest_file()`
- `backend/services/data_importer.py::upsert_product_metrics()`
- `backend/services/enhanced_data_validator.py::validate_*()`

**数据验证逻辑**:
```python
# 根据数据域选择验证函数
if domain == "orders":
    validation_result = validate_orders(rows)
elif domain == "inventory":
    validation_result = validate_inventory(rows)
elif domain == "services":
    validation_result = validate_services(rows)
else:
    validation_result = validate_product_metrics(rows)

# 验证结果
if validation_result['errors']:
    # 隔离错误数据
    quarantine_rows(rows, validation_result['errors'])
```

---

## 🔍 潜在问题分析

### 问题1: 文件筛选逻辑不一致 ⚠️

**问题描述**:
- `get_overview`方法只使用`platform_code`筛选
- 批量同步使用`platform_code`或`source_platform`筛选
- 导致统计结果不一致

**已修复**:
- ✅ 更新`get_overview`方法，同时使用`platform_code`和`source_platform`筛选

### 问题2: 表头行自动检测可能失败 ⚠️

**问题描述**:
- 模板的`header_row`可能设置不正确
- 自动检测表头行需要多次尝试
- 如果所有尝试都失败，文件会被跳过

**建议**:
- 优化表头行自动检测逻辑
- 记录模板匹配失败的详细原因
- 提供手动设置表头行的功能

### 问题3: 文件状态管理 ⚠️

**问题描述**:
- 文件状态可能在处理过程中不一致
- 并发处理可能导致状态冲突

**建议**:
- 确保文件状态更新的原子性
- 添加文件状态审计日志
- 提供文件状态修复工具

### 问题4: 批量同步筛选条件过于严格 ⚠️

**问题描述**:
- 如果用户选择了"当前选择 (platform/domain/granularity)"
- 筛选条件可能过于严格，导致只查询到很少的文件

**建议**:
- 如果查询到0个文件，应该返回明确的提示信息
- 如果查询到文件但处理失败，应该记录详细的失败原因

---

## 📊 流程关键点总结

### ✅ 正常流程

1. **文件扫描** → 注册到`catalog_files`（status='pending'）
2. **批量同步** → 查询符合条件的文件
3. **单文件处理** → 查找模板 → 预览文件 → 应用映射
4. **数据入库** → 验证数据 → 入库 → 更新状态

### ⚠️ 异常流程

1. **无模板** → 跳过文件（status='skipped'）
2. **模板匹配失败** → 跳过文件（status='skipped'）
3. **数据验证失败** → 隔离数据（status='quarantined'）
4. **入库失败** → 标记失败（status='failed'）

---

## 🎯 优化建议

1. **统一文件筛选逻辑** ✅（已修复）
   - 所有查询都使用`platform_code`或`source_platform`

2. **优化表头行自动检测**
   - 提高检测成功率
   - 记录检测过程

3. **改进错误处理**
   - 记录详细的错误信息
   - 提供错误修复工具

4. **增强状态管理**
   - 确保状态更新的原子性
   - 添加状态审计日志

---

**版本**: v4.10.0  
**更新时间**: 2025-11-09  
**状态**: ✅ 流程梳理完成，部分问题已修复

