# Python 组件编写模板

> 更新于 v4.21.0 -- 对齐 `modules/components/` 基类层次结构

本文档提供 Python 采集组件的编写模板。所有模板均基于 `modules/components/` 中的实际基类，
与执行器（`executor_v2.py`）和测试框架（`test_component.py`）完全兼容。

**权威编写规范**：`docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`

---

## 基类层次结构

```
ComponentBase (modules/components/base.py)
  ctx: ExecutionContext     -- 统一执行上下文
  logger                   -- 属性，从 ctx.logger 获取
  guard_overlays(page)     -- 测试模式下自动关闭弹窗
  report_step(...)         -- 步骤进度上报

  +-- LoginComponent (modules/components/login/base.py)
  |     run(self, page) -> LoginResult
  |
  +-- ExportComponent (modules/components/export/base.py)
  |     run(self, page, mode=ExportMode.STANDARD) -> ExportResult
  |
  +-- NavigationComponent (modules/components/navigation/base.py)
  |     run(self, page, target) -> NavigationResult
  |
  +-- DatePickerComponent (modules/components/date_picker/base.py)
        run(self, page, option) -> DatePickResult
```

**关键约定**：
- 所有 `run` 方法必须 `async`
- 账号/配置信息从 `self.ctx.account` / `self.ctx.config` 获取，**不通过参数传递**
- 返回对应的 `ResultBase` 子类，禁止返回裸 `dict`

---

## ExecutionContext 字段

```python
@dataclass
class ExecutionContext:
    platform: str                    # 平台标识（如 "miaoshou"）
    account: dict[str, Any]          # 账号信息（username, password 已解密, login_url, ...）
    logger: Optional[SupportsLogger] # 结构化日志
    config: Optional[dict[str, Any]] # 任务配置（params, task, default_login_url, ...）
    step_callback: Optional[...]     # 步骤进度回调（v4.8.0）
    step_prefix: str                 # 嵌套组件步骤 ID 前缀
    is_test_mode: bool               # 是否测试模式
```

---

## 登录组件模板

```python
from __future__ import annotations

from typing import Any

from playwright.async_api import expect

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginComponent, LoginResult
from modules.apps.collection_center.executor_v2 import VerificationRequiredError


class PlatformLogin(LoginComponent):
    """Platform login component."""

    platform = "platform_name"
    component_type = "login"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def _login_ready(self, page: Any) -> bool:
        """登录成功检测：动作成功不等于业务成功。"""
        cur = str(getattr(page, "url", "") or "").lower()
        if "/login" in cur:
            return False
        # 至少保留一个 URL/页面特征信号；推荐双信号
        return "/welcome" in cur or await page.get_by_text("工作台").is_visible()

    async def _checkbox_checked(self, locator) -> bool:
        try:
            return await locator.is_checked()
        except Exception:
            aria_checked = await locator.get_attribute("aria-checked")
            return str(aria_checked).lower() == "true"

    async def run(self, page: Any) -> LoginResult:
        acc = self.ctx.account or {}
        config = self.ctx.config or {}

        # -- pre-check：已登录则直接跳过 --
        if await self._login_ready(page):
            return LoginResult(success=True, message="already logged in")

        # -- 验证码恢复路径（必须在 page.goto 之前）--
        # 若有回传的验证码/OTP，同页继续，不重新导航
        params = config.get("params") or {}
        captcha_code = params.get("captcha_code") or params.get("otp")
        if captcha_code:
            value = (captcha_code or "").strip()
            if value:
                try:
                    cap_input = page.locator("input[placeholder*='验证码']")
                    await expect(cap_input).to_have_count(1)
                    await cap_input.fill(value, timeout=5000)
                    login_btn = page.get_by_role("button", name="登录")
                    await expect(login_btn).to_have_count(1)
                    await login_btn.click(timeout=3000)
                    if await self._login_ready(page):
                        return LoginResult(success=True, message="ok")
                    return LoginResult(success=False, message="验证码提交后仍未满足登录成功条件")
                except Exception as e:
                    ctx_info = f"url={getattr(page, 'url', '')}"
                    return LoginResult(success=False, message=f"captcha resume failed: {e} ({ctx_info})")

        # -- URL 导航 --
        login_url = (
            str(params.get("login_url_override") or "").strip()
            or str(acc.get("login_url") or "").strip()
            or "https://platform.example.com/login"
        )
        if login_url:
            await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_load_state("domcontentloaded", timeout=10000)
            await self.guard_overlays(page, label="after login navigation")

        # -- 收敛作用域 --
        # 有明确容器时用具体 locator；无容器时用 page
        form = page.locator("#login-form")  # 按实际页面修改
        # form = page  # 无明确容器时

        # -- 填写表单 --
        username_input = form.get_by_role("textbox", name="用户名")
        await expect(username_input).to_be_visible()
        await username_input.fill(acc.get("username", ""), timeout=10000)

        password_input = form.get_by_role("textbox", name="密码")
        await expect(password_input).to_be_visible()
        await password_input.fill(acc.get("password", ""), timeout=10000)

        # -- pre-check + action + post-check：记住我（如业务要求必须勾选） --
        remember_me = form.get_by_role("checkbox", name="记住我")
        await expect(remember_me).to_be_visible()
        if not await self._checkbox_checked(remember_me):
            await remember_me.click(timeout=10000)
            if not await self._checkbox_checked(remember_me):
                return LoginResult(success=False, message="记住我复选框点击后仍未勾选")

        # -- 提交登录 --
        login_btn = form.get_by_role("button", name="登录")
        await expect(login_btn).to_be_visible()
        await login_btn.click(timeout=10000)

        # -- post-check：登录成功条件（必须编辑） --
        # 标准：pre-check -> action -> post-check
        # 动作成功不等于业务成功；至少校验 URL/关键元素/弹窗状态中的一个，推荐双信号
        if await self._login_ready(page):
            return LoginResult(success=True, message="ok")
        return LoginResult(success=False, message="登录按钮点击后仍未满足登录成功条件")
```

