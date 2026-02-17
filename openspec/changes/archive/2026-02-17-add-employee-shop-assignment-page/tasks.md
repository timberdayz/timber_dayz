# Tasks: 人员店铺归属和提成比页面

## Phase 2: 表格化平铺与双子页（2026-01-31 优化）

### 2.1 店铺可分配利润率表

- [x] 2.1.1 在 `schema.py` 中新增 `ShopCommissionConfig` 模型（platform_code, shop_id, allocatable_profit_rate）
- [x] 2.1.2 创建迁移 `shop_commission_config`

### 2.2 前端页面拆分

- [x] 2.2.1 主页面改为 Tab 结构：配置 / 统计
- [x] 2.2.2 配置子页：以店铺为行，表格化平铺（可分配利润率占位、主管/操作员多选展示、+ 添加、移除）
- [x] 2.2.3 统计子页：月份选择器 + 表格（当月销售额、当月利润、当月目标达成率、主管/操作员利润收入，占位 0）
- [x] 2.2.4 权限改为仅 admin：`roles: ['admin']`

### 2.3 后端 API 扩展

- [x] 2.3.1 新增 `GET /api/hr/shop-commission-config` 按店铺维度聚合（含可分配利润率、主管/操作员列表）
- [x] 2.3.2 新增 `PUT /api/hr/shop-commission-config/{platform_code}/{shop_id}` 行内保存
- [x] 2.3.3 新增 `GET /api/hr/shop-profit-statistics?month=YYYY-MM` 统计子页数据

---

## 1. 数据库层（Phase 1 已完成）

### 1.1 创建 ORM 模型

- [x] 1.1.1 在 `modules/core/db/schema.py` 中新增 `EmployeeShopAssignment` 模型
  - 表名 `employee_shop_assignments`，schema `a_class`
  - 字段：id, employee_code, platform_code, shop_id, commission_ratio, role, effective_from, effective_to, status, created_at, updated_at
  - 唯一约束 `(employee_code, platform_code, shop_id)`，命名 `uq_employee_shop_assignments_a`
  - 外键 `(platform_code, shop_id)` → dim_shops，`ON DELETE RESTRICT`
  - 索引（A 类表命名）：`ix_employee_shop_assignments_a_employee`、`ix_employee_shop_assignments_a_shop`、`ix_employee_shop_assignments_a_status`
  - employee_code 逻辑引用 employees；删除员工时需先解除其归属（应用层校验）

- [x] 1.1.2 在 `modules/core/db/__init__.py` 中导出 `EmployeeShopAssignment`

### 1.2 创建迁移

- [x] 1.2.1 执行 `alembic revision --autogenerate -m "add_employee_shop_assignments"`
- [x] 1.2.2 检查生成的迁移脚本，确保创建 `a_class.employee_shop_assignments`
- [x] 1.2.3 本地执行 `alembic upgrade head` 验证（表已存在，已 stamp）

## 2. 后端 API

### 2.1 Pydantic 模型

- [x] 2.1.1 新增 `EmployeeShopAssignmentCreate`（employee_code, platform_code, shop_id, commission_ratio?, role?, effective_from?, effective_to?）
  - commission_ratio 若提供：`ge=0, le=1`（闭区间）
  - effective_from、effective_to 若均提供：`effective_to >= effective_from`
- [x] 2.1.2 新增 `EmployeeShopAssignmentUpdate`（commission_ratio?, role?, effective_from?, effective_to?, status?）
  - 同上 commission_ratio、effective 校验
- [x] 2.1.3 新增 `EmployeeShopAssignmentResponse`（含 id, employee_code, platform_code, shop_id, commission_ratio, role, effective_from, effective_to, status, created_at, updated_at，以及关联的 employee name、shop name）

### 2.2 路由实现

- [x] 2.2.1 `GET /api/hr/employee-shop-assignments` - 列表（分页、筛选）
  - Query: page, page_size, employee_code, shop_id, platform_code, status
  - 返回 items + total，LEFT JOIN employees、dim_shops 补全姓名和店铺名（防御孤儿数据）

- [x] 2.2.2 `POST /api/hr/employee-shop-assignments` - 新增
  - 校验 employee_code 存在于 employees
  - 校验 (platform_code, shop_id) 存在于 dim_shops，否则 400，提示「该店铺尚未同步至系统，请先在账号管理中同步」
  - 校验唯一约束，重复则 409

- [x] 2.2.3 `PUT /api/hr/employee-shop-assignments/{id}` - 更新
  - 若 id 不存在，返回 404

- [x] 2.2.4 `DELETE /api/hr/employee-shop-assignments/{id}` - 删除
  - 若 id 不存在，返回 404

- [x] 2.2.5 员工删除时：在 `DELETE /api/hr/employees/{employee_code}` 中，若该员工有关联归属记录，返回 400 并提示「请先解除该员工的店铺归属」
- [x] 2.2.6 店铺删除时：dim_shops 外键 `ON DELETE RESTRICT`，有归属记录时禁止删除店铺

### 2.3 权限

- [x] 2.3.1 归属 CRUD 需人力管理权限（与人力管理一致；实现时核对实际权限名，可能为 `human-resources` 或 `hr-management`）

## 3. 前端

### 3.1 API 封装

- [x] 3.1.1 在 `frontend/src/api/index.js` 中新增：
  - `getHrEmployeeShopAssignments(params)`
  - `createHrEmployeeShopAssignment(data)`
  - `updateHrEmployeeShopAssignment(id, data)`
  - `deleteHrEmployeeShopAssignment(id)`

### 3.2 依赖数据接口

- [x] 3.2.1 员工列表：使用 `GET /api/hr/employees`，下拉仅展示 `status='active'` 的在职员工
- [x] 3.2.2 店铺列表：**复用 `api.getTargetShops()`**（`GET /api/targets/shops`），禁止使用不存在的 `/api/shops`；后端 POST 前校验 `(platform_code, shop_id)` 存在于 dim_shops

### 3.3 页面实现

- [x] 3.3.1 创建 `frontend/src/views/hr/ShopAssignment.vue`
  - 表格列：员工姓名、员工编号、平台、店铺名称、提成比例、角色、生效区间、状态、操作
  - 筛选：员工、店铺、平台、状态
  - 新增/编辑对话框：员工选择（仅在职）、店铺选择（api.getTargetShops，按平台过滤）、提成比例、角色、生效起始/截止；编辑时员工与店铺为只读
  - 删除确认

- [x] 3.3.2 在 `frontend/src/config/menuGroups.js` 人力资源分组下新增 `/hr-shop-assignment`
- [x] 3.3.3 在 `frontend/src/router/index.js` 中新增路由
- [x] 3.3.4 在 `route.meta.title`（router 配置）中设置「人员店铺归属和提成比」；在 `routeDisplayNames`（menuGroups.js）中新增 `/hr-shop-assignment` 映射

## 4. 测试与验证

- [x] 4.1 运行 `python scripts/verify_architecture_ssot.py` 确保 SSOT 合规
- [ ] 4.2 手动测试：新增归属、编辑、删除、筛选
- [ ] 4.3 验证唯一约束：同一员工+同一店铺重复新增应返回 409

## 5. 文档

- [x] 5.1 在页面或帮助中注明：配置将用于提成计算，计算逻辑由后续任务实现
