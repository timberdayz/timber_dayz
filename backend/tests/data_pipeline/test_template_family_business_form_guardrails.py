"""批次 G 守护测试:「变体归位」。

覆盖三件事
----------
1. **G-1**: 模板族的维度里**不再有账号** ⇒ 账号数变化不影响模板数;
2. **G-2**: 变体按**业务形态**区分(列集合 / 解析方式 / 表头行 / 工作表名),
   ``variant_key`` **不再由文件名推导**; 存量 key 复用不重建;
3. **G-2 迁移**: ``variant_kind`` 的 SQL 回填与 Python 计算**逐字一致**。

口径来源: ``docs/superpowers/plans/2026-11-07-final-work-plan.md`` 批次 G。
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

from backend.services.template_family_service import (
    TemplateFamilyService,
    _account_dimension_matches,
    _dimension_key,
    build_variant_kind,
    infer_variant_key_from_legacy_template,
)
from modules.core.db import (
    FieldMappingTemplate,
    FieldMappingTemplateFamily,
    FieldMappingTemplateVariant,
    FieldMappingTemplateVersion,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPO_ROOT / "current_migrations" / "versions" / "20261129_template_variant_kind.py"
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


# ---------------------------------------------------------------------------
# 公共数据
# ---------------------------------------------------------------------------
_COLUMNS = ["日期", "浏览量", "访客数"]
_DASH_RULES = [
    {
        "target_field": "metric_date",
        "source_column": "日期",
        "value_kind": "single_date",
        "date_format": "dd-mm-yyyy",
        "strict": True,
    }
]
_SLASH_RULES = [
    {
        "target_field": "metric_date",
        "source_column": "日期",
        "value_kind": "single_date",
        "date_format": "dd/mm/yyyy",
        "strict": True,
    }
]


def _make_template(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "platform": "shopee",
        "data_domain": "analytics",
        "granularity": "monthly",
        "sub_domain": None,
        "account": None,
        "header_row": 3,
        "template_name": "shopee_analytics__monthly_slash_v3",
        "version": 3,
        "status": "published",
        "field_count": 3,
        "header_columns": list(_COLUMNS),
        "deduplication_fields": ["日期"],
        "field_parse_rules": [dict(rule) for rule in _SLASH_RULES],
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return FieldMappingTemplate(**payload)


@pytest_asyncio.fixture
async def family_session():
    """内存 SQLite —— 模板族投影用不到 PG 特性。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("ATTACH DATABASE ':memory:' AS core"))
        await conn.run_sync(FieldMappingTemplate.__table__.create)
        await conn.run_sync(FieldMappingTemplateFamily.__table__.create)
        await conn.run_sync(FieldMappingTemplateVersion.__table__.create)
        await conn.run_sync(FieldMappingTemplateVariant.__table__.create)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 1. G-1: 族维度里没有账号
# ---------------------------------------------------------------------------
def test_family_dimension_key_drops_account():
    """账号不是族的维度 ⇒ 不同账号得到同一个族键。"""
    base = _dimension_key("shopee", "analytics", None, "monthly", None)
    assert _dimension_key("shopee", "analytics", None, "monthly", "a@163.com") == base
    assert _dimension_key("shopee", "analytics", None, "monthly", "b@163.com") == base
    # 账号槽位恒为空
    assert base[4] is None


def test_account_dimension_matches_is_always_true():
    """账号差异由变体承载 ⇒ 不再判「不适用」。"""
    assert _account_dimension_matches(None, "shop@163.com") is True
    assert _account_dimension_matches("shop@163.com", "other@163.com") is True
    assert _account_dimension_matches("shop@163.com", None) is True


def test_canonical_dimension_rank_ignores_account():
    """规范度排名不再把 account 算进去。"""
    with_account = FieldMappingTemplateFamily(
        platform="shopee",
        data_domain="analytics",
        sub_domain=None,
        granularity="monthly",
        account="shop@163.com",
    )
    without_account = FieldMappingTemplateFamily(
        platform="shopee",
        data_domain="analytics",
        sub_domain=None,
        granularity="monthly",
        account=None,
    )
    assert TemplateFamilyService._canonical_dimension_rank(
        with_account
    ) == TemplateFamilyService._canonical_dimension_rank(without_account)


