# Miaoshou DatePicker Trigger Fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复妙手采购数据域 `MiaoshouPurchaseExport` 跑不通的问题 —— `MiaoshouDatePicker._open()` 的 trigger fallback 缺少"创建日期 / 创建时间"标签，导致采购页面（标签为"创建日期"）无法打开日期控件。同时修正 `purchase_config.CUSTOM_DATE_INPUT_NAMES` 反映真实 DOM 标签，并加一个 mock-page contract 测试防回归。

**Architecture:**
- 在 `MiaoshouDatePicker._open()` 的 fallback 链中加入"创建日期" / "创建时间"（覆盖妙手未来新增数据域的同类标签）。
- 在 `MiaoshouDatePicker._wait_ready()` 的 `_matches_expected_display` 检查中（`apply_custom_range` 路径使用的 combobox 名称）扩展为兼容妙手所有已知标签：开始时间 / 结束时间 / 创建日期 / 创建时间。
- 修正 `purchase_config.CUSTOM_DATE_INPUT_NAMES` 为 `("创建日期", "创建时间")`，让 `apply_custom_range` 的 `fill_input_by_name` 路径能正确填充。
- 新增 contract 测试：mock page 对象（MagicMock）验证 `_open()` fallback 在不同标签下走不同分支。

**Tech Stack:** Python (asyncio, Playwright page abstraction), pytest。

## Global Constraints

- **不破坏 orders**：orders 页面"下单时间"作为现有 fallback 继续工作；测试必须覆盖此兼容路径。
- **不破坏 inventory**：inventory 不调用 date_picker，本次不需改 inventory_export。
- **TDD 严格**：先写 mock-page contract 测试 RED，再实现，再 GREEN。
- **使用 mock 而非真 Playwright**：项目结构是 canonical V2 组件，运行时依赖 ExecutionContext + Playwright page；测试通过 MagicMock 模拟 page 行为。
- **不引入 emoji / 不使用 `datetime.utcnow()` / 不使用 `page.keyboard.press("Escape")`**（架构惯例）。
- **pre-existing 改动不动**：当前 working tree 中 6 modified + 3 untracked（product_category 范畴）保持现状。

---

### Task 1: 拓展 date_picker._open() fallback + 修正 purchase_config + 加 contract test

**Files:**
- Modify: `modules/platforms/miaoshou/components/date_picker.py:29-42`（`_open` 的 trigger fallback）
- Modify: `modules/platforms/miaoshou/components/date_picker.py:171-184`（`_wait_custom_range_applied` 的 combobox 读取需支持"创建日期"）
- Modify: `modules/platforms/miaoshou/components/purchase_config.py:48-51`（`CUSTOM_DATE_INPUT_NAMES`）
- Create: `backend/tests/test_miaoshou_date_picker_trigger_fallback.py`

**Interfaces:**
- Consumes: Playwright `page.get_by_role("combobox", name=...)` 与 `page.get_by_text(...)` locator API（mock）。
- Produces: `_open()` 的 trigger 解析函数支持 4 个标签：开始时间 / 结束时间 / 创建日期 / 创建时间；`_wait_custom_range_applied` 同步支持。

- [ ] **Step 1: 写 mock-page contract 测试（RED）**

