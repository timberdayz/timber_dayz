# hr-management Specification

## Purpose
TBD - created by archiving change add-link-user-employee-management. Update Purpose after archive.
## Requirements
### Requirement: 员工与用户关联
系统 SHALL 支持将员工档案与登录账号关联，使员工列表可展示关联的登录账号，并在创建或编辑员工时可选择或解除关联。

#### Scenario: 员工列表展示关联账号
- **WHEN** 管理员查看员工列表
- **THEN** 系统显示「登录账号」列
- **AND** 若该员工已关联用户，显示 username
- **AND** 若未关联，显示「-」

#### Scenario: 员工创建时关联账号
- **WHEN** 管理员创建员工并在「关联登录账号」下拉中选择某用户
- **THEN** 系统将新员工的 user_id 设置为该用户的 user_id
- **AND** 校验该用户未被其他员工关联
- **AND** 保存后员工列表与用户列表均正确展示关联

#### Scenario: 员工编辑时关联账号
- **WHEN** 管理员编辑员工并选择「关联登录账号」下拉中的某用户
- **THEN** 系统更新该员工的 user_id
- **AND** 若该用户此前已关联其他员工，则清除原员工的 user_id（保持一对一）
- **AND** 保存后关联正确展示

#### Scenario: 员工解除关联
- **WHEN** 管理员编辑员工并将「关联登录账号」清空
- **THEN** 系统将该员工的 user_id 置为空
- **AND** 保存后双方均显示为未关联

### Requirement: 员工-用户唯一性
系统 SHALL 保证一个用户最多对应一个员工，一个员工最多对应一个用户。

#### Scenario: 关联时唯一性校验
- **WHEN** 管理员将用户 A 关联至员工 E1
- **AND** 用户 A 此前已关联员工 E2
- **THEN** 系统清除 E2 的 user_id 后再设置 E1.user_id = A
- **AND** 确保同一时刻仅 E1 关联用户 A

### Requirement: 员工自助档案（我的档案）
系统 SHALL 提供「我的档案」能力，使已关联员工的用户可查看并自助编辑个人联系方式，减少 HR 手动录入。

#### Scenario: 已关联员工访问我的档案
- **WHEN** 已关联员工的用户访问「我的档案」页面
- **THEN** 系统展示该用户关联的员工档案
- **AND** 允许编辑 phone、email、address、emergency_contact、emergency_phone
- **AND** 部门、职位、薪资、合同、银行账户等为只读

#### Scenario: 未关联员工访问
- **WHEN** 未关联员工的用户访问「我的档案」页面
- **THEN** 系统 GET /api/hr/me/profile 返回 404
- **AND** 页面显示「您尚未关联员工档案，请联系管理员」，不展示档案编辑表单

#### Scenario: 自助更新同步至人力管理
- **WHEN** 员工在「我的档案」中更新联系方式并保存
- **THEN** 系统更新 Employee 表中对应字段
- **AND** 管理员/HR 在人力管理中可见更新后的信息

