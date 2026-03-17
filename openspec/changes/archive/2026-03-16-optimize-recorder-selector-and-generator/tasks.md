## 1. P0: JS 注入增强选择器质量

- [x] 1.1 在 `tools/launch_inspector_recorder.py` 的 `_inject_event_capture_script` 中添加隐式角色映射函数 `getImplicitRole(element)`，覆盖 button/a/input/select/textarea/h1-h6/nav/img 等标签
- [x] 1.2 修改 `generateSelectors` 函数，使用 `getImplicitRole` + accessible name（innerText/value/alt）生成 role 选择器，替代仅检测 `getAttribute('role')`
- [x] 1.3 添加 `placeholder` 选择器捕获：对 input/textarea 元素，若有 placeholder 属性则 push `{type: 'placeholder', value: placeholder, priority: 1.5}`
- [x] 1.4 添加 `label` 选择器捕获：通过 `label[for=id]` 或 `element.closest('label')` 查找关联 label，push `{type: 'label', value: labelText, priority: 1.8}`
- [x] 1.5 添加选择器唯一性验证：按类型使用不同方式检查匹配数量（CSS 用 `querySelectorAll`；placeholder 用 `querySelectorAll('[placeholder="..."]')`；role 用标签查询+文本过滤；text 用 XPath 计数），写入 `unique: true/false` 字段
- [x] 1.6 调整选择器 push 顺序为 role > placeholder > label > text > css，确保 Python 侧 `_selector_from_selectors` 按数组顺序取到最优选择器
- [x] 1.7 修改 `_selector_from_selectors` 消费 `unique` 字段：优先返回 `unique: true` 的最高优先级选择器；若最高优先级非唯一则降级到下一个唯一选择器并返回降级标记；若全部非唯一则取最高优先级并附加警告标记
- [x] 1.8 更新 `_selector_from_selectors` docstring：优先级从 `role > text > label > placeholder` 改为 `role > placeholder > label > text > css`，并说明 unique 降级逻辑

## 2. P1: 生成器补全 action 支持

- [x] 2.1 在 `steps_to_python.py` 的主循环中添加 `select` action 处理：生成 `locator.select_option(value)` 调用
- [x] 2.2 添加 `press` action 处理：生成 `page.keyboard.press(key)` 或 `locator.press(key)` 调用
- [x] 2.3 添加 `download` action 处理：生成 `async with page.expect_download() as download_info` + `download.value.save_as(path)` 模板

## 3. P1: Export 组件完整下载模板

- [x] 3.1 重写 export 分支的 `run()` 方法模板：添加 `build_standard_output_root()` 路径计算
- [x] 3.2 在 export 模板末尾生成 `async with page.expect_download()` 下载处理和 `download.value.save_as(file_path)` 文件保存
- [x] 3.3 修改返回值从 `ExportResult(success=True, file_path=None)` 为 `ExportResult(success=True, file_path=str(file_path))`

## 4. P1: 非 login/export 组件基类修复

- [x] 4.1 修改生成器 else 分支：navigation 类型继承 `NavigationComponent`，import `NavigationResult` 和 `TargetPage`，`run` 签名为 `async def run(self, page, target: TargetPage) -> NavigationResult`（target 为必选参数，与基类一致）
- [x] 4.2 date_picker 类型继承 `DatePickerComponent`，import `DatePickResult` 和 `DateOption`，`run` 签名为 `async def run(self, page, option: DateOption) -> DatePickResult`（option 为必选参数，与基类一致）
- [x] 4.3 其他未知类型继承 `ComponentBase`，保留 `async def run(self, page) -> ResultBase`

## 5. P1: Wait 步骤修复

- [x] 5.1 将无 `fixed_wait_reason` 的 wait 步骤默认生成从 `domcontentloaded` 改为 `networkidle`

## 6. P2: Bug 修复

- [x] 6.1 修复 `had_captcha_raise` 逻辑：验证码 fill 步骤后的非验证码步骤（如勾选框）移到 raise 之前生成，附加注释提醒顺序与录制不同、可能需人工调整
- [x] 6.2 为 `generate_python_code` 添加可选参数 `success_criteria: Optional[Dict] = None`
- [x] 6.3 验证码恢复块 URL 判断：从 `success_criteria` 中读取 `url_contains`/`url_not_contains` 生成条件判断，不硬编码 `/welcome`、`/dashboard`；无 `success_criteria` 时生成 `# TODO: 配置登录成功 URL 条件` 注释
- [x] 6.4 修改 `backend/routers/component_recorder.py` 中两处 `generate_python_code` 调用，传递 `success_criteria` 参数（从请求或录制上下文获取）
- [x] 6.5 清理 `import os` 重复导入：文件头已导入则内部不再重复 import
- [x] 6.6 清理 `params` 重复定义：恢复块与主体共用同一 `params` 变量

## 7. 测试

- [x] 7.1 在 `test_steps_to_python_regression.py` 中补充 select/press/download action 的生成测试
- [x] 7.2 补充 export 组件下载模板测试：验证生成代码包含 `expect_download`、`build_standard_output_root`、`save_as`
- [x] 7.3 补充 navigation/date_picker 组件基类继承测试：验证生成代码继承正确基类
- [x] 7.4 补充 wait 步骤生成 `networkidle` 测试
- [x] 7.5 补充验证码后非验证码步骤保留测试（包括验证重排序注释存在）
- [x] 7.6 补充验证码恢复块 URL 判断可配置测试（传 success_criteria 和不传两种情况）
- [x] 7.7 补充 `_selector_from_selectors` unique 降级逻辑测试：最高优先级非唯一时降级到唯一选择器
- [x] 7.8 补充 JS 注入选择器质量测试脚本（可选）：验证 `<button>Login</button>` 能生成 role=button 选择器
