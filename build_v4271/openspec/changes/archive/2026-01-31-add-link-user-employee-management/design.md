# Design: 用户管理与员工管理关联

## Context

- **用户管理**（dim_users）：登录账号，含 username、email、roles，用于认证与权限
- **员工管理**（a_class.employees）：HR 档案，含 employee_code、name、部门、职位
- 当前两套系统无关联，云端部署需支持：先注册账号（含游客），再按需配置员工并关联
- 游客仅需业务概览访问，不建员工档案

## Goals / Non-Goals

**Goals:**
- 建立用户-员工一对一（或零对一）关联，支持双向展示与编辑
- 新增游客角色，权限仅限业务概览
- 用户管理可关联员工，人力管理可关联登录账号
- 员工自助档案（「我的档案」）：已关联员工可自助维护个人联系方式

**Non-Goals:**
- 不自动同步 User 与 Employee 的姓名/邮箱
- 不修改登录/认证流程
- 不实现跨 schema 的数据库级外键（应用层保证一致性）

## Decisions

### 1. 关联方向：Employee.user_id

- **决策**：在 `a_class.employees` 表新增 `user_id`（nullable, FK to dim_users.user_id）
- **理由**：游客无员工记录，员工有则可选关联用户；Employee 为「可选关联」方，存储 FK 更自然
- **约束**：一个 user_id 最多对应一个 Employee（应用层唯一性校验）

### 2. 跨 Schema 外键

- **决策**：不在 PostgreSQL 中创建跨 schema 外键（dim_users 在 public，employees 在 a_class）
- **理由**：跨 schema FK 需显式指定 schema，Alembic 与 ORM 复杂度增加；应用层校验足够
- **实现**：在 UserUpdate/EmployeeCreate/Update 时校验 user_id 存在且未重复关联

### 3. 游客角色

- **决策**：新增 `tourist` 角色，permissions: `['business-overview']`
- **理由**：支持仅需看板访问的访客、试用等场景
- **实现**：rolePermissions.js 新增配置 + `scripts/ensure_all_roles.py` 扩展 REQUIRED_ROLES 插入 dim_roles
- **说明**：插入后角色可在「角色管理中心」展示；不通过 UI「+ 新增角色」新增（后端 create_role 未传 role_code，会导致插入失败）

### 4. API 设计

| 用途 | API | 说明 |
|------|-----|------|
| 员工编辑时选用户 | `GET /api/users/unlinked` | 返回尚未关联员工的用户（id=user_id, username, email），仅 is_active=true；id 供前端作为 user_id 传给 Employee API；需 `get_current_user`，建议 admin 或 human-resources 权限 |
| 用户编辑时选员工 | 复用 `GET /api/hr/employees` | 响应增加 user_id、username，前端过滤可关联员工 |
| 用户关联员工 | `PUT /api/users/{id}` | body 含 employee_id（Employee.id）；后端校验 employee 存在（a_class.employees）后更新 Employee.user_id |
| 员工关联用户 | `POST/PUT /api/hr/employees` | body 含 user_id |
| 员工自助档案 | `GET /api/hr/me/profile` | 当前用户关联的员工档案（仅本人）；需 `get_current_user`；**未关联时**：首次访问自动创建最小员工记录并关联当前用户后返回档案（系统主要面向内部员工，保证「注册并登录即可用」）；仅当自动创建失败时返回 404；路由须在 `/employees/{employee_code}` 之前定义 |
| 员工自助更新 | `PUT /api/hr/me/profile` | 仅允许更新自助可编辑字段；需 `get_current_user`，校验当前用户为该档案关联用户；请求体仅接受白名单字段（phone、email、address、emergency_contact、emergency_phone），忽略其它字段 |

### 5. 员工自助可编辑字段

| 字段 | 说明 | 权限 |
|------|------|------|
| phone | 手机号码 | 本人可编辑 |
| email | 邮箱 | 本人可编辑 |
| address | 现居地址 | 本人可编辑 |
| emergency_contact | 紧急联系人 | 本人可编辑 |
| emergency_phone | 紧急联系人电话 | 本人可编辑 |
| department_id, position_id, 薪资、合同、银行账户等 | - | 仅 HR/管理员 |

### 6. 解除关联

- **用户侧**：UserUpdate.employee_id = null → 将原 Employee.user_id 置空
- **员工侧**：EmployeeUpdate.user_id = null → 解除该员工的用户关联
- **用户删除/停用**：在 `delete_user`（软删除）、`update_user`（is_active 置为 false）、`reject_user` 中，均需将关联的 Employee.user_id 置空；users.py 需导入 Employee 并操作 a_class.employees

### 7. 我的档案菜单可见性

- **决策**：对可能有员工档案的角色（operator、manager、admin 等）在菜单中展示「我的档案」
- **未关联时**：GET /api/hr/me/profile 在未关联员工时**自动创建**最小员工并关联当前用户，再返回档案；仅当自动创建失败时返回 404，页面展示「您尚未关联员工档案，请联系管理员」
- **理由**：系统主要面向内部员工，业界常见做法为「注册/登录即可用」；首次访问自动建员工，避免人工先建员工再关联

### 8. 我的档案：首次访问自动创建员工

- **决策**：在 `GET /api/hr/me/profile` 中，若当前用户无关联员工，则自动创建一条最小员工记录并关联
- **触发时机**：首次打开「我的档案」时（即首次调用 GET /api/hr/me/profile 且未关联时）
- **最小员工字段**：employee_code（`_generate_employee_code` 生成）、name（`dim_users.full_name` 或 `username`）、user_id（当前用户）、status=active；其余字段可为 null
- **幂等**：先查 `Employee.user_id == current_user.user_id`，已存在则直接返回，不重复创建

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| user_id 重复关联 | 更新时校验：若 A 用户关联员工 E1，再关联 E2，则清除 E1.user_id 再设置 E2.user_id |
| 用户删除/停用 | 将关联 Employee.user_id 置空，删除前可提示解除关联 |
| 员工删除 | 软删除时 user_id 保留；硬删除前解除关联 |
| unlinked 返回无效用户 | 仅返回 is_active=true 的用户 |

## Migration Plan

1. Alembic 迁移添加 `a_class.employees.user_id` 列（Employee 表在 a_class schema，迁移须显式指定）
2. 部署后无数据迁移，已有员工 user_id 为 null
3. **回滚**：删除 user_id 列，移除前后端关联逻辑
