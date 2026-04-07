# 数据同步功能重构任务清单

**日期**: 2025-01-31  
**目标**: 将数据同步功能适配DSS架构（使用RawDataImporter写入JSONB格式）

---

## 🔍 当前状态分析

### ✅ 已完成的组件

1. **RawDataImporter服务** ✅
   - 文件: `backend/services/raw_data_importer.py`
   - 功能: 支持写入B类数据表（fact_raw_data_*），JSONB格式，批量插入

2. **DataSyncService服务** ✅
   - 文件: `backend/services/data_sync_service.py`
   - 功能: 统一的数据同步入口，调用DataIngestionService

### ⚠️ 需要修改的组件

1. **DataIngestionService** ⚠️
   - 文件: `backend/services/data_ingestion_service.py`
   - 问题: 仍在使用旧的入库方式（`stage_orders`, `upsert_orders`, `upsert_product_metrics`）
   - 需要: 改为使用`RawDataImporter`写入JSONB格式

---

## 📋 重构任务清单

### 任务1: 修改DataIngestionService使用RawDataImporter

#### 1.1 导入RawDataImporter
- [ ] 在`data_ingestion_service.py`中导入`RawDataImporter`
- [ ] 创建`RawDataImporter`实例

#### 1.2 修改数据入库逻辑
- [ ] 移除旧的入库调用（`stage_orders`, `upsert_orders`, `upsert_product_metrics`等）
- [ ] 改为使用`RawDataImporter.batch_insert_raw_data()`
- [ ] 确保数据格式为JSONB（中文字段名作为键）

#### 1.3 数据格式转换
- [ ] 将DataFrame转换为字典列表（保留原始中文表头）
- [ ] 计算data_hash（全行业务字段哈希）
- [ ] 准备header_columns（原始表头字段列表）

#### 1.4 处理不同数据域
- [ ] orders数据域 → 使用RawDataImporter
- [ ] products数据域 → 使用RawDataImporter
- [ ] traffic数据域 → 使用RawDataImporter
- [ ] services数据域 → 使用RawDataImporter
- [ ] inventory数据域 → 使用RawDataImporter

### 任务2: 数据去重逻辑集成

#### 2.1 文件级去重
- [ ] 在DataSyncService中检查file_hash
- [ ] 如果文件已处理，跳过整个文件

#### 2.2 行级去重
- [ ] 计算每行的data_hash
- [ ] 批量查询已存在的data_hash
- [ ] 使用ON CONFLICT自动去重（RawDataImporter已实现）

### 任务3: 数据验证和清洗

#### 3.1 保留现有验证逻辑
- [ ] 数据验证（DataValidator）
- [ ] 数据标准化（DataStandardizer）
- [ ] 数据隔离（DataQuarantine）

#### 3.2 适配JSONB格式
- [ ] 确保验证后的数据保留中文字段名
- [ ] 确保标准化后的数据保留中文字段名

### 任务4: 测试和验证

#### 4.1 单元测试
- [ ] 测试RawDataImporter集成
- [ ] 测试数据格式转换
- [ ] 测试去重逻辑

#### 4.2 集成测试
- [ ] 测试完整的数据同步流程
- [ ] 测试不同数据域的数据同步
- [ ] 验证JSONB格式存储
- [ ] 验证中文字段名保存

---

## 🔧 具体修改步骤

### 步骤1: 修改DataIngestionService.ingest_data()

**当前代码**（第369-447行）:
```python
if domain == "orders":
    staged = stage_orders(self.db, valid_rows, ...)
    imported = upsert_orders(self.db, valid_rows, ...)
elif domain == "products":
    staged = stage_product_metrics(self.db, valid_rows, ...)
    imported = upsert_product_metrics(self.db, valid_rows, ...)
```

**修改为**:
```python
from backend.services.raw_data_importer import get_raw_data_importer
from backend.services.deduplication_service import DeduplicationService

# 获取RawDataImporter实例
raw_importer = get_raw_data_importer(self.db)
dedup_service = DeduplicationService(self.db)

# 计算data_hash
data_hashes = dedup_service.batch_calculate_hash(valid_rows)

# 批量插入（使用RawDataImporter）
imported = raw_importer.batch_insert_raw_data(
    rows=valid_rows,  # 原始数据，中文字段名作为键
    data_hashes=data_hashes,
    data_domain=domain,
    granularity=file_record.granularity or "daily",
    platform_code=platform,
    shop_id=file_record.shop_id,
    file_id=file_id,
    header_columns=list(mappings.keys()) if mappings else None
)
```

### 步骤2: 确保数据格式正确

**关键点**:
- `valid_rows`应该是字典列表，键为原始中文表头字段名
- 不要转换为标准字段名
- 保留所有原始字段

### 步骤3: 移除旧的Staging逻辑

**注意**:
- DSS架构不再需要Staging层
- 直接写入Fact层（fact_raw_data_*表）
- 移除`stage_orders`, `stage_product_metrics`等调用

---

## 📝 代码修改位置

### 主要修改文件

1. **backend/services/data_ingestion_service.py**
   - 修改`ingest_data()`方法（第369-447行）
   - 移除旧的入库逻辑
   - 添加RawDataImporter调用

2. **backend/services/data_sync_service.py**
   - 可能需要调整数据格式转换
   - 确保传递的数据保留中文字段名

### 可能需要调整的文件

1. **backend/services/data_validator.py**
   - 确保验证后的数据保留中文字段名

2. **backend/services/data_standardizer.py**
   - 确保标准化后的数据保留中文字段名

---

## ✅ 完成标准

- [ ] DataIngestionService使用RawDataImporter写入数据
- [ ] 数据以JSONB格式存储（中文字段名作为键）
- [ ] 数据写入到fact_raw_data_*表
- [ ] 去重逻辑正常工作
- [ ] 数据验证和隔离正常工作
- [ ] 测试通过

---

## 🚀 下一步

1. 修改`DataIngestionService.ingest_data()`方法
2. 测试数据同步功能
3. 验证JSONB格式存储
4. 验证中文字段名保存

---

**状态**: ⏳ **待开始重构**

