#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模板族目录缓存的行为测试。

对应的问题(2026-10-29): 治理看板一次要解析 27 个组合, 每个组合的解析会递归
展开成 ``get_family_versions`` / ``get_version_variants`` / ``list_families``,
实测一次请求打出 3 万多次查询 + 1.5 万次 commit ⇒ 13~17 秒。
现在靠**进程内目录缓存**压掉, 但缓存必须满足两条:

1. **命中**: 同一个组合重复解析不再打数据库;
2. **目录一变立即作废**: 模板目录(模板/族/版本/变体)或 catalog_files 一被写,
   缓存立刻作废 —— 绝不能给出过期答案。

用 SQLite 内存库(照 ``test_template_family_api.py`` 的写法): 引擎是**函数级**的,
不会踩「session 级 engine 跨 event loop」的坑。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import event as sa_event
from sqlalchemy import text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import (
    CatalogFile,
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest_asyncio.fixture
async def family_session_factory():
    """函数级的 SQLite 内存库(带 core schema)。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)
        await conn.run_sync(FieldMappingTemplateFamily.__table__.create)
        await conn.run_sync(FieldMappingTemplateVersion.__table__.create)
        await conn.run_sync(FieldMappingTemplateVariant.__table__.create)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory, engine
    await engine.dispose()


@pytest.fixture(autouse=True)
def _clean_catalog_cache():
    """每个用例从「缓存全空」开始。"""
    from backend.services.template_family_service import clear_template_catalog_cache

    clear_template_catalog_cache()
    yield
    clear_template_catalog_cache()


@pytest_asyncio.fixture
async def seeded_family(family_session_factory):
    """种一个最小的模板族: 1 个已发布模板 ⇒ 1 个 family。"""
    factory, _engine = family_session_factory
    now = datetime.now(timezone.utc)
    async with factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="orders",
                granularity="weekly",
                sub_domain=None,
                template_name="tiktok_orders__weekly_cache_v1",
                version=1,
                status="published",
                header_row=1,
                header_columns=["订单编号", "金额"],
                created_at=now,
                updated_at=now,
            )
        )
        await session.commit()
    return factory


def _watch_sql(engine) -> list[str]:
    """挂一个统计器, 收集执行过的 SQL。"""
    seen: list[str] = []

    @sa_event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    return seen


@pytest.mark.asyncio
async def test_repeated_list_families_hits_cache(seeded_family, family_session_factory):
    """重复解析同一个组合: 第二次不再打数据库。

    注意第一次调用会**建出投影**(family/version/variant)⇒ 那次写库会让缓存作废,
    所以先热身一次, 再量第二次。
    """
    from backend.services.template_family_service import TemplateFamilyService

    factory, engine = family_session_factory
    seen = _watch_sql(engine)

    async with factory() as session:
        service = TemplateFamilyService(session)
        first = await service.list_families(platform="tiktok", data_domain="orders")
        assert first, "应至少有一个模板族"

        # 热身: 投影已建好, 这次之后再写就不会有了
        await service.list_families(platform="tiktok", data_domain="orders")
        queries_after_warmup = len(seen)

        second = await service.list_families(platform="tiktok", data_domain="orders")

    assert len(second) == len(first)
    assert len(seen) == queries_after_warmup, (
        f"稳定之后解析应当命中缓存, 但仍执行了 {len(seen) - queries_after_warmup} 条 SQL"
    )


@pytest.mark.asyncio
async def test_catalog_write_invalidates_cache(seeded_family, family_session_factory):
    """模板目录一被写 ⇒ 缓存立即作废(下一次解析重新打库)。"""
    from backend.services.template_family_service import TemplateFamilyService

    factory, engine = family_session_factory
    seen = _watch_sql(engine)

    async with factory() as session:
        service = TemplateFamilyService(session)
        await service.list_families(platform="tiktok", data_domain="orders")
        baseline = len(seen)

        # 写一次模板目录(改备注)⇒ 目录变了
        await session.execute(
            update(FieldMappingTemplate)
            .where(FieldMappingTemplate.platform == "tiktok")
            .values(notes="cache-invalidation-probe")
        )
        await session.commit()

        await service.list_families(platform="tiktok", data_domain="orders")

    assert len(seen) > baseline, "目录写入后缓存必须作废, 下一次解析应重新查库"


@pytest.mark.asyncio
async def test_catalog_file_write_invalidates_cache(seeded_family, family_session_factory):
    """catalog_files 一被写 ⇒ 文件计数过期 ⇒ 缓存作废。"""
    from backend.services import template_family_service as tfs
    from backend.services.template_family_service import TemplateFamilyService

    factory, engine = family_session_factory

    async with factory() as session:
        service = TemplateFamilyService(session)
        await service.list_families(platform="tiktok", data_domain="orders")

        before = tfs._FILE_GENERATION
        await session.execute(
            update(CatalogFile).where(CatalogFile.id < 0).values(file_name="__probe__")
        )
        await session.commit()

    assert tfs._FILE_GENERATION > before, "catalog_files 写入应让文件计数缓存作废"
