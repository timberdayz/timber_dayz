# 妙手 Miaoshou purchase / inventory 数据域采集组件实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重写 miaoshou inventory 数据域组件（旧实现半老旧）并新增 miaoshou purchase 数据域组件（异步导出 + 字段选择 + 导出记录轮询），均采用 V2 canonical "独立精细类"风格。

**Architecture:** 
- inventory：完全重写 + 归档旧文件。新建 `inventory_config.py`（`InventorySelectors` dataclass）+ `warehouse_filters.py`（`MiaoshouWarehouseFilters`）+ `inventory_export.py`（`MiaoshouInventoryExport`）。同步下载路径，沿用 orders 模式。
- purchase：新建数据域。新建 `purchase_config.py`（`PurchaseSelectors`）+ `purchase_export.py`（`MiaoshouPurchaseExport`，含异步子流程：触发导出 → 字段选择 → 关闭进度弹窗 → 导航导出记录 → 轮询可下载 → `page.expect_download()` 收文件）。复用 `MiaoshouDatePicker` 处理"创建日期"自定义面板。

**Tech Stack:** Python 3.13+ / Playwright (sync API) / dataclasses / pytest / Type hints

## Global Constraints

来自 spec `docs/superpowers/specs/2026-09-13-miaoshou-finance-inventory-data-domain-recording-design.md`：

1. **命名**：数据域 `purchase`（原 `finance`，已与妙手 ERP 实际页面"采购单"对齐）；inventory 数据域保持。
2. **风格**：独立精细类（独立 `ExportComponent` 子类），**不创建共享基类**、**不复制 orders 的 base + sub_domain 薄子类**模式。
3. **复用**：复用 `MiaoshouNavigation` / `stabilize_safe_notices` / `guard_overlays`（仅测试模式）/ `build_standard_output_root` / `build_filename`；inventory 复用 `MiaoshouWarehouseFilters`（新建，仅 inventory 用）；purchase 复用 `MiaoshouDatePicker`（处理"创建日期"）。
4. **弹窗关闭**：走 `_ensure_popup_closed` 统一轮询，**禁止 `page.keyboard.press("Escape")` 散落**。
5. **重试**：由执行器层 `modules/apps/collection_center/retry_strategy.py` 控制，组件内部不自动重试。
6. **错误处理**：整个 `run()` 包 `try/except`，返回 `ExportResult(success=False, message=str(e), file_path=None)`。
7. **禁止 emoji** / **禁止 `datetime.utcnow()`** / **不修改 `raw_data_importer`** / **不在 `collectors/` 根目录新增**。
8. **archive 前置**：文件不在 active 清单；无 stable `ComponentVersion.file_path` 指向；register/loader guard 已生效；新 canonical 不再 import 旧文件。
9. **进度提示**：inventory 同步导出时调 `_wait_export_progress_ready` 后用 `page.expect_download(timeout=180000)` 接文件；purchase 异步导出走"关闭进度弹窗 → 导出记录轮询 → `page.expect_download(timeout=180000)`"路径。
10. **输出路径**：inventory → `build_standard_output_root(data_type="inventory", granularity="snapshot")`；purchase → `build_standard_output_root(data_type="purchase", granularity="manual")`。

## File Structure

### 新建

| 路径 | 职责 |
|---|---|
| `modules/platforms/miaoshou/components/inventory_config.py` | `InventorySelectors` dataclass + 选择器常量 |
| `modules/platforms/miaoshou/components/warehouse_filters.py` | `MiaoshouWarehouseFilters`（仓库下拉多选 + 全选） |
| `modules/platforms/miaoshou/components/inventory_export.py` | `MiaoshouInventoryExport`（独立精细类） |
| `modules/platforms/miaoshou/components/purchase_config.py` | `PurchaseSelectors` dataclass + 选择器常量 |
| `modules/platforms/miaoshou/components/purchase_export.py` | `MiaoshouPurchaseExport`（独立精细类 + 异步子流程） |
| `backend/tests/test_miaoshou_inventory_export_contract.py` | inventory contract 测试（重写） |
| `backend/tests/test_miaoshou_inventory_export_v2_flow.py` | inventory v2_flow 测试（重写） |
| `backend/tests/test_miaoshou_purchase_export_contract.py` | purchase contract 测试（新建） |
| `backend/tests/test_miaoshou_purchase_export_v2_flow.py` | purchase v2_flow 测试（新建，含异步轮询 mock） |

### 修改

| 路径 | 改动 |
|---|---|
| `modules/components/navigation/base.py` | 新增 `TargetPage.PURCHASE = "purchase"` 枚举值 |
| `modules/platforms/miaoshou/components/navigation.py` | 增加 `if target is TargetPage.PURCHASE` 分支（路径 `/purchase/goods`）；`__init__` 的 `selectors` 类型增加 `PurchaseSelectors` |
| `modules/apps/collection_center/python_component_adapter.py` | `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["inventory"]` → `"MiaoshouInventoryExport"`；新增 `"purchase": "MiaoshouPurchaseExport"`；移除 inventory 特判分支（用通用 `module_name`） |
| `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md` | 加入 `miaoshou/inventory_export`、`miaoshou/purchase_export` |
| `docs/guides/CANONICAL_COMPONENT_STATUS.md` | miaoshou 表格新增 inventory_export / purchase_export，标 `可测试` |

### Archive

| 路径 | 目标 |
|---|---|
| `modules/platforms/miaoshou/components/inventory_snapshot_export.py` | → `modules/platforms/miaoshou/archive/inventory_snapshot_export.py` |
| `modules/platforms/miaoshou/components/warehouse_config.py` | → `modules/platforms/miaoshou/archive/warehouse_config.py` |

---

## Phase A：Inventory 重写

### Task 1: 创建 `inventory_config.py`（InventorySelectors）

**Files:**
- Create: `modules/platforms/miaoshou/components/inventory_config.py`

**Interfaces:**
- Consumes: 无（独立模块）
- Produces: `class InventorySelectors` (frozen dataclass)，包含 `base_url` / `checklist_path` / `open_export_menu` / `menu_export_searched` / `group_titles` / `group_check_all_text` / `export_buttons` / `popup_close_buttons` / `close_poll_max_rounds` / `close_poll_interval_ms` / `progress_texts` / `data_type_dir` 字段

**Note:** inventory 与 purchase 的 UI 流程非常相似（"导入/导出"按钮 + 下拉菜单 + 字段选择对话框），本 Task 抽出 inventory 特定的常量（按钮文字 `导入/导出商品`、菜单项 `导出搜索的商品`、分组标题 `商品信息/其他信息`）。purchase 后续 Task 7 会用自己的常量。

- [ ] **Step 1: 创建 `inventory_config.py` 写入 InventorySelectors dataclass**

```python
"""
Miaoshou ERP inventory (仓库清单) component config

Centralizes base URL, deep-link paths and key selectors used by
navigation/export. Mirrors the orders_config / purchase_config convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, List, Tuple

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
WAREHOUSE_CHECKLIST_PATH: Final[str] = "/warehouse/checklist"

OPEN_EXPORT_MENU_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("导入/导出商品")',
    '[role="button"]:has-text("导入/导出商品")',
    '.operate-side .jx-dropdown button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button.is-plain:has-text("导入/导出商品")',
    'button.jx-button:has-text("导入/导出商品")',
    '.pro-button:has-text("导入/导出商品")',
    '[aria-haspopup="menu"]:has-text("导入/导出商品")',
    'button:has-text("导出")',
)

MENU_EXPORT_SEARCHED_SELECTORS: Final[Tuple[str, ...]] = (
    ".J_warehouseChecklistExportSearch",
    '[role="menuitem"]:has-text("导出搜索的商品")',
    "text=导出搜索的商品",
)

GROUP_TITLES: Final[Tuple[str, ...]] = ("商品信息", "其他信息")
GROUP_CHECK_ALL_TEXT: Final[str] = "全选"

EXPORT_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    "button:has-text(导出)",
    "[role='button']:has-text(导出)",
    ".jx-dialog__body .pro-button:has-text(导出)",
    "button.jx-button.jx-button--primary:has-text(导出)",
    "button.pro-button:has-text(导出)",
)

POPUP_CLOSE_SELECTORS: Final[Tuple[str, ...]] = (
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-notification .anticon-close",
    ".ant-message-notice-close",
    ".ant-popover .ant-popover-close",
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(取消)",
    "button:has-text(OK)",
)

CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

PROGRESS_TEXTS: Final[Tuple[str, ...]] = (
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
    "导出成功",
    "Generating",
    "Processing",
)

DATA_TYPE_DIR: Final[str] = "inventory"


@dataclass(frozen=True)
class InventorySelectors:
    base_url: str = BASE_URL
    checklist_path: str = WAREHOUSE_CHECKLIST_PATH
    open_export_menu: Tuple[str, ...] = OPEN_EXPORT_MENU_SELECTORS
    menu_export_searched: Tuple[str, ...] = MENU_EXPORT_SEARCHED_SELECTORS
    group_titles: Tuple[str, ...] = GROUP_TITLES
    group_check_all_text: str = GROUP_CHECK_ALL_TEXT
    export_buttons: Tuple[str, ...] = EXPORT_BUTTON_SELECTORS
    popup_close_buttons: Tuple[str, ...] = POPUP_CLOSE_SELECTORS
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    progress_texts: Tuple[str, ...] = PROGRESS_TEXTS
    data_type_dir: str = DATA_TYPE_DIR
```

