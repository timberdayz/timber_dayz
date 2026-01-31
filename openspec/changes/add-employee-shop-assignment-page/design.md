# Design: 人员店铺归属和提成比页面

## Context

- **背景**：员工提成计算需明确「员工负责哪些店铺」「各店铺可分配利润率、每人提成比例」
- **现状**：已有 employee_shop_assignments，需扩展为店铺为中心、表格化平铺、双子页结构
- **约束**：参考费用管理页面设计；整个模块仅管理员可见

## Goals / Non-Goals

- **Goals**：
  - 提供配置子页：以店铺为行，表格化平铺，行内编辑（可分配利润率、主管/操作员多选、每人提成比）
  - 提供统计子页：按月份展示当月销售额、利润、目标达成率、人员利润收入
  - 支持一人多店、一店多人，每人每店提成比独立配置
  - 一店多人：店铺可分配利润率固定，多人手动分配（不自动均分）

- **Non-Goals**：
  - 不实现 employee_commissions 的自动写入（配置与统计展示先行）

## Decisions

### 1. 表结构设计

#### 1.1 员工店铺归属（已有）

**表名**：`a_class.employee_shop_assignments`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| employee_code | VARCHAR(64) NOT NULL | 员工编号，外键 a_class.employees.employee_code（逻辑引用） |
| platform_code | VARCHAR(32) NOT NULL | 平台编码，外键 dim_shops.platform_code |
| shop_id | VARCHAR(256) NOT NULL | 店铺ID，外键 dim_shops.shop_id |
| commission_ratio | FLOAT NULL | 提成比例(0-1)，NULL 时使用 salary_structures.commission_ratio |
| role | VARCHAR(32) NULL | 角色：supervisor（主管）/ operator（操作员） |
| effective_from | DATE NULL | 生效起始日，NULL=立即生效 |
| effective_to | DATE NULL | 生效截止日，NULL=无截止 |
| status | VARCHAR(32) NOT NULL DEFAULT 'active' | active/inactive |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

**唯一约束**：`(employee_code, platform_code, shop_id)`，命名为 `uq_employee_shop_assignments_a`

**外键**：
- `(platform_code, shop_id)` → `dim_shops(platform_code, shop_id)`，`ON DELETE RESTRICT`（有归属记录时禁止删除店铺）
- `employee_code` 逻辑引用 `a_class.employees.employee_code`，删除员工时需先解除或删除其归属记录（应用层校验）

**索引**（遵循 A 类表命名规范，添加 `_a` 后缀）：
- `ix_employee_shop_assignments_a_employee` (employee_code)
- `ix_employee_shop_assignments_a_shop` (platform_code, shop_id)
- `ix_employee_shop_assignments_a_status` (status)

#### 1.2 店铺可分配利润率配置（新增）

**表名**：`a_class.shop_commission_config`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| platform_code | VARCHAR(32) NOT NULL | 平台编码 |
| shop_id | VARCHAR(256) NOT NULL | 店铺ID |
| allocatable_profit_rate | FLOAT NOT NULL DEFAULT 0 | 可分配利润率(0-1)，利润的百分之多少用于主管+操作员 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

**唯一约束**：`(platform_code, shop_id)`  
**外键**：`(platform_code, shop_id)` → dim_shops，ON DELETE RESTRICT

### 2. 提成比优先级

1. `employee_shop_assignments.commission_ratio` 若不为 NULL，使用该值
2. 否则使用 `salary_structures.commission_ratio`：按 employee_code 查，取 `status='active'` 且 `effective_date <= 当前日期` 的最新记录
3. 若员工无薪资结构或无可用的薪资结构记录，使用 0

### 2.1 多人同店提成计算语义

**店铺级可分配利润率**：店铺利润的百分之多少用于主管+操作员分配（新增 `shop_commission_config.allocatable_profit_rate`）。

**一店多人**：总比例固定（可分配利润率），多人手动分配各自 commission_ratio；不自动均分。校验：同一店铺所有归属记录的 commission_ratio 之和 ≤ 可分配利润率。

