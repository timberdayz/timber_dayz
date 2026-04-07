from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.apps.collection_center.executor_v2 import VerificationRequiredError
from tools.test_component import (
    ComponentTestResult,
    ComponentTester,
    HeadfulLoginFallbackRequired,
    TestStatus,
)


class _FakeAdapter:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def login(self, page):  # noqa: ANN001
        raise self._exc


@pytest.mark.asyncio
async def test_component_tester_raises_headful_fallback_required_for_manual_continue_in_headless_mode():
    tester = ComponentTester(platform="tiktok", account_id="acc-1", headless=True)
    result = ComponentTestResult(
        component_name="login",
        platform="tiktok",
        status=TestStatus.PENDING,
    )

    adapter = _FakeAdapter(VerificationRequiredError("manual_intervention", "manual.png"))

    with pytest.raises(HeadfulLoginFallbackRequired) as exc_info:
        await tester._run_login_with_verification_support(
            adapter=adapter,
            page=object(),
            component_name="tiktok/login",
            result=result,
        )

    assert exc_info.value.verification_type == "manual_intervention"


@pytest.mark.asyncio
async def test_component_tester_run_login_before_non_login_uses_headful_fallback_result(
    monkeypatch: pytest.MonkeyPatch,
):
    tester = ComponentTester(platform="tiktok", account_id="acc-1", headless=True)
    result = ComponentTestResult(
        component_name="products_export",
        platform="tiktok",
        status=TestStatus.PENDING,
    )

    class _FakeSession:
        def close(self):
            return None

    monkeypatch.setattr("backend.models.database.SessionLocal", lambda: _FakeSession())
    monkeypatch.setattr(
        "backend.services.component_version_service.ComponentVersionService.get_stable_version",
        lambda self, name: SimpleNamespace(file_path="modules/platforms/tiktok/components/login.py", id=1, version="1.0.0"),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.ComponentLoader.load_python_component_from_path",
        lambda self, *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.python_component_adapter.create_adapter",
        lambda *args, **kwargs: object(),
    )

    async def _raise_fallback(*args, **kwargs):  # noqa: ANN002, ANN003
        raise HeadfulLoginFallbackRequired("manual_intervention", "manual.png")

    new_context = object()
    new_page = object()

    monkeypatch.setattr(tester, "_run_login_with_verification_support", _raise_fallback)
    monkeypatch.setattr(
        tester,
        "_run_headful_login_fallback",
        AsyncMock(return_value=(True, new_context, new_page)),
    )

    ok, context, page = await tester._run_login_before_non_login(
        browser=object(),
        context=object(),
        page=object(),
        account_info={"account_id": "acc-1", "login_url": "https://seller.tiktokglobalshop.com"},
        result=result,
    )

    assert ok is True
    assert context is new_context
    assert page is new_page
