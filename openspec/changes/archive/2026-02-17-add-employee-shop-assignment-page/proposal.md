# Change: 人员店铺归属和提成比页面

## Why

西虹ERP作为**决策支撑系统**，需明确**员工与店铺的归属关系**及**提成比例**，以支撑：

1. **提成计算**：`c_class.employee_commissions` 当前无写入逻辑，需依据「员工→店铺归属」将店铺利润按提成比归集到员工
2. **数据透明**：管理员需集中配置「谁负责哪些店铺」「各店铺可分配利润率、每人提成比」，当前无配置入口
3. **我的收入依据**：「我的收入」页展示的提成金额依赖 `employee_commissions`，而该表计算需员工-店铺关联

add-performance-and-personal-income 提案明确「Phase 1 不实现员工-店铺关联表」，本提案补齐该能力并新增前端配置页面。

## What Changes

### 1. 模块结构（参考费用管理）

**人员店铺归属和提成比**模块下分为两个子页面（Tab 切换）：

| 子页面 | 功能 |
|--------|------|
| **人员店铺归属和提成比配置** | 以店铺为行，表格化平铺配置可分配利润率、主管/操作员（多选）、每人提成比 |
| **店铺利润和人员利润统计** | 按月份展示当月销售额、当月利润、当月目标达成率、主管/操作员利润收入 |

### 2. 月份选择器与时间维度

- **配置页**：配置为当前生效规则，可不按月份（或支持按月份生效，后续扩展）
- **统计页**：顶部月份选择器（YYYY-MM），与费用管理一致；所有经营数据与提成统计按所选月份计算

### 3. 数据模型（沿用并扩展）

- **employee_shop_assignments**：员工-店铺归属，每人每店独立 commission_ratio，role 区分 supervisor/operator
- **shop_commission_config**（新增）：店铺级可分配利润率（利润的百分之多少用于主管+操作员分配）
- **计算**：可分配利润 = 店铺利润 × 可分配利润率；每人利润收入 = 可分配利润 × 该人提成比（多人手动分配，不自动均分）

### 4. 权限

- **整个模块仅管理员可见**：`roles: ['admin']`，其他角色不展示菜单与路由

### 5. 前端布局（参考费用管理）

- **配置子页**：以店铺为行，表格化平铺；左列固定（平台、店铺），右列可编辑（可分配利润率、店铺主管多选、主管提成比、店铺操作员多选、操作员提成比）；行内保存/删除
- **统计子页**：月份选择器 + 表格，列：平台、店铺、当月销售额、当月利润、当月目标达成率、主管利润收入、操作员利润收入；只读展示

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