**计算链**：可分配利润 = 店铺当月利润 × 可分配利润率；每人利润收入 = 可分配利润 × 该人 commission_ratio。

**时间维度**：所有经营数据与提成统计按所选月份（YYYY-MM）执行；配置为当前生效规则。

### 3. API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/hr/employee-shop-assignments | 列表，支持 page, page_size, employee_code, shop_id, platform_code, status |
| POST | /api/hr/employee-shop-assignments | 新增，Body: employee_code, platform_code, shop_id, commission_ratio?, role?, effective_from?, effective_to? |
| PUT | /api/hr/employee-shop-assignments/{id} | 更新 |
| DELETE | /api/hr/employee-shop-assignments/{id} | 删除（软删可选，本阶段硬删） |

**响应**：统一格式 `{ success, data, message }`，列表返回 `{ items, total }`

**校验**：
- `commission_ratio`：若提供，则 `0 <= commission_ratio <= 1`（闭区间）
- `effective_from`、`effective_to`：若两者均提供，则 `effective_to >= effective_from`

### 3.1 店铺数据来源

- **前端下拉**：复用 `api.getTargetShops()`（`GET /api/targets/shops`），返回自 `platform_accounts`
- **后端写入**：`(platform_code, shop_id)` 必须存在于 `dim_shops`，否则 400，提示「该店铺尚未同步至系统，请先在账号管理中同步」
- **一致性**：`platform_accounts` 经 `shop_sync_service` 同步至 `dim_shops`，正常情况下两者一致；若店铺仅存在于 platform_accounts 尚未同步，需先完成同步或由管理员在账号管理中触发同步

### 4. 前端页面设计（参考费用管理）

**主页面**：`ShopAssignment.vue`，Tab 切换两个子页

#### 4.1 配置子页（人员店铺归属和提成比配置）

- **以店铺为行**：表格化平铺，参考费用管理；左列固定（平台、店铺），右列可编辑
- **列**：平台、店铺、可分配利润率、店铺主管（多选）、主管提成比（每人独立，可展开明细或子表）、店铺操作员（多选）、操作员提成比（同上）、操作（行内保存、删除）
- **行内编辑**：不弹窗，直接在表格中编辑；支持「+ 为所有店铺添加」快速初始化
- **校验**：同一店铺主管+操作员提成比之和 ≤ 可分配利润率

#### 4.2 统计子页（店铺利润和人员利润统计）

- **月份选择器**：YYYY-MM，与费用管理一致
- **列**：平台、店铺、当月销售额、当月利润、当月目标达成率、主管利润收入、操作员利润收入（只读）
- **数据来源**：销售额/利润来自 B 类订单；达成率来自 sales_targets_a；人员利润收入由后端按所选月份计算

### 5. 替代方案

- **方案 A**：在 Employee 表增加 JSONB 字段存储 shop_ids
  - 否决：无法存储 per-shop commission_ratio，查询不便

- **方案 B**：复用 target_breakdown 等表
  - 否决：语义不同，target_breakdown 用于目标分解

- **方案 C**：独立 A 类表（采用）
  - 优点：结构清晰，易扩展，符合三层分类

## Risks / Trade-offs

- **风险**：employee_commissions 写入逻辑未实现，配置后短期内无可见效果
- **缓解**：在页面说明「配置将用于提成计算，具体计算逻辑由后续任务实现」

## Migration Plan

1. 创建 Alembic 迁移，新建 `a_class.employee_shop_assignments`
2. 在 `schema.py` 中定义 `EmployeeShopAssignment` 模型
3. 在 `__init__.py` 中导出模型
4. 实现后端 CRUD、前端页面、菜单与路由
5. 验证 CRUD 流程

**回滚**：`alembic downgrade -1` 删除表

## Open Questions

- [x] 是否支持一个店铺多人归属（多人分提成）？→ **已确定**：支持，各自按全店销售额×比例独立计算（见 2.1）
- [ ] 是否需要历史快照（变更记录）？→ 本阶段不实现