@pytest.mark.asyncio
async def test_account_count_does_not_change_template_count(family_session):
    """**G 的验收口径**: 账号从 1 个涨到 3 个, 模板族/版本数不变。

    账号差异由**变体**承载 ⇒ 每个账号一套模板 ⇒ 变体数 = 账号数,
    但「模板族」「激活版本」的数量必须保持不变。
    """
    for index, account in enumerate(["a@163.com", "b@163.com", "c@163.com"], start=1):
        family_session.add(
            _make_template(
                account=account,
                template_name=f"shopee_analytics__monthly_acct{index}_v{index}",
                version=index,
            )
        )
    await family_session.flush()

    service = TemplateFamilyService(family_session)
    await service.project_legacy_templates(
        platform="shopee", data_domain="analytics", commit=False
    )
    await family_session.flush()

    from sqlalchemy import select

    families = (
        (await family_session.execute(select(FieldMappingTemplateFamily)))
        .scalars()
        .all()
    )
    versions = (
        (await family_session.execute(select(FieldMappingTemplateVersion)))
        .scalars()
        .all()
    )
    variants = (
        (await family_session.execute(select(FieldMappingTemplateVariant)))
        .scalars()
        .all()
    )

    assert len(families) == 1, "账号数变化不应让模板族变多"
    assert len([item for item in versions if item.status == "active"]) == 1
    # 3 个账号 ⇒ 3 个变体(每个账号一套模板)
    assert len(variants) == 3
    # 族里不再存账号
    assert all(item.account is None for item in families)


# ---------------------------------------------------------------------------
# 2. G-2: 变体按业务形态
# ---------------------------------------------------------------------------
def test_variant_kind_ignores_template_name():
    """模板名(文件名)不再决定变体身份。"""
    a = _make_template(template_name="shopee_analytics__monthly_slash_v3")
    b = _make_template(template_name="shopee_analytics__月度_下划线_完全不同的名字")
    assert infer_variant_key_from_legacy_template(
        a
    ) == infer_variant_key_from_legacy_template(b)


def test_variant_kind_reflects_parse_rules():
    """列相同但解析方式不同 ⇒ 两个业务形态。"""
    dash = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_DASH_RULES, header_row=3
    )
    slash = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=3
    )
    assert dash != slash


def test_variant_kind_reflects_columns_and_header_row():
    """列集合不同 / 表头行不同 ⇒ 不同形态。"""
    base = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=3
    )
    other_columns = build_variant_kind(
        header_columns=_COLUMNS + ["GMV"], field_parse_rules=_SLASH_RULES, header_row=3
    )
    other_row = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=4
    )
    assert base != other_columns
    assert base != other_row


def test_variant_kind_is_stable_under_rule_order():
    """规则顺序不影响形态(同一套规则的两种排列是同一种解析方式)。"""
    two_rules = _SLASH_RULES + [
        {
            "target_field": "visitor_count",
            "source_column": "访客数",
            "value_kind": "number",
            "strict": True,
        }
    ]
    assert build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=two_rules, header_row=3
    ) == build_variant_kind(
        header_columns=_COLUMNS,
        field_parse_rules=list(reversed(two_rules)),
        header_row=3,
    )


def test_variant_kind_has_readable_shape():
    """形态标识是给人看的, 不是哈希黑盒。"""
    kind = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=3
    )
    assert kind.startswith("form_")
    assert kind.endswith("_h3")
    assert len(kind) <= 64


