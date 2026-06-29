from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import Base, CatalogFile, CollectionTask, TaskCenterLink, TaskCenterTask


@pytest_asyncio.fixture
async def collection_ingest_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CollectionTask.__table__.create)
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(TaskCenterTask.__table__.create)
        await conn.run_sync(TaskCenterLink.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_collection_success_enqueues_single_file_ingest_tasks_and_updates_details(
    collection_ingest_session,
    monkeypatch,
):
    from backend.domains.collection.routers import collection_tasks

    task = CollectionTask(
        task_id="collection-post-ingest-1",
        platform="miaoshou",
        account="miaoshou_real_001",
        status="running",
        trigger_type="manual",
        data_domains=["orders"],
        granularity="monthly",
    )
    collection_ingest_session.add(task)
    collection_ingest_session.add_all(
        [
            CatalogFile(
                id=2803,
                file_path="data/raw/2026/tiktok_orders_monthly.xls",
                file_name="tiktok_orders_monthly.xls",
                platform_code="tiktok",
                account="miaoshou_real_001",
                data_domain="orders",
                granularity="monthly",
                status="pending",
                file_metadata={"collection_task_id": "collection-post-ingest-1"},
            ),
            CatalogFile(
                id=2804,
                file_path="data/raw/2026/shopee_orders_monthly.xls",
                file_name="shopee_orders_monthly.xls",
                platform_code="shopee",
                account="miaoshou_real_001",
                data_domain="orders",
                granularity="monthly",
                status="pending",
                file_metadata={"collection_task_id": "collection-post-ingest-1"},
            ),
        ]
    )
    await collection_ingest_session.commit()

    submitted = []

    class _ApplyAsync:
        @staticmethod
        def apply_async(*, args=None, kwargs=None, **_):
            submitted.append({"args": args or (), "kwargs": kwargs or {}})
            return SimpleNamespace(id=f"celery-{len(submitted)}")

    monkeypatch.setattr(
        collection_tasks,
        "sync_single_file_task",
        _ApplyAsync,
        raising=False,
    )

    post_status = await collection_tasks._enqueue_post_collection_ingest_tasks(
        collection_ingest_session,
        "collection-post-ingest-1",
    )
    await collection_ingest_session.commit()

    assert post_status["ingest_status"] == "queued"
    assert post_status["collected_file_ids"] == [2803, 2804]
    assert len(post_status["ingest_task_ids"]) == 2
    assert submitted[0]["kwargs"]["file_id"] == 2803
    assert submitted[1]["kwargs"]["file_id"] == 2804

    mirrored = (
        await collection_ingest_session.execute(
            select(TaskCenterTask).where(TaskCenterTask.task_id == "collection-post-ingest-1")
        )
    ).scalar_one()
    details = mirrored.details_json
    assert details["ingest"]["status"] == "queued"
    assert details["ingest"]["collected_file_ids"] == [2803, 2804]
    assert details["ingest"]["ingest_task_ids"] == post_status["ingest_task_ids"]
