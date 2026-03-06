# 数据采集能力（Delta）

## MODIFIED Requirements

### Requirement: Python 组件测试工具更新

系统 SHALL 更新测试工具支持 Python 组件加载和执行；且当从组件版本的 file_path 加载到具体组件类后，执行测试时必须使用该类，不得再按 component_type 通过适配器内部按模块名（如 "login"）加载其他文件中的实现。

#### Scenario: 加载 Python 组件

- **WHEN** 用户在前端点击"测试组件"
- **THEN** 系统加载指定的 Python 组件类
- **AND** 系统使用 `component_loader.load_python_component()` 或根据 version.file_path 通过 importlib 从指定路径加载
- **AND** 系统不再支持 YAML 组件测试

#### Scenario: 执行 Python 组件测试

- **WHEN** 系统加载 Python 组件后
- **THEN** 系统创建 `PythonComponentAdapter` 实例（或使用注入的组件类）
- **AND** 对从 version.file_path 加载的组件，执行时使用该组件类实例的 run(page)，而非 adapter 内部按 "login" / "navigation" 等模块名重新加载的类
- **AND** 系统返回测试结果（成功/失败、执行时间、错误信息）

#### Scenario: 组件版本测试

- **WHEN** 用户测试已注册的组件版本
- **THEN** 系统根据 `file_path` 字段加载 `.py` 文件并得到组件类
- **AND** 系统验证 Python 文件存在
- **AND** 系统使用该组件类执行并返回测试结果，确保「测试的版本」与「执行的实现」一致

## ADDED Requirements

### Requirement: 登录图形验证码步骤必选暂停

系统 SHALL 在录制/生成器产出的登录组件中，对标记为「图形验证码」的步骤采用「到达即暂停」语义：执行到该步骤时无条件截图并抛出 VerificationRequiredError，等待用户回传验证码后再继续，不做「检测 DOM 存在且可见才截图」的条件判断，以避免静默穿透导致未暂停即点击登录。

#### Scenario: 验证码步骤到达即截图并暂停

- **WHEN** 登录组件执行到录制/生成器标记为图形验证码的步骤
- **THEN** 系统在该步骤进行短暂等待（如 1s）后对当前页面截图
- **AND** 系统抛出 VerificationRequiredError，测试或执行器暂停并展示验证码输入
- **AND** 用户回传验证码后，系统在同一页面填入并继续后续步骤（如点击登录）
- **AND** 不依赖「验证码输入框 count() > 0 且 is_visible()」等条件判断；若该步骤存在则视为必现

#### Scenario: 生成器不生成条件检测与静默穿透

- **WHEN** 步骤→Python 生成器处理图形验证码步骤
- **THEN** 生成的代码不包含「仅当 locator.count() > 0 且 is_visible() 才截图并 raise」的逻辑
- **AND** 不生成会吞掉异常的 `except Exception: pass` 导致继续执行「点击登录」的分支
- **AND** 生成逻辑与《RECORDER_PYTHON_OUTPUT》及验证码回传流程一致
