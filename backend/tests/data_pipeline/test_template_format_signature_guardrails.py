"""批次 H 守护测试:「同一维度、多种格式并存」(format_signature)。

背景
----
``core.field_mapping_templates`` 的 published 唯一键曾经只是「维度」,
等于硬编码「一个维度只能有一种格式」。平台改一次导出格式
(加列 / 改日期分隔符), 历史格式的文件就再也找不到能解释它的模板
—— 数据补不回来。

本文件锁住四件事:

1. **签名口径唯一** —— 模板级 ``format_signature`` 与变体级 ``variant_kind``
   是**同一个值**(同一份实现), 不允许两套定义漂移;
2. **迁移正确** —— 回填 SQL 与 Python 计算逐字一致, 且唯一索引换成
   ``(维度, 格式签名)``;
3. **归档范围正确** —— 保存模板只归档**同格式**的旧模板,
   别的格式的 published 模板必须原样保留;
4. **判定按格式** —— 同维度并存两种格式时, 旧格式的文件仍然由
   **它自己那一版模板**解释, 不会被「维度里最新的一版」带偏。

口径来源: ``docs/adr/2026-11-13-template-drift-classification-ssot.md``
(批次 H) 与 ``docs/reports/2026-11-07-shop-identity-and-template-sync-incident.md``
问题 2 / 问题 3。
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from backend.services.field_mapping_template_service import (
    FieldMappingTemplateService,
)
from backend.services.template_family_service import (
    build_variant_kind,
    compute_format_signature,
    resolve_format_signature,
)
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


REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "current_migrations" / "versions" / "20261229_template_format_signature.py"
)


# ---------------------------------------------------------------------------
# 公共数据: 两种格式
# ---------------------------------------------------------------------------
#: 格式 A: 旧格式(28 列形态的缩影)
_COLUMNS_A = ["订单编号", "订单状态", "商品ID", "下单时间"]
#: 格式 B: 新格式(多一列「退款金额」)
_COLUMNS_B = ["订单编号", "订单状态", "商品ID", "下单时间", "退款金额"]
#: 格式 C: 与 A 列完全一致, 只有日期写法不同(斜杠 / 连字符)
_RULES_SLASH = [
    {
        "target_field": "metric_date",
        "source_column": "下单时间",
        "value_kind": "single_date",
        "date_format": "dd/mm/yyyy",
        "strict": True,
    }
]
_RULES_DASH = [
    {
        "target_field": "metric_date",
        "source_column": "下单时间",
        "value_kind": "single_date",
        "date_format": "dd-mm-yyyy",
        "strict": True,
    }
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def format_session_factory():
    """内存 SQLite —— 模板 / 模板族 / 版本 / 变体 四张表足够。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(CatalogFile.__table__.create)
        await conn.run_sync(FieldMappingTemplate.__table__.create)
        await conn.run_sync(FieldMappingTemplateFamily.__table__.create)
        await conn.run_sync(FieldMappingTemplateVersion.__table__.create)
        await conn.run_sync(FieldMappingTemplateVariant.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


async def _save(
    session,
    *,
    header_columns,
    field_parse_rules=None,
    header_row=0,
    save_mode="create",
    base_template_id=None,
):
    """走**生产入口**保存模板(而不是手工 new 一行)。"""
    service = FieldMappingTemplateService(session)
    return await service.save_template(
        platform="tiktok",
        data_domain="analytics",
        granularity="monthly",
        sub_domain=None,
        account=None,
        header_columns=list(header_columns),
        header_row=header_row,
        sheet_name=None,
        field_parse_rules=list(field_parse_rules or []),
        deduplication_fields=["订单编号"],
        core_fields=[
            {
                "semantic_key": None,
                "raw_name": "订单编号",
                "required": True,
                "in_hash": True,
            }
        ],
        save_mode=save_mode,
        base_template_id=base_template_id,
    )


# ---------------------------------------------------------------------------
# 1. 签名口径唯一(SSOT)
# ---------------------------------------------------------------------------
def test_format_signature_is_exactly_the_variant_kind():
    """模板级 ``format_signature`` 与变体级 ``variant_kind`` 必须是同一个值。

    两套定义迟早漂移 ⇒ 就会出现「模板说自己是格式 1、变体说自己是形态 2」。
    """
    for columns, rules, row, sheet in (
        (_COLUMNS_A, [], 0, None),
        (_COLUMNS_B, [], 1, None),
        (_COLUMNS_A, _RULES_SLASH, 3, None),
        (_COLUMNS_A, _RULES_DASH, 3, "Sheet1"),
    ):
        assert compute_format_signature(
            header_columns=columns,
            field_parse_rules=rules,
            header_row=row,
            sheet_name=sheet,
        ) == build_variant_kind(
            header_columns=columns,
            field_parse_rules=rules,
            header_row=row,
            sheet_name=sheet,
        )


def test_format_signature_distinguishes_formats():
    """列集合不同 / 日期写法不同 ⇒ 签名不同; 完全相同 ⇒ 签名相同。"""
    sig_a = compute_format_signature(header_columns=_COLUMNS_A)
    sig_b = compute_format_signature(header_columns=_COLUMNS_B)
    assert sig_a != sig_b

    slash = compute_format_signature(
        header_columns=_COLUMNS_A, field_parse_rules=_RULES_SLASH
    )
    dash = compute_format_signature(
        header_columns=_COLUMNS_A, field_parse_rules=_RULES_DASH
    )
    assert slash != dash

    # 同样的输入必须稳定
    assert compute_format_signature(header_columns=_COLUMNS_A) == sig_a


def test_resolve_format_signature_prefers_the_stored_column():
    """已落库的签名优先 —— 它就是唯一索引用的那个值。"""
    template = FieldMappingTemplate(
        platform="tiktok",
        data_domain="analytics",
        header_columns=list(_COLUMNS_A),
        format_signature="stored-value",
    )
    assert resolve_format_signature(template) == "stored-value"

    # 存量行(没有这一列)⇒ 按内容现算, 与有列时同值
    legacy = FieldMappingTemplate(
        platform="tiktok",
        data_domain="analytics",
        header_columns=list(_COLUMNS_A),
    )
    assert resolve_format_signature(legacy) == compute_format_signature(
        header_columns=_COLUMNS_A
    )


# ---------------------------------------------------------------------------
# 2. 迁移契约
# ---------------------------------------------------------------------------
def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_20261229", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_column_and_swaps_the_unique_index():
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "format_signature" in source
    assert "ADD COLUMN IF NOT EXISTS" in source
    assert "uq_field_mapping_templates_published_dimension_format" in source
    module = _load_migration()
    assert callable(module.apply_upgrade)
    assert callable(module.apply_downgrade)


def test_migration_chains_after_the_current_head():
    """新迁移必须接在当前链头之后(否则上线会漏跑)。"""
    module = _load_migration()
    assert module.down_revision == (
        "current_schema_20261228_bridge_spu_sku_binding_status_constraint"
    )


@pytest.mark.asyncio
async def test_migration_backfill_matches_python_computation(pg_session):
    """**迁移回填的 SQL 必须与 Python 算出来的值逐字一致**。

    两边口径一旦漂移, 模板的格式签名就会与变体的业务形态标识对不上
    ⇒ 同一种格式出现两个身份 ⇒ 保存模板时归档错人。
    """
    now = _now()
    template = FieldMappingTemplate(
        platform="shopee",
        data_domain="analytics",
        granularity="monthly",
        sub_domain=None,
        account=None,
        header_row=3,
        sheet_name=None,
        template_name="shopee_analytics__monthly_slash_v3",
        version=3,
        status="published",
        field_count=len(_COLUMNS_A),
        header_columns=list(_COLUMNS_A),
        deduplication_fields=["订单编号"],
        field_parse_rules=[dict(rule) for rule in _RULES_SLASH],
        created_at=now,
        updated_at=now,
    )
    pg_session.add(template)
    await pg_session.flush()

    module = _load_migration()
    await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()

    await pg_session.refresh(template)
    expected = compute_format_signature(
        header_columns=_COLUMNS_A,
        field_parse_rules=_RULES_SLASH,
        header_row=3,
    )
    assert template.format_signature == expected


# ---------------------------------------------------------------------------
# 3. 保存模板的归档范围
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_save_template_keeps_a_different_format_published(format_session_factory):
    """存新格式**不能**把旧格式的 published 模板一起归档掉。

    这正是 ISSUE-3「tiktok 8 月数据补不回来」的根因:
    旧格式的模板被归档 ⇒ 旧格式的文件再没有模板能解释它。
    """
    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        await _save(session, header_columns=_COLUMNS_B)

        result = await session.execute(
            text(
                "select header_columns, format_signature, status "
                "from core.field_mapping_templates order by id"
            )
        )
        rows = result.fetchall()

    published = [row for row in rows if row[2] == "published"]
    assert len(published) == 2, "两种格式必须各自留一个 published"
    assert published[0][1] != published[1][1], "两种格式的签名必须不同"


@pytest.mark.asyncio
async def test_save_template_archives_only_the_same_format(format_session_factory):
    """再存一次格式 B ⇒ 只归档格式 B 的旧版, 格式 A 原样保留。"""
    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        await _save(session, header_columns=_COLUMNS_B)
        await _save(session, header_columns=_COLUMNS_B)

        result = await session.execute(
            text(
                "select format_signature, status "
                "from core.field_mapping_templates order by id"
            )
        )
        rows = result.fetchall()

    published = [row for row in rows if row[1] == "published"]
    assert len(published) == 2
    sig_a = compute_format_signature(header_columns=_COLUMNS_A)
    sig_b = compute_format_signature(header_columns=_COLUMNS_B)
    assert {row[0] for row in published} == {sig_a, sig_b}
    # 归档掉的必须是格式 B 的旧版(共 3 行: A + B(v1) + B(v2))
    archived = [row for row in rows if row[1] == "archived"]
    assert len(archived) == 1
    assert archived[0][0] == sig_b


# ---------------------------------------------------------------------------
# 4. 保存意图: 更新=替换, 新建=并存
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_mode_replaces_the_edited_template(format_session_factory):
    """``save_mode='new_version'``(更新既有模板)⇒ 被编辑的那一版被**替换**掉。

    用户心智: 「这一版被新版取代了」——
    不该因为多加了一列就变成「多出一种格式」。
    """
    async with format_session_factory() as session:
        first = await _save(session, header_columns=_COLUMNS_A)
        second = await _save(
            session,
            header_columns=_COLUMNS_B,
            save_mode="new_version",
            base_template_id=first["template_id"],
        )

        rows = (
            await session.execute(
                text(
                    "select id, status from core.field_mapping_templates order by id"
                )
            )
        ).fetchall()

    assert second["operation"] == "new_version"
    assert second["archived_template_id"] == first["template_id"]
    statuses = {row[0]: row[1] for row in rows}
    assert statuses[first["template_id"]] == "archived"


@pytest.mark.asyncio
async def test_create_mode_keeps_other_formats_alive(format_session_factory):
    """``save_mode='create'``(新建模板 / 创建变体)⇒ 别的格式继续生效。"""
    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        second = await _save(session, header_columns=_COLUMNS_B)

        rows = (
            await session.execute(
                text(
                    "select status from core.field_mapping_templates order by id"
                )
            )
        ).fetchall()

    assert second["operation"] == "created"
    assert second["archived_template_id"] is None
    assert [row[0] for row in rows] == ["published", "published"]


# ---------------------------------------------------------------------------
# 5. 家族投影: 每个 published 模板一个变体
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_projection_creates_one_variant_per_published_format(format_session_factory):
    """两种格式 ⇒ 一个族、激活版本下两个变体(各自带自己的列集合)。"""
    import json

    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        await _save(session, header_columns=_COLUMNS_B)

        variants = (
            await session.execute(
                text(
                    "select v.required_headers "
                    "from core.field_mapping_template_variants v "
                    "join core.field_mapping_template_families f "
                    "  on f.active_version_id = v.template_version_id "
                    "where f.platform = 'tiktok' and f.data_domain = 'analytics'"
                )
            )
        ).fetchall()

    assert len(variants) == 2
    header_sets = {tuple(sorted(json.loads(v[0]))) for v in variants}
    assert header_sets == {
        tuple(sorted(_COLUMNS_A)),
        tuple(sorted(_COLUMNS_B)),
    }


# ---------------------------------------------------------------------------
# 5. 判定按格式: 旧格式的文件仍由旧格式的模板解释
# ---------------------------------------------------------------------------
async def test_same_format_published_tells_coexistence_from_upgrade(format_session_factory):
    """**并存 ≠ 升级** —— 这两种情形必须分开判。

    * 并存: 基准那一版仍然 published ⇒「当前模板」就是它自己
      ⇒ 不该报「我们升级过模板」;
    * 升级: 基准那一版已被归档(被新版顶掉)⇒ 同格式没有已发布版本
      ⇒ 「当前模板」仍是当前已发布模板 ⇒ 升级信号照常成立。
    """
    from backend.services.data_sync_template_status_service import (
        DataSyncTemplateStatusService,
    )

    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        await _save(session, header_columns=_COLUMNS_B)

        rows = (
            await session.execute(
                text(
                    "select id from core.field_mapping_templates order by version asc"
                )
            )
        ).fetchall()
        template_a_id, template_b_id = rows[0][0], rows[1][0]
        template_a = await session.get(FieldMappingTemplate, template_a_id)
        template_b = await session.get(FieldMappingTemplate, template_b_id)

        catalog_file = CatalogFile(
            file_path="data/raw/tiktok_analytics_monthly_202608.xls",
            file_name="tiktok_analytics_monthly_202608.xls",
            source="data/raw",
            status="pending",
            platform_code="tiktok",
            data_domain="analytics",
            granularity="monthly",
            file_metadata={},
        )
        service = DataSyncTemplateStatusService(session)

        # 并存: 基准(格式 A)仍然 published ⇒ 「当前模板」= 格式 A 那一版
        coexist = await service._resolve_same_format_published(
            catalog_file=catalog_file,
            reference=template_a,
            fallback=template_b,
            normalized_sub_domain=None,
            normalized_account=None,
        )
        assert coexist is not None and coexist.id == template_a_id

        # 升级: 基准(格式 A)已被归档 ⇒ 同格式没有已发布版本 ⇒ 退回当前已发布模板
        template_a.status = "archived"
        await session.flush()
        upgraded = await service._resolve_same_format_published(
            catalog_file=catalog_file,
            reference=template_a,
            fallback=template_b,
            normalized_sub_domain=None,
            normalized_account=None,
        )
        assert upgraded is not None and upgraded.id == template_b_id


@pytest.mark.asyncio
async def test_baseline_picks_the_template_of_the_files_own_format(format_session_factory):
    """**核心验收**: 维度里最新的一版是格式 B, 但文件是格式 A
    ⇒ 基准必须落到格式 A 的模板上。

    这条不成立, 就会出现「模板一升级, 历史文件全被判成漂移」的老问题。
    """
    from backend.services.template_variant_takeover_service import (
        resolve_baseline_for_file,
    )

    async with format_session_factory() as session:
        await _save(session, header_columns=_COLUMNS_A)
        await _save(session, header_columns=_COLUMNS_B)

        result = await session.execute(
            text(
                "select id, header_columns from core.field_mapping_templates "
                "where status = 'published' order by version desc"
            )
        )
        rows = result.fetchall()
        newest_id = rows[0][0]
        oldest_id = rows[1][0]

        catalog_file = CatalogFile(
            file_path="data/raw/tiktok_analytics_monthly_202608.xls",
            file_name="tiktok_analytics_monthly_202608.xls",
            source="data/raw",
            status="pending",
            platform_code="tiktok",
            data_domain="analytics",
            granularity="monthly",
            file_metadata={},
        )

        async def read_header(row: int):
            # 文件是**格式 A**(旧格式)
            return list(_COLUMNS_A)

        baseline = await resolve_baseline_for_file(
            session,
            catalog_file=catalog_file,
            published_template=await session.get(FieldMappingTemplate, newest_id),
            contract_template=None,
            read_header=read_header,
        )

    assert baseline["baseline_template"] is not None
    assert baseline["baseline_template"].id == oldest_id, (
        "文件是格式 A ⇒ 基准必须是格式 A 的模板, 而不是维度里最新的那一版"
    )
    assert baseline["baseline_template"].id != newest_id
