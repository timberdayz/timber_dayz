# 四层字段映射架构实现方案

## 架构设计

### 四层映射关系

```
原始字段（中文，如"订单号"）
    ↓ 【用户选择】
数据库列名层（中文，如"订单号"，用户可选择）
    ↓ 【系统自动映射】
标准字段（英文，如"order_id"，只读显示）
    ↓ 【直接映射】
数据库列名（英文，如"order_id"，实际存储）
```

## 实现细节

### 1. 数据结构

每个映射项包含：
- `original_column`: 原始字段名（中文）
- `cn_name`: 数据库列名层（中文，用户选择）
- `standard_field`: 标准字段（英文，只读）

### 2. 用户交互流程

1. **用户选择数据库列名层（中文）**
   - 从下拉列表中选择中文名称（如"订单号"）
   - 系统自动查找对应的`field_code`（如"order_id"）
   - 自动填充`standard_field`字段（只读显示）

2. **自动映射机制**
   ```javascript
   updateMappingLayer(originalColumn, cnName) {
     // 查找对应的标准字段
     const field = dictionaryFields.find(f => f.cn_name === cnName)
     if (field) {
       mapping.cn_name = cnName
       mapping.standard_field = field.field_code  // 自动映射
     }
   }
   ```

3. **前端显示**
   - 原始字段列：显示原始字段名
   - 数据库列名层列：下拉选择框（中文）
   - 标准字段列：只读显示（英文，带"自动映射，只读"提示）

### 3. 入库流程

入库时使用`standard_field`（英文）：
```javascript
mappingsObj[m.original_column] = m.standard_field  // 使用英文标准字段
```

## 优势

1. **用户体验友好**：中文用户选择中文名称，直观易懂
2. **系统安全**：标准字段始终是英文，符合最佳实践
3. **自动化**：选择中文后自动映射到英文，无需手动输入
4. **可验证**：用户可以同时看到中文和英文，便于检查映射是否正确

## 注意事项

1. **字典表要求**：
   - `field_code`必须是英文（如"order_id"）
   - `cn_name`是中文（如"订单号"）
   - 一对一映射关系：每个`cn_name`对应一个`field_code`

2. **初始化逻辑**：
   - 预览数据时，初始化为空映射
   - 生成智能映射后，根据`standard_field`查找对应的`cn_name`

3. **入库使用**：
   - 入库时统一使用`standard_field`（英文）
   - 不直接使用`cn_name`（中文）

