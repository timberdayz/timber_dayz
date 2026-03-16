# 录制工具 Python 产出使用说明

录制停止后，系统会根据步骤自动生成符合《采集脚本编写规范》的 Python 组件代码，并支持在前端预览、编辑后保存为 `.py` 文件。本文说明如何查看/编辑生成的 Python、如何按规范微调、以及保存后组件路径与版本注册。

**相关规范**：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`。

---

## 1. 查看与编辑生成的 Python 代码

1. **开始录制**：在「组件录制」页选择平台与组件类型（登录/导出等），点击「开始录制」；在 Inspector 中完成操作后点击「停止录制」。
2. **步骤模式**：若为步骤模式且录到步骤，停止后会在右侧看到 **「Python 代码」** 区域，展示后端根据步骤生成的 Python 源码（不再提供 YAML 预览）。
3. **未生成时**：若区域为空或提示「未生成代码」，可点击 **「重新生成」** 按钮（会调用 `POST /recorder/generate-python`）；若仍无代码，请检查步骤是否有效（如至少包含 navigate/click/fill 等）。
4. **编辑**：文本框支持直接编辑。可按《采集脚本编写规范》微调：
   - 将 `page.locator(selector)` 改为 `get_by_role` / `get_by_label` / `get_by_text` 等更稳定的定位；
   - 补充弹窗、复杂交互、下载等处的注释或实现；
   - 调整 `expect(locator).to_be_visible()` 或超时等等待逻辑。

---

## 2. 保存为 .py（主路径）

1. **组件名称**：前端展示组件名称用于识别；实际保存目标由后端按 `platform + component_type`（export 需 `data_domain`，子域 export 需 `sub_domain`）推导，不再依赖手工输入避免命名漂移。
2. **保存**：点击「保存」时，**必须**保证「Python 代码」区域有内容；当前内容会作为 `python_code` 提交到 `POST /recorder/save`，后端会写入版本化 `.py` 文件并注册新版本。
3. **无 Python 时**：如果未生成或删除了 Python 代码，保存会被前端阻止，并提示“当前只支持保存 Python 组件，请先生成或编辑 Python 代码”；录制工具不再使用 YAML 作为组件保存格式。

---

## 3. 保存后组件位置与版本

- **Python 组件**：保存到版本化文件路径（示例：`modules/platforms/{platform}/components/login_v1_0_1.py`）；`file_path` 在数据库中存相对 `PROJECT_ROOT` 的相对路径。
- **版本注册**：每次保存都会写入 **component_versions** 新版本记录（版本号 patch 递增，`is_stable=False`），用于版本选择、测试和提升稳定版。
- **调用方式**：测试与执行链路按 `version.file_path` 加载 `.py` 文件，确保“选中版本”和“实际执行文件”一致。

### 3.1 保存逻辑：版本化新增（非 UPSERT）

| 场景 | 磁盘文件 | component_versions 表 |
|------|----------|------------------------|
| **首次保存**（该逻辑组件无版本） | 新建版本化 `.py` 文件 | INSERT 首个版本记录（如 1.0.0，默认非稳定） |
| **再次保存**（已有历史版本） | 新建下一版 `.py` 文件（如 1.0.0 -> 1.0.1） | INSERT 新版本记录（不覆盖旧版本） |
| **删除版本** | 按版本删除记录；文件是否保留由版本治理策略决定 | 删除对应版本记录（遵循启用/测试状态约束） |

**结论**：录制保存是 **版本化新增**。每次保存创建新版本与新 file_path，旧版本保留用于回滚与对比测试；不再采用按同路径覆盖的 UPSERT 语义。
- **淘汰**：在 component_versions 中将某版本设为 `is_active=False` 可从版本池淘汰；删除遵循版本管理页面规则。

---

## 4. 图形验证码步骤语义

- **必选暂停**：图形验证码步骤生成「到达即等待 1s → 截图 → raise VerificationRequiredError」，不做 `count() > 0` / `is_visible()` 条件检测。
- **不做条件检测**：避免 `except Exception: pass` 吞掉异常导致静默穿透，确保用户到达验证码步骤时必然暂停并等待回传。

---

## 5. 验收要点

- 从前端：开始录制 → 停止 → 在「Python 代码」区域看到并可编辑生成的代码 → 保存。
- 确认磁盘上存在 `modules/platforms/{platform}/components/{component_name}.py`，且可被执行器加载（无语法错误、符合组件契约）。
- 生成代码具备：组件契约（`async def run(...)`、返回 ResultBase 子类）、get_by_* 优先、click/fill 前 `expect(...).to_be_visible()` 等（可人工抽查或小脚本检查）。

---

## 6. 配置迁离 YAML（与录制器一致）

- **弹窗配置**：平台特定关闭/遮罩选择器由 Python 模块提供，不再读取 `popup_config.yaml`。路径：`modules/platforms/{platform}/popup_config.py`，导出 `get_close_selectors()`、`get_overlay_selectors()`、`get_poll_strategy()`。
- **执行顺序**：组件执行顺序由 `modules/apps/collection_center/execution_order.py` 提供（`get_default_execution_order()`、`get_execution_order(platform)`），不再读取 `execution_order.yaml` / `default_execution_order.yaml`。
- **存量迁移**：若数据库中 component_versions 的 `file_path` 仍为 `.yaml`，可执行 `scripts/migrate_component_versions_to_python.py` 将路径迁为 `.py`。
- **部署必须步骤**：在代码切换为仅 Python 组件后，**部署前必须执行一次** `scripts/migrate_component_versions_to_python.py`，将存量 `component_versions.file_path` 从 .yaml 迁为 .py，否则版本选择与执行器可能找不到组件。清理残留 YAML 文件可使用 `scripts/cleanup_yaml_components.py`（一次性脚本）。

---

## 7. 录制页与组件版本管理的职责边界

- **录制页（组件录制工具）**：仅负责「录制 → 步骤编辑 → 生成/编辑 Python 代码 → 保存为 .py」。录制页**不提供**在页内直接「测试组件」的入口；保存成功后可通过提示「前往组件版本管理并测试」跳转到版本管理页。
- **组件版本管理页**：提供组件的版本列表、A/B 测试、**测试组件**（选择账号后执行有头/无头测试）、提升稳定版、启用/停用等。**所有组件执行与测试统一在组件版本管理页完成**，保证测试使用的是已保存的 .py 文件，避免临时 YAML/Python 与正式组件行为不一致。

---

## 8. 步骤标记含义与生成器行为

录制结果页可为每个步骤设置「步骤标记」，后端会据此补充 `scene_tags` 并影响生成代码：

| 标记         | 含义                     | 生成/执行器行为 |
|--------------|--------------------------|-----------------|
| 普通步骤     | 无特殊语义               | 按 action 生成 click/fill/navigate 等 |
| 日期组件     | 该步骤属于日期选择流程   | 可转为 component_call（date_picker） |
| 筛选器       | 该步骤属于筛选器流程     | 可转为 component_call（filters） |
| 图形验证码   | 需截图给用户看后输入     | scene_tags 含 graphical_captcha；**登录组件**时生成器生成恢复路径 + 到达即暂停 + VerificationRequiredError |
| 短信/OTP验证码 | 用户查收短信/邮件后输入，无需截图 | scene_tags 含 otp；**登录组件**时生成器同上 |
| 验证码（兼容） | 未区分子类型，按图形验证码处理 | 向后兼容旧数据；建议新录制选用「图形验证码」或「短信/OTP验证码」 |
| 导航         | 该步骤为导航/页面跳转    | 生成器会补充 wait_for_load_state 与 guard_overlays |
| 弹窗/通知栏  | 该步骤为关闭弹窗或通知   | 生成可选「等待 dialog 可见 + 点击确定/关闭」逻辑 |

- **验证码类型**：录制时验证码步骤需区分「图形验证码」（用户查看截图后输入）与「短信/OTP」（用户查收后输入），与执行器、前端的 `verification_type` 一致。
- **生成器验证码感知**：当登录组件含「图形验证码」或「短信/OTP验证码」步骤时，生成器会输出「验证码感知」结构：在 `run()` 开头插入**恢复路径**（若 `params` 有 `captcha_code`/`otp`，则同页填入并点击登录，不执行 `page.goto`）；图形验证码步骤不生成 `fill(录制值)`，改为到达该步骤后固定短等待、截图并 `raise VerificationRequiredError`（不做 `count()/is_visible()` 条件分支），由执行器/测试工具暂停并等待用户回传后再次执行。
- **手写组件约定**：手写登录组件若支持验证码回传，**验证码恢复块必须放在 `page.goto` 之前**，否则重试时会刷新页面导致需重新输入账号密码。参见 `modules/platforms/miaoshou/components/login.py`。
- **登录成功条件**：保存登录组件时，可在「登录成功条件」中配置 `success_criteria`，目前支持：
  - `url_contains`: 字符串或字符串数组，表示登录后 URL 必须包含的片段（如 `"/welcome"`）；
  - `url_not_contains`: 字符串或字符串数组，表示登录后 URL 不应再包含的片段（如 `"/login"`）；
  - `element_visible_selector`: 登录成功后应可见的关键元素选择器（如侧边栏导航的 role 选择器）。
  后端在保存时会将这些条件注入组件末尾的统一登录检测代码中，按顺序校验，通过后才返回 `LoginResult(success=True)`。

示例（前端传给 `/recorder/save` 的 `success_criteria`）：

```json
{
  "url_contains": ["/welcome"],
  "url_not_contains": "/login",
  "element_visible_selector": "role=navigation"
}
```

---

## 9. 生成器与运行时职责分离（v4.21.0+）

自 `refactor-generator-runtime-separation` 提案起，生成器遵循以下原则：

- **生成器仅输出忠实回放代码**：不注入"门卫检测"（`_login_element_candidates` + `to_have_count(1)` + `_route_markers`）和"泛化容器发现"（`_form_candidates` 多候选搜索）。
- **URL 导航保留在组件中**：`_target_url` 来源优先级（`login_url_override > account.login_url > config.default_login_url > platform default`）属于组件的业务逻辑。
- **页面就绪检测由运行时承担**：`test_component.py` 在执行 login 组件前会等待关键登录元素可见（`.first.wait_for(state="visible")`），兼容真实页面多元素场景。
- **验证码处理保留在组件中**：验证码检测与 `VerificationRequiredError` 暂停逻辑是业务逻辑，不属于框架。
- **登录成功条件为模板**：生成 TODO 注释引导用户编辑（如 `wait_for_url`），而非硬编码 `_route_markers`。

详见 `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md` 第 15 节"生成器 vs 运行时职责边界"和第 16 节"`.first` 使用原则"。

---

## 10. 后续优化方向

- **success_criteria 扩展**：除 url_contains 外，可支持 element_visible、title_contains 等，并在前端提供更多配置项。
- **步骤标记扩展**：如「店铺切换」「导出主流程」等，与执行器顺序及 component_call 进一步对齐。
- **生成后质量检查**：`/recorder/stop` 与 `/recorder/generate-python` 已返回 `lint_errors` / `lint_warnings`，前端可展示为「质量提示」列表，辅助快速修正。
- **场景模板与抗干扰**：生成器已对登录/导出在关键节点插入 `guard_overlays`；对标记为「弹窗/通知栏」的步骤生成可选关闭逻辑。可继续扩充「业务 Modal」「Cookie 同意」等场景模板。
