# 费用管理API修复报告

**日期**: 2026-01-29  
**问题**: 费用管理页面加载失败，返回500错误  
**状态**: ✅ 已修复

---

## 🔍 问题诊断

### 错误现象

- 前端显示"加载费用列表失败"
- 浏览器控制台显示：`api/expenses:1` 返回500 Internal Server Error
- 错误堆栈指向 `ExpenseManagement.vue:376` 的 `loadExpenses` 函数

### 根本原因

**数据库表使用中文字段名，但ORM模型使用英文字段名，导致查询失败**

- **数据库表结构** (`a_class.operating_costs`):
  - 使用中文字段名：`店铺ID`, `年月`, `租金`, `工资`, `水电费`, `其他成本`, `创建时间`, `更新时间`
- **ORM模型** (`OperatingCost`):
  - 使用英文字段名：`shop_id`, `year_month`, `rent`, `salary`, `utilities`, `other_costs`
- **问题**: SQLAlchemy ORM查询无法匹配中文字段名，导致查询失败

---

## ✅ 修复方案

参考 `target_sync_service.py` 的实现方式，**所有数据库操作改用原始SQL查询**，直接使用中文字段名。

### 修复的方法

1. **`list_expenses`** - 查询费用列表
   - 使用 `text()` 执行原始SQL
   - 使用中文字段名：`"店铺ID"`, `"年月"`, `"租金"` 等
   - 使用 `AS` 别名映射为英文字段名返回给前端

2. **`get_expense`** - 查询费用详情
   - 使用原始SQL查询单条记录

3. **`create_or_update_expense`** - 创建/更新费用（Upsert）
   - 使用 `INSERT ... ON CONFLICT DO UPDATE` 语法
   - 使用中文字段名插入和更新

4. **`update_expense`** - 更新费用
   - 使用原始SQL的 `UPDATE` 语句
   - 只更新提供的字段

5. **`delete_expense`** - 删除费用
   - 使用原始SQL的 `DELETE` 语句

6. **`get_expense_summary`** - 费用汇总统计
   - 已使用原始SQL，无需修改

### 代码变更

**修改前**:

```python
# 使用ORM查询（失败）
query = select(OperatingCost)
expenses = (await db.execute(query)).scalars().all()
```

**修改后**:

```python
# 使用原始SQL查询（成功）
query = text("""
    SELECT
        id,
        "店铺ID" as shop_id,
        "年月" as year_month,
        "租金" as rent,
        ...
    FROM a_class.operating_costs
    WHERE ...
""")
result = await db.execute(query, params)
rows = result.fetchall()
```

---

## 📝 修改的文件

- `backend/routers/expense_management.py`
  - 所有CRUD方法改为使用原始SQL
  - 移除了 `OperatingCost` ORM模型的导入和使用
  - 清理了未使用的导入

---

## ✅ 验证步骤

1. **启动后端服务**:

   ```bash
   python run.py --backend-only
   ```

2. **测试API端点**:

   ```bash
   # 查询费用列表
   curl http://localhost:8000/api/expenses

   # 查询店铺列表
   curl http://localhost:8000/api/expenses/shops
   ```

3. **前端测试**:
   - 访问费用管理页面：`http://localhost:5173/#/finance/expense-management`
   - 应该能正常加载费用列表（即使为空）
   - 测试创建费用功能
   - 测试编辑费用功能
   - 测试删除费用功能

---

## 🔗 相关参考

- `backend/services/target_sync_service.py` - 参考实现（使用原始SQL操作中文字段名）
- `a_class.sales_targets_a` 表 - 同样使用中文字段名，使用相同的处理方式

---

## ⚠️ 注意事项

1. **字段名映射**:
   - 数据库表：中文字段名（`店铺ID`, `年月` 等）
   - API响应：英文字段名（`shop_id`, `year_month` 等）
   - 使用SQL `AS` 别名进行映射

2. **SQL注入防护**:
   - 所有SQL查询使用参数化查询（`:param_name`）
   - 使用 `text()` 和参数字典，避免SQL注入

3. **未来优化**:
   - 考虑创建数据库迁移，将中文字段名重命名为英文字段名
   - 或者修改ORM模型，使用 `name` 参数映射中文字段名

---

**修复完成！** 🎉