- [ ] **Step 2: 验证导入成功**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -c "from modules.platforms.miaoshou.components.inventory_config import InventorySelectors; s=InventorySelectors(); print(s.base_url, s.data_type_dir); assert '导入/导出商品' in s.open_export_menu[0]; assert '导出搜索的商品' in s.menu_export_searched[1]; assert '商品信息' in s.group_titles; assert '正在导出' in s.progress_texts"
```
Expected: `https://erp.91miaoshou.com inventory`（无 AssertionError）

- [ ] **Step 3: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/inventory_config.py
git commit -m "feat(miaoshou): add inventory_config with InventorySelectors dataclass"
```

---

### Task 2: 创建 `warehouse_filters.py`（MiaoshouWarehouseFilters）

**Files:**
- Create: `modules/platforms/miaoshou/components/warehouse_filters.py`

**Interfaces:**
- Consumes: `ExecutionContext`（`modules.components.base`）；`InventorySelectors`（Task 1）
- Produces: `class MiaoshouWarehouseFilters(ComponentBase)` 提供 `async def run(page, filters=None) -> ResultBase`；处理仓库下拉多选 + 全选

- [ ] **Step 1: 写失败 contract 测试**

文件: `backend/tests/test_miaoshou_warehouse_filters_contract.py`

```python
from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.warehouse_filters import MiaoshouWarehouseFilters


def test_miaoshou_warehouse_filters_component_declares_miaoshou_platform():
    assert MiaoshouWarehouseFilters.platform == "miaoshou"
    assert MiaoshouWarehouseFilters.component_type == "filters"
    assert MiaoshouWarehouseFilters.data_domain is None


def test_miaoshou_warehouse_filters_constructor_accepts_inventory_selectors():
    ctx = ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop"},
        logger=None,
        config={},
    )
    selectors = InventorySelectors()
    component = MiaoshouWarehouseFilters(ctx, selectors)

    assert component.sel is selectors
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_warehouse_filters_contract.py -v
```
Expected: `ModuleNotFoundError: No module named 'modules.platforms.miaoshou.components.warehouse_filters'`

- [ ] **Step 3: 实现 `warehouse_filters.py`**

```python
from __future__ import annotations

import re
from typing import Any

from modules.components.base import ComponentBase, ExecutionContext, ResultBase
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors


