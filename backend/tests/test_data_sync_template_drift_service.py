"""模板漂移判定 / 快照 / 计数 的统一服务回归测试。

覆盖本次修复的四个关键行为:

1. **持久化标记优先于实时重算** —— 文件一旦被标记为「模板待更新」,
   即使当前模板已经更新到能匹配该文件, 待办也不能凭空消失。
2. **治理面板以漂移文件为准** —— 被标记漂移的文件所在组合, 必须出现在
   「需要更新」列表里, 而不是因为「当前模板重算结果为 ready」而消失。
3. **语义契约不再产生假阳性** —— analytics 域 100% 精确匹配时,
   契约状态不应是 breaking_drift。
4. **语义契约修复后新增列不能漏报** —— 「源文件新增一列」必须仍然是结构漂移。
"""

from datetime import datetime, timezone

import pandas as pd
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from modules.core.db import CatalogFile, FieldMappingTemplate


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def drift_session_factory(tmp_path):
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


# ----------------------------------------------------------------------
# 1. 文件级判定: 持久化标记优先
# ----------------------------------------------------------------------
def test_resolve_file_state_prefers_persisted_drift_over_live_ready():
    from backend.services.data_sync_template_drift_service import (
        DataSyncTemplateDriftService,
    )

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="template_update_required",
        file_metadata={
            "template_drift": {
                "reason": "新增1个字段, 删除1个字段 (匹配率: 93.1%)",
                "template_id": 364,
                "template_version": 5,
            }
        },
    )

    resolved = DataSyncTemplateDriftService.resolve_file_state(
        catalog_file,
        {"template_status": "ready", "template_update_required": False},
    )

    assert resolved["template_update_required"] is True
    assert resolved["drift_source"] == "persisted"
    assert "93.1%" in resolved["update_reason"]


def test_resolve_file_state_uses_live_result_when_not_persisted():
    from backend.services.data_sync_template_drift_service import (
        DataSyncTemplateDriftService,
    )

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="pending",
        file_metadata={},
    )

    resolved = DataSyncTemplateDriftService.resolve_file_state(
        catalog_file,
        {
            "template_status": "update_required",
            "template_update_required": True,
            "update_reason": "新增1个字段",
        },
    )

    assert resolved["template_update_required"] is True
    assert resolved["drift_source"] == "live"
    assert resolved["update_reason"] == "新增1个字段"


def test_resolve_file_state_is_false_when_no_drift_at_all():
    from backend.services.data_sync_template_drift_service import (
        DataSyncTemplateDriftService,
    )

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="ingested",
        file_metadata={},
    )

    resolved = DataSyncTemplateDriftService.resolve_file_state(
        catalog_file,
        {"template_status": "ready", "template_update_required": False},
    )

    assert resolved["template_update_required"] is False
    assert resolved["drift_source"] is None


# ----------------------------------------------------------------------
# 2. 漂移快照读写
# ----------------------------------------------------------------------
def test_persist_and_read_drift_snapshot_roundtrip():
    from backend.services.data_sync_template_drift_service import (
        DataSyncTemplateDriftService,
    )

    catalog_file = CatalogFile(
        file_path="data/raw/x.xlsx",
        file_name="x.xlsx",
        source="data/raw",
        status="template_update_required",
        file_metadata={},
    )

    snapshot = DataSyncTemplateDriftService.persist_snapshot(
        catalog_file,
        {
            "template_status": "update_required",
            "governance_status": "breaking_drift",
            "header_changes": {
                "added_fields": ["退款金额"],
                "removed_fields": ["已退款的商品件数"],
                "match_rate": 93.1,
                "blocking_changes": ["已退款的商品件数"],
                "non_blocking_changes": [],
            },
        },
        message="新增1个字段, 删除1个字段 (匹配率: 93.1%)",
    )

    assert snapshot["added_fields"] == ["退款金额"]
    assert snapshot["removed_fields"] == ["已退款的商品件数"]
    assert snapshot["match_rate"] == 93.1

    stored = DataSyncTemplateDriftService.read_snapshot(catalog_file)
    assert stored is not None
    assert stored["reason"] == "新增1个字段, 删除1个字段 (匹配率: 93.1%)"
    assert stored["source_file_name"] == "x.xlsx"


