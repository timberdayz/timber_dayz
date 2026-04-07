# Change: 用户管理与员工管理关联 - 账号-员工链接与游客角色

## Why

当前**用户管理**（登录账号）与**员工管理**（HR 档案）相互独立，无法将登录账号与员工档案关联。在云端部署场景下存在以下问题：

1. **无法对应**：管理员无法在用户列表中看出某账号是否对应某员工，人力管理亦然
2. **流程割裂**：先注册账号、再配置员工是合理流程（游客仅看业务概览，员工需完整 HR 档案），但两套系统无联动
3. **角色缺失**：缺少「游客」角色，无法为仅需查看业务概览的外部/访客账号分配最小权限

需要建立用户-员工关联，并新增游客角色，支撑云端多角色访问场景。

## What Changes

### 核心变更

1. **数据库：Employee 表增加 user_id 外键**
   - 在 `a_class.employees` 表新增 `user_id` 列（nullable，FK to dim_users.user_id）
   - 一个用户最多对应一个员工，一个员工最多对应一个用户
   - 游客账号不创建员工记录，user_id 为空；员工账号在创建/编辑员工时可关联已有用户

2. **游客角色**
   - 在 `rolePermissions.js` 和 `dim_roles` 中新增「游客」角色（tourist）
   - 权限：仅 `business-overview`（业务概览页面可视内容）
   - 用于外部访客、未转正试用等仅需看板访问的场景
   - **新增方式**：通过 `scripts/ensure_all_roles.py` 扩展插入（与 admin/manager/operator/finance 一致），插入后将在角色管理中心展示；不通过 UI「+ 新增角色」（因后端 create_role 未传入 role_code）；部署/迁移后需执行 `python scripts/ensure_all_roles.py`

3. **用户管理 UI/API**
   - 用户列表/详情：展示「关联员工」列，编辑时可选择关联员工
   - 新增 API：`GET /api/users/unlinked` 返回尚未关联员工的用户列表（供下拉选择）

4. **人力管理 UI/API**
   - 员工列表/详情：展示「登录账号」列，添加/编辑时可选择「关联登录账号」
   - `EmployeeCreate`/`EmployeeUpdate` 增加可选字段 `user_id`
   - `EmployeeResponse` 增加 `username`（关联时展示）

5. **我的档案（员工自助）**
   - 将占位「员工档案」改为「我的档案」，**所有已登录用户均可使用**（与角色无关）
   - **首次访问自动建员工**：系统主要面向内部员工，若当前用户尚未关联员工，在首次访问 `GET /api/hr/me/profile` 时自动创建一条最小员工记录并关联当前用户，再返回档案；保证「注册并登录即可用」
   - 自助可编辑字段：phone、email、address、emergency_contact、emergency_phone（个人联系方式）
   - 部门、职位、薪资、合同、银行账户等仅 HR/管理员可改
   - **菜单可见性**：对可能有员工档案的角色（operator、manager、admin 等）展示「我的档案」；自动创建后不再出现「未关联」空状态，仅当自动创建失败时保留 404 提示
   - 新增 `GET /api/hr/me/profile`、`PUT /api/hr/me/profile`（需登录，PUT 仅允许更新本人自助字段）

### 业务流程

| 步骤 | 位置 | 动作 |
|------|------|------|
| 1 | 用户管理 | 创建账号（username、email、角色：游客/操作员等） |
| 2 | 人力管理 | 若该人为员工，创建/编辑员工时选择「关联登录账号」 |
| 3 | - | 系统建立 Employee.user_id = 某用户.user_id |
| 4 | 我的档案 | 用户首次打开「我的档案」时，若未关联员工则系统自动创建最小员工并关联；之后在「我的档案」中维护个人信息（手机、邮箱、地址、紧急联系人等） |
| 5 | 人力管理 | 管理员/HR 在人力管理中查看员工完整档案（含员工自助更新的信息） |

**游客**：仅步骤 1，角色选「游客」；若游客也访问「我的档案」，同样会触发自动建员工（系统主要面向内部员工，统一行为）。

## Impact

### 受影响的规格

- **user-management**：ADDED - 用户与员工关联、游客角色、未关联用户列表、用户删除时解除关联
- **hr-management**：ADDED - 员工与用户关联、关联账号展示与编辑、员工自助档案

### 受影响的代码

| 文件 | 修改内容 |
|------|----------|
| `modules/core/db/schema.py` | Employee 表增加 user_id 列 |
| `migrations/` | Alembic 迁移脚本（需对 `a_class.employees` 表操作） |
| `backend/routers/users.py` | 未关联用户列表 API、用户响应/更新增加 employee 信息；导入 Employee，在 update_user（employee_id）、delete_user、update_user（is_active→false）、reject_user 中更新 a_class.employees.user_id |
| `backend/routers/hr_management.py` | Employee CRUD 支持 user_id、响应增加 username、`GET/PUT /api/hr/me/profile` |
| `frontend/src/config/rolePermissions.js` | 新增 tourist 角色，为 operator 增加 employee-management 权限 |
| `frontend/src/router/index.js` | `/employee-management` 的 meta.roles 扩展为含 operator、meta.title 改为「我的档案」 |
| `scripts/ensure_all_roles.py` | 在 REQUIRED_ROLES 中新增 tourist（role_code='tourist', role_name='游客'） |
| `frontend/src/config/menuGroups.js` | 「员工档案」改为「我的档案」 |
| `frontend/src/views/UserManagement.vue`（或等价） | 用户列表/编辑增加关联员工 |
| `frontend/src/views/HumanResources.vue` | 员工列表/编辑增加关联账号 |
| `frontend/src/views/hr/EmployeeManagement.vue` | 占位改为「我的档案」实现，展示并编辑自助字段 |

### 非目标（Non-Goals）

- 不自动同步 User 与 Employee 的姓名/邮箱（可后续迭代）
- 不修改登录/认证流程，仅扩展数据模型与展示
- 不实现跨 schema 的数据库级外键（dim_users 在 public，employees 在 a_class），使用应用层约束
- 本阶段不实现档案变更审批流程，自助更新直接生效

## 成功标准

- [x] Employee 表有 user_id 列，可正确关联 dim_users
- [x] 游客角色存在，仅可访问业务概览，且在角色管理中心可见
- [x] 用户管理可展示并编辑关联员工
- [x] 人力管理可展示并编辑关联登录账号
- [x] 未关联用户列表 API 可用，供下拉选择
- [x] 「我的档案」可用：所有已登录用户可访问；未关联时首次访问自动创建员工并关联，可自助编辑个人联系方式
- [x] 用户删除/停用时，关联员工 user_id 置空

> **验证状态**：上述验证已全部通过（2026-01-30）
