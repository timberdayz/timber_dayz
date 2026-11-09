"""第三批-B：把 ``a_class.operating_costs`` 的中文业务列统一改成英文列名。

背景
----
``a_class.operating_costs`` 是「月度结算单」链路里唯一的手工经营成本明细表，
但它的物理列名一半中文一半英文（``"店铺ID"`` / ``"年月"`` / ``"营销费用"`` …），
与仓库其余 ``a_class`` 表（``a_class.employees``、``a_class.employee_targets``
已在上一批统一成英文）风格不一致，也让每处运行时 SQL 都得写一层中文字面量。

本迁移做两件事
--------------
1. **幂等**地把 16 个中文业务列重命名为英文列名（只重命名，不动数据、
   不动列类型、不动默认值、不动可空性）；
2. 用 ``sql/semantic/shop_month_other_operating_cost.sql`` 资产重建
   ``semantic.shop_month_other_operating_cost`` 视图 —— 视图定义的 SSOT 是
   资产文件，迁移不抄第二份。

为什么删除时间 / 删除人 / platform_code 也一起改
-----------------------------------------------
``删除时间`` / ``删除人`` 是软删除列、``platform_code`` 是平台列，
但它们同样是**中文物理列名**，留着就会让这张表继续"半中半英"。
本次统一按仓库既有英文命名改成 ``deleted_at`` / ``deleted_by`` /
``platform_code``（后者本来就是英文），**语义完全不变**，
只是列名对齐；软删除口径（``deleted_at IS NULL``）与平台列口径不变。

列名映射
--------
===================== ==========================
旧列名（中文）        新列名（英文）
===================== ==========================
``店铺ID``            ``shop_id``
``年月``              ``year_month``
``租金``              ``rent_amount``
``营销费用``          ``marketing_amount``
``水电费``            ``utility_amount``
``AI Token费用``      ``ai_token_amount``
``人力费用``          ``labor_amount``
``其他成本``          ``other_amount``
``成本合计``          ``total_amount``
``备注``              ``remark``
``附件``              ``attachments``
``是否锁定``          ``is_locked``
``创建时间``          ``created_at``
``更新时间``          ``updated_at``
``删除时间``          ``deleted_at``
``删除人``            ``deleted_by``
===================== ==========================

为什么用 ``*_amount`` 而不是 ``rent`` / ``marketing_fee``
-------------------------------------------------------
仓库既有英文列名已经形成 ``_amount`` 后缀约定：
``finance.employee_labor_cost_allocations.total_amount``、
``finance.shop_profit_basis.a_class_cost_amount``、
``monthly_profit_settlement_service`` 里的 ``public_labor_amount`` 等。
本次沿用该约定，避免同一仓库里出现两套金额列命名。

数据安全性
----------
- 只做 ``RENAME COLUMN``：行数、列顺序、数据、约束语义、索引定义全部不变
  （PostgreSQL 会自动把依赖视图/约束里的列名一并改掉）；
- 索引与唯一约束的**名字**保持不变（``uq_operating_costs_a_platform_shop_month`` 等），
  只更新其列引用，避免制造"ORM 声明的约束名"与库内不一致的新漂移；
- 幂等：已经是英文列名的库重跑本迁移不会报错（``DO $$`` 里逐列判断）。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261214_unify_operating_costs_columns"
down_revision = "current_schema_20261213_employee_performance_coefficient"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

TABLE = "a_class.operating_costs"

#: 中文物理列 → 英文物理列（顺序即执行顺序，downgrade 时逆序回退）
COLUMN_RENAMES = (
    ("店铺ID", "shop_id"),
    ("年月", "year_month"),
    ("租金", "rent_amount"),
    ("营销费用", "marketing_amount"),
    ("水电费", "utility_amount"),
    ("AI Token费用", "ai_token_amount"),
    ("人力费用", "labor_amount"),
    ("其他成本", "other_amount"),
    ("成本合计", "total_amount"),
    ("备注", "remark"),
    ("附件", "attachments"),
    ("是否锁定", "is_locked"),
    ("创建时间", "created_at"),
    ("更新时间", "updated_at"),
    ("删除时间", "deleted_at"),
    ("删除人", "deleted_by"),
)

#: 需要重建的视图 → 资产文件（相对仓库根）
VIEW_ASSETS = (
    (
        "semantic.shop_month_other_operating_cost",
        "sql/semantic/shop_month_other_operating_cost.sql",
    ),
)


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


def _table_exists() -> bool:
    return sa.inspect(op.get_bind()).has_table("operating_costs", schema="a_class")


def _column_exists(column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("operating_costs", schema="a_class"):
        return False
    return any(
        col["name"] == column
        for col in inspector.get_columns("operating_costs", schema="a_class")
    )


def _rename_columns(pairs) -> None:
    """幂等重命名一批列。

    用 ``DO $$`` 逐列判断 ``information_schema.columns``，所以：
    - 已经是新列名的库重跑不会报错；
    - 新旧列名同时存在（半迁移状态）也会被收敛到新列名。
    """
    if not _table_exists():
        return
    statements = []
    for old, new in pairs:
        statements.append(
            """
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'a_class'
          AND table_name = 'operating_costs'
          AND column_name = '{old}'
    ) THEN
        EXECUTE 'ALTER TABLE a_class.operating_costs RENAME COLUMN "{old}" TO "{new}"';
    END IF;
""".format(old=old, new=new)
        )
    if not statements:
        return
    _exec_sql_text(
        "DO $$\nBEGIN\n" + "".join(statements) + "END\n$$;"
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
    _exec_sql_text(asset_path.read_text(encoding="utf-8-sig"))
    return True


def _rebuild_views() -> None:
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)


#: downgrade 时用的旧视图定义（中文列名版本）。
#: 资产文件已经是新口径，所以回滚**刻意不复用**资产文件。
_OLD_SEMANTIC_VIEW_SQL = """
CREATE OR REPLACE VIEW semantic.shop_month_other_operating_cost AS
SELECT
    to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
    LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
    "店铺ID" AS shop_id,
    SUM(
        COALESCE(
            "成本合计",
            COALESCE("租金", 0)
            + COALESCE("营销费用", 0)
            + COALESCE("水电费", 0)
            + COALESCE("AI Token费用", 0)
            + COALESCE("人力费用", 0)
            + COALESCE("其他成本", 0)
        ) - COALESCE("人力费用", 0)
    ) AS other_operating_cost
FROM a_class.operating_costs
WHERE "删除时间" IS NULL
GROUP BY
    to_date("年月" || '-01', 'YYYY-MM-DD'),
    LOWER(TRIM(COALESCE(platform_code, ''))),
    "店铺ID";
"""


def upgrade() -> None:
    _rename_columns(COLUMN_RENAMES)
    _rebuild_views()


def downgrade() -> None:
    # 回滚：列名退回中文（逆序），再把视图改回旧口径。
    _rename_columns(tuple(reversed(COLUMN_RENAMES)))
    if _table_exists() and _column_exists("年月"):
        _exec_sql_text(_OLD_SEMANTIC_VIEW_SQL)
