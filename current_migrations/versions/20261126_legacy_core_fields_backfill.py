"""把版本级的核心字段清单回填到 legacy 编辑面(批次 E 收尾)。

背景
----
批次 E 的清单权威副本在 ``core.field_mapping_template_versions.core_fields``,
但**编辑面**在 ``core.field_mapping_templates``(用户在工作台改的就是这一行)。

第一次迁移 ``20261125`` 只给 legacy 表**加了列**, 没有回填 ——
所以 legacy 行全是 ``NULL``, 读侧会退回版本级清单(没问题),
但**保存路径的「继承旧清单」拿不到东西** ⇒ 第一次重存模板时
清单会被「按规范化后的 deduplication_fields 现推」⇒

* 键名从**原始物理列名**变成**规范语义键** ⇒ hash 变了
  ⇒ 已入库的行被当成新数据(离线回放实测 6 个版本 / 81 行受影响)。

本次回填把「当前生效版本」的清单复制到对应的 published legacy 行,
于是重存模板时能**沿用原始物理列名作键名** ⇒ hash 口径不变。

口径
----
* 只回填 ``status='published'`` 的 legacy 模板(当前生效的那一版);
* 清单源 = 该模板所属**家族**的 ``status='active'`` 版本;
* 家族维度含 ``account`` ⇒ 同一 (platform, data_domain, sub_domain, granularity)
  可能有多个家族; 逐个模板按「它在哪几个家族的 legacy_template_ids 里」定位,
  取**版本号最大**的那一版清单(家族目录以最新版本为准);
* 已回填的跳过 ⇒ 幂等。

downgrade: 清空回填值(列本身留给 20261125 的 downgrade 删)。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "current_schema_20261126_legacy_core_fields_backfill"
down_revision = "current_schema_20261125_template_versions_core_fields"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_LEGACY = f"{_SCHEMA}.field_mapping_templates"
_FAMILIES = f"{_SCHEMA}.field_mapping_template_families"
_VERSIONS = f"{_SCHEMA}.field_mapping_template_versions"


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"legacy_core_fields_backfilled": 0}

    bind.execute(
        sa.text(
            f"""
            UPDATE {_LEGACY} t
            SET core_fields = src.core_fields,
                updated_at = now()
            FROM (
                SELECT DISTINCT ON (link.template_id)
                       link.template_id,
                       link.core_fields
                FROM (
                    SELECT v.id AS version_id,
                           v.core_fields,
                           (jsonb_array_elements_text(v.legacy_template_ids))::int AS template_id
                    FROM {_VERSIONS} v
                    WHERE v.status = 'active'
                      AND v.core_fields IS NOT NULL
                      AND jsonb_array_length(v.core_fields) > 0
                      AND COALESCE(jsonb_array_length(v.legacy_template_ids), 0) > 0
                ) AS link
                ORDER BY link.template_id, link.version_id DESC
            ) AS src
            WHERE src.template_id = t.id
              AND t.status = 'published'
              AND t.core_fields IS NULL
            """
        )
    )
    stats["legacy_core_fields_backfilled"] = int(
        bind.execute(
            sa.text(
                f"""
                SELECT count(*) AS cnt
                FROM {_LEGACY}
                WHERE core_fields IS NOT NULL
                  AND jsonb_array_length(core_fields) > 0
                """
            )
        ).scalar()
        or 0
    )

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"legacy_core_fields_cleared": 0}
    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_LEGACY}
            SET core_fields = NULL
            WHERE core_fields IS NOT NULL
            """
        )
    )
    stats["legacy_core_fields_cleared"] = int(result.rowcount or 0)
    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
