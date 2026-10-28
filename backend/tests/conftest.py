"""
测试 Fixture 配置

- sqlite_session: 内存 SQLite, 快速异步单元测试
- pg_session: testcontainers PostgreSQL, 集成测试
- async_client: 带数据库依赖覆盖的 FastAPI AsyncClient
- auth_headers: Mock 认证头
"""

import asyncio
import atexit
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

# ---------------------------------------------------------------------------
# 护栏: 测试绝不能连上真实业务库
# ---------------------------------------------------------------------------
#
# 为什么要这条护栏
# ----------------
# ``backend/utils/config.py`` 的 ``DATABASE_URL`` 默认值就是**真实业务库**
# (``postgresql://erp_user:...@localhost:15432/xihong_erp``), 仓库根的 ``.env``
# 里也是同一个地址。pytest 会加载 ``.env``, 于是**任何**导入了
# ``backend.models.database`` 的测试, 拿到的都是能直连真实库的 engine。
#
# 真实后果(2026-10-28 实测):
#   * 测试里跑了 ``scheduled_tasks.auto_ingest_pending_files``,
#     它用**真实库**的 ``SessionLocal`` 重检了 21 个真实文件,
#     把它们的持久化状态改回 ``template_update_required``,
#     还把其中一个文件刚回填的模板契约整块抹掉了。
#   * 脏数据进了真实库, 之后要靠人工回填才能恢复。
#
# 这类「测试写生产数据」的事故, 靠每次记得打桩是防不住的 ——
# 必须有一道**默认生效**的兜底: 测试期间把 ``DATABASE_URL`` 指向隔离库,
# 真的需要连库的测试用 ``pg_session``(testcontainers) 自己建库, 不受影响。
#
# 实现要点
# --------
# 1. 必须在**任何测试模块被导入之前**改掉环境变量 —— 因为
#    ``backend.models.database`` 在 import 时就会 ``create_engine(DATABASE_URL)``,
#    之后再改就晚了。所以这段放在 **conftest 模块顶层**(早于 collection),
#    而不是 ``pytest_configure`` —— 后者虽然也早, 但 conftest 自身的模块级
#    import 发生在它之前, 若那条 import 链拉起了 ``backend.utils.config``,
#    ``Settings.DATABASE_URL`` 这个**类属性**就已经在 import 时求值完了。
# 2. 隔离库是一个**一次性 PostgreSQL 容器**(testcontainers), 在这里就起好。
#    端口必须是**随机**的: 固定端口在上一次会话异常退出后会残留
#    (TimeWait / 端口被占), 下一次会话就起不来容器。
#    随机端口 + testcontainers 的 ryuk 回收, 才是可重复的。
# 3. 隔离库必须是 **PostgreSQL**: 本项目的表分布在 PG 的 schema 命名空间里
#    (``core`` / ``a_class`` / ...), SQLite 根本建不出来
#    (仓库自带的 ``sqlite_session`` fixture 就是因此一直是坏的)。
# 4. 同时设置 ``XIHONG_TEST_ENV_GUARD`` 标记, 让
#    ``backend.utils.project_env.load_project_env`` **不覆盖**护栏写好的隔离库地址 ——
#    否则 ``backend/main.py`` 里的 ``load_project_env(project_root)``
#    会把隔离库地址重新覆盖回 ``.env`` 里的真实业务库。
#
# 真实业务库地址(一旦匹配就说明护栏失效, 直接让测试失败):
_REAL_DB_MARKERS = ("@localhost:15432/", "@127.0.0.1:15432/", "@postgres:5432/")

from backend.utils.project_env import (  # noqa: E402  (必须早于 backend 其它模块)
    TEST_DATABASE_URL_VAR,
    TEST_ENV_GUARD_VAR,
)


def _start_isolated_postgres() -> str:
    """起一个一次性 PostgreSQL 容器并返回连接串。"""
    from testcontainers.postgres import PostgresContainer

    container = PostgresContainer("postgres:15")
    container.start()
    atexit.register(_stop_container_quietly, container)
    url = container.get_connection_url()
    # testcontainers 默认返回 ``postgresql+psycopg2://``, 去掉驱动后缀
    if url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://") :]
    return url


def _stop_container_quietly(container) -> None:
    try:
        container.stop()
    except Exception:
        pass


# [*] 护栏必须在任何 backend 模块被 import 之前生效。
# 隔离库地址写进**独立变量** ``XIHONG_TEST_DATABASE_URL``,
# ``config.py`` 在护栏开启时只认它, 连 ``DATABASE_URL`` 都不采信。
_ORIGINAL_DATABASE_URL = os.environ.get("DATABASE_URL")
os.environ[TEST_DATABASE_URL_VAR] = _start_isolated_postgres()
os.environ[TEST_ENV_GUARD_VAR] = "1"

