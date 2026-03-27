import pytest


@pytest.mark.asyncio
@pytest.mark.pg_only
@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/field-mapping/auto-ingest/single", {"file_id": 1}),
        ("post", "/api/field-mapping/auto-ingest/batch", {"limit": 10}),
        ("get", "/api/field-mapping/auto-ingest/progress/task-1", None),
        ("get", "/api/field-mapping/auto-ingest/task/task-1/logs", None),
        ("get", "/api/field-mapping/auto-ingest/file/1/logs", None),
    ],
)
async def test_deprecated_auto_ingest_routes_are_retired(
    pg_async_client,
    method,
    path,
    payload,
):
    if method == "post":
        response = await pg_async_client.post(path, json=payload)
    else:
        response = await pg_async_client.get(path)

    assert response.status_code == 404