---

## 导出组件模板

```python
from __future__ import annotations

from typing import Any
from pathlib import Path

from playwright.async_api import expect

from modules.components.base import ExecutionContext
from modules.components.export.base import (
    ExportComponent,
    ExportMode,
    ExportResult,
    build_standard_output_root,
)


class PlatformOrdersExport(ExportComponent):
    """Platform orders export component."""

    platform = "platform_name"
    component_type = "export"
    data_domain = "orders"

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:
        config = self.ctx.config or {}
        date_from = config.get("date_from", "")
        date_to = config.get("date_to", "")

        # -- 导航到数据页面 --
        await page.goto("https://platform.example.com/orders", wait_until="domcontentloaded")
        await self.guard_overlays(page, label="after navigation")

        # -- 设置日期范围（可调用子组件） --
        # date_picker = ...

        # -- 点击导出 --
        export_btn = page.get_by_role("button", name="导出")
        await expect(export_btn).to_be_visible()

        # -- 等待下载 --
        async with page.expect_download() as download_info:
            await export_btn.click(timeout=10000)
        download = await download_info.value

        # -- 保存文件 --
        output_dir = build_standard_output_root(self.ctx, "orders", "daily")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / download.suggested_filename
        await download.save_as(str(file_path))

        if self.logger:
            self.logger.info(f"[OK] Export saved: {file_path}")
        return ExportResult(success=True, file_path=str(file_path))
```

---

## 导航组件模板

```python
from __future__ import annotations

from typing import Any

from playwright.async_api import expect

from modules.components.base import ExecutionContext
from modules.components.navigation.base import (
    NavigationComponent,
    NavigationResult,
    TargetPage,
)


class PlatformNavigation(NavigationComponent):
    """Platform navigation component."""

    platform = "platform_name"
    component_type = "navigation"
    data_domain = None

    def __init__(self, ctx: ExecutionContext) -> None:
        super().__init__(ctx)

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:
        # 根据目标页面执行导航
        target_url = self._get_url(target)
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        await self.guard_overlays(page, label=f"after nav to {target.value}")

        # 等待目标页特征元素可见（SPA/MPA 通用）
        # await expect(page.get_by_role("heading", name="订单列表")).to_be_visible(timeout=10000)

        return NavigationResult(success=True, url=page.url)

    def _get_url(self, target: TargetPage) -> str:
        urls = {
            TargetPage.ORDERS: "https://platform.example.com/orders",
        }
        return urls.get(target, "")
```

---

## 组件开发规范

