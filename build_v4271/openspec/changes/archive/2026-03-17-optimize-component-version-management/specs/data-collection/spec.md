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

#### Scenario: file_path 导入后按元数据优先匹配组件类

- **WHEN** 系统已从 `file_path` 导入模块，且类名不一定符合当前命名约定
- **THEN** 系统优先按 `platform + component_type` 元数据匹配组件类，再回退命名规则
- **AND** 对历史命名类保持兼容，避免 `Failed to load Python component` 阻断测试

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

### Requirement: 采集脚本现实 Web 稳健性约束

系统 SHALL 在采集脚本编写与录制代码生成过程中，遵循面向现实 Web 场景的稳健性约束：定位器唯一性、作用域收敛、条件等待、反模式禁用与失败可观测性，避免 strict mode 冲突与静默穿透导致的不可预期行为。

#### Scenario: 关键交互前定位器在作用域内唯一

- **WHEN** 脚本对元素执行 click/fill/press 或 expect(...).to_be_visible 等关键交互
- **THEN** 系统或开发约定要求该目标 locator 在当前作用域唯一命中（通过作用域收敛与唯一性断言保障）
- **AND** 出现多匹配时，先收敛到稳定容器（如 form/dialog/frame/row）再定位，而不是默认 `.first/.nth()` 掩盖歧义

#### Scenario: 禁止单次检测与静默吞错反模式

- **WHEN** 录制生成器或手写脚本处理元素检测与交互
- **THEN** 不采用 `count()+is_visible()` 单次检测后立刻操作的模式作为关键路径
- **AND** 不采用 `except Exception: pass` 吞掉定位/交互异常后继续主流程
- **AND** 等待策略优先条件等待与 Playwright 自动等待，不以固定 sleep 代替页面状态确认

#### Scenario: 录制生成器输出遵循稳健性约束

- **WHEN** 用户在录制页使用步骤重新生成 Python 代码
- **THEN** 生成代码不得默认输出吞错继续模式（如 `except Exception: pass`）用于关键交互路径
- **AND** 生成代码对关键交互目标应优先使用作用域收敛与唯一性策略，而非默认 `.first/.nth` 消歧
- **AND** 对固定 sleep、宽泛 locator 等风险模式，系统至少输出 lint 提示并给出可操作修复建议

#### Scenario: 关键反模式触发 lint error 时阻断保存

- **WHEN** 录制页代码分析命中关键反模式（如吞错继续、关键路径无依据 `.first/.nth`、无理由固定 sleep）
- **THEN** 系统将该问题标记为 `error`（而非仅 warning）
- **AND** 默认阻断组件保存，直到用户修复或在受控配置下显式放行

#### Scenario: 有显式固定等待理由时不应被误阻断

- **WHEN** 生成代码中的固定等待包含显式理由（例如步骤字段或注释已说明“固定等待原因”）
- **THEN** 系统可给出规范提示（warning）但不应默认以 `error` 阻断保存
- **AND** “无理由固定等待”仍应保持 `error` 阻断

#### Scenario: `.first/.nth` 受控放行需注释依据

- **WHEN** 生成代码使用 `.first/.nth`
- **THEN** 系统仅在存在明确业务语义注释时允许保存（可降级为 warning）
- **AND** 无注释依据时标记为 `error` 并阻断保存

#### Scenario: 可选步骤异常处理代码必须可执行

- **WHEN** 生成器为 optional 步骤输出异常处理分支
- **THEN** 生成代码不得引用生成器侧临时变量（如循环索引变量）导致运行期 NameError
- **AND** 异常日志需包含可诊断上下文（step_index、action、error）

#### Scenario: login 容器收敛不得仅依赖 role=form

- **WHEN** 录制生成器输出 login 组件代码，目标页面不存在可用 `role=form` 容器
- **THEN** 系统采用“语义容器优先 + 业务容器兜底 + page 根作用域告警兜底”的收敛策略，而非直接失败
- **AND** 若最终仍失败，错误信息包含容器候选与当前 URL，便于定位页面结构差异

#### Scenario: login URL 导航采用显式契约

- **WHEN** login 组件执行前未处于可用登录页面
- **THEN** 系统按优先级解析目标 URL（`login_url_override > account.login_url > 平台默认 URL`）并执行导航
- **AND** 导航成功判定采用“URL/路由特征 + 关键登录元素可见”双信号
- **AND** 不得仅依赖单一 `networkidle`/`domcontentloaded` 作为登录页就绪判定

#### Scenario: 失败结果可定位可诊断

- **WHEN** 组件测试或执行失败
- **THEN** 返回结果包含至少 `phase`、`component`、`version` 与当前 URL 等上下文
- **AND** 在验证码或关键失败路径可提供截图等证据，支持快速定位问题
