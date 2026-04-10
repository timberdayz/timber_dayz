import pytest

from modules.components.base import ExecutionContext
from modules.components.navigation.base import TargetPage
from modules.platforms.miaoshou.components.navigation import MiaoshouNavigation
from modules.platforms.miaoshou.components.orders_config import OrdersSelectors
from modules.platforms.miaoshou.components.warehouse_config import WarehouseSelectors


class _WaitLocator:
    def __init__(self) -> None:
        self.first = self

    async def wait_for(self, state: str = "visible", timeout: int = 0) -> None:  # noqa: ARG002
        return None


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.goto_calls: list[str] = []

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 0) -> None:  # noqa: ARG002
        self.url = url
        self.goto_calls.append(url)

    def get_by_text(self, text: str, exact: bool = False):  # noqa: ARG002
        return _WaitLocator()


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"login_url": "https://erp.91miaoshou.com"},
        logger=None,
        config={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "selectors"),
    [
        (TargetPage.ORDERS, OrdersSelectors()),
        (TargetPage.WAREHOUSE_CHECKLIST, WarehouseSelectors()),
    ],
)
async def test_miaoshou_navigation_runs_post_navigation_stabilization(
    target: TargetPage,
    selectors,
) -> None:
    component = MiaoshouNavigation(_ctx(), selectors=selectors)
    page = _FakePage()
    calls: list[str | None] = []

    async def _fake_stabilize(page, *, label=None):  # noqa: ARG001
        calls.append(label)
        return 1

    component.stabilize_safe_notices = _fake_stabilize  # type: ignore[attr-defined]

    result = await component.run(page, target)

    assert result.success is True
    assert calls == ["post-navigation cleanup"]
