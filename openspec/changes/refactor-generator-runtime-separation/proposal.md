# Change: 采集组件生成器与运行时职责分离

## Why

当前组件代码生成器（`steps_to_python.py`）在生成 login 组件时，将本应属于运行时/测试框架层的逻辑（"门卫检测"和"容器发现"）注入到生成的组件代码中。这导致以下问题：

1. **`to_have_count(1)` 严格断言在真实页面上失败**：生成代码中 `_login_element_candidates` 使用 `to_have_count(1)` 检测密码框/登录按钮唯一性，但真实页面（如妙手 ERP 登录页有 8 个密码框、2 个登录按钮）天然存在多匹配元素，导致组件首步即失败。
2. **`_route_markers` 路由标记检测不通用**：默认标记 `["login", "signin"]` 无法覆盖 `https://erp.91miaoshou.com/?redirect=%2Fwelcome` 等真实 URL 模式，导致"login navigation check failed"误报。
3. **容器发现写死策略**：`_form_candidates` 写死 `get_by_role("form")` 等策略，在无语义 `<form>` 标签的页面上失败后回退到 `page` 根作用域，而后续 locator 加 `.first` 掩盖了歧义。
4. **与业界实践不符**：Playwright Codegen、n8n、Puppeteer Recorder 等业界工具生成的代码**仅包含忠实的操作回放**，页面就绪检测、会话管理、重试等框架能力由执行环境承担，而非注入到生成代码中。
5. **150+ 行框架代码污染生成产物**：每个 login 组件都包含 ~150 行 URL 导航契约、元素检测、容器发现等代码，与用户录制的实际操作步骤混杂，降低可读性和可维护性。

## What Changes

### 1. 生成器职责收敛（P0）

- **移除"门卫检测"**：生成器不再注入 `_login_element_candidates` 循环 + `to_have_count(1)` + `_route_markers` 检查逻辑；login 组件仅生成用户录制步骤对应的 Playwright 操作。
- **移除"容器发现"**：生成器不再注入 `_form_candidates` 多候选搜索逻辑；若录制步骤的上下文存在明确的表单 ID/选择器（如录制时在 `#J_loginRegisterForm` 内操作），则按录制信息生成具体的容器 locator；否则不注入泛化容器发现。
- **保留 URL 导航**：login 组件保留 `_target_url` 的来源优先级逻辑（`login_url_override > account.login_url > platform default`），这属于组件自身的导航需求。
- **保留验证码处理**：验证码检测与 `VerificationRequiredError` 暂停逻辑保留在组件中，因为这是业务逻辑而非框架逻辑。

### 2. 页面就绪检测移至运行时层（P0）

- **测试框架层增加"页面就绪检测"**：在 `tools/test_component.py` 的 `_test_python_component_with_browser` 中，执行 login 组件前先做页面就绪判断（等待关键登录元素可见，而非 `to_have_count(1)` 唯一性断言），并在超时时返回结构化诊断信息。
- **执行器层统一处理**：`executor_v2.py` 在调用 login 组件前的流程中已包含导航和弹窗处理，仅需确保导航后页面稳定即可。
- **检测策略改为"至少一个可见"而非"严格唯一"**：检测登录页就绪时使用 `locator.first.wait_for(state="visible")` 或 `expect(locator.first).to_be_visible()` 替代 `to_have_count(1)`，兼容真实页面多元素场景。

### 3. 容器作用域由录制上下文驱动（P1）

- 当录制步骤包含明确的容器信息（如步骤在某个 form/dialog/iframe 内操作），生成器按录制信息写入具体的 `_form = page.locator("#J_loginRegisterForm")`。
- 不再注入"泛化容器搜索"逻辑，因为不同页面的容器结构差异巨大，泛化策略的失败概率高于其价值。
- 若录制步骤无容器上下文，生成的 locator 直接使用 `page` 作用域，用户可在编辑阶段手动添加容器收敛。

### 4. 成功条件模板化（P1）

- login 组件的登录成功判断（当前为 `return LoginResult(success=True, message="ok")` TODO 注释）改为生成器注入可配置的成功条件模板（如 URL 变化检测 + 关键元素出现），供用户编辑完善。
- 导航后的 `domcontentloaded` 等待保留，但不再做"双信号联合判断"的强约束注入（这应由用户在编辑阶段根据实际情况填写）。

## Capabilities

### New Capabilities

_无新增独立能力_

### Modified Capabilities

- `data-collection`: 修改"采集组件录制工具产出"和"步骤转 Python 生成器输出规范"相关 requirement：生成器不再注入框架层逻辑（门卫检测、容器发现），仅生成忠实回放代码；页面就绪检测由运行时/测试框架层承担。

## Impact

- **受影响代码**：
  - `backend/services/steps_to_python.py`：移除 login 组件生成中的 ~150 行门卫检测 + 容器发现代码
  - `tools/test_component.py`：新增 login 组件测试前的页面就绪检测（使用 `.first.wait_for` 替代 `to_have_count(1)`）
  - `backend/services/component_test_service.py`：可能调整测试准备逻辑
  - `backend/tests/test_steps_to_python_regression.py`：更新回归测试用例
- **受影响 API**：无 API 签名变更，仅内部生成逻辑变化
- **受影响文档**：
  - `docs/guides/RECORDER_PYTHON_OUTPUT.md`：更新生成代码示例
  - `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`：强化"框架职责 vs 组件职责"边界说明
- **依赖关系**：基于 `optimize-component-version-management` 提案的成果，不影响其已完成的任务；本提案解决的是该提案在验收中发现的架构层问题
- **兼容性**：已存在的手动优化组件（如 `miaoshou_login.py`）不受影响；已生成的旧组件（如 `login_v1_0_0.py`）重新生成后将简化
