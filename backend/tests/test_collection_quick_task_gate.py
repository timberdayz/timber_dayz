from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.schemas.collection import TaskCreateRequest


@pytest.mark.asyncio
async def test_create_task_rejects_when_config_run_is_active(monkeypatch):
    from backend.routers.collection_tasks import create_task

    active_run = SimpleNamespace(
        id=1,
        run_id="run-1",
        status="running",
        config_id=123,
        main_account_id="main-shopee",
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: active_run)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))

    monkeypatch.setattr(
        "backend.services.shop_account_loader_service.get_shop_account_loader_service",
        lambda: SimpleNamespace(
            load_shop_account_async=AsyncMock(
                side_effect=AssertionError("shop account loader should not run")
            )
        ),
    )
    monkeypatch.setattr(
        "backend.services.account_loader_service.get_account_loader_service",
        lambda: SimpleNamespace(
            load_account_async=AsyncMock(
                side_effect=AssertionError("fallback account loader should not run")
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_task(
            request=TaskCreateRequest(
                platform="shopee",
                account_id="shop-sg-1",
                data_domains=["orders"],
            ),
            fastapi_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
            db=db,
        )

    assert exc_info.value.status_code == 409
    assert "queue" in str(exc_info.value.detail).lower()