class MiaoshouWarehouseFilters(ComponentBase):
    """仓库清单页面的仓库范围筛选器（全选仓库）。"""

    platform = "miaoshou"
    component_type = "filters"
    data_domain = None

    def __init__(self, ctx: ExecutionContext, selectors: InventorySelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()

    async def _warehouse_scope_trigger(self, page: Any) -> Any:
        candidates = [
            page.get_by_label(re.compile(r"仓库", re.IGNORECASE)).first,
            page.get_by_text(re.compile(r"^仓库\s*:?$", re.IGNORECASE)).first.locator(
                "xpath=following::*[@role='combobox' or self::input][1]"
            ),
            page.get_by_role("combobox").first,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=1500)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库范围筛选器不可见")

    async def _wait_overlay_ready(self, page: Any) -> Any:
        candidates = [
            page.get_by_role("tooltip").last,
            page.locator(".el-select-dropdown:visible").last,
            page.locator(".ant-select-dropdown:visible").last,
            page.locator(".jx-select-dropdown:visible").last,
        ]
        for locator in candidates:
            try:
                await locator.wait_for(state="visible", timeout=2000)
                return locator
            except Exception:
                continue
        raise RuntimeError("仓库筛选下拉未出现")

    async def _is_checkbox_selected(self, locator: Any) -> bool:
        try:
            if await locator.is_checked():
                return True
        except Exception:
            pass

        try:
            checked = await locator.evaluate(
                """el => {
                    const root = el.closest(
                        '[role="checkbox"], label, .ant-checkbox-wrapper, .arco-checkbox, .jx-checkbox, .el-checkbox'
                    ) || el;
                    return root.getAttribute('aria-checked') === 'true'
                        || root.className.includes('checked')
                        || !!root.querySelector('input[type="checkbox"]:checked');
                }"""
            )
            return bool(checked)
        except Exception:
            return False

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            try:
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def run(self, page: Any, filters: dict[str, Any] | None = None) -> ResultBase:  # type: ignore[override]
        try:
            trigger = await self._warehouse_scope_trigger(page)
            await trigger.click(timeout=1500)
            overlay = await self._wait_overlay_ready(page)

            full_select = overlay.get_by_role("checkbox", name="全选").first
            try:
                await full_select.wait_for(state="visible", timeout=2000)
            except Exception:
                full_select = overlay.locator("label:has-text('全选') input[type='checkbox']").first
                await full_select.wait_for(state="attached", timeout=2000)

            checked = await self._is_checkbox_selected(full_select)
            if not checked:
                try:
                    await overlay.get_by_text("全选", exact=True).first.click(timeout=1000)
                except Exception:
                    await full_select.click(timeout=1000)

            await self._ensure_popup_closed(page)
            return ResultBase(success=True, message="ok", details={"select_all": True})
        except Exception as e:
            return ResultBase(success=False, message=str(e))
```

- [ ] **Step 4: 跑测试确认通过**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_warehouse_filters_contract.py -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/warehouse_filters.py backend/tests/test_miaoshou_warehouse_filters_contract.py
git commit -m "feat(miaoshou): add warehouse filters component for inventory"
```

---

### Task 3: 创建 `inventory_export.py`（MiaoshouInventoryExport）+ contract 测试

**Files:**
- Create: `modules/platforms/miaoshou/components/inventory_export.py`
- Modify: `modules/apps/collection_center/python_component_adapter.py`（在 Task 5 才改；本 Task 只创建类，不修改 adapter）
- Test: `backend/tests/test_miaoshou_inventory_export_contract.py`

**Interfaces:**
- Consumes: `ExecutionContext`、`InventorySelectors`、`MiaoshouNavigation`、`MiaoshouWarehouseFilters`
- Produces: `class MiaoshouInventoryExport(ExportComponent)`，字段 `platform="miaoshou"` / `component_type="export"` / `data_domain="inventory"`，构造 `__init__(ctx, selectors=None)`

- [ ] **Step 1: 重写 `backend/tests/test_miaoshou_inventory_export_contract.py`**

完整替换该文件：

```python
from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_export import MiaoshouInventoryExport
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com/login"},
        logger=None,
        config={},
    )


def test_miaoshou_inventory_config_uses_inventory_snapshot_semantics():
    selectors = InventorySelectors()

    assert selectors.checklist_path == "/warehouse/checklist"
    assert selectors.data_type_dir == "inventory"
    assert "正在导出" in selectors.progress_texts
    assert "商品信息" in selectors.group_titles
    assert "其他信息" in selectors.group_titles


def test_miaoshou_inventory_export_component_declares_inventory_domain():
    assert MiaoshouInventoryExport.platform == "miaoshou"
    assert MiaoshouInventoryExport.component_type == "export"
    assert MiaoshouInventoryExport.data_domain == "inventory"


def test_miaoshou_inventory_export_constructor_uses_inventory_selectors_by_default():
    component = MiaoshouInventoryExport(_ctx())
    assert isinstance(component.sel, InventorySelectors)


def test_miaoshou_inventory_export_constructor_accepts_custom_selectors():
    selectors = InventorySelectors()
    component = MiaoshouInventoryExport(_ctx(), selectors=selectors)
    assert component.sel is selectors


def test_miaoshou_inventory_export_source_reuses_navigation_without_opening_login():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.WAREHOUSE_CHECKLIST" in source
    assert "page.goto(login_url" not in source


def test_miaoshou_inventory_export_uses_warehouse_filters_for_scope_filter():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "MiaoshouWarehouseFilters" in source
    assert "warehouse_filters_component.run(page" in source


def test_miaoshou_inventory_export_does_not_use_keyboard_escape_for_popups():
    source = Path("modules/platforms/miaoshou/components/inventory_export.py").read_text(encoding="utf-8")

    assert "page.keyboard.press(\"Escape\")" not in source


def test_miaoshou_navigation_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx(), InventorySelectors())
    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_contract.py -v
```
Expected: `ModuleNotFoundError: No module named 'modules.platforms.miaoshou.components.inventory_export'`

- [ ] **Step 3: 实现 `inventory_export.py`**

```python
"""Miaoshou ERP 仓库清单 inventory 数据域导出组件（V2 canonical 独立精细类）

流程:
  navigation → 仓库全选 → 搜索 → 等待结果 → 导出菜单 → 字段全选 → 触发导出 → page.expect_download → 落盘
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.warehouse_filters import MiaoshouWarehouseFilters
from modules.utils.path_sanitizer import build_filename


class MiaoshouInventoryExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "inventory"

    def __init__(self, ctx: ExecutionContext, selectors: InventorySelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.warehouse_filters_component = MiaoshouWarehouseFilters(ctx, self.sel)

    async def _first_visible_selector(
        self, page: Any, selectors: tuple[str, ...], *, timeout: int = 1500
    ) -> Any | None:
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=timeout)
                return locator
            except Exception:
                continue
        return None

    async def _is_checkbox_selected(self, locator: Any) -> bool:
        try:
            if await locator.is_checked():
                return True
        except Exception:
            pass

        try:
            checked = await locator.evaluate(
                """el => {
                    const root = el.closest(
                        '[role="checkbox"], label, .ant-checkbox-wrapper, .arco-checkbox, .jx-checkbox, .el-checkbox'
                    ) || el;
                    return root.getAttribute('aria-checked') === 'true'
                        || root.className.includes('checked')
                        || !!root.querySelector('input[type="checkbox"]:checked');
                }"""
            )
            return bool(checked)
        except Exception:
            return False

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            try:
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def _click_search(self, page: Any) -> None:
        button = page.get_by_role("button", name="搜索").first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("SKU总数", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("库存总价值", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_role("button", name="导入/导出商品").first.wait_for(state="visible", timeout=15000)

    async def _export_dialog(self, page: Any) -> Any:
        candidates = [
            page.get_by_role("dialog").filter(has_text="选择导出字段").last,
            page.locator('.jx-overlay[style*="display: block"]').filter(has_text="选择导出字段").last,
            page.locator('.jx-dialog:visible').filter(has_text="选择导出字段").last,
        ]
        for dialog in candidates:
            try:
                await dialog.wait_for(state="visible", timeout=3000)
                return dialog
            except Exception:
                continue
        raise RuntimeError("选择导出字段弹窗不可见")

    async def _open_export_dialog(self, page: Any) -> None:
        button = page.get_by_role("button", name="导入/导出商品").first
        try:
            await button.wait_for(state="visible", timeout=3000)
        except Exception:
            button = await self._first_visible_selector(page, self.sel.open_export_menu, timeout=3000)
        if button is None:
            raise RuntimeError("导入/导出商品按钮不可见")
        await button.click(timeout=1500)

        menu_item = page.get_by_role("menuitem", name="导出搜索的商品").first
        try:
            await menu_item.wait_for(state="visible", timeout=3000)
        except Exception:
            menu_item = await self._first_visible_selector(page, self.sel.menu_export_searched, timeout=3000)
        if menu_item is None:
            raise RuntimeError("导出搜索的商品菜单项不可见")
        await menu_item.click(timeout=1500)

        await self._export_dialog(page)

    async def _ensure_group_check_all_selected(self, container: Any) -> None:
        full_select = container.get_by_role("checkbox", name="全选").first
        try:
            await full_select.wait_for(state="visible", timeout=1500)
        except Exception:
            full_select = container.locator("label:has-text('全选') input[type='checkbox']").first
            await full_select.wait_for(state="attached", timeout=1500)

        checked = await self._is_checkbox_selected(full_select)
        if not checked:
            try:
                await container.get_by_text("全选", exact=True).first.click(timeout=1000)
            except Exception:
                await full_select.click(timeout=1000)

    async def _ensure_export_fields_all_selected(self, page: Any) -> None:
        dialog = await self._export_dialog(page)
        await dialog.get_by_text("商品信息", exact=False).first.wait_for(state="visible", timeout=5000)
        await dialog.get_by_text("其他信息", exact=False).first.wait_for(state="visible", timeout=5000)

        checkboxes = dialog.get_by_role("checkbox", name="全选")
        count = await checkboxes.count()
        if count < 2:
            raise RuntimeError("导出字段全选复选框数量不足")

        await self._ensure_group_check_all_selected(dialog.locator("xpath=.").first)
        second_checkbox = checkboxes.nth(1)
        if not await self._is_checkbox_selected(second_checkbox):
            try:
                await second_checkbox.click(timeout=1000)
            except Exception:
                second_label = dialog.get_by_text("全选", exact=True).nth(1)
                await second_label.click(timeout=1000)

    async def _trigger_export(self, page: Any) -> None:
        dialog = await self._export_dialog(page)
        button = None
        for selector in self.sel.export_buttons:
            try:
                candidate = dialog.locator(selector).first
                await candidate.wait_for(state="visible", timeout=1000)
                button = candidate
                break
            except Exception:
                continue
        if button is None:
            button = dialog.get_by_role("button", name="导出").first
            await button.wait_for(state="visible", timeout=2000)
        await button.click(timeout=1500)

    async def _wait_export_progress_ready(self, page: Any) -> None:
        for text in self.sel.progress_texts:
            try:
                await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=3000)
                return
            except Exception:
                continue
        raise RuntimeError("未检测到导出进度提示")

    async def _wait_download_complete(self, page: Any, download: Any) -> Path:
        try:
            await self._wait_export_progress_ready(page)
        except Exception:
            pass

        out_root = build_standard_output_root(self.ctx, data_type="inventory", granularity="snapshot")
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = getattr(download, "suggested_filename", None) or "inventory_snapshot.xlsx"
        tmp_path = out_root / raw_name
        await download.save_as(str(tmp_path))

        if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
            raise RuntimeError("download file missing or empty")

        account = self.ctx.account or {}
        cfg = self.ctx.config or {}
        account_label = account.get("label") or account.get("store_name") or account.get("username") or "unknown"
        shop_name = cfg.get("shop_name") or account.get("store_name") or "unknown_shop"
        target = out_root / build_filename(
            ts=datetime.now().strftime("%Y%m%d_%H%M%S"),
            account_label=account_label,
            shop_name=shop_name,
            data_type="inventory",
            granularity="snapshot",
            suffix=tmp_path.suffix or ".xlsx",
        )
        try:
            tmp_path.rename(target)
        except Exception:
            if target != tmp_path:
                target.write_bytes(tmp_path.read_bytes())
                tmp_path.unlink(missing_ok=True)

        return target

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            nav_result = await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)
            if not nav_result.success:
                raise RuntimeError(nav_result.message or "navigation failed")

            await self._ensure_popup_closed(page)

            filter_result = await self.warehouse_filters_component.run(page, {"select_all": True})
            if not filter_result.success:
                raise RuntimeError(filter_result.message or "warehouse filters failed")

            await self._click_search(page)
            await self._wait_search_results_ready(page)
            await self._open_export_dialog(page)
            await self._ensure_export_fields_all_selected(page)

            async with page.expect_download(timeout=180000) as dl_info:
                await self._trigger_export(page)
            download = await dl_info.value

            target = await self._wait_download_complete(page, download)
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            return ExportResult(success=False, message=str(e), file_path=None)
```

- [ ] **Step 4: 跑 contract 测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_contract.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/inventory_export.py backend/tests/test_miaoshou_inventory_export_contract.py
git commit -m "feat(miaoshou): add MiaoshouInventoryExport canonical V2 component"
```

---

### Task 4: 写 inventory v2_flow 测试 + 注册到 DATA_DOMAIN_EXPORT_MAP

**Files:**
- Create: `backend/tests/test_miaoshou_inventory_export_v2_flow.py`
- Modify: `modules/apps/collection_center/python_component_adapter.py:284-286`（inventory 特判分支）

**Interfaces:**
- Consumes: 静态读 `modules/platforms/miaoshou/components/inventory_export.py` 源码
- Produces: v2_flow 测试 + adapter 修改

- [ ] **Step 1: 创建 `backend/tests/test_miaoshou_inventory_export_v2_flow.py`**

```python
from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/inventory_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_inventory_export_navigates_to_warehouse_after_login():
    source = _source()
    assert "await self.navigation_component.run(page, TargetPage.WAREHOUSE_CHECKLIST)" in source
    assert "page.goto(login_url" not in source


def test_inventory_export_applies_warehouse_scope_filter_before_search():
    source = _source()
    filter_index = source.index("await self.warehouse_filters_component.run(page")
    search_index = source.index("await self._click_search(page)")
    assert filter_index < search_index


def test_inventory_export_opens_export_dialog_and_selects_all_groups_before_export():
    source = _source()
    open_dialog = source.index("await self._open_export_dialog(page)")
    ensure_fields = source.index("await self._ensure_export_fields_all_selected(page)")
    trigger_export = source.index("await self._trigger_export(page)")
    assert open_dialog < ensure_fields < trigger_export


def test_inventory_export_treats_progress_as_intermediate_and_download_as_final_signal():
    source = _source()
    assert "await self._wait_export_progress_ready(page)" in source
    assert "async with page.expect_download(" in source
    assert "if not tmp_path.exists() or tmp_path.stat().st_size <= 0" in source


def test_inventory_export_uses_role_based_trigger_and_menuitem_for_export_dropdown():
    source = _source()
    assert 'page.get_by_role("button", name="导入/导出商品").first' in source
    assert 'page.get_by_role("menuitem", name="导出搜索的商品").first' in source


def test_inventory_export_uses_unified_popup_close_not_keyboard_escape():
    source = _source()
    assert "_ensure_popup_closed" in source
    assert 'page.keyboard.press("Escape")' not in source


def test_inventory_export_uses_build_standard_output_root_and_build_filename():
    source = _source()
    assert "build_standard_output_root(self.ctx, data_type=\"inventory\", granularity=\"snapshot\")" in source
    assert "build_filename(" in source
```

- [ ] **Step 2: 跑 v2_flow 测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_v2_flow.py -v
```
Expected: 7 passed

- [ ] **Step 3: 修改 `python_component_adapter.py`**

文件: `modules/apps/collection_center/python_component_adapter.py`

修改两处：

(1) `DATA_DOMAIN_EXPORT_MAP["miaoshou"]`（约 line 51-57）：

```python
"miaoshou": {
    "orders": "MiaoshouOrdersShopeeExport",
    "products": "MiaoshouExport",
    "warehouse": "MiaoshouExport",
    "inventory": "MiaoshouInventoryExport",
    "analytics": "MiaoshouExport",
},
```

(2) 删除 `export()` 方法内的 inventory 特判分支（约 line 284-286）：

```python
            elif self.platform == "miaoshou" and data_domain == "inventory":
                export_class_name = "MiaoshouInventorySnapshotExport"
                module_name = "inventory_snapshot_export"
```

替换为通用 mapping 路径（不需要单独处理，因为 `module_name = f"{data_domain}_export"` 已经得到 `inventory_export`，且 `export_class_name` 从 `DATA_DOMAIN_EXPORT_MAP` 取 `MiaoshouInventoryExport` 已正确）。

- [ ] **Step 4: 跑 inventory 全部测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_warehouse_filters_contract.py -v
```
Expected: 8 + 7 + 2 = 17 passed

- [ ] **Step 5: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/apps/collection_center/python_component_adapter.py backend/tests/test_miaoshou_inventory_export_v2_flow.py
git commit -m "feat(miaoshou): wire inventory export to canonical adapter and add v2_flow tests"
```

---

### Task 5: 归档旧 inventory 文件 + 更新 docs

**Files:**
- Move: `modules/platforms/miaoshou/components/inventory_snapshot_export.py` → `modules/platforms/miaoshou/archive/inventory_snapshot_export.py`
- Move: `modules/platforms/miaoshou/components/warehouse_config.py` → `modules/platforms/miaoshou/archive/warehouse_config.py`
- Modify: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`
- Modify: `docs/guides/CANONICAL_COMPONENT_STATUS.md`

- [ ] **Step 1: 确认 DB 中无 stable ComponentVersion 引用旧文件**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
grep -r "inventory_snapshot_export\|warehouse_config" backend/ modules/ docs/ 2>/dev/null | grep -v "__pycache__" | grep -v "archive/" | head -30
```
Expected: 只命中 `python_component_adapter.py` 的旧引用（Task 4 已删除）；若无其他主链路引用，可安全归档。

- [ ] **Step 2: git mv 归档旧文件**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
mkdir -p modules/platforms/miaoshou/archive
git mv modules/platforms/miaoshou/components/inventory_snapshot_export.py modules/platforms/miaoshou/archive/inventory_snapshot_export.py
git mv modules/platforms/miaoshou/components/warehouse_config.py modules/platforms/miaoshou/archive/warehouse_config.py
```

- [ ] **Step 3: 跑 inventory 测试确认归档后仍通过**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_warehouse_filters_contract.py -v
```
Expected: 17 passed（contract 测试的"in source"检查的是 `inventory_export.py`，归档不影响）

- [ ] **Step 4: 更新 `ACTIVE_COLLECTION_COMPONENTS.md`**

文件: `docs/guides/ACTIVE_COLLECTION_COMPONENTS.md`

在 "当前活跃组件" 列表（约 line 7-11）改为：

```markdown
## 当前活跃组件

当前已确认进入 V2 主链路的组件有：

- `miaoshou/login`
- `miaoshou/orders_export`
- `miaoshou/inventory_export`
- `miaoshou/purchase_export`
```

并在 "已进入 miaoshou/archive" 段（约 line 39-44）末尾追加：

```markdown
当前已进入 `modules/platforms/miaoshou/archive/` 的第三批文件：

- `inventory_snapshot_export.py`
- `warehouse_config.py`
```

- [ ] **Step 5: 更新 `CANONICAL_COMPONENT_STATUS.md`**

文件: `docs/guides/CANONICAL_COMPONENT_STATUS.md`

在 "妙手 Miaoshou" 表格（约 line 58-63）替换为：

```markdown
| `miaoshou/login` | 可测试 | 成功判定已修，不再停留 TODO 状态 |
| `miaoshou/navigation` | 可测试 | 当前可作为轻量前置组件 |
| `miaoshou/date_picker` | 可测试 | 可作为前置组件，但后续仍需真实页面收敛 |
| `miaoshou/export` | 继续修 | 已修数据域口径、download await、count 判断、context download 清理，但 dropdown/dialog/iframe 复合链路仍最复杂 |
| `miaoshou/inventory_export` | 可测试 | V2 canonical 独立精细类；warehouse_filters + 字段对话框；同步下载 |
| `miaoshou/purchase_export` | 可测试 | V2 canonical 独立精细类；异步导出 + 字段对话框 + 导出记录轮询 |

### 不应作为默认维护对象
- `modules/platforms/miaoshou/components/miaoshou_login.py`
- `modules/platforms/miaoshou/components/inventory_snapshot_export.py`
- `modules/platforms/miaoshou/components/warehouse_config.py`
- `modules/platforms/miaoshou/components/overlay_guard.py`
```

- [ ] **Step 6: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/archive/inventory_snapshot_export.py modules/platforms/miaoshou/archive/warehouse_config.py docs/guides/ACTIVE_COLLECTION_COMPONENTS.md docs/guides/CANONICAL_COMPONENT_STATUS.md
git commit -m "chore(miaoshou): archive old inventory_snapshot_export + warehouse_config; update docs"
```

> **Follow-up**: archive `warehouse_config.py` 时发现 `MiaoshouNavigation` 硬 import `WarehouseSelectors`。已在 Task 5 就地修复（inline `_DefaultNavSelectors` + `__init__` 拓宽签名 in Task 10），但 plan 未明确登记。建议作为 future plan 候选。

---

## Phase B：Purchase 新建

### Task 6: 新增 `TargetPage.PURCHASE` 枚举值 + 更新 navigation.py

**Files:**
- Modify: `modules/components/navigation/base.py`（新增 PURCHASE 枚举值）
- Modify: `modules/platforms/miaoshou/components/navigation.py`（新增 PURCHASE 分支 + selectors 类型扩展）

**Interfaces:**
- Consumes: `TargetPage` enum；`OrdersSelectors | WarehouseSelectors | PurchaseSelectors`
- Produces: `TargetPage.PURCHASE = "purchase"`；`MiaoshouNavigation.run()` 支持 PURCHASE 分支（菜单路径 `采购 → 商品采购 → 采购单`，URL `https://erp.91miaoshou.com/purchase/goods`，等待"采购单"标题）

- [ ] **Step 1: 修改 `TargetPage` 枚举**

文件: `modules/components/navigation/base.py`

在 `class TargetPage(str, Enum):` 内新增一行（约 line 14 后）：

```python
class TargetPage(str, Enum):
    PRODUCTS_PERFORMANCE = "products_performance"
    TRAFFIC_OVERVIEW = "traffic_overview"
    SERVICE_ANALYTICS = "service_analytics"
    ORDERS = "orders"
    FINANCE = "finance"
    WAREHOUSE_CHECKLIST = "warehouse_checklist"
    PURCHASE = "purchase"
```

- [ ] **Step 2: 修改 `navigation.py`**

文件: `modules/platforms/miaoshou/components/navigation.py`

完整替换为（**用 duck-typing 不强依赖 `PurchaseSelectors` 类**，Task 7 创建后自动接管）：

```python
from __future__ import annotations

from typing import Any

from modules.components.base import ExecutionContext
from modules.components.navigation.base import NavigationComponent, NavigationResult, TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


class MiaoshouNavigation(NavigationComponent):
    platform = "miaoshou"
    component_type = "navigation"
    data_domain = None

    def __init__(
        self,
        ctx: ExecutionContext,
        selectors: "OrdersSelectors | InventorySelectors | Any | None" = None,
    ) -> None:
        super().__init__(ctx)
        self.sel = selectors or InventorySelectors()

    def _orders_detail_url(self, subtype: str) -> str:
        subtype_norm = (subtype or "shopee").strip().lower()
        return f"{self.sel.base_url}{self.sel.deep_link_template.format(platform=subtype_norm)}"

    def _warehouse_checklist_url(self) -> str:
        return f"{self.sel.base_url}{self.sel.checklist_path}"

    def _purchase_goods_url(self) -> str:
        purchase_path = getattr(self.sel, "purchase_path", "/purchase/goods")
        base_url = getattr(self.sel, "base_url", InventorySelectors.base_url)
        return f"{base_url}{purchase_path}"

    async def run(self, page: Any, target: TargetPage) -> NavigationResult:  # type: ignore[override]
        if target is TargetPage.ORDERS:
            cfg = self.ctx.config or {}
            subtype = str(cfg.get("orders_subtype") or "shopee").strip().lower()
            await page.goto(
                self._orders_detail_url(subtype),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("利润明细", exact=False).first.wait_for(state="visible", timeout=15000)
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))

        if target is TargetPage.WAREHOUSE_CHECKLIST:
            await page.goto(
                self._warehouse_checklist_url(),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("仓库清单", exact=False).first.wait_for(state="visible", timeout=15000)
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))

        if target is TargetPage.PURCHASE:
            await page.goto(
                self._purchase_goods_url(),
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.get_by_text("采购单", exact=False).first.wait_for(state="visible", timeout=15000)
            await self.stabilize_safe_notices(page, label="post-navigation cleanup")
            return NavigationResult(success=True, message="ok", url=str(getattr(page, "url", "") or ""))

        return NavigationResult(success=False, message=f"unsupported target: {target}", url=str(getattr(page, "url", "") or ""))
```

- [ ] **Step 3: 验证导入 + 枚举值**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -c "from modules.components.navigation.base import TargetPage; print('PURCHASE:', TargetPage.PURCHASE.value)"
```
Expected: `PURCHASE: purchase`

- [ ] **Step 4: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/components/navigation/base.py modules/platforms/miaoshou/components/navigation.py
git commit -m "feat(miaoshou): add TargetPage.PURCHASE and navigation branch for purchase/goods"
```

---

### Task 7: 创建 `purchase_config.py`（PurchaseSelectors）

**Files:**
- Create: `modules/platforms/miaoshou/components/purchase_config.py`

**Interfaces:**
- Consumes: 无（独立模块）
- Produces: `class PurchaseSelectors` (frozen dataclass)，含 `base_url` / `purchase_path` / `status_tabs` / `filter_field_names` / `date_shortcuts` / `import_export_button_text` / `export_menu_items` / `export_field_groups` / `progress_dialog_title` / `progress_text` / `export_record_path` / `export_record_row_status_text` / `export_record_poll_interval_s` / `export_record_poll_timeout_s` / `export_buttons` / `popup_close_buttons` / `close_poll_max_rounds` / `close_poll_interval_ms` / `data_type_dir`

- [ ] **Step 1: 创建 `purchase_config.py`**

```python
"""
Miaoshou ERP purchase (采购单) component config

Centralizes selectors used by the async-export purchase flow.
Mirrors the orders_config / inventory_config convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Tuple

BASE_URL: Final[str] = "https://erp.91miaoshou.com"
PURCHASE_GOODS_PATH: Final[str] = "/purchase/goods"
PURCHASE_EXPORT_RECORD_PATH: Final[str] = "/purchase/export_record"

STATUS_TABS: Final[Tuple[str, ...]] = (
    "全部",
    "草稿箱",
    "待审核",
    "待收货",
    "已完成",
    "已取消/退货",
)

FILTER_FIELD_NAMES: Final[Tuple[str, ...]] = (
    "采购单号",
    "货源单号",
    "商品SKU",
    "中文名称",
    "收货仓库",
    "供货商",
    "有无物流单号",
    "备注",
    "采购员",
    "创建日期",
    "采购单类型",
    "关联包裹号",
)

DATE_SHORTCUTS: Final[Tuple[str, ...]] = (
    "今天",
    "昨天",
    "近7天",
    "近30天",
    "近90天",
)

CUSTOM_DATE_INPUT_NAMES: Final[Tuple[str, ...]] = (
    "开始时间",
    "结束时间",
)

IMPORT_EXPORT_BUTTON_TEXT: Final[str] = "导入/导出"

EXPORT_MENU_ITEMS: Final[Tuple[str, ...]] = (
    "导入采购单",
    "导出选中",
    "导出全部搜索结果",
    "导出记录",
)

EXPORT_FIELD_GROUPS: Final[Tuple[str, ...]] = (
    "采购单信息",
    "商品信息",
    "关联运单信息",
)

EXPORT_FIELD_GROUPS_FULL_SELECT_TEXT: Final[str] = "全选"

PROGRESS_DIALOG_TITLE: Final[str] = "正在导出"

PROGRESS_TEXT_VARIANTS: Final[Tuple[str, ...]] = (
    "正在导出包裹",
    "正在导出",
    "生成中",
    "处理中",
    "排队中",
)

EXPORT_RECORD_ROW_READY_TEXTS: Final[Tuple[str, ...]] = (
    "导出成功",
    "可下载",
    "下载",
)

EXPORT_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "导出",
    "确定导出",
)

CANCEL_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "取消",
)

CLOSE_BTN_TEXTS: Final[Tuple[str, ...]] = (
    "关闭",
    "我知道了",
)

EXPORT_RECORD_POLL_INTERVAL_S: Final[int] = 5
EXPORT_RECORD_POLL_TIMEOUT_S: Final[int] = 300

POPUP_CLOSE_SELECTORS: Final[Tuple[str, ...]] = (
    ".ant-modal-close",
    ".ant-modal-wrap .ant-modal-close",
    ".ant-drawer-close",
    ".ant-notification-notice-close",
    ".ant-popover .ant-popover-close",
    "button[aria-label='关闭此对话框']",
    ".jx-dialog__headerbtn",
    ".jx-dialog__close",
    ".notice-message-box-dialog .jx-dialog__headerbtn",
    ".notice-message-box-dialog footer .pro-button",
    "button:has-text(我知道了)",
    "button:has-text(知道了)",
    "button:has-text(关闭)",
    "button:has-text(确认)",
    "button:has-text(确定)",
    "button:has-text(取消)",
    "button:has-text(OK)",
)

CLOSE_POLL_MAX_ROUNDS: Final[int] = 20
CLOSE_POLL_INTERVAL_MS: Final[int] = 300

DATA_TYPE_DIR: Final[str] = "purchase"


@dataclass(frozen=True)
class PurchaseSelectors:
    base_url: str = BASE_URL
    purchase_path: str = PURCHASE_GOODS_PATH
    export_record_path: str = PURCHASE_EXPORT_RECORD_PATH
    status_tabs: Tuple[str, ...] = STATUS_TABS
    filter_field_names: Tuple[str, ...] = FILTER_FIELD_NAMES
    date_shortcuts: Tuple[str, ...] = DATE_SHORTCUTS
    custom_date_input_names: Tuple[str, ...] = CUSTOM_DATE_INPUT_NAMES
    import_export_button_text: str = IMPORT_EXPORT_BUTTON_TEXT
    export_menu_items: Tuple[str, ...] = EXPORT_MENU_ITEMS
    export_field_groups: Tuple[str, ...] = EXPORT_FIELD_GROUPS
    export_field_groups_full_select_text: str = EXPORT_FIELD_GROUPS_FULL_SELECT_TEXT
    progress_dialog_title: str = PROGRESS_DIALOG_TITLE
    progress_text_variants: Tuple[str, ...] = PROGRESS_TEXT_VARIANTS
    export_record_row_ready_texts: Tuple[str, ...] = EXPORT_RECORD_ROW_READY_TEXTS
    export_btn_texts: Tuple[str, ...] = EXPORT_BTN_TEXTS
    cancel_btn_texts: Tuple[str, ...] = CANCEL_BTN_TEXTS
    close_btn_texts: Tuple[str, ...] = CLOSE_BTN_TEXTS
    export_record_poll_interval_s: int = EXPORT_RECORD_POLL_INTERVAL_S
    export_record_poll_timeout_s: int = EXPORT_RECORD_POLL_TIMEOUT_S
    popup_close_buttons: Tuple[str, ...] = POPUP_CLOSE_SELECTORS
    close_poll_max_rounds: int = CLOSE_POLL_MAX_ROUNDS
    close_poll_interval_ms: int = CLOSE_POLL_INTERVAL_MS
    data_type_dir: str = DATA_TYPE_DIR
```

- [ ] **Step 2: 验证导入成功**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -c "from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors; s=PurchaseSelectors(); print(s.base_url, s.purchase_path); assert s.purchase_path == '/purchase/goods'; assert '导出全部搜索结果' in s.export_menu_items; assert '采购单信息' in s.export_field_groups; assert '近30天' in s.date_shortcuts; assert s.data_type_dir == 'purchase'"
```
Expected: `https://erp.91miaoshou.com /purchase/goods`（无 AssertionError）

- [ ] **Step 3: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/purchase_config.py
git commit -m "feat(miaoshou): add purchase_config with PurchaseSelectors dataclass"
```

---

### Task 8: 创建 `purchase_export.py`（MiaoshouPurchaseExport）+ contract 测试

**Files:**
- Create: `modules/platforms/miaoshou/components/purchase_export.py`
- Test: `backend/tests/test_miaoshou_purchase_export_contract.py`

**Interfaces:**
- Consumes: `ExecutionContext`、`PurchaseSelectors`、`MiaoshouNavigation`、`MiaoshouDatePicker`、`OrdersSelectors`（复用 date_picker）
- Produces: `class MiaoshouPurchaseExport(ExportComponent)`，字段 `platform="miaoshou"` / `component_type="export"` / `data_domain="purchase"`，含异步子流程 `_trigger_async_export_and_download()`

- [ ] **Step 1: 创建 `backend/tests/test_miaoshou_purchase_export_contract.py`**

```python
from pathlib import Path

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
from modules.platforms.miaoshou.components.purchase_export import MiaoshouPurchaseExport


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com/login"},
        logger=None,
        config={},
    )


