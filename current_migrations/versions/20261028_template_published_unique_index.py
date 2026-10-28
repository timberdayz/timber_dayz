"""模板 ``published`` 唯一性: 收敛历史重复 + 加部分唯一索引。

背景
----
``core.field_mapping_templates`` 只有普通索引 ``ix_template_dimension_v2``,
**没有** (platform, data_domain, granularity, sub_domain, account) 的唯一约束。
唯一性一直靠应用层「保存模板时归档旧 published + 版本递增」维持。

问题:
* 数据库里存在 5 组同维度多个 ``published`` 的历史脏数据
* ``find_best_template()`` 只能靠 ``ORDER BY version DESC`` 碰运气取第一条
* ``save_template()`` 用 ``scalar_one_or_none()`` 找旧模板, 遇到重复直接抛
  ``MultipleResultsFound`` -> 「保存模板」接口整体 500

处理方式
--------
先归档每个维度里**非胜出**的 published 模板, 再建部分唯一索引兜底。

胜出规则(与实际源文件比对结果核对过):
  ``version DESC, created_at DESC, id DESC``

逐组核对结果:
* ``shopee/analytics/monthly``        保留 v3 (321) —— 与实际文件一致
* ``shopee/orders/daily``              保留 356 (同版本, 创建更晚) —— 与实际文件一致
* ``shopee/services/monthly/agent``    保留 v2 (322)
* ``shopee/services/monthly/ai_assistant`` 保留 v2 (323)
* ``tiktok/analytics/daily``           保留 v9 (365) —— 与实际文件一致

幂等: 归档步骤只处理当前仍是 published 的行; 索引使用 ``IF NOT EXISTS``。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261028_template_published_unique_index"
down_revision = "current_schema_20261028_analytics_contract_shop_id_optional"
branch_labels = None
depends_on = None


TABLE = "field_mapping_templates"
SCHEMA = "core"
INDEX_NAME = "uq_field_mapping_templates_published_dimension"


def _table_exists() -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(TABLE, schema=SCHEMA)


def upgrade() -> None:
    if not _table_exists():
        return

    # 1) 归档同维度中非胜出的 published 模板
    op.execute(
        f"""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY platform,
                                    data_domain,
                                    COALESCE(granularity, ''),
                                    COALESCE(sub_domain, ''),
                                    COALESCE(account, '')
                       ORDER BY COALESCE(version, 0) DESC, created_at DESC, id DESC
                   ) AS rn
            FROM {SCHEMA}.{TABLE}
            WHERE status = 'published'
        )
        UPDATE {SCHEMA}.{TABLE} AS t
        SET status = 'archived',
            updated_at = now()
        FROM ranked AS r
        WHERE t.id = r.id
          AND r.rn > 1
        """
    )

    # 2) 部分唯一索引: 同一维度只允许一个 published 模板
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME}
        ON {SCHEMA}.{TABLE} (
            platform,
            data_domain,
            COALESCE(granularity, ''),
            COALESCE(sub_domain, ''),
            COALESCE(account, '')
        )
        WHERE status = 'published'
        """
    )


def downgrade() -> None:
    if not _table_exists():
        return
    op.execute(f"DROP INDEX IF EXISTS {SCHEMA}.{INDEX_NAME}")
