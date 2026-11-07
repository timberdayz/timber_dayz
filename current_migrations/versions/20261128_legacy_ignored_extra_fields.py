"""给 legacy 模板加「已确认的新列」忽略清单(批次 F-4 / API-6)。

背景
----
源文件比模板多出来的列, 会被算成 ``extra_raw_fields`` ⇒ 治理面板上是一条
**永久噪音**: 不阻断入库, 但每次都被报出来, 而且系统没有「这列我确认过,
忽略它」的表达方式(规格 §2.4 的 FE-8)。

本次给 ``core.field_mapping_templates`` 加一列 JSONB(字符串数组),
让用户能在模板编辑里勾掉确认过的新列。

口径
----
* 只加列, **不回填** —— 存量模板的忽略清单为空(等价于「还没确认过任何新列」,
  与迁移前的行为完全一致);
* 不涉及版本级 —— 忽略清单是**模板级**的业务配置, 与清单(``core_fields``)
  不同: 清单决定「这一行是什么」(进指纹), 忽略清单只决定「这一列算不算噪音」;
* 幂等: ``ADD COLUMN IF NOT EXISTS``。

downgrade: 删列。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "current_schema_20261128_legacy_ignored_extra_fields"
down_revision = "current_schema_20261127_semantic_contract_backfill"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_LEGACY = f"{_SCHEMA}.field_mapping_templates"


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"ignored_extra_fields_column_added": 0}

    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_LEGACY}
            ADD COLUMN IF NOT EXISTS ignored_extra_fields JSONB
            """
        )
    )
    stats["ignored_extra_fields_column_added"] = 1

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"ignored_extra_fields_column_dropped": 0}

    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_LEGACY}
            DROP COLUMN IF EXISTS ignored_extra_fields
            """
        )
    )
    stats["ignored_extra_fields_column_dropped"] = 1

    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
