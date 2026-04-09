import pytest

from modules.components.base import ExecutionContext
from modules.components.export.base import ExportResult
from modules.components.navigation.base import NavigationResult
from modules.platforms.miaoshou.components.orders_export_base import MiaoshouOrdersExportBase


class _FakeDownload:
    suggested_filename = "orders.xlsx"

    async def save_as(self, path: str) -> None:
        from pathlib import Path

        Path(path).write_bytes(b"x")


class _DownloadContextManager:
    def __init__(self) -> None:
        self.value = _FakeDownload()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"

    async def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 0) -> None:  # noqa: ARG002
        self.url = url

    def expect_download(self, timeout: int = 0):  # noqa: ARG002
        return _DownloadContextManager()


def _ctx(tmp_path) -> ExecutionContext:
    return ExecutionContext(
        platform="miaoshou",
        account={"label": "acc", "store_name": "shop", "login_url": "https://erp.91miaoshou.com"},
        logger=None,
        config={
            "time_selection": {"mode": "preset", "preset": "yesterday"},
            "download_dir": str(tmp_path),
        },
    )


@pytest.mark.asyncio
async def test_miaoshou_orders_export_stabilizes_before_first_interaction(tmp_path) -> None:
    component = MiaoshouOrdersExportBase(_ctx(tmp_path))
    page = _FakePage()
    calls: list[str] = []

    async def _fake_stabilize(page, *, label=None):  # noqa: ARG001
        calls.append("stabilize")
        return 1

    async def _fake_select_subtype(page, subtype):  # noqa: ARG001
        calls.append("subtype")
        raise RuntimeError("stop after subtype")

    component.stabilize_safe_notices = _fake_stabilize  # type: ignore[attr-defined]
    component.navigation_component.run = _fake_navigation_run  # type: ignore[method-assign]
    component._ensure_popup_closed = _fake_noop  # type: ignore[method-assign]
    component._ensure_orders_subtype_selected = _fake_select_subtype  # type: ignore[method-assign]

    result = await component.run(page)

    assert result.success is False
    assert calls == ["stabilize", "subtype"]


async def _fake_navigation_run(page, target):  # noqa: ARG001
    return NavigationResult(success=True, message="ok", url="https://erp.91miaoshou.com/stat/profit_statistics/detail?platform=shopee")


async def _fake_noop(*args, **kwargs):
    return None
