# Design: 人员店铺归属和提成比页面

## Context

- **背景**：员工提成计算需明确「员工负责哪些店铺」「各店铺提成比例多少」
- **现状**：无员工-店铺关联表，SalaryStructure 仅有全局 commission_ratio
- **约束**：遵循三层数据分类（A类=用户配置），与 add-performance-and-personal-income 解耦

## Goals / Non-Goals

- **Goals**：
  - 提供 A 类配置表存储员工-店铺归属及提成比
  - 提供前端页面支持 CRUD 配置
  - 为后续 employee_commissions 写入逻辑提供数据基础

- **Non-Goals**：
  - 不实现 employee_commissions 的自动计算与写入
  - 不在本提案内实现 Metabase 或 Celery 定时任务

## Decisions

### 1. 表结构设计

**表名**：`a_class.employee_shop_assignments`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGSERIAL | 主键 |
| employee_code | VARCHAR(64) NOT NULL | 员工编号，外键 a_class.employees.employee_code（逻辑引用） |
| platform_code | VARCHAR(32) NOT NULL | 平台编码，外键 dim_shops.platform_code |
| shop_id | VARCHAR(256) NOT NULL | 店铺ID，外键 dim_shops.shop_id |
| commission_ratio | FLOAT NULL | 提成比例(0-1)，NULL 时使用 salary_structures.commission_ratio |
| role | VARCHAR(32) NULL | 角色（可选，如 primary/secondary） |
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

### 2. 提成比优先级

1. `employee_shop_assignments.commission_ratio` 若不为 NULL，使用该值
2. 否则使用 `salary_structures.commission_ratio`：按 employee_code 查，取 `status='active'` 且 `effective_date <= 当前日期` 的最新记录
3. 若员工无薪资结构或无可用的薪资结构记录，使用 0

### 2.1 多人同店提成计算语义

同一店铺可归属多人，**各自按全店销售额 × 各自 commission_ratio 独立计算**（不拆分销售额）。例如：店铺 A 月销 10 万，员工甲 5%、员工乙 3%，则甲提成 5000、乙提成 3000，公司总提成支出 8000。

**提成计算时**：仅考虑 `status='active'` 的归属记录；`effective_from` 为 NULL 视为立即生效（无起始限制），`effective_to` 为 NULL 视为无截止；某月归属是否生效：该月须落在 `[effective_from, effective_to]` 区间内。

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

### 4. 前端页面设计

**页面**：`ShopAssignment.vue`（人员店铺归属和提成比）

**布局**：
- 顶部：筛选（员工、店铺、平台、状态）、新增按钮
- 表格：员工姓名、员工编号、平台、店铺名称、提成比例、角色、生效区间、状态、操作
- 操作：编辑、删除

**表单（新增/编辑）**：
- 员工：下拉选择（从 employees 列表，**仅展示 status='active' 的在职员工**，便于日常配置；历史归属仍可在列表中查看）
- 店铺：下拉选择（复用 `api.getTargetShops()`，按 platform 过滤；后端写入前校验 dim_shops）
- 提成比例：数字输入 0-1，可空（使用薪资结构默认）
- 角色：可选
- 生效起始/截止：日期选择，可选

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
