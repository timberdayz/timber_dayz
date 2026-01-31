# Tasks: 用户管理与员工管理关联

> **状态**：全部完成，验证已通过（2026-01-30）

## 1. 数据库

- [x] 1.1 在 `schema.py` 的 `Employee` 模型中新增 `user_id` 列（BigInteger, nullable）
- [x] 1.2 创建 Alembic 迁移：`alembic revision --autogenerate -m "add_user_id_to_employees"`，确保对 `a_class.employees` 表添加 user_id 列
- [x] 1.3 执行迁移：`alembic upgrade head`

## 2. 游客角色

- [x] 2.1 在 `frontend/src/config/rolePermissions.js` 中新增 `tourist` 配置，permissions: `['business-overview']`
- [x] 2.2 在 `normalizeRoleCode` 中增加「游客」→ tourist 映射
- [x] 2.3 在 `scripts/ensure_all_roles.py` 的 REQUIRED_ROLES 中新增 tourist（role_code='tourist', role_name='游客', description='访客，仅可访问业务概览', is_system=False）；部署/迁移后执行 `python scripts/ensure_all_roles.py` 插入 dim_roles；插入后在角色管理中心可见「游客」（权限由 rolePermissions.js 控制，dim_roles.permissions 可后续通过「配置权限」补充）

## 3. 后端 API

- [x] 3.1 用户管理：新增 `GET /api/users/unlinked`，返回尚未关联员工的用户列表（id=user_id, username, email），仅 is_active=true；需 get_current_user，建议 admin 或 human-resources 权限；id 供员工编辑时作为 user_id 传入
- [x] 3.2 用户管理：`UserResponse` 或用户详情增加 `employee_code`、`employee_name`（关联时）
- [x] 3.3 用户管理：`UserUpdate` 增加可选 `employee_id`（Employee.id）；保存时校验 employee 存在（a_class.employees），存在则更新 Employee.user_id，支持关联/解除关联；users.py 需导入 Employee
- [x] 3.4 人力管理：`EmployeeCreate`、`EmployeeUpdate` 增加可选 `user_id`
- [x] 3.5 人力管理：`EmployeeResponse` 增加 `username`（关联时展示）
- [x] 3.6 人力管理：创建/更新员工时校验 user_id 唯一性（同一 user_id 不能关联多个员工）
- [x] 3.7 用户管理：在 `delete_user`（软删除）、`update_user`（is_active 置为 false）、`reject_user` 三处 handler 中，将关联的 Employee.user_id 置空；users.py 需导入 Employee 并更新 a_class.employees

## 4. 前端 - 用户管理

- [x] 4.1 用户列表表格增加「关联员工」列（员工姓名/工号，无则显示「-」）
- [x] 4.2 用户编辑弹窗增加「关联员工」选择（下拉可选员工，支持清空解除关联）
- [x] 4.3 调用 `UserUpdate` 时传递 employee 关联信息

## 5. 前端 - 人力管理

- [x] 5.1 员工列表表格增加「登录账号」列（username，无则显示「-」）
- [x] 5.2 员工添加/编辑弹窗增加「关联登录账号」选择（下拉调用 `/api/users/unlinked` 及已关联用户）
- [x] 5.3 调用 `EmployeeCreate`/`EmployeeUpdate` 时传递 user_id

## 6. 验证

- [x] 6.1 创建游客账号，确认仅可访问业务概览
- [x] 6.2 创建用户后，在员工管理中关联，确认双向展示正确
- [x] 6.3 解除关联后，确认双方均显示为未关联
- [x] 6.4 已关联员工用户访问「我的档案」可自助编辑联系方式，HR 在人力管理中可见更新
- [x] 6.5 用户被拒绝（reject_user）后，若此前已关联员工，则 Employee.user_id 已被置空

## 7. 我的档案（员工自助）

- [x] 7.1 将「员工档案」占位改为「我的档案」：`menuGroups.js` 文案、`router/index.js` 中 meta.title 改为「我的档案」、`EmployeeManagement.vue` 实现；在 `rolePermissions.js` 中为 operator 增加 `employee-management` 权限；在 `router/index.js` 中将 `/employee-management` 的 meta.roles 扩展为 `['admin','manager','operator']`（后演进为所有人可见：permission=null, roles=[]）
- [x] 7.2 新增 `GET /api/hr/me/profile`：需 get_current_user；根据当前用户关联员工返回档案；**未关联时**首次访问自动创建最小员工（employee_code 自动生成、name 取自 full_name 或 username、user_id=当前用户、status=active）并关联后返回档案；仅当自动创建失败时返回 404；路由定义在 `/employees/{employee_code}` 之前
- [x] 7.3 新增 `PUT /api/hr/me/profile`：需 get_current_user；校验当前用户为该档案关联用户；仅接受白名单字段（phone、email、address、emergency_contact、emergency_phone），忽略其它字段
- [x] 7.4 前端「我的档案」页面：调用上述 API 展示并编辑自助字段
- [x] 7.5 菜单/路由：对 operator、manager、admin 等角色展示「我的档案」；页面在 GET me/profile 返回 404 时显示「您尚未关联员工档案，请联系管理员」（仅在自动创建失败时出现）；已演进为所有人可见（permission=null, roles=[]）
