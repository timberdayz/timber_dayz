## Purpose

用户管理能力提供系统登录账号、角色权限、以及账号与员工档案的关联管理，支持游客、操作员、管理员等多角色访问控制。

## ADDED Requirements

### Requirement: 用户与员工关联
系统 SHALL 支持将用户账号与员工档案关联，使用户列表可展示关联员工信息，并在编辑用户时可选择或解除关联。

#### Scenario: 用户列表展示关联员工
- **WHEN** 管理员查看用户列表
- **THEN** 系统显示「关联员工」列
- **AND** 若该用户已关联员工，显示员工姓名与工号
- **AND** 若未关联，显示「-」

#### Scenario: 用户编辑关联员工
- **WHEN** 管理员编辑用户并选择「关联员工」下拉中的某员工
- **THEN** 系统更新该员工的 user_id 指向被编辑的用户
- **AND** 若该用户此前已关联其他员工，则清除原员工的 user_id
- **AND** 保存后用户列表与员工列表均正确展示关联

#### Scenario: 用户解除关联
- **WHEN** 管理员编辑用户并将「关联员工」清空
- **THEN** 系统将原关联员工的 user_id 置为空
- **AND** 保存后双方均显示为未关联

### Requirement: 未关联用户列表 API
系统 SHALL 提供 API 返回尚未关联员工的用户列表，供员工编辑时「关联登录账号」下拉选择。

#### Scenario: 获取可关联用户
- **WHEN** 客户端请求 GET /api/users/unlinked
- **THEN** 系统返回所有不存在 Employee.user_id 指向该用户、且 is_active=true 的用户
- **AND** 响应包含 id（即 user_id，供员工关联时传入）、username、email 等字段

#### Scenario: 用户删除时解除关联
- **WHEN** 管理员删除用户或将用户 is_active 置为 false
- **THEN** 系统将该用户关联的 Employee.user_id 置空
- **AND** 避免悬空引用

### Requirement: 游客角色
系统 SHALL 提供「游客」角色，权限仅限业务概览页面的可视内容，用于访客、试用等仅需看板访问的场景。

#### Scenario: 游客权限
- **WHEN** 用户被分配游客角色
- **THEN** 该用户仅可访问业务概览页面
- **AND** 不可访问数据采集、产品、财务、人力等其它模块

#### Scenario: 游客角色创建账号
- **WHEN** 管理员创建新用户并选择游客角色
- **THEN** 系统创建账号并分配游客权限
- **AND** 无需创建员工档案