from modules.core.db import Base  # noqa: E402  (必须晚于上面的护栏设置)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _is_real_database_url(url: str) -> bool:
    return any(marker in url for marker in _REAL_DB_MARKERS)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "pg_only: mark test to run only with PostgreSQL via testcontainers"
    )

    if _ORIGINAL_DATABASE_URL and _is_real_database_url(_ORIGINAL_DATABASE_URL):
        print(
            "\n[测试护栏] DATABASE_URL 已重定向到隔离库(一次性 PostgreSQL 容器)"
            "\n         真实业务库不会被测试读写；需要连库请用 pg_session fixture。\n"
        )


@pytest.fixture(scope="session", autouse=True)
def _assert_database_guard_active():
    """护栏自检 + 在隔离库里建出与生产一致的 schema。

    这是**最后一道防线**。护栏本身失效(比如有人改了 ``load_project_env``)
    时, 宁可让整个测试会话直接失败, 也不能让测试去读写真实数据 ——
    2026-10-28 就因为测试连上真实库, 把 21 个真实文件的入库状态改坏了。

    这里校验的是**引擎实际用的地址**(``backend.models.database.DATABASE_URL``),
    而不是环境变量 —— 环境变量对了但引擎建得早, 一样会连上真实库。
    """
    from backend.utils.project_env import is_test_env_guarded

    if not is_test_env_guarded():
        pytest.fail(
            "测试护栏未生效: XIHONG_TEST_ENV_GUARD 标记丢失。"
            "测试绝不允许连上真实业务库。"
        )

    env_url = os.environ.get(TEST_DATABASE_URL_VAR, "")
    if not env_url or _is_real_database_url(env_url):
        pytest.fail(
            f"测试护栏未生效: 隔离库地址异常 ({env_url})。"
            "测试绝不允许连上真实业务库。"
        )

    from backend.models.database import ASYNC_DATABASE_URL, DATABASE_URL as engine_url

    for label, url in (("同步 engine", engine_url), ("异步 engine", ASYNC_DATABASE_URL)):
        if _is_real_database_url(url):
            pytest.fail(
                f"测试护栏未生效: {label} 指向真实业务库 ({url})。"
                "测试绝不允许连上真实业务库。"
            )

    _create_isolated_schema(engine_url)
    yield