def test_miaoshou_purchase_config_uses_purchase_goods_semantics():
    selectors = PurchaseSelectors()

    assert selectors.purchase_path == "/purchase/goods"
    assert selectors.export_record_path == "/purchase/export_record"
    assert selectors.data_type_dir == "purchase"
    assert "导出全部搜索结果" in selectors.export_menu_items
    assert "采购单信息" in selectors.export_field_groups
    assert "商品信息" in selectors.export_field_groups
    assert "关联运单信息" in selectors.export_field_groups
    assert selectors.export_record_poll_timeout_s == 300
    assert selectors.export_record_poll_interval_s == 5


def test_miaoshou_purchase_export_component_declares_purchase_domain():
    assert MiaoshouPurchaseExport.platform == "miaoshou"
    assert MiaoshouPurchaseExport.component_type == "export"
    assert MiaoshouPurchaseExport.data_domain == "purchase"


def test_miaoshou_purchase_export_constructor_uses_purchase_selectors_by_default():
    component = MiaoshouPurchaseExport(_ctx())
    assert isinstance(component.sel, PurchaseSelectors)


def test_miaoshou_purchase_export_constructor_accepts_custom_selectors():
    selectors = PurchaseSelectors()
    component = MiaoshouPurchaseExport(_ctx(), selectors=selectors)
    assert component.sel is selectors


