# 数据同步功能重构总结

**日期**: 2025-01-31  
**目标**: 将数据同步功能适配DSS架构

---

## 📋 当前状态

### ✅ 已完成的组件

1. **RawDataImporter** ✅
   - 支持写入B类数据表（fact_raw_data_*）
   - 支持JSONB格式存储（中文字段名作为键）
   - 批量插入优化

2. **DeduplicationService** ✅
   - 批量计算data_hash
   - 批量查询已存在哈希
   - 过滤重复数据

### ⚠️ 需要修改的组件

**DataIngestionService** ⚠️
- 当前：使用旧的入库方式（`stage_orders`, `upsert_orders`等）
- 需要：改为使用`RawDataImporter`写入JSONB格式

---

## 🔧 修改方案

### 修改位置

**文件**: `backend/services/data_ingestion_service.py`  
**方法**: `ingest_data()`  
**行数**: 第369-447行

### 修改内容

1. **导入新服务**
   ```python
   from backend.services.raw_data_importer import get_raw_data_importer
   from backend.services.deduplication_service import DeduplicationService
   ```

2. **替换入库逻辑**
   - 移除：`stage_orders`, `upsert_orders`, `stage_product_metrics`, `upsert_product_metrics`等
   - 添加：使用`RawDataImporter.batch_insert_raw_data()`

3. **数据格式处理**
   - 确保`valid_rows`保留原始中文字段名
   - 计算data_hash
   - 准备header_columns

4. **处理所有数据域**
   - orders, products, traffic, services, inventory, analytics
   - 统一使用RawDataImporter

---

## ⚠️ 注意事项

1. **数据格式**
   - 确保`valid_rows`是字典列表，键为原始中文表头字段名
   - 不要转换为标准字段名
   - 保留所有原始字段

2. **Staging层**
   - DSS架构不再需要Staging层
   - 直接写入Fact层（fact_raw_data_*表）
   - 移除所有`stage_*`调用

3. **订单金额数据**
   - 保留`ingest_order_amounts`调用（Pattern-based Mapping）
   - 这是独立的功能，不影响主流程

---

## 📝 下一步

1. 修改`DataIngestionService.ingest_data()`方法
2. 测试数据同步功能
3. 验证JSONB格式存储
4. 验证中文字段名保存

---

**状态**: ⏳ **准备开始修改**