```python
"""
MiaoshouDatePicker trigger fallback 契约测试
（feat/miaoshou-date-picker-trigger-fallback 配套）

验证 _open() 在不同妙手页面标签下走不同 fallback 路径，并修复后能在采购
页面（"创建日期"）上正常工作。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.platforms.miaoshou.components.date_picker import MiaoshouDatePicker
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors


def _make_page(triggers: dict):
    """triggers: {"combobox:开始时间": locator, "combobox:结束时间": locator,
                   "combobox:创建日期": locator, "combobox:创建时间": locator,
                   "text:下单时间": locator, "text:创建日期": locator}

    locator 支持 .click(timeout=...) 与 .wait_for(state="visible", timeout=...) async API。
    """
    page = MagicMock()
    page.get_by_role = MagicMock(side_effect=lambda role, name=None: (
        triggers.get(f"{role}:{name}") or MagicMock()
    ))
    page.get_by_text = MagicMock(side_effect=lambda text, exact=False: (
        triggers.get(f"text:{text}") or MagicMock()
    ))
    page.locator = MagicMock(side_effect=lambda selector: MagicMock())
    page.wait_for_timeout = AsyncMock()
    return page


def _clickable_locator():
    """返回一个 mock locator，count()==1, is_visible()==True, click/wait_for 都不抛异常"""
    locator = MagicMock()
    locator.count = AsyncMock(return_value=1)
    locator.is_visible = AsyncMock(return_value=True)
    locator.wait_for = AsyncMock(return_value=None)
    locator.click = AsyncMock(return_value=None)
    locator.input_value = AsyncMock(return_value="")
    locator.text_content = AsyncMock(return_value="")
    return locator


@pytest.mark.asyncio
async def test_date_picker_open_prefers_combobox_start_time_when_available():
    """向后兼容：orders 页面"开始时间"combobox 仍走第一优先路径"""
    start_locator = _clickable_locator()
    page = _make_page({"combobox:开始时间": start_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    start_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_create_date_text():
    """采购页面无"开始时间" combobox，但有"创建日期"文本，应走 fallback 打开"""
    create_date_locator = _clickable_locator()
    page = _make_page({"text:创建日期": create_date_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    create_date_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_create_time_text():
    """'创建时间' 也是合法 fallback"""
    create_time_locator = _clickable_locator()
    page = _make_page({"text:创建时间": create_time_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    create_time_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_falls_back_to_order_time_text():
    """保留 orders 页面 fallback（"下单时间"）"""
    order_time_locator = _clickable_locator()
    page = _make_page({"text:下单时间": order_time_locator})
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    await dp._open(page)
    order_time_locator.click.assert_called()


@pytest.mark.asyncio
async def test_date_picker_open_raises_when_no_known_trigger():
    """如果 4 个标签都不在页面上，应抛 RuntimeError 而不是无声失败"""
    page = _make_page({})  # 所有 locator 都不存在（count=0）
    dp = MiaoshouDatePicker(ctx=MagicMock(), selectors=OrdersSelectors())
    with pytest.raises(RuntimeError):
        await dp._open(page)
```

- [ ] **Step 2: 跑测试确认 RED**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_date_picker_trigger_fallback.py -v
```
Expected: 5 failed（fallback 链未含"创建日期" / "创建时间"，以及无 trigger 时不抛错）。

- [ ] **Step 3: 实现 date_picker._open() fallback 扩展**

`modules/platforms/miaoshou/components/date_picker.py` line 29-42 改为：

```python
async def _open(self, page: Any) -> None:
    trigger = None
    # 第一优先：标准 combobox（"开始时间" / "结束时间"）—— orders 页面
    for name in ("开始时间", "结束时间"):
        try:
            candidate = page.get_by_role("combobox", name=name).first
            await candidate.click(timeout=1500)
            trigger = candidate
            break
        except Exception:
            continue
    if trigger is None:
        # 第二优先：文本标签 —— 覆盖所有妙手已知数据域
        # - "下单时间"：orders
        # - "创建日期" / "创建时间"：purchase（采购单创建日期）
        for name in ("下单时间", "创建日期", "创建时间"):
            try:
                candidate = page.get_by_text(name, exact=False).first
                await candidate.click(timeout=1500)
                trigger = candidate
                break
            except Exception:
                continue
    if trigger is None:
        raise RuntimeError(
            "日期控件 trigger 不可用：未找到 '开始时间' / '结束时间' combobox "
            "或 '下单时间' / '创建日期' / '创建时间' 文本标签"
        )
    await self._wait_ready(page)
```

`_wait_custom_range_applied`（line 171-184）的 combobox 读取也要同步扩展。改为：

```python
async def _wait_custom_range_applied(self, page: Any, date_range: MiaoshouCustomDateRange) -> None:
    # 兼容妙手所有已知日期控件标签：
    # - "开始时间" / "结束时间"：orders
    # - "创建日期" / "创建时间"：purchase
    start_names = ("开始时间", "创建日期")
    end_names = ("结束时间", "创建时间")
    for _ in range(10):
        start_value = ""
        end_value = ""
        for name in start_names:
            try:
                start_value = await self._read_combobox_value(page, name)
                if start_value:
                    break
            except Exception:
                continue
        for name in end_names:
            try:
                end_value = await self._read_combobox_value(page, name)
                if end_value:
                    break
            except Exception:
                continue
        if (
            self._matches_expected_display(start_value, date_range.start_date, date_range.start_time)
            and self._matches_expected_display(end_value, date_range.end_date, date_range.end_time)
        ):
            return
        try:
            await page.wait_for_timeout(200)
        except Exception:
            continue
    raise RuntimeError("自定义时间范围未正确应用")