def test_miaoshou_purchase_export_source_reuses_navigation_with_purchase_target():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "MiaoshouNavigation" in source
    assert "TargetPage.PURCHASE" in source
    assert "page.goto(login_url" not in source


def test_miaoshou_purchase_export_source_uses_async_export_subroutine():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "async def _trigger_async_export_and_download(" in source
    assert "_poll_export_record_until_ready" in source or "_poll_export_record" in source
    assert "async with page.expect_download(" in source


def test_miaoshou_purchase_export_does_not_use_keyboard_escape_for_popups():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "page.keyboard.press(\"Escape\")" not in source


def test_miaoshou_purchase_export_uses_build_standard_output_root_and_build_filename():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "build_standard_output_root(self.ctx, data_type=\"purchase\", granularity=\"manual\")" in source
    assert "build_filename(" in source


def test_miaoshou_purchase_export_reuses_miaoshou_date_picker_for_create_date():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert "MiaoshouDatePicker" in source


def test_miaoshou_purchase_export_uses_role_based_trigger_for_export_dropdown():
    source = Path("modules/platforms/miaoshou/components/purchase_export.py").read_text(encoding="utf-8")

    assert 'page.get_by_role("button", name="导入/导出")' in source
    assert 'page.get_by_role("menuitem", name="导出全部搜索结果")' in source
