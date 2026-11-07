"""给变体加「业务形态标识」列(批次 G-2)。

背景
----
批次 G 要把「变体」从**按文件名分隔符切分**改成**按业务形态区分**:
``daily_slash`` / ``monthly_dash`` 这类 key 是**文件名的形状**, 换个文件名就变;
真正的业务形态是「列集合 + 解析方式 + 表头行 + 工作表名模式」。

⇒ 变体表加一列 ``variant_kind``, 明确回答「这个变体是什么业务形态」。

口径
----
* ``variant_key`` **保留原值**(存量 key 不改名)—— 改名会让变体 id 变化,
  打破前端与外部引用; 退役的是「按文件名生成 key」这个**机制**, 不是这一列;
* ``variant_kind`` 由变体**自己已有的数据**算出(``required_headers`` /
  ``field_parse_rules`` / ``header_row`` / ``sheet_name_pattern``),
  所以回填是自包含的, 不需要 import backend;
* 回填 SQL 与 Python 侧
  :func:`backend.services.template_family_service.build_variant_kind`
  **逐字一致**(同样的归一化: 去空白 → 小写 → 排序 → md5)——
  ``backend/tests/data_pipeline/test_template_family_business_form_guardrails.py``
  里有守护测试逐行比对两边算出来的值。

downgrade: 删列。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261129_template_variant_kind"
down_revision = "current_schema_20261128_legacy_ignored_extra_fields"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_VARIANTS = f"{_SCHEMA}.field_mapping_template_variants"

#: 参与「解析方式签名」的字段(顺序与 Python 侧 ``_PARSE_SIGNATURE_FIELDS`` 一致)。
_PARSE_FIELDS = ("target_field", "source_column", "value_kind", "date_format", "strict")

#: Python ``str.strip()`` 会去掉的空白字符。
_TRIM_CHARS = " \t\r\n\f\v"

#: 列集合签名 —— 与 Python ``_header_signature`` 一致:
#:     逐项 strip + lower → 用 '|' 连接 → md5 取前 8 位。
#:     (``required_headers`` 是 JSONB 数组 ⇒ 用 ``jsonb_array_elements_text`` 取文本。)
_COLS_ARRAY = """
    (select coalesce(
        array_agg(lower(btrim(x, E'{chars}'))),
        '{{}}'::text[]
     )
       from jsonb_array_elements_text(coalesce(v.required_headers, '[]'::jsonb)) as x
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
        "from jsonb_array_elements(coalesce(v.field_parse_rules, '[]'::jsonb)) as r"
        ") s)"
    )


def _variant_kind_sql() -> str:
    """整个 ``variant_kind`` 的 SQL 表达式。"""
    parse_items = _parse_items_sql()
    parse_sig = _PARSE_SIG.format(_parse_items=parse_items)
    cols_array = _COLS_ARRAY.format(chars=_TRIM_CHARS)
    cols_sig = _COLS_SIG.format(cols_array=cols_array)
    sheet = f"lower(btrim(coalesce(v.sheet_name_pattern, ''), E'{_TRIM_CHARS}'))"
    return """
    'form_' || {cols} || '_' || {parse}
        || case when coalesce(v.header_row, 0) = 0
                then '' else '_h' || v.header_row::text end
        || case when coalesce({sheet}, '') = ''
                then '' else '_s' || substr(md5({sheet}), 1, 6) end
    """.format(
        cols=cols_sig,
        parse=parse_sig,
        sheet=sheet,
    )


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"variant_kind_column_added": 0, "variant_kind_backfilled": 0}

    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_VARIANTS}
            ADD COLUMN IF NOT EXISTS variant_kind VARCHAR(64)
            """
        )
    )
    stats["variant_kind_column_added"] = 1

    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_VARIANTS} v
            SET variant_kind = {_variant_kind_sql()}
            WHERE v.variant_kind IS DISTINCT FROM {_variant_kind_sql()}
            """
        )
    )
    stats["variant_kind_backfilled"] = int(result.rowcount or 0)

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"variant_kind_column_dropped": 0}

    bind.execute(
        sa.text(
            f"""
            ALTER TABLE {_VARIANTS}
            DROP COLUMN IF EXISTS variant_kind
            """
        )
    )
    stats["variant_kind_column_dropped"] = 1

    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