# ----------------------------------------------------------------------
# 3. 组合级聚合与计数
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_drift_groups_groups_by_dimension(drift_session_factory):
    from backend.services.data_sync_template_drift_service import (
        DataSyncTemplateDriftService,
    )

    now = _now()
    async with drift_session_factory() as session:
        session.add_all(
            [
                CatalogFile(
                    file_path="data/raw/a1.xlsx",
                    file_name="a1.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    status="template_update_required",
                    first_seen_at=now,
                    file_metadata={
                        "template_drift": {
                            "reason": "列改名",
                            "template_id": 364,
                            "template_version": 5,
                            "detected_at": now.isoformat(),
                        }
                    },
                ),
                CatalogFile(
                    file_path="data/raw/a2.xlsx",
                    file_name="a2.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    status="template_update_required",
                    first_seen_at=now,
                    file_metadata={},
                ),
                CatalogFile(
                    file_path="data/raw/b1.xlsx",
                    file_name="b1.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    data_domain="products",
                    granularity="monthly",
                    sub_domain=None,
                    status="template_update_required",
                    first_seen_at=now,
                    file_metadata={},
                ),
                CatalogFile(
                    file_path="data/raw/c1.xlsx",
                    file_name="c1.xlsx",
                    source="data/raw",
                    platform_code="tiktok",
                    data_domain="analytics",
                    granularity="daily",
                    sub_domain=None,
                    status="ingested",
                    first_seen_at=now,
                    file_metadata={},
                ),
            ]
        )
        await session.commit()

        service = DataSyncTemplateDriftService(session)
        groups = await service.list_drift_groups()
        count = await service.count_files_requiring_update()

    assert count == 3
    assert len(groups) == 2

    analytics = next(
        group
        for group in groups
        if group["domain"] == "analytics" and group["granularity"] == "monthly"
    )
    assert analytics["file_count"] == 2
    assert analytics["platform"] == "tiktok"
    assert analytics["update_reason"] == "列改名"
    assert analytics["drift_snapshot"]["template_id"] == 364


# ----------------------------------------------------------------------
# 4. 语义契约: 假阳性消失 + 新增列不漏报
# ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_analytics_contract_is_ready_on_exact_header_match(drift_session_factory):
    """R4: 100% 精确匹配时, 契约状态不应再是 breaking_drift。"""
    from backend.services.semantic_field_contract_service import (
        SemanticFieldContractService,
    )

    async with drift_session_factory() as session:
        result = await SemanticFieldContractService(session).evaluate(
            platform="tiktok",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            header_bindings=[
                {"raw_name": "日期", "semantic_key": "metric_date"},
            ],
            current_columns=["日期", "商品访客数", "页面浏览次数", "转化率"],
            template_columns=["日期", "商品访客数", "页面浏览次数", "转化率"],
        )

    assert result.missing_required_keys == []
    assert result.should_block is False
    assert result.status == "ready"


@pytest.mark.asyncio
async def test_analytics_new_column_is_still_structural_drift(drift_session_factory):
    """R4: 契约修好之后, 「源文件新增一列」必须仍然触发模板更新。"""
    from backend.services.data_sync_template_status_service import (
        DataSyncTemplateStatusService,
    )

    now = _now()
    async with drift_session_factory() as session:
        template = FieldMappingTemplate(
            platform="tiktok",
            data_domain="analytics",
            granularity="monthly",
            sub_domain=None,
            template_name="tiktok_analytics__monthly_v1",
            version=1,
            status="published",
            header_row=8,
            header_columns=["日期", "商品访客数", "页面浏览次数"],
            created_at=now,
            updated_at=now,
        )
        session.add(template)
        await session.commit()
        await session.refresh(template)

        catalog_file = CatalogFile(
            file_path="data/raw/analytics.xlsx",
            file_name="analytics.xlsx",
            source="data/raw",
            platform_code="tiktok",
            data_domain="analytics",
            granularity="monthly",
            status="pending",
            first_seen_at=now,
        )
        session.add(catalog_file)
        await session.commit()

        status = await DataSyncTemplateStatusService(session).evaluate_catalog_file(
            catalog_file,
            template=template,
            current_columns=["日期", "商品访客数", "页面浏览次数", "新增指标列"],
        )

    assert status["template_status"] == "update_required"
    assert status["template_update_required"] is True
    assert "新增指标列" in status["header_changes"]["added_fields"]


# ----------------------------------------------------------------------
# 5. 账号(地区)维度
# ----------------------------------------------------------------------
def test_alias_registry_account_scope_overrides_generic_mapping():
    from backend.services.template_alias_registry import get_header_alias_mapping

    generic = get_header_alias_mapping("tiktok", "analytics", "monthly")
    assert generic == {}

    scoped = get_header_alias_mapping(
        "tiktok", "analytics", "monthly", account="us_store"
    )
    assert scoped == {}