@pytest.mark.asyncio
async def test_projection_reuses_existing_variant_keys(family_session):
    """存量变体 key **不重建** —— key 生成规则变了也不能让变体 id 变化。

    存量 key 是历史值(``daily_slash`` 这类); 规则改成「按业务形态」之后,
    投影仍然要沿用它, 否则变体会被删掉重建 ⇒ id 变化 ⇒ 前端引用全部失效。
    """
    template = _make_template()
    family_session.add(template)
    await family_session.flush()

    service = TemplateFamilyService(family_session)
    await service.project_legacy_templates(
        platform="shopee", data_domain="analytics", commit=False
    )
    await family_session.flush()

    from sqlalchemy import select

    version = (
        await family_session.execute(
            select(FieldMappingTemplateVersion).where(
                FieldMappingTemplateVersion.status == "active"
            )
        )
    ).scalar_one()
    variant = (
        await family_session.execute(
            select(FieldMappingTemplateVariant).where(
                FieldMappingTemplateVariant.template_version_id == version.id
            )
        )
    ).scalar_one()
    generated_key = variant.variant_key
    variant_id = variant.id

    # 模拟「存量 key 是历史值」: 直接改 key, 再跑一次投影
    variant.variant_key = "daily_slash"
    await family_session.flush()

    await service.project_legacy_templates(
        platform="shopee", data_domain="analytics", commit=False
    )
    await family_session.flush()

    refreshed = (
        await family_session.execute(
            select(FieldMappingTemplateVariant).where(
                FieldMappingTemplateVariant.id == variant_id
            )
        )
    ).scalar_one()
    assert refreshed.variant_key == "daily_slash", "存量 key 必须复用, 不能重建"
    assert refreshed.variant_kind == generated_key
    assert refreshed.variant_kind.startswith("form_")


@pytest.mark.asyncio
async def test_projection_writes_variant_kind(family_session):
    """投影时把业务形态标识落库。"""
    family_session.add(_make_template())
    await family_session.flush()

    service = TemplateFamilyService(family_session)
    await service.project_legacy_templates(
        platform="shopee", data_domain="analytics", commit=False
    )
    await family_session.flush()

    from sqlalchemy import select

    variant = (
        await family_session.execute(select(FieldMappingTemplateVariant))
    ).scalar_one()
    expected = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=3
    )
    assert variant.variant_kind == expected
    assert variant.variant_key == expected


# ---------------------------------------------------------------------------
# 3. G-2 迁移: SQL 回填与 Python 逐字一致
# ---------------------------------------------------------------------------
def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_20261129", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_variant_kind_column():
    """迁移必须加列, 且是幂等的写法。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "variant_kind" in source
    assert "ADD COLUMN IF NOT EXISTS" in source
    module = _load_migration()
    assert callable(module.apply_upgrade)
    assert callable(module.apply_downgrade)


@pytest.mark.asyncio
async def test_migration_backfill_matches_python_computation(pg_session):
    """**迁移回填的 SQL 必须与 Python 算出来的值逐字一致**。

    两边口径一旦漂移, 存量变体的形态标识就会与新投影出来的对不上
    ⇒ 同一个形态出现两个身份 ⇒ 变体分裂。
    """
    from sqlalchemy import select

    now = datetime.now(timezone.utc)
    template = _make_template()
    pg_session.add(template)
    await pg_session.flush()

    version = FieldMappingTemplateVersion(
        family_id=999,
        version_no=1,
        status="active",
        template_name="t",
        deduplication_fields=["日期"],
        header_bindings=[],
        core_fields=[],
        field_parse_rules=[],
        legacy_template_ids=[template.id],
        created_at=now,
        updated_at=now,
    )
    pg_session.add(version)
    await pg_session.flush()

    pg_session.add(
        FieldMappingTemplateVariant(
            template_version_id=version.id,
            variant_key="daily_slash",
            header_row=3,
            sheet_name_pattern=None,
            required_headers=list(_COLUMNS),
            field_parse_rules=[dict(rule) for rule in _SLASH_RULES],
            source_legacy_template_id=template.id,
            template_name=template.template_name,
            created_at=now,
            updated_at=now,
        )
    )
    await pg_session.flush()

    module = _load_migration()
    await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()

    variant = (
        await pg_session.execute(select(FieldMappingTemplateVariant))
    ).scalar_one()
    expected = build_variant_kind(
        header_columns=_COLUMNS, field_parse_rules=_SLASH_RULES, header_row=3
    )
    assert variant.variant_kind == expected
    # 历史 key 不被改名
    assert variant.variant_key == "daily_slash"


@pytest.mark.asyncio
async def test_migration_is_idempotent(pg_session):
    """重复执行不报错, 也不二次改写。"""
    module = _load_migration()
    await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()
    await pg_session.run_sync(module.apply_upgrade)
    await pg_session.flush()
