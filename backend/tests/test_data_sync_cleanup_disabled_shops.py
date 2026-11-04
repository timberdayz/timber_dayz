"""清理重采时**停用店不参与**：停用店的采集文件不再排进重采队列。

背景
----
生产 52 个店铺账号里有 33 个是停用状态（32 个 shopee + 1 个测试账号），
它们的历史采集文件还躺在 ``public.catalog_files`` 里（实测 18 行）。

以前清空事实数据时，这些文件会被**一起**重置成 ``pending`` ⇒ 重采去连那些
已经停掉的店铺账号：一方面白跑采集，另一方面又把停用店的数据灌回事实表。

口径
----
- 停用店判定：``core.shop_accounts.enabled IS NOT TRUE``
- 身份键：平台店铺ID / 业务店铺ID / 账号主键 **三种都收**
  （采集文件上的 shop_id 可能落在任意一种上，漏一个就等于漏掉一批停用店）
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.services.data_sync_cleanup_service import DataSyncCleanupService
from modules.core.db import CatalogFile, ShopAccount


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def cleanup_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        for schema_name in ("core", "a_class", "b_class", "c_class", "finance"):
            await conn.execute(text(f"ATTACH DATABASE ':memory:' AS {schema_name}"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(ShopAccount.__table__.create)
        await conn.execute(
            text(
                """
                CREATE TABLE b_class.fact_tiktok_orders_weekly (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    order_id VARCHAR(128)
                )
                """
            )
        )

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _catalog_file(**kwargs) -> CatalogFile:
    defaults = {
        "file_path": "/tmp/data.csv",
        "file_name": "data.csv",
        "platform_code": "shopee",
        "shop_id": "12345",
        "status": "ingested",
    }
    defaults.update(kwargs)
    return CatalogFile(**defaults)


def _write_source_file(tmp_path: Path, name: str) -> tuple[str, str]:
    """在磁盘上造出「原始文件 + 伴生 meta 文件」。

    清理服务只在「文件与 meta 都在」时才把状态重置成 pending（排进重采队列）；
    文件不在 ⇒ 标记 source_missing（没法自动重建）。所以要测重采路径必须造真文件。
    """
    data_path = tmp_path / name
    data_path.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    meta_path = tmp_path / f"{name}.meta.json"
    meta_path.write_text("{}", encoding="utf-8")
    return str(data_path), str(meta_path)


def _shop_account(**kwargs) -> ShopAccount:
    defaults = {
        "platform": "shopee",
        "shop_account_id": "shopee_xx_yy",
        "main_account_id": "main_1",
        "store_name": "xx.yy",
        "platform_shop_id": "12345",
        "enabled": True,
    }
    defaults.update(kwargs)
    return ShopAccount(**defaults)


@pytest.mark.asyncio
async def test_disabled_shop_files_are_not_requeued(cleanup_session, tmp_path) -> None:
    """停用店的采集文件不重置成 pending。"""
    dead_path, dead_meta = _write_source_file(tmp_path, "dead.csv")
    alive_path, alive_meta = _write_source_file(tmp_path, "alive.csv")
    cleanup_session.add(
        _shop_account(
            platform_shop_id="99999",
            shop_account_id="shopee_dead_1",
            enabled=False,
        )
    )
    cleanup_session.add(
        _catalog_file(
            shop_id="99999",
            platform_shop_id="99999",
            status="ingested",
            file_path=dead_path,
            meta_file_path=dead_meta,
        )
    )
    cleanup_session.add(
        _catalog_file(
            shop_id="88888",
            platform_shop_id="88888",
            status="ingested",
            file_path=alive_path,
            meta_file_path=alive_meta,
        )
    )
    await cleanup_session.commit()

    service = DataSyncCleanupService(cleanup_session)
    result = await service.cleanup_database()

    assert result["skipped_disabled_shop_count"] == 1
    assert result["reset_files_count"] == 1

    from sqlalchemy import select

    rows = (
        (
            await cleanup_session.execute(
                select(CatalogFile).order_by(CatalogFile.shop_id)
            )
        )
        .scalars()
        .all()
    )
    statuses = {row.shop_id: row.status for row in rows}
    # 停用店的文件保持原状态，不进重采队列
    assert statuses["99999"] == "ingested"
    # 启用店的文件正常排进重采
    assert statuses["88888"] == "pending"


@pytest.mark.asyncio
async def test_disabled_shop_is_matched_by_every_identity_key(cleanup_session) -> None:
    """三种身份键（平台店铺ID / 业务店铺ID / 账号主键）都要能识别停用店。"""
    disabled = _shop_account(
        id=4321,
        platform_shop_id="70001",
        shop_account_id="shopee_dead_2",
        enabled=False,
    )
    cleanup_session.add(disabled)
    cleanup_session.add(
        _catalog_file(shop_id="70001", platform_shop_id="70001", status="ingested")
    )
    cleanup_session.add(_catalog_file(shop_id="shopee_dead_2", status="ingested"))
    cleanup_session.add(_catalog_file(shop_id="4321", status="ingested"))
    await cleanup_session.commit()

    service = DataSyncCleanupService(cleanup_session)
    result = await service.cleanup_database()

    assert result["skipped_disabled_shop_count"] == 3
    assert result["reset_files_count"] == 0


@pytest.mark.asyncio
async def test_enabled_shops_are_still_requeued(cleanup_session, tmp_path) -> None:
    """启用店照常排重采（别把过滤做过头）。"""
    alive_path, alive_meta = _write_source_file(tmp_path, "alive2.csv")
    cleanup_session.add(
        _shop_account(
            platform_shop_id="55555",
            shop_account_id="shopee_alive_1",
            enabled=True,
        )
    )
    cleanup_session.add(
        _catalog_file(
            shop_id="55555",
            platform_shop_id="55555",
            status="ingested",
            file_path=alive_path,
            meta_file_path=alive_meta,
        )
    )
    await cleanup_session.commit()

    service = DataSyncCleanupService(cleanup_session)
    result = await service.cleanup_database()

    assert result["skipped_disabled_shop_count"] == 0
    assert result["reset_files_count"] == 1


@pytest.mark.asyncio
async def test_missing_shop_accounts_table_degrades_gracefully(
    cleanup_session,
    tmp_path,
) -> None:
    """店铺账号表读不到时退化成「没有已知停用店」，不抛错、不阻断清理。"""
    from sqlalchemy import delete

    alive_path, alive_meta = _write_source_file(tmp_path, "alive3.csv")
    await cleanup_session.execute(delete(ShopAccount))
    await cleanup_session.commit()
    cleanup_session.add(
        _catalog_file(
            shop_id="77777",
            platform_shop_id="77777",
            status="ingested",
            file_path=alive_path,
            meta_file_path=alive_meta,
        )
    )
    await cleanup_session.commit()

    service = DataSyncCleanupService(cleanup_session)
    result = await service.cleanup_database()

    assert result["reset_files_count"] == 1
    assert result["skipped_disabled_shop_count"] == 0
