# 全量辞典加载与中文名词扫描方案

## 方案概述

### 问题
- 当前辞典按数据域加载，导致某些字段（如"日期"）找不到匹配的标准字段
- 用户需要更丰富的标准字段选择

### 解决方案
1. **全量辞典加载**：不再按数据域过滤，加载整个数据库的所有辞典
2. **中文名词扫描**：扫描所有数据域文件中的中文字段名
3. **自动翻译**：将中文名词翻译为英文标准字段
4. **一对一映射**：确保每个中文名称只对应一个英文标准字段

## 实现细节

### 1. 前端修改

**文件**: `frontend/src/views/FieldMappingEnhanced.vue`

**变更**:
- `loadDictionary()`函数不再需要`selectedDomain`
- API调用改为：`/field-mapping/dictionary`（不传`data_domain`参数）
- 提示信息改为："已加载 X 个标准字段（全量辞典）"

### 2. 后端API更新

**文件**: `backend/routers/field_mapping_dictionary.py`

**变更**:
- `GET /dictionary`接口的`data_domain`参数改为可选
- 不传`data_domain`时返回全量辞典
- 传`data_domain`时仍可按域过滤（向后兼容）

### 3. 中文名词扫描工具

**文件**: `backend/services/field_mapping/chinese_column_scanner.py`

**功能**:
1. `scan_all_chinese_columns()`: 扫描所有已注册文件中的中文字段名
2. `translate_chinese_to_english()`: 将中文名词翻译为英文标准字段
3. `generate_english_field_code()`: 生成唯一的英文字段代码
4. `scan_and_translate()`: 完整的扫描和翻译流程

**特点**:
- 自动检测中文字符
- 使用常见中英文映射词典
- 确保字段代码唯一性
- 统计出现频率和数据域分布

### 4. 命令行工具

**文件**: `scripts/scan_and_translate_chinese_columns.py`

**使用方法**:
```bash
# 预览扫描结果（不更新数据库）
python scripts/scan_and_translate_chinese_columns.py --dry-run

# 扫描并更新辞典
python scripts/scan_and_translate_chinese_columns.py --update-dict

# 限制扫描文件数（测试用）
python scripts/scan_and_translate_chinese_columns.py --max-files 10 --dry-run
```

**功能**:
- 扫描所有文件中的中文字段名
- 翻译为英文标准字段
- 确保一对一映射（按`cn_name`唯一性检查）
- 更新或插入到辞典表

## 数据库约束

### 重要：确保一对一映射

为了确保每个中文名称只对应一个英文标准字段，需要在数据库表上添加唯一约束：

```sql
-- 添加cn_name唯一约束（如果还没有）
ALTER TABLE field_mapping_dictionary 
ADD CONSTRAINT uq_field_mapping_dictionary_cn_name UNIQUE (cn_name);
```

**注意**：如果表中已有重复的`cn_name`，需要先清理：

```sql
-- 查找重复的cn_name
SELECT cn_name, COUNT(*) as cnt
FROM field_mapping_dictionary
GROUP BY cn_name
HAVING COUNT(*) > 1;

-- 保留第一个，删除其他重复项（需要手动处理）
```

### 映射策略

1. **唯一性检查**：
   - 按`cn_name`（中文名称）检查是否已存在
   - 如果已存在，只更新描述等信息，不创建新记录
   - 如果不存在，创建新记录

2. **字段代码生成**：
   - 基础翻译：使用常见映射词典
   - 唯一性保证：如果基础代码已存在，添加数字后缀（如`date_1`）
   - 格式规范：转换为snake_case格式

3. **冲突处理**：
   - 如果同一个中文名称在不同数据域出现，使用第一个数据域作为主数据域
   - 在描述中记录所有出现的数据域

## 翻译词典

### 常见映射（内置）

```python
{
    "日期": "date",
    "订单号": "order_id",
    "浏览量": "page_views",
    "访客数": "visitors",
    "跳出率": "bounce_rate",
    "转化率": "conversion_rate",
    # ... 更多映射
}
```

### 扩展策略

1. **直接匹配**：优先使用内置词典
2. **部分匹配**：如果无法完全匹配，尝试部分匹配
3. **拼音占位**：如果无法翻译，使用拼音首字母（可后续手动修正）

## 使用流程

### 管理员操作

1. **扫描和翻译**：
   ```bash
   python scripts/scan_and_translate_chinese_columns.py --update-dict
   ```

2. **验证结果**：
   - 检查前20个高频字段的翻译是否正确
   - 确认一对一映射关系

3. **手动修正**（如需要）：
   - 通过API或数据库直接修改不准确的翻译

### 用户操作

1. **加载辞典**：
   - 前端自动加载全量辞典（无需选择数据域）

2. **选择字段**：
   - 在"数据库列名层（中文）"列选择中文名称
   - 系统自动显示对应的英文标准字段

3. **验证映射**：
   - 同时看到中文和英文，便于检查映射是否正确

## 优势

1. **字段齐全**：全量加载，不再受数据域限制
2. **自动发现**：扫描所有文件，自动发现新的中文字段名
3. **一对一映射**：确保数据一致性，避免混乱
4. **用户友好**：中文用户选择中文名称，系统自动映射到英文

## 注意事项

1. **性能考虑**：
   - 全量辞典可能包含数百个字段，需要优化前端渲染
   - 考虑添加搜索和筛选功能

2. **翻译质量**：
   - 自动翻译可能不准确，需要人工审核
   - 建议定期运行扫描工具，更新翻译

3. **向后兼容**：
   - API仍支持按数据域过滤（可选参数）
   - 前端可以逐步迁移到全量加载

## 后续优化

1. **智能翻译**：
   - 使用AI翻译API提高翻译准确性
   - 学习用户的手动修正，改进翻译词典

2. **同义词处理**：
   - 识别同义词（如"日期"和"统计日期"）
   - 映射到同一个标准字段

3. **分类优化**：
   - 根据字段含义自动分类（dimension/amount/quantity等）
   - 提高字段分组准确性

