# 费用管理功能实施总结

**版本**: v4.21.0  
**日期**: 2026-01-29  
**状态**: ✅ 已完成

---

## 📋 实施内容

### 1. 后端API (`backend/routers/expense_management.py`)

创建了新的费用管理API，使用 `a_class.operating_costs` 表（中文字段名）：

**API端点**:

- `GET /api/expenses` - 查询费用列表（支持分页、筛选）
- `GET /api/expenses/{id}` - 查询费用详情
- `POST /api/expenses` - 创建/更新费用（Upsert逻辑）
- `PUT /api/expenses/{id}` - 更新费用
- `DELETE /api/expenses/{id}` - 删除费用
- `GET /api/expenses/shops` - 获取店铺列表（复用目标管理的店铺API）
- `GET /api/expenses/summary/monthly` - 按月汇总统计

**关键特性**:

- ✅ 使用 `a_class.operating_costs` 表（中文字段名：`店铺ID`, `年月`, `租金`, `工资`, `水电费`, `其他成本`）
- ✅ Upsert逻辑：同店铺+同月份 → 更新，否则创建
- ✅ 复用目标管理的店铺列表API
- ✅ 支持分页和筛选（按年月、店铺）
- ✅ 自动计算合计金额

### 2. 前端页面 (`frontend/src/views/finance/ExpenseManagement.vue`)

创建了完整的费用管理前端页面：

**功能**:

- ✅ 费用列表展示（表格）
- ✅ 统计卡片（总费用、租金、工资、其他）
- ✅ 筛选功能（按年月、店铺）
- ✅ 创建/编辑费用对话框
- ✅ 删除费用（带确认）
- ✅ 分页支持
- ✅ 自动计算合计金额

**UI设计**:

- 参考目标管理页面的设计风格
- 使用Element Plus组件
- 响应式布局

### 3. 清理工作

**删除旧API** (`backend/routers/config_management.py`):

- ✅ 删除了 `OperatingCostCreate`, `OperatingCostUpdate`, `OperatingCostResponse` Pydantic模型
- ✅ 删除了 `/operating-costs` GET和POST端点
- ✅ 添加了删除注释说明

**数据库清理脚本** (`scripts/cleanup_public_operating_costs.py`):

- ✅ 创建了清理脚本，用于删除 `public` schema 下的 `operating_costs` 表
- ✅ 包含安全检查（检查数据量、确认操作）
- ✅ 检查 `a_class.operating_costs` 表是否存在

### 4. 路由注册 (`backend/main.py`)

- ✅ 在 `main.py` 中导入 `expense_management` 模块
- ✅ 注册路由：`/api/expenses`，标签：`费用管理`

---

## 🔧 后续步骤

### 1. 执行数据库清理（可选但推荐）

```bash
# 运行清理脚本，删除 public schema 下的旧表
python scripts/cleanup_public_operating_costs.py
```

**注意**:

- 执行前请确认 `a_class.operating_costs` 表已存在
- 如果有数据需要迁移，请先迁移数据再执行清理

### 2. 测试新功能

1. **后端API测试**:

   ```bash
   # 启动后端服务
   python run.py --backend-only

   # 测试API端点
   curl http://localhost:8000/api/expenses/shops
   curl http://localhost:8000/api/expenses
   ```

2. **前端页面测试**:
   - 访问费用管理页面：`http://localhost:5173/#/finance/expense-management`
   - 测试创建费用
   - 测试编辑费用
   - 测试删除费用
   - 测试筛选功能

### 3. 验证与Metabase的联动

确保经营指标SQL (`business_overview_operational_metrics.sql`) 能正确读取费用数据：

```sql
-- 验证查询
SELECT
    "年月",
    COUNT(*) as count,
    SUM("租金" + "工资" + "水电费" + "其他成本") as total
FROM a_class.operating_costs
GROUP BY "年月"
ORDER BY "年月" DESC;
```

---

## 📊 数据表结构

### `a_class.operating_costs` (正确表)

| 字段名     | 类型          | 说明              |
| ---------- | ------------- | ----------------- |
| `id`       | BIGINT        | 主键              |
| `店铺ID`   | VARCHAR(256)  | 店铺ID            |
| `年月`     | VARCHAR(7)    | 费用月份(YYYY-MM) |
| `租金`     | NUMERIC(15,2) | 租金(CNY)         |
| `工资`     | NUMERIC(15,2) | 工资(CNY)         |
| `水电费`   | NUMERIC(15,2) | 水电费(CNY)       |
| `其他成本` | NUMERIC(15,2) | 其他成本(CNY)     |
| `创建时间` | TIMESTAMP     | 创建时间          |
| `更新时间` | TIMESTAMP     | 更新时间          |

**唯一约束**: `(店铺ID, 年月)`

---

## ⚠️ 注意事项

1. **表结构一致性**:
   - ✅ 新API使用 `a_class.operating_costs` 表（中文字段名）
   - ✅ Metabase SQL也使用 `a_class.operating_costs` 表
   - ❌ 不再使用 `public.operating_costs` 表

2. **字段映射**:
   - ORM模型 (`OperatingCost`) 使用英文字段名（`shop_id`, `year_month`, `rent`, `salary`, `utilities`, `other_costs`）
   - 数据库表使用中文字段名（`店铺ID`, `年月`, `租金`, `工资`, `水电费`, `其他成本`）
   - SQLAlchemy会自动处理映射（通过ORM模型定义）

3. **API兼容性**:
   - 新API路径：`/api/expenses/*`
   - 旧API路径：`/api/config/operating-costs`（已删除）
   - 前端需要更新API调用路径

---

## 📝 相关文件

- `backend/routers/expense_management.py` - 费用管理API
- `frontend/src/views/finance/ExpenseManagement.vue` - 费用管理前端页面
- `backend/routers/config_management.py` - 已删除旧API（保留注释）
- `scripts/cleanup_public_operating_costs.py` - 数据库清理脚本
- `backend/main.py` - 路由注册
- `sql/metabase_questions/business_overview_operational_metrics.sql` - 经营指标SQL（使用费用数据）

---

## ✅ 完成检查清单

- [x] 创建后端API (`expense_management.py`)
- [x] 创建前端页面 (`ExpenseManagement.vue`)
- [x] 删除旧API (`config_management.py`)
- [x] 创建数据库清理脚本
- [x] 注册路由 (`main.py`)
- [x] 代码检查（无语法错误）
- [ ] 执行数据库清理脚本（需要手动执行）
- [ ] 功能测试（需要手动测试）
- [ ] 验证Metabase联动（需要手动验证）

---

**实施完成！** 🎉
