"""刷新队列「按域分道并发」+「失败自动退避重排队」+「物化刷新超时预算」的守护测试。

背景
----
2026-11-05 生产实测：刷新队列 614 条任务、失败 144 条（**23%**），
其中商品域 59%（56/137）。根因有三条：

1. 队列是**单通道**的 —— 慢域（最慢 250.5 秒）把其它域全堵在后面；
2. 失败任务**永不重试** —— ``status='failed'`` 就是终态；
3. 物化视图的 ``REFRESH`` 贴着连接池的 ``statement_timeout=120s``
   （``fact_orders_atomic_mv`` 实测 115 秒）—— 机器一忙就被静默掐断。

本文件把三件事的行为钉死，防止以后被改回去。
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from modules.core.db import RefreshQueueTask


@pytest_asyncio.fixture
async def refresh_queue_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(RefreshQueueTask.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# 一、按业务域分道
# ---------------------------------------------------------------------------


def test_resolve_refresh_lane_uses_context_domain():
    """域判定主用 ``context['data_domain']``，不靠 targets 反推。

    targets 反推不可靠：目标集合里含已退役目标
    （``api.store_analysis_*`` / ``mart.shop_hour_traffic_kpi`` 等），
    同一个集合可能同时属于多个域。
    """
    from backend.services.data_pipeline.refresh_queue_service import (
        DEFAULT_LANE,
        resolve_refresh_lane,
    )

    assert resolve_refresh_lane({"data_domain": "products"}) == "products"
    assert resolve_refresh_lane({"data_domain": "orders"}) == "orders"
    assert resolve_refresh_lane({"data_domain": "analytics"}) == "analytics"
    assert resolve_refresh_lane({"data_domain": "inventory"}) == "inventory"
    assert resolve_refresh_lane({"data_domain": "services"}) == "services"
    # 历史别名 traffic 要归一到 analytics（与 data_domains SSOT 一致）
    assert resolve_refresh_lane({"data_domain": "traffic"}) == "analytics"
    # 认不出来的域归共享道
    assert resolve_refresh_lane({"data_domain": "finance"}) == DEFAULT_LANE
    assert resolve_refresh_lane({}) == DEFAULT_LANE
    assert resolve_refresh_lane(None) == DEFAULT_LANE


@pytest.mark.asyncio
async def test_enqueue_refresh_stores_domain(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-products",
        targets=["semantic.fact_products_atomic"],
        context={"data_domain": "products"},
    )

    assert task.domain == "products"


@pytest.mark.asyncio
async def test_claim_takes_other_domain_but_not_same_domain(refresh_queue_session):
    """同域串行、不同域并行 —— 这是「按业务域分道」的核心语义。"""
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)

    running_products = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-running-products",
        targets=["semantic.fact_products_atomic"],
        context={"data_domain": "products"},
    )
    pending_products = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-pending-products",
        targets=["semantic.fact_products_atomic_mv"],
        context={"data_domain": "products"},
    )
    pending_orders = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-pending-orders",
        targets=["semantic.fact_orders_atomic"],
        context={"data_domain": "orders"},
    )

    running_products.status = "running"
    await refresh_queue_session.commit()

    claimed = await service.claim_next_refresh_task()

    # 同域的那条不能被领走（否则同域并发刷新会互相锁死）
    assert claimed is not None
    assert claimed.id == pending_orders.id

    still_pending = await refresh_queue_session.get(
        RefreshQueueTask, pending_products.id
    )
    assert still_pending.status == "pending"


@pytest.mark.asyncio
async def test_claim_respects_global_concurrency_cap(refresh_queue_session):
    """并发上限是**库里的事实**：最多 2 道同时跑。"""
    from backend.services.data_pipeline.refresh_queue_service import (
        REFRESH_QUEUE_MAX_CONCURRENT,
        RefreshQueueService,
    )

    assert REFRESH_QUEUE_MAX_CONCURRENT == 2

    service = RefreshQueueService(refresh_queue_session)
    for index, domain in enumerate(["orders", "products"]):
        task = await service.enqueue_refresh(
            trigger_type="data_ingested",
            pipeline_name=f"pipeline-running-{index}",
            targets=[f"semantic.running_{index}"],
            context={"data_domain": domain},
        )
        task.status = "running"
    await refresh_queue_session.commit()

    await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-extra",
        targets=["semantic.extra"],
        context={"data_domain": "analytics"},
    )

    claimed = await service.claim_next_refresh_task()

    assert claimed is None


# ---------------------------------------------------------------------------
# 二、失败自动带退避重排队
# ---------------------------------------------------------------------------


def test_retry_backoff_is_exponential_and_capped():
    from backend.services.data_pipeline.refresh_queue_service import (
        RETRY_BACKOFF_BASE_SECONDS,
        RETRY_BACKOFF_MAX_SECONDS,
        retry_backoff_seconds,
    )

    assert retry_backoff_seconds(1) == RETRY_BACKOFF_BASE_SECONDS
    assert retry_backoff_seconds(2) == RETRY_BACKOFF_BASE_SECONDS * 2
    assert retry_backoff_seconds(3) == RETRY_BACKOFF_BASE_SECONDS * 4
    assert retry_backoff_seconds(99) == RETRY_BACKOFF_MAX_SECONDS


@pytest.mark.asyncio
async def test_mark_failed_with_retryable_requeues_with_backoff(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-retryable",
        targets=["semantic.retryable"],
        context={"data_domain": "orders"},
    )
    task.attempt_count = 1
    await refresh_queue_session.commit()

    before = datetime.now(timezone.utc).replace(tzinfo=None)
    await service.mark_failed(task.id, "deadlock detected", retryable=True)

    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "pending"
    assert refreshed.next_retry_at is not None
    assert refreshed.next_retry_at.replace(tzinfo=None) >= before
    # 次数**不归零** —— 归零等于无限重排队
    assert refreshed.attempt_count == 1
    assert refreshed.finished_at is None


@pytest.mark.asyncio
async def test_mark_failed_without_retryable_is_terminal(refresh_queue_session):
    """口径错、对象缺失这类「重跑也没用」的错误不自动重排队。"""
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-terminal",
        targets=["semantic.terminal"],
        context={"data_domain": "orders"},
    )
    await refresh_queue_session.commit()

    await service.mark_failed(task.id, "relation does not exist", retryable=False)

    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "failed"
    assert refreshed.next_retry_at is None
    assert refreshed.finished_at is not None


@pytest.mark.asyncio
async def test_mark_failed_stops_retrying_after_max_attempts(refresh_queue_session):
    from backend.services.data_pipeline.refresh_queue_service import (
        MAX_AUTO_RETRY_ATTEMPTS,
        RefreshQueueService,
    )

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-exhausted",
        targets=["semantic.exhausted"],
        context={"data_domain": "orders"},
    )
    task.attempt_count = MAX_AUTO_RETRY_ATTEMPTS
    await refresh_queue_session.commit()

    await service.mark_failed(task.id, "deadlock detected", retryable=True)

    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "failed"
    assert refreshed.next_retry_at is None


def test_error_classification_uses_sqlstate():
    """可重试 = 环境类故障；其它一律不可重试。"""

    class _FakeOrig(Exception):
        sqlstate = "40P01"

    class _FakeWrapper(Exception):
        orig = _FakeOrig()

    from backend.tasks.refresh_queue_tasks import (
        RETRYABLE_SQLSTATES,
        is_retryable_exception,
        is_retryable_failure,
    )

    assert is_retryable_exception(_FakeWrapper())
    assert not is_retryable_exception(ValueError("口径写错了"))

    assert is_retryable_failure({"semantic.a": {"sqlstate": "57014"}})
    # 混着「不可重试」就不重排队
    assert not is_retryable_failure(
        {
            "semantic.a": {"sqlstate": "57014"},
            "semantic.b": {"sqlstate": "42P01"},
        }
    )
    assert not is_retryable_failure({})
    assert not is_retryable_failure(None)
    assert "57014" in RETRYABLE_SQLSTATES
    assert "42P01" not in RETRYABLE_SQLSTATES


def test_stale_running_threshold_exceeds_celery_hard_time_limit():
    """判死阈值必须大于 Celery 硬超时 —— 否则会把还在跑的任务误判成死的。

    旧阈值 600 秒 < 软超时 1500 秒，一直是错的：任务还在跑就被重排队，
    同一条刷新会被跑第二遍，还可能并发。
    """
    from backend.celery_app import celery_app
    from backend.tasks.refresh_queue_tasks import REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS

    hard_limit = int(celery_app.conf.task_time_limit)
    assert REFRESH_QUEUE_RUNNING_TIMEOUT_SECONDS > hard_limit


# ---------------------------------------------------------------------------
# 三、物化刷新：超时预算 + 互斥锁 + 逐目标提交
# ---------------------------------------------------------------------------


class _RecordingSession:
    """记录执行过的 SQL 的假 session。"""

    def __init__(self, *, dialect: str = "postgresql", lock_result: bool = True):
        self.statements: list[str] = []
        self.params: list[dict] = []
        self._dialect = dialect
        self._lock_result = lock_result

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement)
        self.statements.append(sql)
        # SQLAlchemy 2.0 的 ``execute(statement, params)`` —— params 是**位置参数**
        params = kwargs.get("params")
        if params is None and args:
            params = args[0]
        self.params.append(params or {})

        class _Result:
            def __init__(self, value):
                self._value = value

            def scalar_one_or_none(self):
                return self._value

            def scalar_one(self):
                return self._value

        if "pg_try_advisory_xact_lock" in sql:
            return _Result(self._lock_result)
        if "pg_class" in sql:
            return _Result(b"m")
        if "current_setting" in sql:
            return _Result("2min")
        return _Result(None)

    def get_bind(self):
        class _Dialect:
            name = self._dialect

        class _Bind:
            dialect = _Dialect()

        return _Bind()


@pytest.mark.asyncio
async def test_materialized_view_refresh_applies_timeout_budget_and_restores_it():
    """REFRESH 必须临时抬高语句超时，结束后恢复 —— 不污染连接池。"""
    from backend.services.data_pipeline.refresh_runner import (
        MATERIALIZED_VIEW_REFRESH_TIMEOUT_MS,
        _refresh_materialized_view,
    )

    assert MATERIALIZED_VIEW_REFRESH_TIMEOUT_MS >= 10 * 60 * 1000

    session = _RecordingSession()
    await _refresh_materialized_view(
        session,
        "semantic.fact_products_atomic_mv",
        "sql/semantic/products_atomic_mv.sql",
    )

    set_config_calls = [
        (sql, params)
        for sql, params in zip(session.statements, session.params)
        if "set_config" in sql
    ]
    assert len(set_config_calls) >= 2, "必须先抬高、再恢复"
    # 超时预算是**绑定参数**（set_config 能绑参数，SET 不能）
    applied_values = [str(params.get("value")) for _sql, params in set_config_calls]
    assert str(MATERIALIZED_VIEW_REFRESH_TIMEOUT_MS) in applied_values
    # 事务级（第三个参数 true）⇒ 事务结束自动恢复
    assert all("true" in sql for sql, _params in set_config_calls)
    assert any("REFRESH MATERIALIZED VIEW" in sql for sql in session.statements)


@pytest.mark.asyncio
async def test_materialized_view_refresh_skips_when_other_lane_holds_the_lock():
    """另一条道正在刷同一个物化视图 ⇒ 本次跳过，不排队等锁。"""
    from backend.services.data_pipeline.refresh_runner import _refresh_materialized_view

    session = _RecordingSession(lock_result=False)
    refreshed = await _refresh_materialized_view(
        session,
        "semantic.fact_products_atomic_mv",
        "sql/semantic/products_atomic_mv.sql",
    )

    assert refreshed is False
    assert not any("REFRESH MATERIALIZED VIEW" in sql for sql in session.statements)


def test_materialized_view_lock_key_is_stable_and_distinct():
    from backend.services.data_pipeline.refresh_runner import (
        _materialized_view_lock_key,
    )

    first = _materialized_view_lock_key("semantic.fact_products_atomic_mv")
    second = _materialized_view_lock_key("semantic.fact_orders_atomic_mv")
    assert first == _materialized_view_lock_key("semantic.fact_products_atomic_mv")
    assert first != second
    assert -(2**63) <= first < 2**63


def test_products_domain_refresh_plan_includes_materialized_view():
    """商品域必须把物化副本列进刷新链 —— 否则副本永远停在建库时的旧快照。"""
    from backend.services.data_pipeline.refresh_registry import (
        _base_targets_for_refresh_domain,
    )

    targets = _base_targets_for_refresh_domain("products")
    assert "semantic.fact_products_atomic" in targets
    assert "semantic.fact_products_atomic_mv" in targets


# ---------------------------------------------------------------------------
# 四、编排：2 道 + 独立队列
# ---------------------------------------------------------------------------


def test_beat_dispatches_two_refresh_lanes():
    """每分钟派 2 道 ⇒ 慢域不再堵住快域。"""
    from backend.celery_app import celery_app

    beat_schedule = celery_app.conf.beat_schedule or {}
    lane_entries = [
        (name, entry)
        for name, entry in beat_schedule.items()
        if entry.get("task")
        == "backend.tasks.refresh_queue_tasks.process_refresh_queue_task"
    ]
    assert len(lane_entries) == 2


def test_refresh_task_routed_to_dedicated_queue():
    from backend.celery_app import celery_app

    routes = celery_app.conf.task_routes or {}
    route = routes.get("backend.tasks.refresh_queue_tasks.process_refresh_queue_task")
    assert route is not None
    assert route.get("queue") == "refresh_queue"


def test_worker_queues_cover_refresh_queue():
    """编排文件里的 worker 必须消费 ``refresh_queue`` 队列。

    漏了 = 刷新任务堆在队列里没人领（而且没有任何报错）。
    """
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[3]
    compose_files = [
        "docker-compose.prod.yml",
        "docker-compose.dev.yml",
        "docker-compose.cloud.yml",
        "docker-compose.cloud-4c8g.yml",
    ]
    for name in compose_files:
        path = project_root / name
        assert path.is_file(), f"缺少编排文件 {name}"
        content = path.read_text(encoding="utf-8")
        worker_lines = [
            line
            for line in content.splitlines()
            if "celery" in line and "--queues" in line
        ]
        assert worker_lines, f"{name} 里找不到 worker 的 --queues 配置"
        for line in worker_lines:
            assert "refresh_queue" in line, f"{name} 的 worker 没消费 refresh_queue"


@pytest.mark.asyncio
async def test_manual_retry_resets_attempt_counter(refresh_queue_session):
    """人工重试 = 承认「失败原因已处理」⇒ 次数归零。"""
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-manual",
        targets=["semantic.manual"],
        context={"data_domain": "orders"},
    )
    task.status = "failed"
    task.attempt_count = 3
    task.next_retry_at = datetime.now(timezone.utc)
    await refresh_queue_session.commit()

    await service.retry_failed_task(task.id)

    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "pending"
    assert refreshed.attempt_count == 0
    assert refreshed.next_retry_at is None


@pytest.mark.asyncio
async def test_claim_skips_tasks_whose_retry_is_not_due(refresh_queue_session):
    """退避没到点的任务不能被领走。"""
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    task = await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-not-due",
        targets=["semantic.not_due"],
        context={"data_domain": "orders"},
    )
    task.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    await refresh_queue_session.commit()

    claimed = await service.claim_next_refresh_task()

    assert claimed is None
    refreshed = await refresh_queue_session.get(RefreshQueueTask, task.id)
    assert refreshed.status == "pending"


def test_refresh_queue_task_model_exposes_lane_columns():
    """ORM 必须暴露分道与重试两列（否则运行期和库里对不上）。"""
    table = RefreshQueueTask.__table__
    assert "domain" in table.c
    assert "next_retry_at" in table.c
    index_names = {index.name for index in table.indexes}
    assert "ix_refresh_queue_tasks_status_domain" in index_names
    assert "ix_refresh_queue_tasks_retry_due" in index_names


def test_orm_and_migration_agree_on_domain_values():
    """ORM 的默认值必须和迁移回填口径一致（default 共享道）。"""
    from backend.services.data_pipeline.refresh_queue_service import DEFAULT_LANE

    table = RefreshQueueTask.__table__
    assert table.c.domain.default.arg == DEFAULT_LANE


@pytest.mark.asyncio
async def test_refresh_queue_rows_are_listed_with_lane(refresh_queue_session):
    """列表接口能拿到分道信息（运营排查「谁在跑哪条道」要用）。"""
    from backend.services.data_pipeline.refresh_queue_service import RefreshQueueService

    service = RefreshQueueService(refresh_queue_session)
    await service.enqueue_refresh(
        trigger_type="data_ingested",
        pipeline_name="pipeline-listed",
        targets=["semantic.listed"],
        context={"data_domain": "products"},
    )

    rows = await service.list_tasks()
    assert len(rows) == 1
    assert rows[0].domain == "products"
    assert (await service.list_tasks(status="pending"))[0].id == rows[0].id
