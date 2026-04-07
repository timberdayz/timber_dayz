"""
验收 6.3：Resume 接口在任务已非「等待验证」时返回 4xx。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from backend.models.database import get_async_db
from backend.routers.collection import router as collection_router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(collection_router, prefix="/collection", tags=["collection"])
    app.state.redis = None
    return app


def _make_mock_db(mock_task):
    async def mock_get_async_db():
        session = MagicMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = mock_task
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.add = MagicMock()
        yield session
    return mock_get_async_db


@pytest.mark.anyio
async def test_resume_returns_400_when_task_not_paused(app):
    """任务状态非 paused 时，POST /resume 应返回 400，提示重新发起采集。"""
    task_id = str(uuid4())
    mock_task = MagicMock()
    mock_task.task_id = task_id
    mock_task.status = "completed"
    mock_task.id = 1

    mock_get_async_db = _make_mock_db(mock_task)

    app.dependency_overrides[get_async_db] = mock_get_async_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/collection/tasks/{task_id}/resume",
                json={"captcha_code": "1234"},
            )
        assert resp.status_code == 400
        data = resp.json()
        assert "detail" in data
        assert "验证已超时或任务已结束" in data["detail"] or "重新发起" in data["detail"]
    finally:
        app.dependency_overrides.pop(get_async_db, None)


@pytest.mark.anyio
async def test_resume_returns_400_when_task_failed(app):
    """任务状态为 failed 时，POST /resume 应返回 400。"""
    task_id = str(uuid4())
    mock_task = MagicMock()
    mock_task.task_id = task_id
    mock_task.status = "failed"
    mock_task.id = 1

    mock_get_async_db = _make_mock_db(mock_task)
    app.dependency_overrides[get_async_db] = mock_get_async_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/collection/tasks/{task_id}/resume",
                json={"otp": "666666"},
            )
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_async_db, None)
