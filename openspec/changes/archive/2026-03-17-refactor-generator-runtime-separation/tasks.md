# Tasks: 采集组件生成器与运行时职责分离

**目标**：移除生成器中的"门卫检测"和"容器发现"框架逻辑，将页面就绪检测移至运行时/测试框架层，使生成代码仅包含忠实回放 + 必要的组件业务逻辑。

## 1. 生成器简化（P0）

- [x] 1.1 移除门卫检测代码：在 `steps_to_python.py` 的 `generate_python_code` 中，移除 login 组件的 `_login_element_candidates` 循环（含 `to_have_count(1)` 检测）、`_route_markers` URL 检测、`_ready_before_nav` 判断及相关的 `_selector_context_parts` 错误收集逻辑。
- [x] 1.2 移除容器发现代码：移除 `_form_candidates` 循环（含 `to_have_count(1)` + page 根作用域兜底）及相关诊断代码。
- [x] 1.3 简化 URL 导航：保留 `_target_url` 来源优先级，保留 `page.goto`，移除导航后的门卫重检逻辑。导航后仅保留 `wait_for_load_state("domcontentloaded")` 和 `guard_overlays`。
- [x] 1.4 容器作用域按录制上下文生成：无容器上下文时，login 组件 locator 默认使用 `_form = page` 作用域（不注入泛化搜索）。
- [x] 1.5 登录成功条件模板：在步骤回放代码末尾，注入 `# TODO: edit success condition` 模板，使用 `page.wait_for_url` 模式匹配作为建议。

## 2. 运行时页面就绪检测（P0）

- [x] 2.1 `test_component.py` 增加 login 页面就绪检测：在 `_test_python_component_with_browser` 的 login 组件 `run()` 调用前，增加页面就绪等待（多候选 `.first.wait_for(state="visible", timeout=15000)`）；超时时返回结构化错误（`phase=page_readiness`、`current_url`、候选元素状态）。
- [x] 2.2 `executor_v2.py` 确认调用链兼容：执行器在 login 组件调用前的现有流程（导航 + 弹窗处理）已提供足够的页面稳定保障，无需额外注入检测。
- [x] 2.3 `component_test_service.py` 确认不影响现有准备逻辑：测试服务的 URL 规范化逻辑不受影响。

## 3. 回归测试更新（P1）

- [x] 3.1 更新 `test_steps_to_python_regression.py`：移除旧断言（_form_candidates、_route_markers、_ready_before_nav 等），新增 `TestGeneratorRuntimeSeparation` 测试类。
- [x] 3.2 新增"简化输出"测试用例：`test_framework_code_lines_limited` 验证框架代码行数 <= 50 行。
- [x] 3.3 新增"无容器上下文"测试用例：`test_no_container_discovery_form_candidates` 验证不注入泛化搜索。
- [x] 3.4 新增"有容器上下文"测试用例：验证当 metadata 包含 `container_selector: "#J_loginRegisterForm"` 时，生成具体的 `_form = page.locator("#J_loginRegisterForm")`。通过 `generate_python_code(..., metadata={"container_selector": ...})` 实现。

## 4. 文档与关联更新（P1）

- [x] 4.1 更新 `docs/guides/RECORDER_PYTHON_OUTPUT.md`：新增第 9 节"生成器与运行时职责分离"。
- [x] 4.2 更新 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`：新增第 16 节"生成器 vs 运行时职责边界"。
- [x] 4.3 更新 `optimize-component-version-management` 提案：在 proposal.md Impact 中添加交叉引用。

## 5. 生成器质量优化（P1）

- [x] 5.1 消除 `.first` 自矛盾：`_form = page` 时不再无条件添加 `.first`（`use_first=False`），生成代码通过 lint 检查。
- [x] 5.2 click+fill 步骤合并：检测相邻 click 与 fill 操作同选择器时，自动跳过冗余 click（Playwright `fill()` 自动聚焦）。
- [x] 5.3 容器上下文扩展点：`generate_python_code` 新增 `metadata` 参数，当 `metadata.container_selector` 存在时生成 `_form = page.locator(...)` 而非 `_form = page`。
- [x] 5.4 规范文档更新：第 16 节补充 `.first` 使用原则表格和 click+fill 合并说明。
- [x] 5.5 回归测试：新增 `TestGeneratorQualityOptimizations` 测试类（5 个用例），全部通过。

## 6. 验收

- [x] 6.1 生成 login 组件代码后，确认无 `to_have_count(1)`（门卫/容器部分）、`_login_element_candidates`、`_form_candidates` 等框架逻辑。（25 个回归测试全部通过）
- [ ] 6.2 在妙手 ERP 登录页（多密码框、多登录按钮、无 form 标签）上测试生成的组件，确认无首步失败。（需人工验收）
- [ ] 6.3 在测试框架中确认页面就绪检测正常工作（密码框可见即继续，超时返回诊断信息）。（需人工验收）
- [x] 6.4 回归验证：验证码处理、URL 导航、非 login 组件生成均不受影响。（lint 测试 6/6 通过，回归测试 25/25 通过）
