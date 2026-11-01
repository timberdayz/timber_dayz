"""服务重启后回收采集僵尸任务的行为测试。

背景：采集任务在接口里落库(status=pending)后由**本进程内**的后台协程执行，
排队(queued)的任务也只靠进程内的"上一个任务结束 -> 拉起下一个"回调推进。
进程一挂，这些任务就没人再管，会永远停在 pending/queued，页面上看着像"还在跑"。

本测试用一次性 SQLite（ATTACH 出 core schema）验证回收口径，不依赖外部数据库。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.services.task_service import TaskService
from modules.core.db import CollectionTask


@pytest.fixture
def collection_task_session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _attach_schemas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            cursor.execute(f"ATTACH DATABASE ':memory:' AS {schema_name}")
        cursor.close()

    CollectionTask.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _seed_task(session: Session, task_id: str, status: str, age_seconds: int = 0):
    now = datetime.now(timezone.utc)
    task = CollectionTask(
        task_id=task_id,
        platform="shopee",
        account="shop-sg-1",
        status=status,
        created_at=now - timedelta(seconds=age_seconds),
        updated_at=now - timedelta(seconds=age_seconds),
    )
    session.add(task)
    session.commit()
    return task


def _status_of(session: Session, task_id: str) -> str:
    task = session.execute(
        select(CollectionTask).where(CollectionTask.task_id == task_id)
    ).scalar_one()
    session.expire(task)
    return task.status


def test_running_task_is_always_reclaimed_on_restart(collection_task_session):
    _seed_task(collection_task_session, "running-task", "running", age_seconds=1)

    service = TaskService(collection_task_session)
    reclaimed = service.mark_interrupted_tasks()

    assert reclaimed == 1
    assert _status_of(collection_task_session, "running-task") == "interrupted"


def test_stale_pending_task_is_reclaimed_on_restart(collection_task_session):
    _seed_task(collection_task_session, "stale-pending", "pending", age_seconds=600)

    service = TaskService(collection_task_session)
    reclaimed = service.mark_interrupted_tasks()

    assert reclaimed == 1
    assert _status_of(collection_task_session, "stale-pending") == "interrupted"


def test_stale_queued_task_is_reclaimed_on_restart(collection_task_session):
    _seed_task(collection_task_session, "stale-queued", "queued", age_seconds=600)

    service = TaskService(collection_task_session)
    reclaimed = service.mark_interrupted_tasks()

    assert reclaimed == 1
    assert _status_of(collection_task_session, "stale-queued") == "interrupted"


def test_fresh_pending_task_is_left_alone(collection_task_session):
    """[*] 多 worker 部署下，别的 worker 刚建的任务不能被误杀。"""
    _seed_task(collection_task_session, "fresh-pending", "pending", age_seconds=1)

    service = TaskService(collection_task_session)
    reclaimed = service.mark_interrupted_tasks()

    assert reclaimed == 0
    assert _status_of(collection_task_session, "fresh-pending") == "pending"


def test_finished_tasks_are_never_touched(collection_task_session):
    _seed_task(collection_task_session, "done-task", "completed", age_seconds=600)
    _seed_task(collection_task_session, "failed-task", "failed", age_seconds=600)

    service = TaskService(collection_task_session)
    reclaimed = service.mark_interrupted_tasks()

    assert reclaimed == 0
    assert _status_of(collection_task_session, "done-task") == "completed"
    assert _status_of(collection_task_session, "failed-task") == "failed"
