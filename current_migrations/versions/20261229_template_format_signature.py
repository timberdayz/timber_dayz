"""模板「格式签名」列 + published 唯一索引改为 (维度, 格式签名)。

背景
----
``core.field_mapping_templates`` 的 published 唯一键是
``(platform, data_domain, granularity, sub_domain, account)`` ——
也就是**一个维度只能有一种格式**。

但平台的导出格式是**按站点 / 按时间**变的:

* ``shopee/analytics/monthly``: PH 站 ``01/10/2026``(斜杠) vs SG/MY 站
  ``01-10-2026``(连字符) —— **表头完全一致**, 只有日期写法不同;
* ``tiktok/analytics/monthly``: 旧格式 28 列 vs 新格式 29 列。

于是每升级一次模板, 旧格式的文件就再也找不到能解释它的模板 ——
历史数据补不回来(``docs/reports/2026-11-07-shop-identity-and-template-sync-incident.md``
问题 2 / 问题 3)。

做法
----
1. 加一列 ``format_signature`` —— 「这个模板服务的是哪一种文件格式」;
2. 唯一键从 (维度) 改成 (维度, 格式签名) ⇒ 同维度允许多种格式并存;
3. ``save_template`` 归档时只归档**同签名**的旧模板(应用层改动)。

口径
----
``format_signature`` 与变体的 ``variant_kind`` **同一个口径、同一份实现**
(列集合 + 解析方式 + 表头行 + 工作表名模式), 见
:func:`backend.services.template_family_service.build_variant_kind`。
本文件的回填 SQL 与 Python 侧**逐字一致**(同样的归一化), 由
``backend/tests/data_pipeline/test_template_format_signature_guardrails.py``
里的守护测试逐行比对。

为什么复用「业务形态标识」而不是另立一套
----------------------------------------
「格式」与「业务形态」在本题上是同一件事: 平台改一次导出格式
(加列 / 改日期分隔符)⇒ 文件的业务形态变了 ⇒ 这是另一种格式。
若另立一套签名, 就会出现「模板说自己是格式 1、变体说自己是形态 2」
这种自相矛盾的状态 —— 而矛盾的两份定义迟早会漂移。

幂等: 加列用 ``IF NOT EXISTS``; 回填只改「算出来与已存值不同」的行;
索引用 ``IF NOT EXISTS``。

downgrade: 删列, 并把唯一索引还原成 (维度)。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261229_template_format_signature"
down_revision = "current_schema_20261228_bridge_spu_sku_binding_status_constraint"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_TABLE = f"{_SCHEMA}.field_mapping_templates"

#: 旧索引(按维度唯一)与新索引(按维度 + 格式签名唯一)。
OLD_INDEX_NAME = "uq_field_mapping_templates_published_dimension"
NEW_INDEX_NAME = "uq_field_mapping_templates_published_dimension_format"

#: 参与「解析方式签名」的字段(顺序与 Python 侧 ``_PARSE_SIGNATURE_FIELDS`` 一致)。
_PARSE_FIELDS = ("target_field", "source_column", "value_kind", "date_format", "strict")

#: Python ``str.strip()`` 会去掉的空白字符。
_TRIM_CHARS = " \t\r\n\f\v"

#: 列集合签名 —— 与 Python ``_header_signature`` 一致:
#:     逐项 strip + lower → 用 '|' 连接 → md5 取前 8 位。
_COLS_ARRAY = """
    (select coalesce(
        array_agg(lower(btrim(x, E'{chars}'))),
        '{{}}'::text[]
     )
       from jsonb_array_elements_text(coalesce(t.header_columns, '[]'::jsonb)) as x
      where btrim(x, E'{chars}') <> '')
"""

_COLS_SIG = """
    case
        when coalesce(array_length({cols_array}, 1), 0) = 0 then 'empty'
        else substr(
            md5(lower(array_to_string({cols_array}, '|'))),
            1, 8
        )
    end
"""

#: 解析方式签名 —— 与 Python ``_parse_signature`` 一致:
#:     逐项取 5 个字段 → strip + lower → 用 '|' 连接 → **排序** → 用 ';' 连接
#:     → md5 取前 8 位。
_PARSE_SIG = """
    case
        when {_parse_items} is null or {_parse_items} = '' then 'empty'
        else substr(md5({_parse_items}), 1, 8)
    end
