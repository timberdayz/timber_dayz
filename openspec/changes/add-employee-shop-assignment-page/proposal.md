# Change: 人员店铺归属和提成比页面

## Why

西虹ERP作为**决策支撑系统**，需明确**员工与店铺的归属关系**及**提成比例**，以支撑：

1. **提成计算**：`c_class.employee_commissions` 当前无写入逻辑，需依据「员工→店铺归属」将店铺销售额按提成比归集到员工
2. **数据透明**：管理员需集中配置「谁负责哪些店铺」「各店铺提成比例多少」，当前无配置入口
3. **我的收入依据**：「我的收入」页展示的提成金额依赖 `employee_commissions`，而该表计算需员工-店铺关联

add-performance-and-personal-income 提案明确「Phase 1 不实现员工-店铺关联表」，本提案补齐该能力并新增前端配置页面。

## What Changes

### 1. 新增 A 类表：员工店铺归属（employee_shop_assignments）

- **位置**：`a_class.employee_shop_assignments`
- **字段**：employee_code, platform_code, shop_id, commission_ratio（可选，覆盖薪资结构默认值）, role（可选）, effective_from, effective_to, status
- **唯一约束**：(employee_code, platform_code, shop_id)
- **用途**：配置员工负责的店铺及该店铺对应的提成比例

### 2. 新增 API：员工店铺归属 CRUD

- `GET /api/hr/employee-shop-assignments` - 列表（分页、筛选）
- `POST /api/hr/employee-shop-assignments` - 新增归属
- `PUT /api/hr/employee-shop-assignments/{id}` - 更新归属
- `DELETE /api/hr/employee-shop-assignments/{id}` - 删除归属

### 3. 新增前端页面：人员店铺归属和提成比

- **路由**：`/hr-shop-assignment`（建议）
- **菜单位置**：人力资源分组下
- **功能**：列表、新增、编辑、删除、按员工/店铺/平台筛选

### 4. 提成比逻辑说明

- **优先级**：`employee_shop_assignments.commission_ratio` > `salary_structures.commission_ratio`（取 status=active 且 effective_date≤当前日期的最新记录）> 0
- **计算**：员工某月提成 = Σ(归属店铺当月销售额 × 该归属的提成比)
- **多人同店**：同一店铺可归属多人，各自按全店销售额×各自比例独立计算（不拆分销售额）
- **写入**：`c_class.employee_commissions` 由后端定时任务或 Metabase 依据本表计算后写入（本提案仅提供配置，写入逻辑可后续实现）

## Impact

### 受影响的规格

- **hr-management**：ADDED - 人员店铺归属与提成比配置能力

### 受影响的代码与数据

| 类型 | 文件/对象 | 修改内容 |
|------|-----------|----------|
| Schema | `modules/core/db/schema.py` | 新增 EmployeeShopAssignment 模型 |
| 迁移 | `migrations/versions/` | 新建迁移创建 a_class.employee_shop_assignments |
| 后端 | `backend/routers/hr_management.py` | 新增归属 CRUD 端点 |
| 前端 | `frontend/src/views/hr/ShopAssignment.vue` | 新建页面 |
| 前端 | `frontend/src/api/index.js` | 新增归属 API 封装 |
| 前端 | `frontend/src/config/menuGroups.js` | 新增菜单项 |
| 前端 | `frontend/src/router/index.js` | 新增路由 |

### 依赖关系

- **前置**：add-performance-and-personal-income（我的收入、绩效公示）可独立进行，本提案不阻塞
- **后置**：employee_commissions 写入逻辑（定时任务/Metabase）依赖本表，可单独实现

## 非目标（Non-Goals）

- 本提案不实现 employee_commissions 的自动写入逻辑（仅提供配置表与页面）
- 不实现店铺销售额的实时归集展示（仅配置层）
- 不修改 SalaryStructure 的 commission_ratio 字段（保留为默认值）
