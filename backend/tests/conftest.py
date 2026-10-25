"""
测试 Fixture 配置

- sqlite_session: 内存 SQLite, 快速异步单元测试
- pg_session: testcontainers PostgreSQL, 集成测试
- async_client: 带数据库依赖覆盖的 FastAPI AsyncClient
- auth_headers: Mock 认证头
"""

import asyncio
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

from modules.core.db import Base


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "pg_only: mark test to run only with PostgreSQL via testcontainers"
    )


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
