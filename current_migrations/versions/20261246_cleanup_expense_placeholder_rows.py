"""清理费用管理里的「未来月份占位行」。

背景
----
2026-06-09 15:51 的一次批量操作，为当时所有运营店铺预建了 2026 年 1-12 月
共 12 个月的空费用行，并写入「每月 20,000 元人力成本」按 19 家店均摊的结果
（每店 1052.63 = 20000 / 19）。这些行：

* ``remark`` / ``attachments`` 全空 —— 没有任何人工录入痕迹；
* 六个成本科目里除 ``labor_amount`` 外全是 0；
* ``created_at`` 全部相同（同一批 INSERT）；
* 06~12 月每月金额完全相同（整 20,000），而真实工资单投影
  （``finance.employee_labor_cost_allocations`` 的 2026-07 / 2026-10）
  是 31,184.61 / 25,291.93 这类非整数值。

⇒ 它们不是业务事实，是那次批量操作的副作用。已停用店铺因此在 11 月
仍会出现在费用管理页面上。

本迁移做什么
------------
把 2026-06 ~ 2026-12 的**纯占位行**软删（``deleted_at`` + ``deleted_by``
+ 批次标记 ``remark``），共 113 行、labor 合计 118,947.37。

为什么不碰 2026-01 ~ 2026-05
-----------------------------
那 18 行同形态行落在历史月份，与真实录入行混在同一批数据里
（ETERNALBLOOM_SG 的 2026-01 行含真实租金 50.30）。清 06 之后已能解决
「停用店出现在未来月份」；历史月份的口径留给「店铺营业时间轴」方案一并处理。

连带影响（已由业务签字确认）
--------------------------
看板业务概览 2026-06 / 09 / 11 / 12 的成本会从 20,000 变为 ``--``，
2026-08 从 20,027.79 变为 1,080.42 —— 这是**更真实**的状态：
那几个月本来就没有任何人工录入的费用，也没有工资单投影。
同仓库先例：``20261243_drop_legacy_profit_basis`` 同样接受"删掉后那些月份
变成空白，这是刻意的"。

可逆性
------
**可逆**：``downgrade()`` 按批次标记精确还原这 113 行。
数据可恢复性另由发版流程的迁移前备份兜底。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261246_cleanup_expense_placeholder_rows"
# ⚠️ 本迁移接在**在途迁移** current_schema_20261245_drop_b_cost_analysis_views 之后。
# 该在途文件目前只存在于主工作区（未跟踪），worktree 内没有 —— 迁移链在 worktree 内
# 仍呈现单头，但**迁移只在 main 的完整链上执行**（发版流程）。
down_revision = "current_schema_20261245_drop_b_cost_analysis_views"
branch_labels = None
depends_on = None


#: 批次标记：写在 ``remark`` 上，让软删行在「已删除费用记录」区可识别，
#: 也让 ``downgrade()`` 能精确还原本批次。
BATCH_MARK = "[占位行清理 2026-11-28]"

CLEANUP_START = "2026-06"
CLEANUP_END = "2026-12"

#: ``core.dim_users.user_id`` = 4（xihong，超管），与既有 5 条软删行一致。
CLEANUP_BY = 4

#: 纯占位行判定：除人力费外六个科目全 0，且无备注、无附件。
PLACEHOLDER_PREDICATE = """
    deleted_at IS NULL
    AND COALESCE(rent_amount, 0) = 0
    AND COALESCE(marketing_amount, 0) = 0
    AND COALESCE(utility_amount, 0) = 0
    AND COALESCE(ai_token_amount, 0) = 0
    AND COALESCE(other_amount, 0) = 0
    AND COALESCE(total_amount, 0) = COALESCE(labor_amount, 0)
    AND COALESCE(remark, '') = ''
    AND COALESCE(attachments, '[]'::jsonb) = '[]'::jsonb
"""


def upgrade() -> None:
    statement = sa.text(
        f"""
        UPDATE a_class.operating_costs
           SET deleted_at = now(),
               deleted_by = :deleted_by,
               remark = :batch_mark,
               updated_at = now()
         WHERE year_month BETWEEN :start_month AND :end_month
           AND {PLACEHOLDER_PREDICATE}
        """
    ).bindparams(
        sa.bindparam("deleted_by", value=CLEANUP_BY),
        sa.bindparam("batch_mark", value=BATCH_MARK),
        sa.bindparam("start_month", value=CLEANUP_START),
        sa.bindparam("end_month", value=CLEANUP_END),
    )
    op.execute(statement)


def downgrade() -> None:
    statement = sa.text(
        f"""
        UPDATE a_class.operating_costs
           SET deleted_at = NULL,
               deleted_by = NULL,
               remark = '',
               updated_at = now()
         WHERE remark = :batch_mark
           AND deleted_at IS NOT NULL
           AND year_month BETWEEN :start_month AND :end_month
        """
    ).bindparams(
        sa.bindparam("batch_mark", value=BATCH_MARK),
        sa.bindparam("start_month", value=CLEANUP_START),
        sa.bindparam("end_month", value=CLEANUP_END),
    )
    op.execute(statement)
