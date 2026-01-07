# 设计：修复数据同步完整导入

## 背景

当前数据同步系统只导入1行数据，而不是完整的源数据表。这是一个严重缺陷，需要修复以确保数据完整性和正确的Metabase集成。

## 根本原因分析

### 问题1：去重逻辑 - 核心字段配置缺失（核心问题）
**核心问题**：用户无法在前端配置核心字段（`deduplication_fields`），只能依赖后端默认配置。

**风险场景**：
- 如果默认字段（如`order_id`）在源数据中不存在，所有行的核心字段值都是NULL
- 所有行产生相同的hash（因为核心字段都是NULL）
- `ON CONFLICT DO NOTHING`跳过除第一行外的所有行

**解决方案**：
- 在模板保存界面添加核心字段选择器（用户必须手动选择）
- 验证用户选择的字段在源数据中存在
- 如果字段不存在，记录警告但不阻止保存（允许用户继续，但提示风险）

### 问题2：使用表达式索引的批量插入
当使用表达式索引（带有`COALESCE(shop_id, '')`）时，代码使用逐行插入。可能存在以下问题：
- 只插入了第一行
- 事务在第一行后提交
- 循环提前退出

### 问题3：ON CONFLICT行为
如果出现以下情况，`ON CONFLICT DO NOTHING`子句可能跳过除第一行外的所有行：
- 所有行具有相同的唯一键（platform_code, shop_id, data_domain, granularity, data_hash）
- 唯一约束/索引配置不正确

## 解决方案设计

### 修复1：核心字段配置UI（新增）
- **当前**：用户无法在前端配置核心字段，只能依赖后端默认配置
- **修复**：
  - 在模板保存界面添加核心字段选择器（多选框，从表头字段中选择）
  - 用户必须手动选择核心字段（不允许使用默认值）
  - 显示默认推荐字段（基于数据域），但不自动勾选
  - 验证用户选择的字段在`headerColumns`中存在
- **验证**：
  - 前端验证：至少选择1个字段才能保存
  - 后端验证：`deduplication_fields`不能为空
  - 字段存在性验证：如果字段不在数据中，记录警告

### 修复2：改进去重字段检测
- **当前**：如果模板中有`deduplication_fields`则使用，否则使用所有字段
- **修复**：
  - 确保`deduplication_fields`至少包含一个唯一字段（用户必须选择）
  - 验证核心字段在数据中存在（如果不存在，记录警告）
  - 支持中英文字段名匹配（如"订单号"和"order_id"）
- **验证**：记录用于哈希计算的字段和匹配情况

### 修复3：修复批量插入循环
- **当前**：表达式索引使用逐行插入
- **修复**：确保循环处理所有行，而不仅仅是第一行
- **验证**：添加日志显示正在处理多少行

### 修复4：改进行数验证
- **当前**：通过比较插入前后的计数来计算`actual_inserted`
- **修复**：添加验证确保`actual_inserted`匹配预期计数（考虑重复）
- **警告**：如果检测到显著数据丢失（>5%行被跳过），记录警告

### 修复5：更好的错误处理
- **当前**：错误可能被静默忽略
- **修复**：在每行插入周围添加try-catch，记录错误但继续处理
- **指标**：跟踪插入成功率

## 数据去重流程设计

### 完整流程

