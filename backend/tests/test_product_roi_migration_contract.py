"""阶段 1 · ROI 迁移的契约与幂等性测试。

两个迁移：
* ``20261113_add_platform_roi_config.py`` —— 平台级 ROI 配置（安全边际 / 可填上限）
* ``20261114_add_sku_roi_columns.py`` —— SKU 级 ROI 列 + C2 完整度取值域约束

两个测试层次：
1. **源码契约**：迁移链、幂等守卫、回填 SQL、CHECK 表达式。
2. **真实 PostgreSQL**：在隔离测试库上跑 upgrade → upgrade → downgrade → upgrade，
   确认重复执行不报错、downgrade 能干净回滚。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text

from backend.utils.project_env import isolated_database_url


VERSIONS_DIR = Path("current_migrations/versions")
PLATFORM_MIGRATION = VERSIONS_DIR / "20261113_add_platform_roi_config.py"
SKU_MIGRATION = VERSIONS_DIR / "20261114_add_sku_roi_columns.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_contract_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_roi_migrations_are_chained_on_the_current_head():
    platform_source = _read(PLATFORM_MIGRATION)
    sku_source = _read(SKU_MIGRATION)

    assert (
        'revision = "current_schema_20261113_add_platform_roi_config"'
        in platform_source
    )
    assert (
        'down_revision = "current_schema_20261112_realign_identity_candidates_anchor"'
        in platform_source
    )
    assert 'revision = "current_schema_20261114_add_sku_roi_columns"' in sku_source
    assert (
        'down_revision = "current_schema_20261113_add_platform_roi_config"'
        in sku_source
    )


def test_platform_roi_migration_guards_every_column_and_constraint():
    source = _read(PLATFORM_MIGRATION)

    assert "def _has_column(" in source
    assert "def _has_constraint(" in source
    for column in ("roi_safety_margin", "target_roi_ceiling", "target_roi_floor"):
        assert f'"{column}"' in source
    # 平台实际值回填：TikTok 20 / Shopee 50
    assert '"tiktok": 20' in source
    assert '"shopee": 50' in source
    assert "UPDATE core.dim_platforms SET target_roi_ceiling" in source
    # downgrade 必须先删约束再删列
    assert source.index("drop_constraint") < source.index("drop_column")
    for name in (
        "ck_dim_platforms_roi_safety_margin_range",
        "ck_dim_platforms_target_roi_ceiling_range",
        "ck_dim_platforms_target_roi_floor_range",
    ):
        assert name in source


def test_sku_roi_migration_guards_columns_and_closes_completeness_domains():
    source = _read(SKU_MIGRATION)

    assert "def _has_column(" in source
    assert "def _has_constraint(" in source
    for column in (
        "expected_selling_price_source",
        "break_even_roi",
        "suggested_roi",
        "suggested_roi_clamped",
        "equivalent_target_roi",
    ):
        assert f'"{column}"' in source
    # C2：先清洗存量，再加 CHECK 约束（顺序反了约束加不上）
    assert source.index(
        "UPDATE finance.sku_profit_estimates SET cost_completeness"
    ) < source.index("create_check_constraint")
    assert "ck_sku_profit_estimate_cost_completeness" in source
    assert "ck_sku_profit_estimate_actual_completeness" in source
    # downgrade 先删约束再删列
    assert source.index("drop_constraint") < source.index("drop_column")


@pytest.fixture(scope="module")
def isolated_engine():
    url = isolated_database_url()
    if not url:
        pytest.skip("隔离测试库地址未就绪")
    engine = create_engine(url)
    yield engine
    engine.dispose()


def _run_migration(engine, module, func_name: str) -> None:
    def _do(connection):
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            getattr(module, func_name)()

    with engine.begin() as connection:
        _do(connection)


def test_roi_migrations_are_repeatable_and_rollback_cleanly(isolated_engine):
    """在真实 PostgreSQL 上跑：upgrade ×2 → downgrade → upgrade。

    重复执行必须是无害的（部署脚本会重跑）；downgrade 必须能把列和约束都撤掉。
    """
    platform_module = _load_module(PLATFORM_MIGRATION)
    sku_module = _load_module(SKU_MIGRATION)

    # 隔离库只有表结构、没有平台种子行 —— 塞两行进去，回填才有对象可验。
    with isolated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO core.dim_platforms "
                "(platform_code, name, platform_role, is_active, created_at, updated_at) "
                "VALUES ('tiktok', 'TikTok', 'sales', true, now(), now()), "
                "       ('shopee', 'Shopee', 'sales', true, now(), now()) "
                "ON CONFLICT (platform_code) DO NOTHING"
            )
        )

    # 1) 幂等：列已经存在（create_all 建过）时重复 upgrade 不报错
    _run_migration(isolated_engine, platform_module, "upgrade")
    _run_migration(isolated_engine, sku_module, "upgrade")

    inspector = inspect(isolated_engine)
    platform_columns = {
        column["name"]
        for column in inspector.get_columns("dim_platforms", schema="core")
    }
    assert {
        "roi_safety_margin",
        "target_roi_ceiling",
        "target_roi_floor",
    } <= platform_columns

    estimate_columns = {
        column["name"]
        for column in inspector.get_columns("sku_profit_estimates", schema="finance")
    }
    assert {
        "expected_selling_price_source",
        "break_even_roi",
        "suggested_roi",
        "suggested_roi_clamped",
        "equivalent_target_roi",
    } <= estimate_columns

    # 2) downgrade 能干净撤掉
    _run_migration(isolated_engine, sku_module, "downgrade")
    _run_migration(isolated_engine, platform_module, "downgrade")

    inspector = inspect(isolated_engine)
    platform_columns = {
        column["name"]
        for column in inspector.get_columns("dim_platforms", schema="core")
    }
    assert "roi_safety_margin" not in platform_columns
    assert "target_roi_ceiling" not in platform_columns
    assert "target_roi_floor" not in platform_columns

    estimate_columns = {
        column["name"]
        for column in inspector.get_columns("sku_profit_estimates", schema="finance")
    }
    assert "break_even_roi" not in estimate_columns
    assert "expected_selling_price_source" not in estimate_columns

    # 3) 再 upgrade 回来，并校验回填值与 CHECK 约束
    _run_migration(isolated_engine, platform_module, "upgrade")
    _run_migration(isolated_engine, sku_module, "upgrade")

    inspector = inspect(isolated_engine)
    platform_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "dim_platforms", schema="core"
        )
    }
    assert {
        "ck_dim_platforms_roi_safety_margin_range",
        "ck_dim_platforms_target_roi_ceiling_range",
        "ck_dim_platforms_target_roi_floor_range",
    } <= platform_constraints

    estimate_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "sku_profit_estimates", schema="finance"
        )
    }
    assert {
        "ck_sku_profit_estimate_cost_completeness",
        "ck_sku_profit_estimate_actual_completeness",
    } <= estimate_constraints

    with isolated_engine.connect() as connection:
        ceilings = dict(
            connection.execute(
                text(
                    "SELECT platform_code, target_roi_ceiling "
                    "FROM core.dim_platforms WHERE platform_code IN ('tiktok', 'shopee')"
                )
            ).all()
        )
    assert str(ceilings["tiktok"]) == "20.00"
    assert str(ceilings["shopee"]) == "50.00"

    # 清掉种子行，别影响同一会话里的其它用例
    with isolated_engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM core.dim_platforms "
                "WHERE platform_code IN ('tiktok', 'shopee')"
            )
        )
