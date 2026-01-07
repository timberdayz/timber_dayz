# 变更：修复数据同步完整导入

## 问题背景

当前数据同步系统只导入1行数据，而不是完整的源数据表。这是一个严重缺陷，会阻止正常的数据入库。该问题同时影响单文件和批量同步操作。

**已识别的根本原因**：
1. **去重逻辑问题**：`data_hash`计算可能为所有行生成相同的哈希值，导致`ON CONFLICT DO NOTHING`跳过除第一行外的所有行
   - **核心问题**：用户无法在前端配置核心字段（`deduplication_fields`），只能依赖后端默认配置
   - **风险场景**：如果默认字段（如`order_id`）在源数据中不存在，所有行的核心字段值都是NULL，导致所有行产生相同的hash
2. **批量插入Bug**：批量插入逻辑可能未正确处理多行数据，特别是使用表达式索引时
3. **缺少行数验证**：系统在插入前未验证所有源数据行是否被处理

**影响**：
- 数据丢失：只导入1行而不是完整表
- Metabase集成中断：由于数据不完整，无法正确编辑外键关系
- 数据质量受损：缺失数据导致无法进行准确分析

## 变更内容

### 核心修复
- **修复去重逻辑**：确保`data_hash`计算包含所有唯一标识字段，防止误判重复
- **修复批量插入**：确保所有行都被正确插入，而不仅仅是第一行
- **添加行数验证**：验证导入行数与源文件行数匹配（考虑合法重复）
- **改进错误处理**：插入失败或行被跳过时提供更好的日志和错误消息

### 增强功能
- **核心字段配置UI**：在模板保存界面添加核心字段选择器，用户必须手动选择核心字段（不允许使用默认值）
  - **涉及页面**：`DataSyncTemplates.vue`（模板管理页面）和`DataSyncFileDetail.vue`（文件详情页面）
- **字段验证**：验证用户选择的核心字段在源数据中存在，如果不存在则警告（软验证，不阻止保存）
- **字段匹配增强**：支持中英文字段名匹配（如"订单号"和"order_id"）
- **模板详情显示**：在模板列表和详情中显示核心字段信息
- **向后兼容性**：现有模板如果没有`deduplication_fields`，系统使用默认配置（基于数据域和子类型）
- **批量插入优化**：在确保所有行都被插入的同时，提高大文件的处理性能
- **Metabase外键支持**：确保数据结构支持Metabase外键关系编辑

### 测试
- **端到端测试**：验证各种文件大小和数据类型的完整表导入
- **去重测试**：验证合法重复被跳过，但唯一行被插入
- **核心字段配置测试**：验证核心字段选择、验证和使用的完整流程
- **向后兼容性测试**：验证现有模板（无`deduplication_fields`）仍能正常工作
- **Metabase集成测试**：验证导入的数据可以在Metabase中正确查询和编辑

## 影响范围

- **受影响的能力规范**：`data-sync`能力、`field-mapping`能力
- **受影响的代码**：
  - `backend/services/data_ingestion_service.py` - 主要入库逻辑
  - `backend/services/raw_data_importer.py` - 批量插入逻辑
  - `backend/services/deduplication_service.py` - 哈希计算逻辑
  - `backend/services/data_sync_service.py` - 同步编排逻辑
  - `backend/routers/field_mapping_dictionary.py` - 模板保存API
  - `backend/services/deduplication_fields_config.py` - 核心字段配置服务
  - `frontend/src/views/DataSyncTemplates.vue` - 模板管理界面
  - `frontend/src/views/DataSyncFileDetail.vue` - 文件详情界面（也需要添加核心字段配置）
  - `frontend/src/api/index.js` - API客户端
- **数据库影响**：无（无需架构变更，`deduplication_fields`字段已存在）
- **API影响**：
  - 需要添加`GET /api/field-mapping/templates/default-deduplication-fields` API
  - `POST /api/field-mapping/templates/save` API需要验证`deduplication_fields`必填
- **前端影响**：需要添加核心字段配置UI（两个页面）

## 数据去重流程说明

### 完整流程
1. **模板保存阶段**：用户保存模板时，必须手动选择核心字段（`deduplication_fields`）
2. **数据同步阶段**：系统查找模板，从模板读取核心字段配置
3. **数据入库阶段**：确定最终使用的核心字段（优先级：模板配置 > 默认配置 > 所有字段）
4. **data_hash计算阶段**：基于核心字段计算SHA256哈希值
5. **数据插入阶段**：使用`ON CONFLICT DO NOTHING`自动去重

### 核心字段确定优先级
- **优先级1**：模板配置的核心字段（用户手动选择）
- **优先级2**：默认配置（基于`data_domain`和`sub_domain`）- 用于向后兼容现有模板
- **优先级3**：所有业务字段（如果前两者都不可用）

### 向后兼容性处理
- **现有模板**：如果模板没有`deduplication_fields`字段或字段为空，系统使用默认配置（基于数据域和子类型）
- **数据同步**：如果模板没有核心字段配置，系统自动使用默认配置，确保现有模板仍能正常工作
- **迁移路径**：用户可以在下次保存模板时添加核心字段配置，无需立即迁移所有模板

### 唯一约束
- 唯一约束包含：`(platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)`
- 如果所有行的`data_hash`相同，只有第一行会被插入，其他行会被跳过

## 成功标准

1. ✅ 源Excel文件的所有行都被导入（排除合法重复）
2. ✅ 去重正确识别并仅跳过真正的重复数据
3. ✅ 导入行数与源文件行数匹配（考虑重复）
4. ✅ 用户可以在前端界面选择核心字段（必填，不允许使用默认值）
5. ✅ 系统验证核心字段在源数据中存在，如果不存在则警告
6. ✅ 核心字段配置正确用于`data_hash`计算
7. ✅ 现有模板（无`deduplication_fields`）仍能正常工作（向后兼容）
8. ✅ Metabase可以正确查询和编辑外键关系
9. ✅ 大文件（1000+行）的性能保持可接受水平
