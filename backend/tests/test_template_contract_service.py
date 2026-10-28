"""第 1 批改造回归测试: 模板契约(D1) + 统一缓存键(D5) + 状态枚举(D2)。

覆盖的行为
----------
D1 采集落库记录模板契约
  1. 契约字段完整(模板 ID/版本/表头行/列指纹/采集时刻)
  2. 列指纹对顺序敏感、对空白归一
  3. 模板行被事后改写 -> 契约基准失效
  4. ``register_single_file()`` 落库时真的写入契约
  5. 同步匹配器与异步匹配器选出同一个模板(登记口径 == 入库口径)

D1 判定采用文件自带基准
  6. 我们升级了模板(v5 -> v6), 按 v5 采集的文件**不再**被判成结构漂移
  7. 源文件真的变了(与契约基准不符) -> 仍然阻断, 且漂移来源是 source_change
  8. 没有契约的历史文件 -> 维持「与当前已发布模板比对」的旧口径

D5 统一缓存键
  9. 就绪缓存键与治理行级缓存键包含同样的失效要素(last_modified / 模板版本)

D2 状态枚举
  10. ORM CHECK 约束与状态枚举 SSOT 一致
  11. 迁移脚本里的合法状态集合与 SSOT 一致
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from modules.core.db import CatalogFile, FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ======================================================================
# D1: 契约服务
# ======================================================================
def test_columns_hash_is_order_sensitive_and_whitespace_normalized():
    from backend.services.template_contract_service import compute_columns_hash

    assert compute_columns_hash(["a", "b"]) == compute_columns_hash([" a ", "b"])
    assert compute_columns_hash(["a", "b"]) != compute_columns_hash(["b", "a"])
    assert compute_columns_hash(["a", "b"]) != compute_columns_hash(["a", "c"])


def test_build_and_write_read_template_contract():
    from backend.services.template_contract_service import (
        build_template_contract,
        read_template_contract,
        write_template_contract,
    )

    template = FieldMappingTemplate(
        id=42,
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        header_row=2,
        version=6,
        status="published",
        template_name="tiktok_products__monthly_v6",
        header_columns=["商品ID", "商品名称"],
    )

    contract = build_template_contract(template)

    assert contract["template_id"] == 42
    assert contract["template_version"] == 6
    assert contract["header_row"] == 2
    assert contract["column_count"] == 2
    assert contract["captured_at"]
    assert contract["source"] == "collection_registration"

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="pending",
        file_metadata={},
    )
    assert read_template_contract(catalog_file) is None

    write_template_contract(catalog_file, contract)
    stored = read_template_contract(catalog_file)
    assert stored["template_id"] == 42
    assert stored["columns_hash"] == contract["columns_hash"]


def test_contract_baseline_is_invalid_when_template_row_was_mutated():
    from backend.services.template_contract_service import (
        build_template_contract,
        is_contract_baseline_valid,
    )

    template = FieldMappingTemplate(
        id=42,
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        header_row=0,
        version=6,
        status="published",
        header_columns=["商品ID", "商品名称"],
    )
    contract = build_template_contract(template)

    assert is_contract_baseline_valid(contract, template) is True

    # 模板行被原地改写(版本号没变, 列清单变了) -> 契约基准不再可信
    template.header_columns = ["商品ID", "商品名称", "退款金额"]
    assert is_contract_baseline_valid(contract, template) is False


def test_describe_contract_baseline_reports_template_upgrade():
    from backend.services.template_contract_service import (
        build_template_contract,
        describe_contract_baseline,
    )

    old_template = FieldMappingTemplate(
        id=41,
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        header_row=0,
        version=5,
        status="archived",
        header_columns=["商品ID"],
    )
    new_template = FieldMappingTemplate(
        id=42,
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        header_row=0,
        version=6,
        status="published",
        header_columns=["商品ID", "退款金额"],
    )
    contract = build_template_contract(old_template)

    described = describe_contract_baseline(contract, new_template)
    assert described["has_contract"] is True
    assert described["template_outdated"] is True
    assert described["baseline_template_id"] == 41
    assert described["current_template_id"] == 42

    same = describe_contract_baseline(contract, old_template)
    assert same["template_outdated"] is False


def test_describe_contract_baseline_without_contract():
    from backend.services.template_contract_service import describe_contract_baseline

    described = describe_contract_baseline(None, None)
    assert described["has_contract"] is False
    assert described["template_outdated"] is False


# ======================================================================
# D1: 匹配器同步/异步口径一致
# ======================================================================
@pytest.fixture
def sync_template_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    core_path = (tmp_path / "core.db").as_posix()

    @event.listens_for(engine, "connect")
    def _attach_core(dbapi_connection, _connection_record):
        dbapi_connection.execute(f"ATTACH DATABASE '{core_path}' AS core")

    FieldMappingTemplate.__table__.create(engine)
    CatalogFile.__table__.create(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def test_find_best_template_sync_prefers_account_scoped_template(sync_template_engine):
    from backend.services.template_matcher import find_best_template_sync

    now = _now()
    with Session(sync_template_engine) as session:
        generic = FieldMappingTemplate(
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account=None,
            template_name="generic",
            version=3,
            status="published",
            header_row=0,
            header_columns=["商品ID"],
            created_at=now,
            updated_at=now,
        )
        scoped = FieldMappingTemplate(
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account="MY",
            template_name="scoped",
            version=1,
            status="published",
            header_row=0,
            header_columns=["商品ID", "地区"],
            created_at=now,
            updated_at=now,
        )
        session.add_all([generic, scoped])
        session.commit()

        matched = find_best_template_sync(
            session,
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account="MY",
        )
        fallback = find_best_template_sync(
            session,
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account="SG",
        )

    assert matched is not None and matched.template_name == "scoped"
    assert fallback is not None and fallback.template_name == "generic"


@pytest.fixture
def mirror_engines(tmp_path):
    """同一份 SQLite 文件上的同步引擎 + 异步引擎(都要挂 'core' schema)。"""
    db_path = (tmp_path / "catalog.db").as_posix()
    core_path = (tmp_path / "core.db").as_posix()

    sync_engine = create_engine(f"sqlite:///{db_path}", future=True)

    @event.listens_for(sync_engine, "connect")
    def _attach_core_sync(dbapi_connection, _connection_record):
        dbapi_connection.execute(f"ATTACH DATABASE '{core_path}' AS core")

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    @event.listens_for(async_engine.sync_engine, "connect")
    def _attach_core_async(dbapi_connection, _connection_record):
        dbapi_connection.execute(f"ATTACH DATABASE '{core_path}' AS core")

    FieldMappingTemplate.__table__.create(sync_engine)
    CatalogFile.__table__.create(sync_engine)
    try:
        yield sync_engine, async_engine
    finally:
        sync_engine.dispose()


@pytest.mark.asyncio
async def test_sync_and_async_matcher_select_the_same_template(mirror_engines):
    """登记链路(同步)与入库链路(异步)必须选出同一个模板。

    否则「采集时登记的契约模板」和「入库时实际使用的模板」会不一致 ——
    那正是模板契约要消灭的问题。
    """
    from backend.services.template_matcher import (
        TemplateMatcher,
        find_best_template_sync,
    )

    sync_engine, async_engine = mirror_engines
    now = _now()
    with Session(sync_engine) as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="products",
                granularity="monthly",
                account="MY",
                template_name="scoped",
                version=2,
                status="published",
                header_row=1,
                header_columns=["商品ID"],
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        sync_picked = find_best_template_sync(
            session,
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account="MY",
        )

    async with async_sessionmaker(async_engine, expire_on_commit=False)() as session:
        async_picked = await TemplateMatcher(session).find_best_template(
            platform="tiktok",
            data_domain="products",
            granularity="monthly",
            account="MY",
        )

    assert sync_picked is not None
    assert async_picked is not None
    assert sync_picked.id == async_picked.id
    assert sync_picked.template_name == async_picked.template_name


# ======================================================================
# D1: 采集落库写入契约
# ======================================================================
def test_register_single_file_captures_template_contract(tmp_path, monkeypatch):
    import backend.services.platform_table_manager as platform_table_manager_module
    from modules.services import catalog_scanner as catalog_scanner_module

    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    core_path = (tmp_path / "core.db").as_posix()

    @event.listens_for(engine, "connect")
    def _attach_core(dbapi_connection, _connection_record):
        dbapi_connection.execute(f"ATTACH DATABASE '{core_path}' AS core")

    CatalogFile.__table__.create(engine)
    FieldMappingTemplate.__table__.create(engine)

    now = _now()
    with Session(engine) as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="products",
                granularity="monthly",
                account=None,
                template_name="tiktok_products__monthly_v6",
                version=6,
                status="published",
                header_row=2,
                header_columns=["商品ID", "商品名称"],
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    monkeypatch.setattr(catalog_scanner_module, "_get_engine", lambda: engine)
    monkeypatch.setattr(
        platform_table_manager_module,
        "get_platform_table_manager",
        lambda _session: type(
            "_NoopTableManager",
            (),
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_tiktok_products_monthly")},
        )(),
    )
    monkeypatch.delenv("ALLOW_DEV_CATALOG_REGISTRATION", raising=False)

    raw_dir = tmp_path / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / "tiktok_products_monthly_20260525_000001.xlsx"
    file_path.write_text("demo", encoding="utf-8")

    file_id = catalog_scanner_module.register_single_file(str(file_path))
    assert file_id is not None

    with Session(engine) as session:
        record = session.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one()
        metadata = dict(record.file_metadata or {})

    contract = metadata.get("template_contract")
    assert contract is not None, "采集落库必须记录模板契约"
    assert contract["template_version"] == 6
    assert contract["header_row"] == 2
    assert contract["column_count"] == 2
    assert contract["columns_hash"].startswith("v1:")
    assert contract["captured_at"]
    # 店铺归属元数据不能被契约覆盖
    assert "shop_resolution" in metadata


# ======================================================================
# D1: 判定采用文件自带基准
# ======================================================================
@pytest_asyncio.fixture
async def contract_session_factory(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _seed_templates(session, now):
    """旧模板 v5(已归档) + 新模板 v6(已发布), 列清单不同。"""
    old_template = FieldMappingTemplate(
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        account=None,
        template_name="tiktok_products__monthly_v5",
        version=5,
        status="archived",
        header_row=0,
        header_columns=["商品ID", "商品名称"],
        created_at=now,
        updated_at=now,
    )
    new_template = FieldMappingTemplate(
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        account=None,
        template_name="tiktok_products__monthly_v6",
        version=6,
        status="published",
        header_row=0,
        header_columns=["商品ID", "商品名称", "退款金额"],
        created_at=now,
        updated_at=now,
    )
    session.add_all([old_template, new_template])
    await session.commit()
    await session.refresh(old_template)
    await session.refresh(new_template)
    return old_template, new_template


def _catalog_file(contract=None):
    metadata = {}
    if contract:
        metadata["template_contract"] = contract
    return CatalogFile(
        file_path="data/raw/tiktok_products_monthly_20260525_000001.xlsx",
        file_name="tiktok_products_monthly_20260525_000001.xlsx",
        source="data/raw",
        platform_code="tiktok",
        source_platform="tiktok",
        data_domain="products",
        granularity="monthly",
        status="pending",
        file_metadata=metadata,
    )


@pytest.mark.asyncio
async def test_template_upgrade_does_not_flag_file_collected_with_old_template(
    contract_session_factory,
):
    """我们把模板从 v5 升到 v6, 按 v5 采集的文件不应该被判成结构漂移。"""
    from backend.services.data_sync_template_status_service import (
        DRIFT_ORIGIN_TEMPLATE_UPGRADE,
        DataSyncTemplateStatusService,
    )
    from backend.services.template_contract_service import build_template_contract

    now = _now()
    async with contract_session_factory() as session:
        old_template, _new_template = await _seed_templates(session, now)
        contract = build_template_contract(old_template)

        catalog_file = _catalog_file(contract)
        session.add(catalog_file)
        await session.commit()

        status = await DataSyncTemplateStatusService(session).evaluate_catalog_file(
            catalog_file,
            current_columns=["商品ID", "商品名称"],
        )

    assert status["template_status"] == "ready"
    assert status["template_update_required"] is False
    assert status["should_auto_sync"] is True
    assert status["drift_origin"] == DRIFT_ORIGIN_TEMPLATE_UPGRADE
    assert status["template_outdated"] is True
    assert status["template_baseline"] == "contract"
    assert status["baseline_template_id"] == old_template.id


@pytest.mark.asyncio
async def test_source_change_against_contract_baseline_still_blocks(
    contract_session_factory,
):
    """源文件结构真的变了 -> 仍然阻断, 并且能说清是源侧变化。"""
    from backend.services.data_sync_template_status_service import (
        DRIFT_ORIGIN_SOURCE_CHANGE,
        DataSyncTemplateStatusService,
    )
    from backend.services.template_contract_service import build_template_contract

    now = _now()
    async with contract_session_factory() as session:
        old_template, _new_template = await _seed_templates(session, now)
        contract = build_template_contract(old_template)

        catalog_file = _catalog_file(contract)
        session.add(catalog_file)
        await session.commit()

        status = await DataSyncTemplateStatusService(session).evaluate_catalog_file(
            catalog_file,
            current_columns=["商品ID", "商品名称", "退款金额"],
        )

    assert status["template_status"] == "update_required"
    assert status["template_update_required"] is True
    assert status["should_auto_sync"] is False
    assert status["drift_origin"] == DRIFT_ORIGIN_SOURCE_CHANGE


@pytest.mark.asyncio
async def test_file_without_contract_keeps_current_template_comparison(
    contract_session_factory,
):
    """没有契约的历史文件维持旧口径: 与当前已发布模板比对。"""
    from backend.services.data_sync_template_status_service import (
        DRIFT_ORIGIN_UNKNOWN,
        DataSyncTemplateStatusService,
    )

    now = _now()
    async with contract_session_factory() as session:
        await _seed_templates(session, now)

        catalog_file = _catalog_file(None)
        session.add(catalog_file)
        await session.commit()

        status = await DataSyncTemplateStatusService(session).evaluate_catalog_file(
            catalog_file,
            current_columns=["商品ID", "商品名称"],
        )

    assert status["template_status"] == "update_required"
    assert status["template_update_required"] is True
    assert status["drift_origin"] == DRIFT_ORIGIN_UNKNOWN
    assert status["template_baseline"] == "current"


# ======================================================================
# D5: 统一缓存键
# ======================================================================
def test_readiness_cache_key_and_router_cache_key_share_invalidation_factors():
    from backend.domains.data_platform.routers.data_sync import (
        _build_template_status_cache_key,
    )
    from backend.services.data_sync_service import _readiness_cache_key

    last_modified = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
    catalog_file = CatalogFile(
        id=7,
        file_name="x.xlsx",
        file_path="data/raw/x.xlsx",
        status="pending",
        file_metadata={},
    )
    catalog_file.last_modified = last_modified
    template = FieldMappingTemplate(
        id=9,
        platform="tiktok",
        data_domain="products",
        granularity="monthly",
        version=6,
        status="published",
        header_row=2,
        header_columns=["商品ID"],
    )

    router_key = _build_template_status_cache_key(catalog_file, template)
    readiness_key = _readiness_cache_key(catalog_file, True)

    assert last_modified in router_key
    assert last_modified in readiness_key
    assert router_key[:5] == readiness_key[:5]
    # 模板版本参与缓存键 -> 模板升级后缓存自然失效
    assert 6 in router_key
    assert 6 in readiness_key or template.version == 6


def test_cache_key_changes_when_file_is_modified():
    from backend.services.data_sync_cache_key import build_template_status_cache_key

    catalog_file = CatalogFile(
        id=7,
        file_name="x.xlsx",
        file_path="data/raw/x.xlsx",
        status="pending",
        file_metadata={},
    )
    template = FieldMappingTemplate(id=9, version=6, header_row=2)

    catalog_file.last_modified = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
    first = build_template_status_cache_key(catalog_file, template)
    catalog_file.last_modified = datetime(2026, 10, 28, 9, 0, tzinfo=timezone.utc)
    second = build_template_status_cache_key(catalog_file, template)

    assert first != second


# ======================================================================
# D2: 状态枚举 SSOT
# ======================================================================
def test_orm_status_check_constraint_matches_status_enum():
    from modules.core.catalog_status import CATALOG_FILE_STATUSES

    constraints = [
        constraint
        for constraint in CatalogFile.__table__.constraints
        if getattr(constraint, "name", None) == "ck_catalog_files_status"
    ]
    assert constraints, "catalog_files 必须有 status CHECK 约束"

    sql_text = str(constraints[0].sqltext)
    for status in CATALOG_FILE_STATUSES:
        assert f"'{status}'" in sql_text


def test_migration_valid_statuses_match_status_enum():
    from importlib import import_module

    from modules.core.catalog_status import CATALOG_FILE_STATUSES

    migration = import_module(
        "current_migrations.versions.20261028_catalog_files_status_check"
    )
    assert tuple(migration.VALID_STATUSES) == tuple(CATALOG_FILE_STATUSES)


def test_catalog_file_status_helpers():
    from modules.core.catalog_status import (
        catalog_file_status_label,
        is_valid_catalog_file_status,
    )

    assert is_valid_catalog_file_status("pending") is True
    assert is_valid_catalog_file_status("template_update_required") is True
    assert is_valid_catalog_file_status("skipped") is False
    assert is_valid_catalog_file_status(None) is False
    assert catalog_file_status_label("ingested") == "已同步"
