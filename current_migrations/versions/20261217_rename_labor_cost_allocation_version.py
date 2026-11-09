"""人力成本分摊口径改中性名：``LABOR_COST_V2`` → ``LABOR_COST_ALLOC_V1``。

背景
----
``finance.employee_labor_cost_allocations.calculation_version`` 上长期挂着
``LABOR_COST_V1`` / ``LABOR_COST_V2`` 两个值。

它们**不是两个口径在并行跑**，而是历史遗留：

* ``LABOR_COST_V1`` —— 旧算法（按人头平均分摊）算出来的历史行；
* ``LABOR_COST_V2`` —— 现行算法（按责任比例加权 + 公司级无归属成本二次分摊）
  写出来的行。

业务上早就只有一个口径了，名字却带着序号，看起来像「还有第二个版本」，
排查问题时经常被问「现在到底跑的是 V1 还是 V2」。

这与利润基数的口径收敛是同一件事：利润基数已经把 ``A_ONLY_V1`` /
``A_PRE_COMMISSION_LABOR_V2`` 收敛成 ``SETTLEMENT_BASIS_V1``，
人力成本分摊这边也一并改成中性名 ``LABOR_COST_ALLOC_V1``
（与 ``SETTLEMENT_BASIS_V1`` 同一风格：「V1」= 收敛后的唯一一版口径）。

本迁移做三件事
--------------
1. 把现有 ``LABOR_COST_V2`` 行**原地改名**成 ``LABOR_COST_ALLOC_V1``；
2. 把列的默认值改成新口径名（默认值以前是 ``LABOR_COST_V1`` ——
   那是旧口径名，任何没显式写版本号的插入都会落进「读端看不见」的口袋）；
3. 用资产文件重建 ``mart.shop_month_labor_cost``（视图里写死了版本字面量）。

刻意**不改写** ``LABOR_COST_V1`` 历史行
------------------------------------
那一行是旧算法算出来的结果，改名字等于伪造历史。
读端只认当前口径（按 ``LABOR_COST_CALCULATION_VERSION`` 过滤），
所以历史行不参与任何当期计算。

发布顺序
--------
**必须先跑本迁移、再发布新代码。**

反序（先发代码、后跑迁移）会让
``LaborCostProjectionService.refresh_month`` 找不到旧版本的行
⇒ 新建一批同名不同版本的重复行 ⇒ 人力成本算两遍。
本迁移是原地改名，不新增行，所以不会有这个问题 ——
前提是它在应用启动之前执行完。

安全性
------
* 改名不新增行、不删除行 ⇒ 行数不变、金额不变；
* ``uq_employee_labor_cost_shop_scope`` /
  ``uq_employee_labor_cost_company_scope`` 的唯一键里含 ``calculation_version``，
  若同一把钥匙上同时存在新旧两版行，UPDATE 会直接触发唯一约束冲突而中止
  ⇒ 天然 fail-closed。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261217_rename_labor_cost_allocation_version"
down_revision = "current_schema_20261216_unify_profit_basis_snapshot_rows"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 旧口径名 → 新口径名
OLD_VERSION = "LABOR_COST_V2"
NEW_VERSION = "LABOR_COST_ALLOC_V1"

TABLE = "finance.employee_labor_cost_allocations"
COLUMN = "calculation_version"

#: 需要重建的视图 → 资产文件（相对仓库根）
VIEW_ASSETS = (("mart.shop_month_labor_cost", "sql/mart/shop_month_labor_cost.sql"),)


def _driver_connection():
    """拿到原生 psycopg2 连接。

    ``Connection.connection`` 是**属性**（不是方法）；真正的驱动连接在它的
    ``driver_connection`` 上，后面**不能加括号**。
    """
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（**可以含多条语句**）。"""
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _rebuild_view(view_name: str, asset_rel_path: str) -> bool:
    """用 ``sql/`` 下的资产文件重建视图；资产缺失 → 跳过并告警。"""
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        print(
            "[WARN] 资产文件缺失，跳过视图重建：{view} ← {path}".format(
                view=view_name, path=asset_rel_path
            )
        )
        return False
    _exec_sql_text(asset_path.read_text(encoding="utf-8-sig"))
    return True


def _rename_rows(old_version: str, new_version: str) -> int:
    """把指定口径名的行改名，返回受影响的行数。"""
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE finance.employee_labor_cost_allocations
               SET calculation_version = :new_version,
                   updated_at = CURRENT_TIMESTAMP
             WHERE calculation_version = :old_version
            """
        ),
        {"old_version": old_version, "new_version": new_version},
    )
    return int(result.rowcount or 0)


def _set_default(version: str) -> None:
    op.execute(
        f"ALTER TABLE {TABLE} ALTER COLUMN {COLUMN} SET DEFAULT '{version}'"
    )


def upgrade() -> None:
    renamed = _rename_rows(OLD_VERSION, NEW_VERSION)
    print(f"[INFO] 人力成本分摊口径改名：{OLD_VERSION} → {NEW_VERSION}，{renamed} 行")
    _set_default(NEW_VERSION)
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)


def downgrade() -> None:
    """回滚：把行名与默认值改回旧口径名，并重建视图。"""
    renamed = _rename_rows(NEW_VERSION, OLD_VERSION)
    print(f"[INFO] 人力成本分摊口径回滚：{NEW_VERSION} → {OLD_VERSION}，{renamed} 行")
    _set_default(OLD_VERSION)
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)
