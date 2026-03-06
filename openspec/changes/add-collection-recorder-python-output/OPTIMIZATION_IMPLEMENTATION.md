# 采集录制与解析优化实施说明（已实施）

本文档记录已完成的优化项：消除步骤重复（方案 A + C）、生成器 selector 归一化、步骤间等待、Inspector 加固去重。

---

## 已实施的修改

### 1. Trace 解析器：方案 A + 方案 C

**文件**：`backend/utils/trace_parser.py`

- **方案 A**：仅处理 `event_type == 'action'` 或 `'action' in event`，已移除对 `before`/`after` 的处理，同一操作只产生一条 action。
- **方案 C**：新增 `DEDUP_TIME_WINDOW_MS = 500` 与 `_deduplicate_actions(actions)`，在 500ms 时间窗内对相同 `(action_type, selector, value)` 只保留第一条；在 `_extract_actions` 中 sort 后调用去重再返回。

### 2. 生成器：selector 归一化

**文件**：`backend/services/steps_to_python.py`

- 新增 `_selector_from_selectors(selectors)`：从 Inspector 的 `selectors` 列表（`[{type, value}, ...]`）按优先级 role > text > label > placeholder > css 推导出单个 selector 字符串。
- 在处理每条 step 时，若 `selector` 为空且 `step.get("selectors")` 非空，则 `selector = _selector_from_selectors(step["selectors"])`，使生成的 Python 包含真实 locator/expect/click/fill 代码。

### 3. 生成器：步骤间等待

**文件**：`backend/services/steps_to_python.py`

- 在每步代码输出后，若当前步为 `navigate` 或 `goto`，则插入 `await page.wait_for_load_state("domcontentloaded", timeout=10000)`，再进入下一步，减少导航未完成即执行下一步的偶发失败。

### 4. Inspector：加固去重

**文件**：`tools/launch_inspector_recorder.py`

- 在 `_handle_normal_event` 中，在原有「与上一步同 action+description 则合并/跳过」基础上，增加对最近 2～3 步的检查：若存在相同 `action` 且主 selector（`_get_primary_selector(selectors)`）相同，则对 fill 更新 value 并 return，对 click 直接 return，避免同一操作因事件多次触发产生多条步骤。

---

## 优化后效果

- **步骤重复**：Trace 解析不再因 before/after 重复计数；时间窗去重进一步合并残留重复；Inspector 事件层同 selector 同 action 在最近几步内合并/跳过。
- **生成代码可执行**：有 `selectors` 无 `selector` 的步骤能推导出 selector，生成 locator + expect + click/fill，测试组件可正常执行。
- **步骤衔接**：navigate/goto 后增加 wait_for_load_state，符合《采集脚本编写规范》的等待策略。

与提案及《采集脚本编写规范》的符合性见前文分析总结。

---

## 组件测试流程优化（版本管理页测试）

### 5. 版本统计更新：同步 Session 替代线程内异步

**文件**：`backend/routers/component_versions.py`

- **问题**：子进程测试结束后，在独立线程内通过 `asyncio.new_event_loop()` + `AsyncSessionLocal` 更新版本统计与测试历史，导致 asyncpg 连接绑定到主事件循环，出现 "Future attached to a different loop" 与 "unknown protocol state 3"。
- **方案**：在回调线程内使用**同步** `SessionLocal`：读取 `result.json` 后，用 `SessionLocal()` 创建同步 session，更新 `ComponentVersion` 的 usage_count/success_rate，并调用新增的 `save_test_history_sync(db, ...)` 写入测试历史，最后 `db.close()`。不再在线程内创建新事件循环或使用 AsyncSession。
- **结果**：统计与历史写入稳定完成，不再产生跨 loop 异常；若写入失败，将 `stats_update_error` 写入 `progress.json`，状态接口返回该字段，前端可展示「测试已执行完成，但版本统计更新失败」的提示。

### 6. 测试浏览器窗口：有头模式全屏

**文件**：`tools/test_component.py`

- **行为**：有头模式（`headless=False`）下，`browser.launch` 使用 `args=['--start-maximized']`，`new_context(viewport=None)` 不固定 viewport，页面随窗口实际大小显示，便于用户观察自动化效果；无头模式仍使用固定 `viewport={'width': 1920, 'height': 1080}` 便于 CI。
- **位置**：Python 组件测试入口 `_test_python_component` 与 YAML/步骤组件测试分支 `_test_with_browser` 中两处 `new_context` 均已统一为上述逻辑。

---

## 待实施：验证码类型与测试阶段回传（见 proposal §10、tasks §7）

### 验证码类型区分（录制器）

- **目标**：与《COLLECTION_LOGIN_VERIFICATION》对齐，将录制器步骤中的「验证码」拆为「图形验证码」（需截图）与「短信/OTP」（无需截图）；在 `_enrich_steps_semantics` 中为 step_group 补充 scene_tags（graphical_captcha / otp），供生成器与执行器区分。
- **向后兼容**：保留对 step_group=captcha 的识别，未区分子类型时视为 graphical_captcha 或 scene_tags 保留 captcha。
- **涉及**：前端步骤标记选项、`backend/routers/component_recorder.py` 的 `_enrich_steps_semantics`、RECORDER_PYTHON_OUTPUT.md 或采集规范文档。

### 测试阶段验证码暂停与回传

- **适用范围**：仅 **Python 组件测试**（组件版本管理页）；YAML/步骤组件若有需求留作后续。
- **目标**：组件测试时若登录需验证码（手写组件抛 `VerificationRequiredError`），子进程不立刻失败，而是写 progress 为 `verification_required` 并轮询 `verification_response.json`；用户在测试弹窗中看到截图或输入框，输入后提交；后端将回传写入文件，子进程填入当前 page 并继续。
- **API 路径**：`GET/POST /component-versions/{version_id}/test/{test_id}/status`、`GET .../verification-screenshot`、`POST .../resume`；version_id 必选。
- **子进程**：捕获 `VerificationRequiredError`，将 verification 字段**合并**写入现有 progress.json（status、verification_type、verification_screenshot 为 test_dir 内路径）；轮询 `verification_response.json`（超时约 5 分钟）；超时则 status=failed 并写 `verification_timeout: true` 或 error；读到后在同一 page 填入并继续。
- **后端**：GET status 在 verification_required 时返回 verification_type、**verification_screenshot_url**（供前端请求截图）；GET verification-screenshot 读 test_dir 内文件返回图片流；POST resume 校验 test 存在、status 为 verification_required、当前用户有权限，超时或已结束后再调用返回 4xx，通过后写入 `verification_response.json`。
- **前端**：轮询 status；发现 `verification_required` 时用 verification_screenshot_url 展示截图（图形验证码）+ 输入框或仅输入框（OTP）；用户提交后调用 resume，继续轮询直至完成。
- **与采集的区别**：采集使用 task_id + Redis + `POST /collection/tasks/{task_id}/resume`，用户在任务列表/详情操作；测试使用 test_id + 文件 + `POST .../resume`，用户在测试弹窗操作；语义一致，仅介质与入口不同。
- **多实例**：截图在 test_dir（单机 temp），多实例时需共享存储或保证同一 test 的请求路由到同一实例。
