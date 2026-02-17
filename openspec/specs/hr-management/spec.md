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

### Requirement: 人员店铺归属配置
系统 SHALL 支持配置员工与店铺的归属关系，存储于 `a_class.employee_shop_assignments` 表，供提成计算与展示使用。

#### Scenario: 新增归属
- **WHEN** 管理员在「人员店铺归属和提成比」页面选择员工、店铺并保存
- **THEN** 系统在 `a_class.employee_shop_assignments` 中插入记录
- **AND** 校验 employee_code 存在于 a_class.employees
- **AND** 校验 (platform_code, shop_id) 存在于 dim_shops，若不存在返回 400，提示「该店铺尚未同步至系统，请先在账号管理中同步」
- **AND** 若 (employee_code, platform_code, shop_id) 已存在，返回 409 冲突

#### Scenario: 编辑归属
- **WHEN** 管理员编辑某条归属记录的提成比例、角色或生效区间
- **THEN** 系统更新对应记录
- **AND** 更新后列表与详情正确展示
- **AND** 若记录 id 不存在，返回 404

#### Scenario: 删除归属
- **WHEN** 管理员删除某条归属记录
- **THEN** 系统从表中移除该记录
- **AND** 列表不再展示该归属
- **AND** 若记录 id 不存在，返回 404

#### Scenario: 列表筛选
- **WHEN** 管理员按员工、店铺、平台或状态筛选
- **THEN** 系统仅返回符合筛选条件的归属记录
- **AND** 支持分页

### Requirement: 提成比配置
系统 SHALL 支持在归属记录上配置提成比例（0-1），用于后续提成计算；若未配置则使用薪资结构中的默认提成比例。

#### Scenario: 归属级提成比
- **WHEN** 管理员在新增或编辑归属时填写「提成比例」
- **THEN** 系统将 commission_ratio 存入 employee_shop_assignments
- **AND** 该值用于该员工在该店铺的提成计算（计算逻辑由后续任务实现）

#### Scenario: 多人同店提成
- **WHEN** 同一店铺归属多名员工，各自配置 commission_ratio
- **THEN** 提成计算时各自按「全店当月销售额 × 各自比例」独立计算
- **AND** 不拆分销售额（例如店铺月销 10 万，甲 5%、乙 3%，则甲 5000、乙 3000）
- **AND** 仅考虑 status='active' 且生效区间覆盖该月的归属记录

#### Scenario: 默认提成比回退
- **WHEN** 归属记录的 commission_ratio 为空
- **THEN** 提成计算时使用 salary_structures.commission_ratio（按 employee_code 查，取 status='active' 且 effective_date<=当前日期的最新记录）
- **AND** 若薪资结构无记录或无可用的薪资结构记录，使用 0

#### Scenario: commission_ratio 与 effective 校验
- **WHEN** 用户新增或编辑归属时填写 commission_ratio 或 effective_from/effective_to
- **THEN** 若 commission_ratio 提供，须满足 0 <= commission_ratio <= 1（闭区间）
- **AND** 若 effective_from 与 effective_to 均提供，须满足 effective_to >= effective_from

### Requirement: 人员店铺归属和提成比页面
系统 SHALL 提供「人员店铺归属和提成比」前端页面，使管理员可对归属关系与提成比进行 CRUD 操作。

#### Scenario: 页面访问
- **WHEN** 具备人力管理权限的用户访问「人员店铺归属和提成比」页面
- **THEN** 系统展示归属列表
- **AND** 表格列包含：员工姓名、员工编号、平台、店铺名称、提成比例、角色、生效区间、状态、操作
- **AND** 支持筛选与新增按钮

#### Scenario: 新增与编辑表单
- **WHEN** 用户点击「新增」或「编辑」
- **THEN** 系统展示表单，包含员工选择、店铺选择、提成比例、角色、生效起始/截止
- **AND** 员工下拉仅展示 status='active' 的在职员工
- **AND** 店铺选择复用 api.getTargetShops()，按平台过滤
- **AND** 提成比例可选（空表示使用薪资结构默认）
- **AND** 保存后列表刷新并展示新数据

#### Scenario: 员工删除前校验
- **WHEN** 管理员删除某员工
- **AND** 该员工存在未解除的店铺归属
- **THEN** 系统返回 400，提示「请先解除该员工的店铺归属」
- **AND** 不执行删除

#### Scenario: 店铺删除前校验
- **WHEN** 尝试删除 dim_shops 中某店铺
- **AND** 该店铺存在归属记录
- **THEN** 数据库外键 RESTRICT 阻止删除
- **AND** 需先删除或解除相关归属记录