```

`apply_custom_range` 中的 `_fill_input_by_name` 调用（line 198-201）也需兼容"创建日期" / "创建时间"。改为：

```python
async def apply_custom_range(self, page: Any, date_range: MiaoshouCustomDateRange) -> DatePickResult:
    await self._open(page)
    used_range_inputs = await self._type_range_inputs(page, date_range)
    if not used_range_inputs:
        await self._open(page)
        # 兼容妙手所有已知日期标签：开始/结束 或 创建日期/创建时间
        for start_name, end_name in (("开始日期", "结束日期"), ("创建日期", "结束日期")):
            try:
                await self._fill_input_by_name(page, start_name, date_range.start_date)
                await self._fill_input_by_name(page, "开始时间", date_range.start_time)
                await self._fill_input_by_name(page, end_name, date_range.end_date)
                await self._fill_input_by_name(page, "结束时间", date_range.end_time)
                break
            except Exception:
                continue
    await self._click_confirm_if_visible(page)
    await self._wait_custom_range_applied(page, date_range)
    return DatePickResult(success=True, message="ok", option=DateOption.YESTERDAY)
```

- [ ] **Step 4: 修正 purchase_config.CUSTOM_DATE_INPUT_NAMES**

`modules/platforms/miaoshou/components/purchase_config.py` line 48-51：

```python
CUSTOM_DATE_INPUT_NAMES: Final[Tuple[str, ...]] = (
    "创建日期",
    "创建时间",
)
```

- [ ] **Step 5: 跑测试确认 GREEN**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_date_picker_trigger_fallback.py -v
```
Expected: 5 passed。

- [ ] **Step 6: 跑关联回归测试（orders 走"下单时间" fallback 不应破坏）**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py -v
```
Expected: 全部 passed（pre-existing 失败可接受）。

- [ ] **Step 7: Commit**

```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git add modules/platforms/miaoshou/components/date_picker.py modules/platforms/miaoshou/components/purchase_config.py backend/tests/test_miaoshou_date_picker_trigger_fallback.py
git commit -m "fix(miaoshou): extend date picker trigger fallback to cover purchase page labels"
```

---

### Task 2: 静态验收（ruff / mypy / pytest）

**Files:** 无（只跑命令）

- [ ] **Step 1: ruff lint**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m ruff check modules/platforms/miaoshou/components/date_picker.py modules/platforms/miaoshou/components/purchase_config.py backend/tests/test_miaoshou_date_picker_trigger_fallback.py
```
Expected: 无错误。

- [ ] **Step 2: mypy**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m mypy modules/platforms/miaoshou/components/date_picker.py modules/platforms/miaoshou/components/purchase_config.py
```
Expected: 无新增错误。

- [ ] **Step 3: pytest 全量回归**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
python -m pytest backend/tests/test_miaoshou_date_picker_trigger_fallback.py backend/tests/test_miaoshou_orders_export_contract.py backend/tests/test_miaoshou_orders_export_v2_flow.py backend/tests/test_miaoshou_purchase_export_contract.py backend/tests/test_miaoshou_purchase_export_v2_flow.py backend/tests/test_miaoshou_inventory_export_contract.py backend/tests/test_miaoshou_inventory_export_v2_flow.py -v
```
Expected: 5 + orders(20) + purchase(18) + inventory(15) ≈ 58 passed（pre-existing 无关失败可接受）。

- [ ] **Step 4: 工作区状态确认**

Run:
```bash
cd f:/Vscode/python_programme/AI_code/xihong_erp
git status --short
```
Expected: 仅显示 pre-existing product_category 改动 + plan 文件；本任务 3 个文件已 commit。

- [ ] **Step 5: 最终验证报告**

输出 ruff / mypy / pytest 实际结果，列出 commit 列表，标记是否通过。

---

## Self-Review

### Spec coverage 检查

| 段落 | 对应 Task |
|---|---|
| 1. date_picker._open() fallback 扩展 | Task 1 Step 3 |
| 2. purchase_config CUSTOM_DATE_INPUT_NAMES 修正 | Task 1 Step 4 |
| 3. contract test 防回归 | Task 1 Step 1-5 |
| 4. 静态验收 | Task 2 |

### Placeholder 扫描

- ✅ 无 TBD / TODO
- ✅ Step 3 完整代码块
- ✅ 测试代码完整，可直接运行

### Type 一致性

- `MiaoshouDatePicker._open()` 返回 `None`，与原签名一致
- `apply_custom_range` 返回 `DatePickResult`，与原签名一致
- `_wait_custom_range_applied` 返回 `None`，与原签名一致
- `PurchaseSelectors.custom_date_input_names` 字段类型未变（`Tuple[str, ...]`），仅值从 `("开始时间", "结束时间")` 改为 `("创建日期", "创建时间")`

### Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-13-miaoshou-date-picker-trigger-fallback.md`.

**Subagent-Driven** 流程，分发 Task 1 给独立子代理。