"""

#: 工作表名 —— 与 Python ``str(sheet_name or '').strip().lower()`` 对齐。
_SHEET = f"lower(btrim(coalesce(t.sheet_name, ''), E'{_TRIM_CHARS}'))"


def _parse_items_sql() -> str:
    """构造「解析方式签名」的 SQL 片段。

    字段取值用 ``->>``(取 JSON 标量的文本形式) + ``coalesce``(缺失/JSON null → ''),
    与 Python 侧 ``"" if value is None else str(value)`` 对齐。
    """
    cells = " || '|' || ".join(
        "lower(btrim(coalesce(r->>'{field}', ''), E'{chars}'))".format(
            field=field, chars=_TRIM_CHARS
        )
        for field in _PARSE_FIELDS
    )
    return (
        "(select string_agg(item, ';' order by item) from ("
        f"select {cells} as item "
        "from jsonb_array_elements(coalesce(t.field_parse_rules, '[]'::jsonb)) as r"
        ") s)"
    )


def _format_signature_sql() -> str:
    """整个 ``format_signature`` 的 SQL 表达式。"""
    parse_items = _parse_items_sql()
    parse_sig = _PARSE_SIG.format(_parse_items=parse_items)
    cols_sig = _COLS_SIG.format(cols_array=_COLS_ARRAY.format(chars=_TRIM_CHARS))
    return """
    'form_' || {cols} || '_' || {parse}
        || case when coalesce(t.header_row, 0) = 0
                then '' else '_h' || t.header_row::text end
        || case when coalesce({sheet}, '') = ''
                then '' else '_s' || substr(md5({sheet}), 1, 6) end
    """.format(
        cols=cols_sig,
        parse=parse_sig,
        sheet=_SHEET,
    )


def _dimension_columns() -> str:
    """维度列(与旧唯一索引逐字一致 —— 含 COALESCE 空值归一)。"""
    return """
        platform,
        data_domain,
        coalesce(granularity, ''),
        coalesce(sub_domain, ''),
        coalesce(account, '')
    """


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {
        "format_signature_column_added": 0,
        "format_signature_backfilled": 0,
        "duplicates_archived": 0,
        "old_index_dropped": 0,
        "new_index_created": 0,
    }

    # 1) 加列
    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_TABLE}
            ADD COLUMN IF NOT EXISTS format_signature VARCHAR(64)
            """
        )
    )
    stats["format_signature_column_added"] = 1

    # 2) 回填(与 Python 侧同一份口径)
    signature_sql = _format_signature_sql()
    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} t
            SET format_signature = {signature_sql}
            WHERE t.format_signature IS DISTINCT FROM {signature_sql}
            """
        )
    )
    stats["format_signature_backfilled"] = int(result.rowcount or 0)

    # 3) 同 (维度, 格式签名) 只留一个 published ——
    #    否则新唯一索引建不起来。胜出规则与旧迁移一致:
    #    version DESC, created_at DESC, id DESC。
    result = bind.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY platform,
                                        data_domain,
                                        coalesce(granularity, ''),
                                        coalesce(sub_domain, ''),
                                        coalesce(account, ''),
                                        coalesce(format_signature, '')
                           ORDER BY coalesce(version, 0) DESC,
                                    created_at DESC,
                                    id DESC
                       ) AS rn
                FROM {_TABLE}
                WHERE status = 'published'
            )
            UPDATE {_TABLE} AS t
            SET status = 'archived',
                updated_at = now()
            FROM ranked AS r
            WHERE t.id = r.id
              AND r.rn > 1
            """
        )
    )
    stats["duplicates_archived"] = int(result.rowcount or 0)

    # 4) 旧索引(按维度唯一)退场
    bind.execute(
        sa.text(f"DROP INDEX IF EXISTS {_SCHEMA}.{OLD_INDEX_NAME}")
    )
    stats["old_index_dropped"] = 1

    # 5) 新索引(按维度 + 格式签名唯一)
    bind.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {NEW_INDEX_NAME}
            ON {_TABLE} (
                {_dimension_columns()},
                coalesce(format_signature, '')
            )
            WHERE status = 'published'
            """
        )
    )
    stats["new_index_created"] = 1

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {
        "new_index_dropped": 0,
        "duplicates_archived": 0,
        "old_index_created": 0,
        "format_signature_column_dropped": 0,
    }

    # 1) 新索引退场
    bind.execute(
        sa.text(f"DROP INDEX IF EXISTS {_SCHEMA}.{NEW_INDEX_NAME}")
    )
    stats["new_index_dropped"] = 1

    # 2) 还原旧索引前, 必须先把同维度的多个 published 归档到只剩一个
    #    (旧索引要求「一个维度一个 published」)。
    result = bind.execute(
        sa.text(
            f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY platform,
                                        data_domain,
                                        coalesce(granularity, ''),
                                        coalesce(sub_domain, ''),
                                        coalesce(account, '')
                           ORDER BY coalesce(version, 0) DESC,
                                    created_at DESC,
                                    id DESC
                       ) AS rn
                FROM {_TABLE}
                WHERE status = 'published'
            )
            UPDATE {_TABLE} AS t
            SET status = 'archived',
                updated_at = now()
            FROM ranked AS r
            WHERE t.id = r.id
              AND r.rn > 1
            """
        )
    )
    stats["duplicates_archived"] = int(result.rowcount or 0)

    # 3) 还原旧索引
    bind.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS {OLD_INDEX_NAME}
            ON {_TABLE} (
                {_dimension_columns()}
            )
            WHERE status = 'published'
            """
        )
    )
    stats["old_index_created"] = 1

    # 4) 删列
    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_TABLE}
            DROP COLUMN IF EXISTS format_signature
            """
        )
    )
    stats["format_signature_column_dropped"] = 1

    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