@pytest.mark.asyncio
async def test_find_best_template_prefers_account_scoped_template(drift_session_factory):
    from backend.services.template_matcher import TemplateMatcher

    now = _now()
    async with drift_session_factory() as session:
        session.add_all(
            [
                FieldMappingTemplate(
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    account=None,
                    template_name="tiktok_analytics__monthly_v1",
                    version=1,
                    status="published",
                    header_row=8,
                    header_columns=["日期"],
                    created_at=now,
                    updated_at=now,
                ),
                FieldMappingTemplate(
                    platform="tiktok",
                    data_domain="analytics",
                    granularity="monthly",
                    sub_domain=None,
                    account="us_store",
                    template_name="tiktok_analytics__monthly_us",
                    version=1,
                    status="published",
                    header_row=8,
                    header_columns=["日期", "销售额"],
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        await session.commit()

        matcher = TemplateMatcher(session)

        scoped = await matcher.find_best_template(
            platform="tiktok",
            data_domain="analytics",
            granularity="monthly",
            account="us_store",
        )
        fallback = await matcher.find_best_template(
            platform="tiktok",
            data_domain="analytics",
            granularity="monthly",
            account="unknown_store",
        )
        generic = await matcher.find_best_template(
            platform="tiktok",
            data_domain="analytics",
            granularity="monthly",
        )

    assert scoped.template_name == "tiktok_analytics__monthly_us"
    assert fallback.template_name == "tiktok_analytics__monthly_v1"
    assert generic.template_name == "tiktok_analytics__monthly_v1"


# ----------------------------------------------------------------------
# 6. 治理面板: 漂移文件必须出现在「需要更新」
# ----------------------------------------------------------------------
@pytest_asyncio.fixture
async def governance_client(tmp_path, monkeypatch):
    from backend.main import app
    from backend.dependencies.auth import get_current_user
    from backend.models.database import get_async_db

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_async_db():
        async with session_factory() as session:
            yield session

    class _MockUser:
        id = 1
        username = "test_admin"
        is_active = True
        is_superuser = True
        role_id = 1

    async def override_current_user():
        return _MockUser()

    class _ExecutorManagerStub:
        async def run_cpu_intensive(self, _fn, *_args, **_kwargs):
            return pd.DataFrame(columns=["日期"])

    monkeypatch.setattr(
        "backend.services.data_sync_service.get_executor_manager",
        lambda: _ExecutorManagerStub(),
    )
    monkeypatch.setattr(
        "backend.services.excel_parser.ExcelParser.read_excel",
        staticmethod(lambda *_args, **_kwargs: pd.DataFrame(columns=["日期"])),
    )

    app.dependency_overrides[get_async_db] = override_get_async_db
    app.dependency_overrides[get_current_user] = override_current_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client, session_factory, tmp_path

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_drift_file_group_appears_in_needs_update_list(governance_client):
    """R1: 被标记漂移的组合必须出现在「需要更新」, 且带上漂移文件数。"""
    client, session_factory, tmp_path = governance_client
    now = _now()

    drift_path = tmp_path / "tiktok_analytics_monthly_drift.xlsx"
    drift_path.write_text("demo", encoding="utf-8")

    async with session_factory() as session:
        session.add(
            FieldMappingTemplate(
                platform="tiktok",
                data_domain="analytics",
                granularity="monthly",
                sub_domain=None,
                template_name="tiktok_analytics__monthly_v6",
                version=6,
                status="published",
                header_row=8,
                header_columns=["日期", "GMV"],
                created_at=now,
                updated_at=now,
            )
        )
        session.add(
            CatalogFile(
                file_path=str(drift_path),
                file_name=drift_path.name,
                source="data/raw",
                platform_code="tiktok",
                source_platform="tiktok",
                data_domain="analytics",
                granularity="monthly",
                sub_domain=None,
                status="template_update_required",
                first_seen_at=now,
                file_metadata={
                    "template_drift": {
                        "reason": "新增1个字段, 删除1个字段 (匹配率: 93.1%)",
                        "template_id": 368,
                        "template_version": 6,
                        "detected_at": now.isoformat(),
                    }
                },
            )
        )
        await session.commit()

    response = await client.get("/api/data-sync/governance/detailed-coverage")
    assert response.status_code == 200
    coverage = response.json()["data"]

    needs_update = coverage["current_needs_update"]
    assert len(needs_update) == 1
    row = needs_update[0]
    assert row["platform"] == "tiktok"
    assert row["domain"] == "analytics"
    assert row["granularity"] == "monthly"
    assert row["governance_status"] == "breaking_drift"
    assert row["drift_file_count"] == 1
    assert "93.1%" in (row["update_reason"] or "")

    # 漂移组合不应同时出现在「已覆盖」里
    covered = coverage["current_covered"]
    assert all(
        not (
            item["platform"] == "tiktok"
            and item["domain"] == "analytics"
            and item["granularity"] == "monthly"
        )
        for item in covered
    )
