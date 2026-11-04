"""人力成本分摊口径统一：视图与读路径都只认 V2，杜绝「同月算两遍」。

背景
----
``finance.employee_labor_cost_allocations`` 里同一行会被写入**两个口径版本**：

- ``calculation_version = 'LABOR_COST_V1'`` —— 历史行；
- ``calculation_version = 'LABOR_COST_V2'`` —— 现在写入的行
  （见 ``backend/services/labor_cost_projection_service.py``）。

``scripts/migrate_profit_basis_to_v2.py`` 是**原地 UPDATE** 把 V1 行改成 V2，
但它会**跳过受保护的工资月**（已确认/已发放的月份）⇒ 那些月份仍然是 V1 行。
随后 ``refresh_month`` 又会为同一个月新建 V2 行 ⇒ **同一个人力成本两行并存**。

后果
----
``mart.shop_month_labor_cost`` 与几处直接查 base 表的读路径**没有按版本过滤**
⇒ 看板经营指标里的「人力成本」虚高（最多两倍）。

利润基数侧（``backend/services/profit_basis_service.py``）**本来就是按版本过滤的**，
所以之前是「利润基数一套口径、看板另一套口径」。

本迁移做两件事
--------------
1. 用 ``sql/mart/shop_month_labor_cost.sql`` 资产文件重建视图（视图定义的 SSOT
   是资产文件，迁移不抄第二份）—— 资产里已加上
   ``AND calculation_version = 'LABOR_COST_V2'``；
2. 把视图里 ``source_payroll_status IN ('confirmed','paid')`` 改成与
   ``backend/services/payroll_period_lock_service.py`` 的
   ``PAYROLL_LOCKED_STATUSES`` 一致（多一个 ``approved``）。

其余读路径（看板服务、费用管理、月结服务）的版本过滤是**代码层**的改动，
随应用发布生效，不需要迁移。

数据安全性
----------
生产上 ``finance.employee_labor_cost_allocations`` 目前是 **0 行**，
本次迁移只是改视图定义，不动任何业务数据。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261108_align_labor_cost_allocation_version"
down_revision = "current_schema_20261107_align_dim_shops_with_shop_accounts"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

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
    """执行一段原生 SQL（**可以含多条语句**）。

    psycopg2 走 PostgreSQL 的简单查询协议（``PQexec``），一条 query 里可以带
    多条语句，由数据库自己按分号切分。整份资产文件一次执行，保证
    ``CREATE SCHEMA`` 与视图定义在同一个隐式事务里。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": name}
        ).scalar_one_or_none()
        is not None
    )


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
    _exec_sql_text(asset_path.read_text(encoding="utf-8"))
    return True


def upgrade() -> None:
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)


def downgrade() -> None:
    """回滚：把视图改回「不按版本过滤」的旧定义。

    旧定义只在本仓库的 baseline 迁移里出现过，直接从那里取 SSOT：
    ``current_migrations/versions/20260805_current_schema_baseline.py``。
    这里直接重建成旧口径 —— 口径回滚是**有意的**（回到 V1/V2 混算的旧行为），
    所以刻意不复用资产文件（资产文件已经是新口径了）。
    """
    if not _exists("mart.shop_month_labor_cost"):
        return
    _exec_sql_text(
        """
        CREATE OR REPLACE VIEW mart.shop_month_labor_cost AS
        SELECT
            to_date(period_month || '-01', 'YYYY-MM-DD') AS period_month,
            LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
            shop_id,
            SUM(pre_commission_amount) AS pre_commission_labor_cost,
            SUM(performance_amount) AS performance_labor_cost,
            SUM(commission_amount) AS commission_labor_cost,
            SUM(total_amount) AS total_labor_cost,
            CASE
                WHEN BOOL_AND(source_payroll_status IN ('confirmed', 'paid'))
                    THEN 'confirmed'
                ELSE 'projected'
            END AS cost_status
        FROM finance.employee_labor_cost_allocations
        WHERE allocation_scope = 'shop'
        GROUP BY
            to_date(period_month || '-01', 'YYYY-MM-DD'),
            LOWER(TRIM(COALESCE(platform_code, ''))),
            shop_id;
        """
    )
