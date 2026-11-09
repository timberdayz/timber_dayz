"""人力成本分摊口径中性名的守护测试。

背景
----
``finance.employee_labor_cost_allocations.calculation_version`` 历史上挂着
``LABOR_COST_V1`` / ``LABOR_COST_V2`` 两个值。业务上其实只有一个口径
（旧名带序号，看着像还有第二个版本在跑）。现已改成中性名
``LABOR_COST_ALLOC_V1``，与利润基数的 ``SETTLEMENT_BASIS_V1`` 同一风格。

这些测试的作用是**防止旧名字悄悄回流**：

* 常量必须是中性名；
* ORM 默认值、mart 视图资产、迁移脚本三处必须与常量一致
  （三处各写各的，是这类口径名最常见的漂移方式）；
* 现行代码里不允许再出现旧口径名的**字符串字面量**
  （注释里可以提「以前叫 V2」，那是解释，不是行为）。
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.services.labor_cost_projection_service import (
    LABOR_COST_CALCULATION_VERSION,
)


REPO_ROOT = Path(__file__).parents[2]

#: 当前口径（中性名）
NEUTRAL_VERSION = "LABOR_COST_ALLOC_V1"

#: 旧口径名 —— 拼接出来，免得本文件自己被扫描命中
LEGACY_VERSION = "LABOR_COST" + "_V2"

#: 历史迁移链（只读归档，允许出现旧口径名）
_HISTORY_PREFIXES = (
    "current_migrations/versions/",
    "migrations/versions/",
)

#: 需要扫描的现行代码 / 资产目录
_SCAN_DIRS = (
    "backend",
    "modules",
    "sql",
    "scripts",
    "frontend/src",
)

_SCAN_SUFFIXES = {".py", ".sql", ".js", ".vue", ".mjs", ".ts", ".json"}

_MIGRATION_REL = (
    "current_migrations/versions/" "20261217_rename_labor_cost_allocation_version.py"
)


def _iter_scanned_files():
    for rel_dir in _SCAN_DIRS:
        base = REPO_ROOT / rel_dir
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(_HISTORY_PREFIXES):
                continue
            if rel == Path(__file__).relative_to(REPO_ROOT).as_posix():
                continue
            yield rel, path


def test_constant_uses_neutral_name():
    assert LABOR_COST_CALCULATION_VERSION == NEUTRAL_VERSION
    # 中性名里不该再带「V2」这种序号
    assert "V2" not in LABOR_COST_CALCULATION_VERSION


def test_orm_default_matches_constant():
    from modules.core.db.schema_parts.business import EmployeeLaborCostAllocation

    default = EmployeeLaborCostAllocation.__table__.c.calculation_version.default
    assert default is not None
    assert default.arg == LABOR_COST_CALCULATION_VERSION


def test_mart_view_asset_filters_on_current_version():
    asset = (REPO_ROOT / "sql/mart/shop_month_labor_cost.sql").read_text(
        encoding="utf-8-sig"
    )
    assert (
        f"calculation_version = '{LABOR_COST_CALCULATION_VERSION}'" in asset
    ), "mart 视图必须只认当前口径，否则人力成本会被算两遍"


def test_current_sources_have_no_legacy_version_literal():
    """现行代码里不得再出现旧口径名的字符串字面量（注释可以提）。"""
    pattern = re.compile(r"['\"]" + re.escape(LEGACY_VERSION) + r"['\"]")
    offenders = [
        rel
        for rel, path in _iter_scanned_files()
        if pattern.search(path.read_text(encoding="utf-8-sig", errors="ignore"))
    ]
    assert offenders == [], f"旧口径名仍被现行代码当作字面量使用：{offenders}"


def test_production_migration_script_uses_current_version():
    script = REPO_ROOT / "scripts/migrate_profit_basis_to_v2.py"
    source = script.read_text(encoding="utf-8-sig")
    assert f'"{LABOR_COST_CALCULATION_VERSION}"' in source
    # 历史口径行（LABOR_COST_V1）+ 当前口径行都要认，否则会漏掉待改写的旧行
    assert (
        f"'LABOR_COST_V1', '{LABOR_COST_CALCULATION_VERSION}'" in source
    ), "生产 dry-run 脚本的版本过滤必须同时认旧口径行与当前口径行"


def test_rename_migration_contract():
    migration = REPO_ROOT / _MIGRATION_REL
    source = migration.read_text(encoding="utf-8-sig")

    assert f'OLD_VERSION = "{LEGACY_VERSION}"' in source
    assert f'NEW_VERSION = "{NEUTRAL_VERSION}"' in source
    assert (
        'down_revision = "current_schema_20261216_unify_profit_basis_snapshot_rows"'
        in source
    )
    # 改名不改金额、不改行数：迁移只 UPDATE 版本列
    assert "pre_commission_amount" not in source
    assert "DELETE FROM" not in source


def test_rename_migration_revision_id_length():
    migration = REPO_ROOT / _MIGRATION_REL
    source = migration.read_text(encoding="utf-8-sig")
    match = re.search(r'^revision = "([^"]+)"', source, re.MULTILINE)
    assert match is not None
    assert len(match.group(1)) <= 64, "alembic version_num 字段是 varchar(64)"
