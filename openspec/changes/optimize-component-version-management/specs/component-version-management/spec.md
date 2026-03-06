# 组件版本管理能力（Delta）

## ADDED Requirements

### Requirement: 组件版本删除规则

系统 SHALL 允许用户在组件版本管理界面删除满足条件的组件版本记录，且删除按钮的显示条件与后端校验一致。

#### Scenario: 已禁用版本可删除

- **WHEN** 某组件版本处于已禁用状态（is_active=False）且未处于 A/B 测试中（is_testing=False）
- **THEN** 系统在列表中显示该版本的「删除」按钮
- **AND** 用户点击删除后，后端校验通过并删除该版本记录（及可选地清理仅被该版本引用的 .py 文件）
- **AND** 稳定版（is_stable=True）在禁用后也允许被删除

#### Scenario: 启用中或测试中的版本不可删除

- **WHEN** 某组件版本处于启用状态（is_active=True）或正在 A/B 测试中（is_testing=True）
- **THEN** 系统不显示「删除」按钮或后端拒绝删除请求并返回明确错误信息
- **AND** 删除规则为「可删除 = 非测试中且已禁用」（`!is_testing && !is_active`），启用中的版本无论是否稳定版均不可删除

### Requirement: 组件版本测试执行一致性

系统 SHALL 在用户对某一组件版本发起测试时，实际执行的代码必须来自该版本的 file_path 所指向的 Python 文件，不得执行同平台其他文件中的同名类型组件。

#### Scenario: 测试选中版本即执行该版本

- **WHEN** 用户在组件版本管理页对版本 A（如 miaoshou_login v1.0.0，file_path 指向 miaoshou_login.py）点击「测试」
- **THEN** 系统根据 version.file_path 加载对应的 .py 文件并得到组件类
- **AND** 执行测试时使用该类（或通过适配器注入该类）运行 run(page)，而非按 component_type 再加载其他模块（如 login.py）
- **AND** 若涉及验证码回传，用户输入验证码后继续执行时，系统仍使用同一组件类（不得回退到按模块名加载的其他实现）
- **AND** 测试结果与用户选中的版本一一对应，避免「测试 A 组件却执行 B 组件」

#### Scenario: 测试结果可区分实际执行文件

- **WHEN** 测试完成或进行中
- **THEN** 系统在进度或结果中可展示或返回实际执行的组件文件路径或类名，便于用户确认
