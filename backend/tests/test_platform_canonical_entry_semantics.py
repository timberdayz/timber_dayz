import sys
import types
import py_compile
from pathlib import Path

import pytest

from modules.components.base import ExecutionContext
from modules.platforms.shopee.components.metrics_selector import ShopeeMetricsSelector


def _ctx():
    return ExecutionContext(
        platform="shopee",
        account={"username": "u"},
        logger=None,
        config={},
    )


def test_shopee_adapter_does_not_advertise_metrics_capability():
    fake_services_export = types.ModuleType("modules.platforms.shopee.components.services_export")
    class _FakeServicesExport:  # noqa: N801
        pass
    fake_services_export.ShopeeServicesExport = _FakeServicesExport
    sys.modules["modules.platforms.shopee.components.services_export"] = fake_services_export

    from modules.platforms.shopee.adapter import ShopeeAdapter

    adapter = ShopeeAdapter(_ctx())

    capabilities = adapter.capabilities()

    assert capabilities["products"]["metrics"] is False


@pytest.mark.asyncio
async def test_shopee_metrics_selector_returns_explicit_not_supported():
    component = ShopeeMetricsSelector(_ctx())

    result = await component.run(page=None, metrics=("sales",))

    assert result.success is False
    assert "not supported" in result.message.lower()


def test_shopee_services_export_is_python_compilable():
    file_path = Path("modules/platforms/shopee/components/services_export.py")

    py_compile.compile(str(file_path), doraise=True)