def _create_isolated_schema(database_url: str) -> None:
    """在隔离库里建出与生产一致的 schema(各命名空间 + 全部表)。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from backend.models.database import get_async_database_url

    async_url = get_async_database_url(database_url)
    engine = create_async_engine(async_url)

    async def _create():
        async with engine.begin() as conn:
            for schema_name in ("core", "a_class", "b_class", "c_class", "finance", "ops"):
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_create())
    finally:
        loop.close()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def clear_app_dependency_overrides():
    """Avoid cross-test leakage from FastAPI dependency overrides."""
    from backend.main import app

    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _restore_main_app_after_reload():
    """防止 ``importlib.reload(backend.main)`` 的用例把 app 泄漏给后续用例。

    ``backend/tests/test_runtime_mode_route_registration.py`` 与
    ``test_shop_directory_api.py`` 会用 ``APP_RUNTIME_MODE`` 重载 ``backend.main``。
    reload 会**重新执行模块体**, 于是 ``backend.main.app`` 变成一个
    「按该模式注册路由」的**新对象**:
    production 模式只注册 production 路由, 采集路由不在其中。

    重载之后不恢复的话, 后续用例请求 ``/api/collection/*`` 会直接 404 ——
    实测 ``test_task_center_collection_projection.py`` 就被这样带崩
    (单独跑通过, 放在全量里就失败)。
    """
    import sys

    main_module = sys.modules.get("backend.main")
    if main_module is None:
        yield
        return

    original_app = getattr(main_module, "app", None)
    yield
    if original_app is not None and getattr(main_module, "app", None) is not original_app:
        main_module.app = original_app


@pytest_asyncio.fixture
async def sqlite_session() -> AsyncGenerator[AsyncSession, None]:
    """基于内存 SQLite 的异步 Session, 适用于快速单元测试。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def pg_engine():
    """基于 testcontainers 的 PostgreSQL Engine（会话级别）。"""
    try:
        from testcontainers.postgres import PostgresContainer  # type: ignore
    except ImportError:
        pytest.skip("testcontainers[postgres] 未安装, 跳过 pg_only 测试")

    from urllib.parse import urlparse, urlunparse

    with PostgresContainer("postgres:15") as pg:
        sync_url = pg.get_connection_url()
        parsed = urlparse(sync_url)
        # 无论原始驱动是什么(可能是 postgresql+psycopg2), 强制使用 asyncpg
        parsed = parsed._replace(scheme="postgresql+asyncpg")
        async_url = urlunparse(parsed)

        engine = create_async_engine(async_url, echo=False)

        async with engine.begin() as conn:
            # 创建项目使用的 schema, 避免 JSONB / schema 不存在等错误
            from sqlalchemy import text

            for schema_name in ("core", "a_class", "b_class", "c_class", "finance", "ops"):
                await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))

            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_engine) -> AsyncGenerator[AsyncSession, None]:
    """每个测试用例独立的 PostgreSQL Session, 用于集成测试。"""
    session_factory = async_sessionmaker(pg_engine, expire_on_commit=False)

    async with session_factory() as session:
        await session.begin()
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def async_client(
    sqlite_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """带有 get_async_db 覆盖的 AsyncClient, 走内存 SQLite。"""
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield sqlite_session

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def pg_async_client(
    pg_session: AsyncSession,
) -> AsyncGenerator[AsyncClient, None]:
    """FastAPI AsyncClient backed by PostgreSQL testcontainer session."""
    from backend.main import app
    from backend.models.database import get_async_db

    async def override_get_async_db():
        yield pg_session

    app.dependency_overrides[get_async_db] = override_get_async_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Mock 认证头, 并覆盖 get_current_user 依赖。"""
    from backend.main import app
    from backend.dependencies.auth import get_current_user

    class _MockUser:
        id = 1
        username = "test_admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    app.dependency_overrides[get_current_user] = override_current_user

    return {"Authorization": "Bearer test-token-for-unit-tests"}


@pytest_asyncio.fixture
async def pricing_auth_headers(pg_session):
    """带 user_id 的 mock 用户——没有 user_id 审计不会落库。"""
    from backend.main import app
    from backend.dependencies.auth import get_current_user

    class _MockUser:
        id = 1
        user_id = 1
        username = "test_admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    app.dependency_overrides[get_current_user] = override_current_user
    yield {}
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# SKU 定价底线：共用种子与清理
# ---------------------------------------------------------------------------

PRICING_SEED_CLEANUP_SQL = (
    # 子表先删，父表后删（FK 顺序）
    "DELETE FROM ops.feishu_projection_tasks "
    "WHERE business_key = '9001' "
    "OR business_key IN (SELECT profile_id::text FROM finance.sku_operating_profiles WHERE sku_id = 9001)",
    "DELETE FROM finance.sku_profit_estimates WHERE sku_id = 9001",
    # 审计：resource_id 有三种形态——纯 sku_id、平台 code、
    # 以及草稿/利润版本的复合 key（"tiktok:MY-01:9001"），所以用 user_id 兜底
    "DELETE FROM public.fact_audit_logs "
    "WHERE user_id = 1 OR resource_id = '9001' OR resource_id = 'tiktok' "
    "OR resource_id LIKE '%9001%' OR resource_type = 'sku_pricing_policy'",
    "DELETE FROM finance.sku_operating_profiles WHERE sku_id = 9001",
    "DELETE FROM finance.sku_pricing_policies",
    "DELETE FROM finance.logistics_provider_rules WHERE logistics_provider = 'TEST-LOG'",
    "DELETE FROM finance.warehouse_storage_rules WHERE warehouse_code = 'MY-01'",
    "DELETE FROM core.bridge_spu_sku WHERE sku_id = 9001",
    "DELETE FROM core.dim_erp_sku WHERE sku_id = 9001",
    "DELETE FROM core.dim_spu WHERE spu = 'TEST-SPU-1'",
    "DELETE FROM core.dim_warehouses WHERE warehouse_code = 'MY-01'",
    "DELETE FROM core.dim_platforms WHERE platform_code = 'tiktok'",
    "DELETE FROM core.dim_users WHERE user_id = 1",
)


async def _seed_pricing_fixtures(pg_session, *, with_cost_rules: bool = True):
    """种下商品中心定价底线相关的最小数据集。

    ⚠️ **必须按 FK 依赖顺序逐个 flush**：
    SQLAlchemy 的 unit-of-work 排 INSERT 顺序只认 `relationship()` 派生的 mapper 依赖，
    **不认裸 `ForeignKey` 约束**（裸 FK 只影响 DDL 排序）。实测
    `LogisticsProviderRule` / `WarehouseStorageRule` / `BridgeSpuSku` 的
    `__mapper__.relationships` 都是 `[]`，一次 flush 会让
    `core.dim_warehouses` / `core.dim_spu` 排在规则表之前 →
    `ForeignKeyViolationError: Key (warehouse_code)=(MY-01) is not present in table "dim_warehouses"`。

    `with_cost_rules=False` 构造「缺物流规则 / 缺仓储规则」的场景，
    用来验证**护栏排在缺资料校验之前**——用完整 seed 时 `missing_fields` 恒为 `[]`，
    那条断言永远观察不到差别。
    """
    from datetime import date

    from modules.core.db import (
        BridgeSpuSku, DimErpSku, DimPlatform, DimSpu, DimUser, DimWarehouse,
        LogisticsProviderRule, SkuPricingPolicy, WarehouseStorageRule,
    )

    effective_from = date(2026, 1, 1)

    pg_session.add(DimUser(
        user_id=1, username="test_admin",
        email="test_admin@example.com", password_hash="not-a-real-hash",
    ))
    await pg_session.flush()

    pg_session.add(DimPlatform(
        platform_code="tiktok", name="TikTok", platform_role="sales", is_active=True,
        default_fee_rate=0.0737,
        default_creator_commission_rate=0.0606,
        other_cost_rate=0.2727,
        # 刻意给一个**非今日**的生效日期：用来验证「部分更新」不会把它刷成当天
        fee_rate_effective_from=date(2026, 9, 1),
        fee_rate_source="test_seed",
        fee_rate_version="v0",
    ))
    await pg_session.flush()

    pg_session.add(DimWarehouse(
        warehouse_code="MY-01", warehouse_name="主仓",
        country_code="MY", country_name="马来西亚", status="active",
    ))
    await pg_session.flush()

    pg_session.add(DimSpu(
        spu="TEST-SPU-1", spu_name="测试SPU",
        return_loss_rate=0.0467, logistics_damage_rate=0.0158,
    ))
    await pg_session.flush()

    pg_session.add(DimErpSku(
        sku_id=9001, sku_key="TEST-SKU-1", sku_name="测试SKU",
        status="active", default_purchase_cost=10, reference_selling_price=30,
        weight_kg=0.5, unit_volume_cbm=0.01, turnover_class="slow",
    ))
    await pg_session.flush()

    pg_session.add(BridgeSpuSku(
        sku_id=9001, spu="TEST-SPU-1", binding_status="active",
        effective_from=effective_from,
    ))
    await pg_session.flush()

    # 库龄档位规则：缺这 4 行 -> 最低售价算不出来 -> 护栏永不触发
    for min_restock_days, tier_label, discount_rate, target_margin_rate in (
        (0, "日常", 0.10, 0.25),
        (60, "滞销30天", 0.15, 0.22),
        (90, "滞销60天", 0.20, 0.18),
        (120, "滞销60天以上", 0.30, 0.10),
    ):
        pg_session.add(SkuPricingPolicy(
            min_restock_days=min_restock_days, tier_label=tier_label,
            discount_rate=discount_rate, target_margin_rate=target_margin_rate,
            platform_basis="tiktok", effective_from=effective_from,
            status="active", source="test_seed", version="v1",
        ))
    await pg_session.flush()

    if with_cost_rules:
        # ⚠️ billing_unit 必须用仓库 CHECK 约束要求的值：
        #   WarehouseStorageRule -> 'CNY/CBM/month'（ck_warehouse_storage_rules_unit）
        #   LogisticsProviderRule -> 'CNY/CBM'（与仓库既有迁移口径一致）
        # 写成 'cbm' 会撞 CheckViolationError
        pg_session.add(LogisticsProviderRule(
            logistics_provider="TEST-LOG", warehouse_code="MY-01", transport_type="sea",
            status="active", is_sensitive=False, is_default=True, currency="CNY",
            billing_basis="volume", billing_unit="CNY/CBM", freight_unit_rate=5,
            effective_from=effective_from,
        ))
        pg_session.add(WarehouseStorageRule(
            warehouse_code="MY-01", billing_basis="volume", billing_unit="CNY/CBM/month",
            unit_rate_cny=100, label_fee=0.5, status="active",
            effective_from=effective_from,
        ))
        await pg_session.flush()


@pytest_asyncio.fixture
async def pricing_seed(pg_session):
    """返回「种数据」的协程；用例结束后自动清理干净。

    ⚠️ **必须清理**：pg 容器是 **session 级**的，而端点内部会 `db.commit()`——
    种下去的行会被**提交**，不会��� pg_session 的 teardown `rollback()` 掉。
    不清理的话，下一个用例种同样的主键会撞
    `UniqueViolationError: duplicate key value violates unique constraint "dim_users_pkey"`。
    """
    from sqlalchemy import text

    async def _seed(*, with_cost_rules: bool = True):
        await _seed_pricing_fixtures(pg_session, with_cost_rules=with_cost_rules)

    yield _seed

    for sql in PRICING_SEED_CLEANUP_SQL:
        await pg_session.execute(text(sql))
    await pg_session.commit()
