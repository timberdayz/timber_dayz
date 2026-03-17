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

from modules.core.db import Base


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "pg_only: mark test to run only with PostgreSQL via testcontainers"
    )


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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

            for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
                await conn.execute(
                    text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
                )

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


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Mock 认证头, 并覆盖 get_current_user 依赖。"""
    from backend.main import app
    from backend.dependencies.auth import get_current_user

    class _MockUser:
        id = 1
        username = "test_admin"
        is_active = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    app.dependency_overrides[get_current_user] = override_current_user

    return {"Authorization": "Bearer test-token-for-unit-tests"}

