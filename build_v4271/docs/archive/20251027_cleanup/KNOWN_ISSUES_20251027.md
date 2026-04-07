# 已知问题与修复计划

**日期**: 2025-10-27  
**版本**: v2.3  
**状态**: 核心功能已完成，部分问题待修复

---

## 高优先级问题

### 1. data_importer与schema不同步

**问题描述**:
- `backend/services/data_importer.py`使用的字段结构与`modules/core/db/schema.py`不一致
- `StagingProductMetrics`表实际结构：`platform_code`, `shop_id`, `platform_sku`, `metric_data`(JSON)
- `data_importer`期望结构：`product_id`, `pv_raw`, `uv_raw`等独立字段

**影响范围**:
- 产品指标数据入库失败（500错误）
- 订单数据入库可能也有类似问题

**根本原因**:
- schema在v4.3.1升级时简化了暂存表结构（用JSON替代独立列）
- data_importer没有同步更新

**修复方案**:
1. **方案A（推荐）**: 更新data_importer以使用JSON字段存储
   - 修改`stage_product_metrics`: 将整行数据序列化为JSON存入`metric_data`
   - 修改`upsert_product_metrics`: 从JSON反序列化后再插入事实表
   - 工作量：2-3小时

2. **方案B（临时）**: 回滚schema到独立字段版本
   - 创建新迁移添加独立字段
   - 工作量：1小时，但增加schema复杂度

**优先级**: 高  
**计划完成时间**: 本周内

---

### 2. XLS文件格式解析失败

**问题描述**:
- 部分`.xls`文件实际是损坏的OLE格式或HTML伪装
- xlrd读取失败："Workbook corruption: seen[2] == 4"
- HTML兜底也失败（编码问题）

**影响范围**:
- 约40个.xls文件（10%）
- 主要是shopee和tiktok的订单文件

**已尝试修复**:
- ✅ 增加HTML兜底（多编码尝试）
- ⚠️ 仍有部分文件无法解析

**建议解决方案**:
1. **用户操作**: 用Excel打开这些.xls文件，另存为标准.xlsx格式
2. **系统优化**: 在采集模块直接保存为.xlsx格式（避免.xls）
3. **降级处理**: 标记为"unsupported_format"，跳过入库

**优先级**: 中  
**计划完成时间**: 下周

---

## 中优先级问题

### 3. 大文件预览性能

**问题描述**:
- 文件>10MB时预览较慢
- miaoshou产品快照文件（11MB）预览超时

**已实施修复**:
- ✅ 大文件限制预览行数（50行 vs 100行）
- ✅ 跳过规范化处理

**当前状态**: 已部分解决

**后续优化**:
- 增加进度条显示
- 异步预览（后台处理）

**优先级**: 中  
**计划完成时间**: 两周内

---

## 低优先级问题

### 4. 第二、三阶段迁移未执行

**问题描述**:
- 迁移脚本已创建，但未执行
- 包括：COPY流水线、分区表、dim_date、监控体系

**原因**:
- 需要在低峰期执行（凌晨2-4点）
- 需要生产环境验证

**计划**:
- 第二阶段：本周末凌晨执行
- 第三阶段：下周末凌晨执行

**优先级**: 低（不阻塞核心功能）

---

## 已修复问题

### ✅ 1. account_name字段缺失
- 修复：移除不存在字段引用
- 提交：backend/routers/field_mapping.py:437

### ✅ 2. normalize_table类型转换错误
- 修复：增加try-except安全转换
- 提交：backend/services/excel_parser.py:206-210

### ✅ 3. 文件未找到问题
- 修复：统一使用CatalogFile + file_id
- 提交：backend/routers/field_mapping.py（全文件）

### ✅ 4. 前端选择器对象序列化
- 修复：value=id，label=file_name
- 提交：frontend/src/views/FieldMapping.vue

---

## 临时解决方案

### 当前可用功能

**完全可用**:
- ✅ 文件扫描（100%）
- ✅ 文件分组（100%）
- ✅ 文件信息查询（100%）
- ✅ XLSX文件预览（90%）
- ✅ 字段映射生成（100%）
- ✅ 合并单元格还原（100%）

**部分可用**:
- ⚠️ XLS文件预览（0%，需转换为xlsx）
- ⚠️ 数据入库（0%，等待schema同步）

### 建议工作流程

在data_importer修复前，用户可以：
1. 扫描文件 → ✅ 正常
2. 选择XLSX格式文件 → ✅ 正常
3. 预览数据 → ✅ 正常（含合并单元格还原）
4. 生成字段映射 → ✅ 正常
5. **入库** → ⚠️ 暂不可用（等待修复）

---

## 修复优先级排序

1. **立即**（今天）: 修复data_importer与schema同步问题
2. **本周**: 执行第二阶段PostgreSQL优化
3. **下周**: 解决XLS文件格式问题
4. **两周内**: 执行第三阶段优化

---

**更新时间**: 2025-10-27 19:00  
**下次更新**: data_importer修复后