```

- [ ] **Step 2: 跑测试确认失败**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_purchase_export_contract.py -v
```
Expected: `ModuleNotFoundError: No module named 'modules.platforms.miaoshou.components.purchase_export'`

- [ ] **Step 3: 实现 `purchase_export.py`**

```python
"""Miaoshou ERP 采购单 purchase 数据域导出组件（V2 canonical 独立精细类）

异步导出流程:
  1. 导航到 /purchase/goods
  2. 选择状态 Tab（默认"全部"）+ 设置创建日期（MiaoshouDatePicker）
  3. 搜索 + 等待结果就绪
  4. 点击"导入/导出" → 下拉菜单 → "导出全部搜索结果"
  5. 字段选择对话框：三组字段全选
  6. 点击"导出" → 关闭"正在导出"进度弹窗
  7. 导航到 /purchase/export_record
  8. 轮询最新记录直到状态变为"可下载/导出成功"
  9. 点击"下载"链接 → page.expect_download → 落盘
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from modules.components.base import ExecutionContext
from modules.components.date_picker.base import DateOption
from modules.components.export.base import ExportComponent, ExportMode, ExportResult, build_standard_output_root
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.date_picker import MiaoshouCustomDateRange, MiaoshouDatePicker
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.purchase_config import PurchaseSelectors
from modules.utils.path_sanitizer import build_filename


class MiaoshouPurchaseExport(ExportComponent):
    platform = "miaoshou"
    component_type = "export"
    data_domain = "purchase"

    def __init__(self, ctx: ExecutionContext, selectors: PurchaseSelectors | None = None) -> None:
        super().__init__(ctx)
        self.sel = selectors or PurchaseSelectors()
        self.navigation_component = MiaoshouNavigation(ctx, self.sel)
        self.date_picker_component = MiaoshouDatePicker(ctx, OrdersSelectors())

    async def _ensure_popup_closed(self, page: Any) -> None:
        for _ in range(self.sel.close_poll_max_rounds):
            closed_any = False
            for selector in self.sel.popup_close_buttons:
                try:
                    locator = page.locator(selector).first
                    if await locator.count() > 0 and await locator.is_visible():
                        await locator.click(timeout=500)
                        closed_any = True
                except Exception:
                    continue
            if not closed_any:
                break
            try:
                await page.wait_for_timeout(self.sel.close_poll_interval_ms)
            except Exception:
                continue

    async def _click_search(self, page: Any) -> None:
        button = page.get_by_role("button", name="搜索").first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _wait_search_results_ready(self, page: Any) -> None:
        await page.get_by_text("采购单信息", exact=False).first.wait_for(state="visible", timeout=15000)
        await page.get_by_text("商品信息", exact=False).first.wait_for(state="visible", timeout=15000)

    async def _select_status_tab(self, page: Any, tab_name: str = "全部") -> None:
        try:
            tab = page.get_by_role("tab", name=tab_name).first
            await tab.click(timeout=2000)
        except Exception:
            label = page.get_by_text(re.compile(rf"^{re.escape(tab_name)}\s*\(\d+\)$")).first
            await label.click(timeout=2000)

    async def _open_import_export_dropdown(self, page: Any) -> None:
        button = page.get_by_role("button", name=self.sel.import_export_button_text).first
        await button.wait_for(state="visible", timeout=10000)
        await button.click(timeout=1500)

    async def _click_export_all_results(self, page: Any) -> None:
        menu_item = page.get_by_role("menuitem", name="导出全部搜索结果").first
        await menu_item.wait_for(state="visible", timeout=10000)
        await menu_item.click(timeout=1500)

    async def _field_dialog(self, page: Any) -> Any:
        dialog = page.get_by_role("dialog").filter(has_text="选择导出字段").last
        await dialog.wait_for(state="visible", timeout=10000)
        return dialog

    async def _select_all_export_fields(self, page: Any) -> None:
        dialog = await self._field_dialog(page)
        for group_name in self.sel.export_field_groups:
            try:
                group_root = dialog.get_by_text(group_name, exact=True).first
                await group_root.wait_for(state="visible", timeout=3000)
                full_select = group_root.locator(
                    "xpath=ancestor::*[1]"
                ).get_by_role("checkbox", name=self.sel.export_field_groups_full_select_text).first
                await full_select.wait_for(state="visible", timeout=2000)
                checked = await full_select.is_checked()
                if not checked:
                    try:
                        await group_root.locator(
                            "xpath=ancestor::*[1]"
                        ).get_by_text(self.sel.export_field_groups_full_select_text, exact=True).first.click(timeout=1000)
                    except Exception:
                        await full_select.click(timeout=1000)
            except Exception:
                continue

    async def _click_export_button_in_dialog(self, page: Any) -> None:
        dialog = await self._field_dialog(page)
        button = dialog.get_by_role("button", name="导出").last
        await button.wait_for(state="visible", timeout=5000)
        await button.click(timeout=1500)

    async def _close_progress_dialog(self, page: Any) -> None:
        try:
            title = page.get_by_role("heading", name=self.sel.progress_dialog_title).first
            await title.wait_for(state="visible", timeout=10000)
        except Exception:
            return

        for close_text in self.sel.close_btn_texts:
            try:
                close_button = page.get_by_role("button", name=close_text).first
                await close_button.wait_for(state="visible", timeout=2000)
                await close_button.click(timeout=1000)
                return
            except Exception:
                continue

    async def _navigate_to_export_record(self, page: Any) -> None:
        await page.goto(
            f"{self.sel.base_url}{self.sel.export_record_path}",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await page.get_by_text("导出记录", exact=False).first.wait_for(state="visible", timeout=15000)
        await self.stabilize_safe_notices(page, label="export-record nav cleanup")

    async def _poll_export_record_until_ready(self, page: Any) -> None:
        import asyncio

        deadline_s = self.sel.export_record_poll_timeout_s
        interval_s = self.sel.export_record_poll_interval_s
        elapsed = 0
        while elapsed < deadline_s:
            try:
                first_row = page.locator("table tbody tr").first
                if await first_row.count() > 0 and await first_row.is_visible():
                    row_text = " ".join(((await first_row.text_content()) or "").split())
                    if any(token in row_text for token in self.sel.export_record_row_ready_texts):
                        return
            except Exception:
                pass

            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            await asyncio.sleep(interval_s)
            elapsed += interval_s

        raise RuntimeError(
            f"导出记录轮询超时（{deadline_s}s），未检测到可下载状态"
        )

    async def _click_download_in_export_record(self, page: Any) -> None:
        first_row = page.locator("table tbody tr").first
        download_link = first_row.get_by_role("link", name=re.compile(r"下载")).first
        try:
            await download_link.wait_for(state="visible", timeout=5000)
        except Exception:
            download_link = first_row.get_by_role("button", name=re.compile(r"下载")).first
            await download_link.wait_for(state="visible", timeout=5000)

    async def _trigger_async_export_and_download(self, page: Any) -> Path:
        await self._open_import_export_dropdown(page)
        await self._click_export_all_results(page)
        await self._select_all_export_fields(page)
        await self._click_export_button_in_dialog(page)
        await self._close_progress_dialog(page)
        await self._navigate_to_export_record(page)
        await self._poll_export_record_until_ready(page)

        async with page.expect_download(timeout=180000) as dl_info:
            await self._click_download_in_export_record(page)
        download = await dl_info.value

        out_root = build_standard_output_root(self.ctx, data_type="purchase", granularity="manual")
        out_root.mkdir(parents=True, exist_ok=True)

        raw_name = getattr(download, "suggested_filename", None) or "purchase.xlsx"
        tmp_path = out_root / raw_name
        await download.save_as(str(tmp_path))

        if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
            raise RuntimeError("download file missing or empty")

        account = self.ctx.account or {}
        cfg = self.ctx.config or {}
        account_label = account.get("label") or account.get("store_name") or account.get("username") or "unknown"
        shop_name = cfg.get("shop_name") or account.get("store_name") or "unknown_shop"
        target = out_root / build_filename(
            ts=datetime.now().strftime("%Y%m%d_%H%M%S"),
            account_label=account_label,
            shop_name=shop_name,
            data_type="purchase",
            granularity="manual",
            start_date=cfg.get("start_date"),
            end_date=cfg.get("end_date"),
            suffix=tmp_path.suffix or ".xlsx",
        )
        try:
            tmp_path.rename(target)
        except Exception:
            if target != tmp_path:
                target.write_bytes(tmp_path.read_bytes())
                tmp_path.unlink(missing_ok=True)

        return target

    async def run(self, page: Any, mode: ExportMode = ExportMode.STANDARD) -> ExportResult:  # type: ignore[override]
        try:
            cfg = self.ctx.config or {}
            time_selection = cfg.get("time_selection") or {}
            time_mode = str(time_selection.get("mode") or "").strip().lower()
            date_preset = str(time_selection.get("preset") or "").strip()
            custom_range = cfg.get("custom_date_range")

            nav_result = await self.navigation_component.run(page, TargetPage.PURCHASE)
            if not nav_result.success:
                raise RuntimeError(nav_result.message or "navigation failed")

            await self.stabilize_safe_notices(page, label="before-first-action cleanup")
            await self._ensure_popup_closed(page)

            await self._select_status_tab(page, "全部")

            if custom_range:
                date_result = await self.date_picker_component.apply_custom_range(
                    page,
                    MiaoshouCustomDateRange(
                        start_date=str(custom_range.get("start_date")),
                        end_date=str(custom_range.get("end_date")),
                        start_time=str(custom_range.get("start_time", "00:00:00")),
                        end_time=str(custom_range.get("end_time", "23:59:59")),
                    ),
                )
            elif date_preset:
                preset_map = {
                    "今天": DateOption.TODAY_REALTIME,
                    "昨天": DateOption.YESTERDAY,
                    "近7天": DateOption.LAST_7_DAYS,
                    "近30天": DateOption.LAST_30_DAYS,
                    "近90天": DateOption.LAST_30_DAYS,
                }
                option = preset_map.get(date_preset, DateOption.LAST_30_DAYS)
                date_result = await self.date_picker_component.run(page, option)
            else:
                date_result = None

            if date_result is not None and not date_result.success:
                raise RuntimeError(date_result.message or "date picker failed")

            await self._click_search(page)
            await self._wait_search_results_ready(page)

            target = await self._trigger_async_export_and_download(page)
            return ExportResult(success=True, message="download complete", file_path=str(target))
        except Exception as e:
            return ExportResult(success=False, message=str(e), file_path=None)
```