```
阶段1: 模板保存（用户配置核心字段）
  ↓
  用户保存模板
  - 选择表头行（header_row）
  - 保存表头字段列表（header_columns）
  - 选择核心字段（deduplication_fields）← 用户必须手动选择
  ↓
  后端保存到数据库
  FieldMappingTemplate表：
  - platform, data_domain, granularity
  - sub_domain（子类型）
  - header_columns（JSONB数组）
  - deduplication_fields（JSONB数组）← 用户选择的核心字段

阶段2: 数据同步（查找模板并读取核心字段）
  ↓
  DataSyncService.sync_single_file()
  1. 查找模板（TemplateMatcher）
     - platform_code, data_domain, granularity, sub_domain
  2. 从模板读取核心字段
     if template.deduplication_fields:
         deduplication_fields = template.deduplication_fields
     else:
         deduplication_fields = None
  3. 调用DataIngestionService
     ingest_data(deduplication_fields=..., sub_domain=...)

阶段3: 数据入库（确定最终使用的核心字段）
  ↓
  DataIngestionService.ingest_data()
  调用get_deduplication_fields()
  ↓
  优先级：
  1. 模板配置（template_fields）← 最高优先级
  2. 默认配置（基于data_domain+sub_domain）
  3. 所有字段（返回空列表）
  ↓
  示例：
  - data_domain = 'orders'
  - sub_domain = None
  - template_fields = ['订单号', '订单日期']
  → 最终使用: ['订单号', '订单日期']

阶段4: data_hash计算（基于核心字段）
  ↓
  DeduplicationService.batch_calculate_data_hash()
  ↓
  calculate_data_hash()
  对每一行数据：
  1. 如果提供了deduplication_fields:
     - 只使用核心字段计算hash
     - 支持中英文字段名匹配
       * 精确匹配（key == field）
       * 忽略大小写（key.lower() == field.lower()）
     - 如果字段不存在，记录警告但继续（使用NULL值）
  2. 否则：
     - 使用所有业务字段计算hash
  ↓
  计算SHA256哈希
  1. 提取核心字段的值
  2. 排序键值对（确保一致性）
  3. 转换为JSON字符串
  4. 计算SHA256哈希
  → 返回64字符的hex字符串

阶段5: 数据插入和去重（ON CONFLICT DO NOTHING）
  ↓
  RawDataImporter.batch_insert_raw_data()
  准备插入数据：
  - platform_code
  - shop_id（可能为NULL）
  - data_domain
  - granularity
  - data_hash（基于核心字段）← 用于去重
  - raw_data（JSONB，完整数据）
  - header_columns（JSONB数组）
  ↓
  INSERT INTO fact_raw_data_*
  ON CONFLICT (
      platform_code,
      COALESCE(shop_id, ''),
      data_domain,
      granularity,
      data_hash
  ) DO NOTHING
  ↓
  去重结果：
  - 如果(platform_code, shop_id, data_domain, granularity, data_hash)已存在 → 跳过（不插入）
  - 如果不存在 → 插入新行
```

### 核心字段确定优先级

```python
# 在 DataIngestionService.ingest_data() 中
final_deduplication_fields = get_deduplication_fields(
    data_domain=domain,                    # 数据域（如'orders'）
    template_fields=deduplication_fields,  # 模板配置的核心字段（用户选择）
    sub_domain=sub_domain                  # 子类型（如'ai_assistant'）
)

# get_deduplication_fields() 的优先级：
# 1. 模板配置（template_fields）← 最高优先级
# 2. 默认配置（基于data_domain + sub_domain）
# 3. 所有字段（返回空列表，使用所有业务字段）
```

### 唯一约束和去重

```sql
-- 唯一约束（v4.14.0）
UNIQUE (platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)

-- 插入时自动去重
INSERT INTO fact_raw_data_* (...)
ON CONFLICT (platform_code, COALESCE(shop_id, ''), data_domain, granularity, data_hash)
DO NOTHING
```

## 字段验证建议

### 建议方案：软验证 + 警告提示（推荐）

**验证时机**：
1. **前端验证**（保存模板前）：
   - 验证用户选择的字段是否在`headerColumns`中
   - 如果不在，显示警告："以下字段不在表头中：{字段列表}，可能导致去重失败"
   - 允许用户继续保存，但提示风险

2. **后端验证**（保存模板时）：
   - 验证`deduplication_fields`不为空（必填）
   - 验证字段格式正确（列表，字符串元素）
   - 如果字段不在`header_columns`中，记录警告但不阻止保存

3. **运行时验证**（数据同步时）：
   - 验证核心字段在数据行中存在
   - 如果字段不存在，记录警告并使用NULL值
   - 如果所有核心字段都是NULL，记录严重警告

**理由**：
- **灵活性**：允许用户选择字段，即使字段名不完全匹配（支持中英文匹配）
- **用户友好**：不阻止保存，但提供清晰的警告
- **可追溯性**：记录警告日志，便于问题排查

## 显示位置建议

### 建议方案：模板列表 + 模板详情（推荐）

1. **模板列表显示**：
   - 在模板列表表格中添加"核心字段"列
   - 显示格式：`3个字段`（显示数量）
   - 鼠标悬停时显示完整字段列表（tooltip）
   - **理由**：快速了解模板配置，不占用太多空间

2. **模板详情显示**：
   - 在模板详情弹窗中显示完整核心字段列表
   - 显示格式：每个字段一行，带复选框样式（已选择状态）
   - 显示字段说明："用于数据去重，确保每行数据唯一"
   - **理由**：详细查看模板配置

