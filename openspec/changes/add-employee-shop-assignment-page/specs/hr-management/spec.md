## ADDED Requirements

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