- [ ] **Step 4: 跑 contract 测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_purchase_export_contract.py -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/purchase_export.py backend/tests/test_miaoshou_purchase_export_contract.py
git commit -m "feat(miaoshou): add MiaoshouPurchaseExport canonical V2 component with async polling"
```

---

### Task 9: 写 purchase v2_flow 测试 + 注册到 DATA_DOMAIN_EXPORT_MAP

**Files:**
- Create: `backend/tests/test_miaoshou_purchase_export_v2_flow.py`
- Modify: `modules/apps/collection_center/python_component_adapter.py:51-57`（DATA_DOMAIN_EXPORT_MAP miaoshou 段）

- [ ] **Step 1: 创建 `backend/tests/test_miaoshou_purchase_export_v2_flow.py`**

```python
from pathlib import Path


SOURCE_PATH = Path("modules/platforms/miaoshou/components/purchase_export.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_purchase_export_navigates_to_purchase_goods_in_run_flow():
    source = _source()
    assert "await self.navigation_component.run(page, TargetPage.PURCHASE)" in source
    assert "page.goto(login_url" not in source


def test_purchase_export_searches_before_triggering_async_export():
    source = _source()
    search_index = source.index("await self._click_search(page)")
    wait_index = source.index("await self._wait_search_results_ready(page)")
    trigger_index = source.index("await self._trigger_async_export_and_download(page)")
    assert search_index < wait_index < trigger_index


def test_purchase_export_triggers_export_then_polls_export_record_then_downloads():
    source = _source()

    open_dropdown = source.index("await self._open_import_export_dropdown(page)")
    select_all_results = source.index("await self._click_export_all_results(page)")
    close_progress = source.index("await self._close_progress_dialog(page)")
    nav_record = source.index("await self._navigate_to_export_record(page)")
    poll_record = source.index("await self._poll_export_record_until_ready(page)")
    expect_download = source.index("async with page.expect_download(")

    assert open_dropdown < select_all_results < close_progress < nav_record < poll_record < expect_download


def test_purchase_export_uses_miaoshou_date_picker_for_create_date():
    source = _source()
    assert "MiaoshouDatePicker" in source
    assert "apply_custom_range(" in source
    assert "MiaoshouCustomDateRange(" in source


def test_purchase_export_polls_export_record_with_timeout_and_interval():
    source = _source()
    assert "export_record_poll_timeout_s" in source
    assert "export_record_poll_interval_s" in source
    assert "await asyncio.sleep(interval_s)" in source


def test_purchase_export_uses_role_based_trigger_for_import_export_dropdown():
    source = _source()
    assert 'page.get_by_role("button", name="导入/导出")' in source
    assert 'page.get_by_role("menuitem", name="导出全部搜索结果")' in source


def test_purchase_export_uses_unified_popup_close_not_keyboard_escape():
    source = _source()
    assert "_ensure_popup_closed" in source
    assert 'page.keyboard.press("Escape")' not in source


def test_purchase_export_uses_build_standard_output_root_and_build_filename():
    source = _source()
    assert "build_standard_output_root(self.ctx, data_type=\"purchase\", granularity=\"manual\")" in source
    assert "build_filename(" in source
```

- [ ] **Step 2: 跑 v2_flow 测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_purchase_export_v2_flow.py -v
```
Expected: 8 passed

- [ ] **Step 3: 修改 `python_component_adapter.py` 注册 purchase**

文件: `modules/apps/collection_center/python_component_adapter.py`

`DATA_DOMAIN_EXPORT_MAP["miaoshou"]`（约 line 51-57）改为：

```python
    "miaoshou": {
        "orders": "MiaoshouOrdersShopeeExport",
        "products": "MiaoshouExport",
        "warehouse": "MiaoshouExport",
        "inventory": "MiaoshouInventoryExport",
        "purchase": "MiaoshouPurchaseExport",
        "analytics": "MiaoshouExport",
    },
```

- [ ] **Step 4: 跑 purchase 全部测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py -v
```
Expected: 9 + 8 = 17 passed

- [ ] **Step 5: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add backend/tests/test_miaoshou_purchase_export_v2_flow.py modules/apps/collection_center/python_component_adapter.py
git commit -m "feat(miaoshou): wire purchase export to canonical adapter and add v2_flow tests"
```

---

## Phase C：验证

### Task 10: 全套验证（ruff / mypy / pytest）

**Files:** 无（只跑命令）

- [ ] **Step 1: ruff lint**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m ruff check modules/platforms/miaoshou/components/ backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py backend/tests/test_miaoshou_warehouse_filters_contract.py
```
Expected: 无错误（最多 warning）

- [ ] **Step 2: mypy 类型检查（仅新文件）**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m mypy modules/platforms/miaoshou/components/inventory_config.py modules/platforms/miaoshou/components/inventory_export.py modules/platforms/miaoshou/components/warehouse_filters.py modules/platforms/miaoshou/components/purchase_config.py modules/platforms/miaoshou/components/purchase_export.py modules/platforms/miaoshou/components/navigation.py modules/components/navigation/base.py
```
Expected: 无错误

- [ ] **Step 3: 跑全部 miaoshou 测试**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py backend/tests/test_miaoshou_warehouse_filters_contract.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py -v
```
Expected: 8 + 7 + 9 + 8 + 2 + orders 测试数 = 全部 passed

- [ ] **Step 4: 提交（若 Step 1-3 全部通过则无需 commit；若有 fix 则单独 commit）**

如需修复：
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add -u
git commit -m "chore: fix lint/types from full validation pass"
```

---

## Self-Review

### Spec coverage 检查

| Spec 段落 | 对应 Task |
|---|---|
| §1. 决策（风格、数据域命名、inventory 处理、purchase 处理、复用策略、注册位置、文档更新） | Task 1-9（全部） |
| §2. inventory 改动清单（新建/修改/archive/测试） | Task 1, 2, 3, 4, 5 |
| §3. purchase 新建清单（evidence / 新建 / 修改 / 测试 / 异步流程） | Task 6, 7, 8, 9（异步子流程见 purchase_export.py `_trigger_async_export_and_download`） |
| §4. 公共组件复用矩阵 | Task 1-9 全部满足（inventory 用 `MiaoshouWarehouseFilters`，purchase 用 `MiaoshouDatePicker`，两者都用 `MiaoshouNavigation`） |
| §5. 数据流 | Task 3（inventory）和 Task 8（purchase）实现 |
| §6. 错误处理（try/except、`_ensure_popup_closed`、不重试、不 `Escape`） | 全部 Task 已包含 |
| §7. 测试策略（contract + v2_flow） | Task 1-9 已写 |
| §8. 落地步骤 | Task 顺序与 §8 Phase 一致 |
| §9. 风险与缓解 | Task 6 处理 `TargetPage.PURCHASE`；Task 4-5 处理 inventory 旧引用；Task 7-9 处理异步导出轮询超时（默认 300s） |
| §10. 验收标准 | Task 10 验证 |

### Placeholder 扫描

✅ 无 TBD / TODO / "implement later" / "fill in details"
✅ 无 "Add appropriate error handling"（已在每个 try/except 中具体化）
✅ 无 "Similar to Task N" 重复
✅ 每个代码 step 都有完整代码块

### Type 一致性

- `PurchaseSelectors.purchase_path` → Task 6 `navigation.py` 的 `_purchase_goods_url()` 使用 `self.sel.purchase_path` ✅
- `MiaoshouInventoryExport.data_domain = "inventory"` → adapter 映射 `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["inventory"] = "MiaoshouInventoryExport"` ✅
- `MiaoshouPurchaseExport.data_domain = "purchase"` → adapter 映射 `DATA_DOMAIN_EXPORT_MAP["miaoshou"]["purchase"] = "MiaoshouPurchaseExport"` ✅
- `MiaoshouPurchaseExport._trigger_async_export_and_download()` → v2_flow 测试 `test_purchase_export_triggers_export_then_polls_export_record_then_downloads` 引用同名 ✅
- `build_standard_output_root(self.ctx, data_type="inventory", granularity="snapshot")` ↔ `data_type="purchase", granularity="manual"` 与 v2_flow 测试断言一致 ✅

无 type/name 不一致问题。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-13-miaoshou-purchase-inventory-export.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** - 我为每个 Task 分发独立子代理，在 Task 之间做两阶段审阅（实现审阅 + 测试验证）
2. **Inline Execution** - 在当前会话中顺序执行所有 Task，每完成一个 Phase 做 checkpoint 让你审阅

你偏好哪种方式？