3. **模板保存界面显示**：
   - 在"原始表头字段列表"卡片下方添加"核心字段选择"卡片
   - 显示所有表头字段，用户勾选核心字段
   - 显示推荐字段（基于数据域），但不自动勾选
   - **理由**：配置核心字段的主要入口

## 实施策略

### 阶段1：调查
1. 添加详细日志以了解正在发生的情况
2. 使用示例文件测试以重现问题
3. 确定确切的根本原因

### 阶段2：修复核心逻辑
1. 修复去重哈希计算
2. 修复批量插入循环
3. 添加行数验证

### 阶段3：核心字段配置UI
1. 前端：添加核心字段选择器
2. 前端：添加字段验证和提示
3. 后端：添加字段验证逻辑
4. 后端：添加默认字段推荐API

### 阶段4：测试和验证
1. 使用各种文件大小和数据类型进行测试
2. 验证所有行都被导入
3. 验证重复数据被正确跳过
4. 测试核心字段配置UI
5. 测试Metabase集成

## 风险和缓解措施

### 风险1：性能影响
- **风险**：添加验证和日志可能会减慢插入速度
- **缓解**：尽可能使用批量操作，仅在INFO级别记录日志

### 风险2：破坏现有功能
- **风险**：修复可能会破坏现有的去重逻辑
- **缓解**：彻底测试，逐步推出，如需要可使用功能标志

### 风险3：数据损坏
- **风险**：修复可能会引入数据损坏
- **缓解**：添加验证检查，首先使用示例数据进行测试

### 风险4：用户配置错误
- **风险**：用户选择的核心字段不正确，导致去重失败
- **缓解**：
  - 提供清晰的字段选择指导
  - 显示默认推荐字段
  - 验证字段存在性并警告
  - 记录详细日志便于问题排查

## 考虑的替代方案

### 替代方案1：临时禁用去重
- **优点**：快速修复以导入所有行
- **缺点**：将导入重复数据，不是长期解决方案
- **决定**：不推荐 - 应修复根本原因

### 替代方案2：使用不同的插入策略
- **优点**：可能避免表达式索引问题
- **缺点**：需要架构变更，更复杂
- **决定**：不推荐 - 应修复当前逻辑

### 替代方案3：自动检测核心字段
- **优点**：用户无需手动选择
- **缺点**：可能检测不准确，用户无法控制
- **决定**：不推荐 - 用户必须手动选择以确保准确性

## 向后兼容性考虑

### 现有模板处理
- **问题**：现有模板可能没有`deduplication_fields`字段或字段为空
- **解决方案**：
  - 如果模板没有`deduplication_fields`，系统使用默认配置（基于数据域和子类型）
  - 在数据同步时，如果模板没有核心字段配置，记录警告但继续处理
  - 用户可以在下次保存模板时添加核心字段配置

### API兼容性
- **保存模板API**：如果`deduplication_fields`为None或空列表，使用默认配置（但记录警告）
- **数据同步**：如果模板没有核心字段配置，自动使用默认配置，确保现有模板仍能正常工作

### 迁移路径
- **无需立即迁移**：现有模板可以继续使用，系统会自动使用默认配置
- **逐步迁移**：用户可以在下次编辑模板时添加核心字段配置
- **新模板**：所有新保存的模板必须包含核心字段配置（必填）

## 开放问题（已解决）

1. ✅ 核心字段选择UI位置：已确认在模板保存界面添加（DataSyncTemplates.vue和DataSyncFileDetail.vue）
2. ✅ 默认值处理：已确认用户必须选择，不允许使用默认值（但向后兼容时使用默认配置）
3. ✅ 字段验证：已确认使用软验证 + 警告提示方案
4. ✅ 显示位置：已确认在模板列表和详情中显示
5. ✅ 向后兼容性：已确认现有模板使用默认配置，无需立即迁移

## 成功指标

- ✅ 源文件中100%的唯一行都被导入
- ✅ 去重正确识别并仅跳过真正的重复数据
- ✅ 导入性能保持可接受（1000行<10秒）
- ✅ Metabase可以正确查询和编辑外键关系
- ✅ 用户可以在前端界面选择核心字段（必填）
- ✅ 系统验证核心字段存在性并警告（如果不存在）
