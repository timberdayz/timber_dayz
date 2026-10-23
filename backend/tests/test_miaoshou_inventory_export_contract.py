from __future__ import annotations

import pytest

from miaoshou_page_fakes import FakeLocator, FakePage
from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.inventory_config import InventorySelectors
from modules.platforms.miaoshou.components.inventory_export import (
    MiaoshouInventoryExport,
)
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={
            "label": "acc",
            "store_name": "shop",
            "login_url": "https://erp.91miaoshou.com/login",
        },
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


def test_miaoshou_inventory_export_reuses_navigation_component_instead_of_opening_login():
    """导出组件必须复用导航组件走「仓库清单」，不得自己 goto 登录页。

    行为验证在 ``test_miaoshou_inventory_export_v2_flow.py``（用替身组件断言
    步骤调用序列）；此处只锁住「持有导航组件」这个结构事实。
    """
    component = MiaoshouInventoryExport(_ctx())

    assert isinstance(component.navigation_component, MiaoshouNavigation)
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"


def test_miaoshou_navigation_supports_warehouse_checklist_target():
    nav = MiaoshouNavigation(_ctx(), InventorySelectors())
    assert hasattr(nav, "_warehouse_checklist_url")
    assert TargetPage.WAREHOUSE_CHECKLIST.value == "warehouse_checklist"


# ── L2-6 导航双信号（《规范》§13.2）───────────────────────────────────


class _StaticUrlPage(FakePage):
    """goto 不改变 URL 的 page 替身（模拟 SPA 未更新地址栏）。"""

    async def goto(self, url, wait_until=None, timeout=None) -> None:  # noqa: ARG002
        self.goto_calls.append(url)


def _nav() -> MiaoshouNavigation:
    """构造导航组件，并把弹窗收敛（slow polling）替换成替身。"""
    nav = MiaoshouNavigation(_ctx(), InventorySelectors())

    async def _fake_stabilize(page, *, label=None):  # noqa: ARG001
        return 0

    nav.stabilize_safe_notices = _fake_stabilize  # type: ignore[attr-defined]
    return nav


@pytest.mark.asyncio
async def test_navigation_warehouse_checklist_succeeds_when_both_signals_present() -> (
    None
):
    """路由信号与元素信号都满足时才算就绪。"""
    nav = _nav()
    page = FakePage(url="about:blank", locators={"text:仓库清单": FakeLocator()})

    result = await nav.run(page, TargetPage.WAREHOUSE_CHECKLIST)

    assert result.success is True
    assert page.url == "https://erp.91miaoshou.com/warehouse/checklist"


@pytest.mark.asyncio
async def test_navigation_warehouse_checklist_fails_when_route_signal_missing() -> None:
    """URL 既不含清单路径也没切换 → 路由信号缺失，必须失败并点名该信号。"""
    nav = _nav()
    page = _StaticUrlPage(
        url="https://erp.91miaoshou.com/spa-shell",
        locators={"text:仓库清单": FakeLocator()},
    )

    result = await nav.run(page, TargetPage.WAREHOUSE_CHECKLIST)

    assert result.success is False
    assert "warehouse_checklist_ready_failed" in (result.message or "")
    assert "route_signal" in (result.message or "")
    assert "element_signal" not in (result.message or "")
    assert "current_url=https://erp.91miaoshou.com/spa-shell" in (result.message or "")


@pytest.mark.asyncio
async def test_navigation_warehouse_checklist_fails_when_element_signal_missing() -> (
    None
):
    """「仓库清单」标题不可见 → 元素信号缺失，必须失败并点名该信号。"""
    nav = _nav()
    page = FakePage(url="about:blank", locators={})

    result = await nav.run(page, TargetPage.WAREHOUSE_CHECKLIST)

    assert result.success is False
    assert "warehouse_checklist_ready_failed" in (result.message or "")
    assert "element_signal" in (result.message or "")
    assert "route_signal" not in (result.message or "")


@pytest.mark.asyncio
async def test_inventory_export_surfaces_navigation_failure_with_structured_fields() -> (
    None
):
    """真实导航组件判定不就绪时，导出阶段要报 navigation_failed + 结构化字段。"""
    component = MiaoshouInventoryExport(_ctx())
    component.navigation_component = _nav()
    page = FakePage(url="about:blank", locators={})

    result = await component.run(page)
    message = result.message or ""

    assert result.success is False
    assert "navigation_failed" in message
    assert "stage=navigation_ready" in message
    assert "status=failed" in message
    assert "current_url=" in message
    assert "matched_signal=" in message