### 1. 异步方法（必须）

所有组件的 `run` 方法必须是异步的，Playwright 操作必须 `await`：

```python
# 正确
async def run(self, page: Any) -> LoginResult:
    await page.goto(url)
    await page.get_by_role("button", name="登录").click()

# 错误：缺少 async / await
def run(self, page):
    page.goto(url)
```

### 2. 使用 Playwright 官方 API

优先使用 `get_by_role`、`get_by_text` 等官方推荐的定位器，先收敛作用域再定位元素：

```python
# 推荐：先容器后元素
form = page.locator("#login-form")
username = form.get_by_role("textbox", name="用户名")
await expect(username).to_be_visible()
await username.fill(value)

# 不推荐：用 .first 掩盖多匹配
await page.locator("input.username").first.click()
```

### 3. 检测层模板（强制）

所有关键步骤按下面顺序编写，不得省略 post-check：

```python
# pre-check
await expect(locator).to_be_visible()

# action
await locator.click(timeout=10000)

# post-check
if not await target_state_detector():
    return LoginResult(success=False, message="目标状态未达成")
```

常见 `target_state_detector()`：

- 登录：URL 已离开登录页，且欢迎页/工作台元素可见
- checkbox：`is_checked()` 或 `aria-checked=true`
- 弹窗关闭：dialog hidden/detached，overlay 不再遮挡
- 导出：文件存在且非空

推荐 helper 命名：

- `detect_login_ready()`
- `ensure_remember_me_checked()`
- `ensure_popup_closed()`
- `wait_navigation_ready()`
- `wait_export_complete()`

### 4. 弹窗关闭模板

```python
dialog = page.get_by_role("dialog", name="导出确认")
await expect(dialog).to_be_visible()
confirm_btn = dialog.get_by_role("button", name="确定")
await confirm_btn.click(timeout=10000)
await expect(dialog).to_be_hidden(timeout=10000)
```

### 5. 日志输出（禁止 Emoji）

使用 ASCII 符号代替 Emoji（Windows 编码兼容性）：

```python
# 正确
if self.logger:
    self.logger.info("[OK] Login successful")
    self.logger.error("[FAIL] Login failed")
    self.logger.warning("[WARN] Password expired")

# 错误：emoji 字符会导致 Windows UnicodeEncodeError
# self.logger.info("\u2705 Login successful")  # 禁止使用 emoji
```

### 6. 错误处理

返回 `ResultBase` 子类，关键失败需包含可诊断信息：

```python
async def run(self, page: Any) -> LoginResult:
    try:
        # 业务逻辑
        return LoginResult(success=True, message="ok")
    except Exception as e:
        if self.logger:
            self.logger.error(f"[FAIL] Login failed: {e}")
        return LoginResult(
            success=False,
            message=str(e),
            details={"url": getattr(page, "url", ""), "phase": "form_submit"},
        )
```

### 7. 组件元数据（必须）

```python
class MyComponent(ExportComponent):
    platform = "shopee"           # 平台代码（必需）
    component_type = "export"     # 组件类型（必需）
    data_domain = "orders"        # 数据域（export 组件必需）
```

### 8. 等待策略

```python
# 推荐：条件等待
await expect(page.get_by_role("button", name="导出")).to_be_visible(timeout=10000)

# 推荐：等待 URL 变化
await page.wait_for_url("**/dashboard**", timeout=15000)

# 推荐：等待加载消失
await page.locator(".loading-spinner").wait_for(state="hidden", timeout=10000)

# 仅在确需人为节奏时使用，并注明原因
await page.wait_for_timeout(1000)  # 固定等待: 动画结束
```

---

## 组件目录结构

```
modules/platforms/
  {platform}/
    components/
      login.py                    # 手写稳定版
      login_v1_0_0.py             # 录制生成版本
      login_v1_0_1.py             # 迭代版本
      orders_export.py
      navigation.py
      date_picker.py
```

---

## 验证组件

```python
from modules.apps.collection_center.component_loader import ComponentLoader

loader = ComponentLoader()
component_class = loader.load_python_component("shopee", "login")
result = loader.validate_python_component(component_class)
if result['valid']:
    print(f"[OK] Metadata: {result['metadata']}")
else:
    print(f"[FAIL] Errors: {result['errors']}")
```
