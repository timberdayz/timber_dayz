"""Turn the baseline-price source into a closed enum (Stage 4, tool 1).

``core.dim_erp_sku.selling_price_source`` was a free-text column: every value
typed by a human was "valid" as far as the database was concerned, so the field
could not answer the only question it exists for — *where did this number come
from?*

Stage 4 replaces it with three values:

``platform_listing``
    Taken from the platform's own product page.  The enum slot is kept because
    the concept is real, but **there is no reliable data source today** (the
    platform SKU catalogue is maintained by hand and its coverage is unknown),
    so nothing promises to fill it automatically.
``erp``
    Came in with the ERP master data.
``manual``
    Typed by an operator in the product centre.

What the migration does, in order:

1. add ``selling_price_source_cleaned_at`` — the timestamp of the cleanup, so
   the normalisation is auditable after the fact;
2. normalise the historical free text:
   - ``NULL`` / empty string **with a baseline price** → ``'manual'``
     (somebody entered that price; the source was simply never recorded);
   - ``NULL`` / empty string **without a baseline price** → ``NULL``
     (there is no price, so there is no source — do not invent one);
   - any other value that is not one of the three enum members → ``'manual'``
     (we cannot tell what it meant, and "manual" is the honest fallback);
3. backfill ``selling_price_confirmed_at`` for rows that carry a baseline price
   but were never confirmed.  The only timestamp available is the row's own
   ``created_at`` — the moment the record entered the system.  ``updated_at`` is
   **not** usable: the "collector → cloud" sync rewrites it on every run, so it
   would make every legacy price look freshly confirmed;
4. add the two CHECK constraints:
   - ``ck_dim_erp_sku_selling_price_source`` — the enum;
   - ``ck_dim_erp_sku_selling_price_confirmed`` — a baseline price implies a
     confirmation date.

Step 3 has to happen before step 4: the second CHECK would otherwise reject the
legacy rows.  Step 3 also has to happen for the **sync** to keep working —
``scripts/sync_product_center_to_cloud.py`` copies every column of
``dim_erp_sku`` from the local database to the cloud one, and a CHECK constraint
is enforced on INSERT, so a source row without a confirmation date would break
the next sync run.

The normalising step is intentionally **not** reversible: the original free
text is gone once it has been mapped onto the enum.  ``downgrade()`` therefore
only removes the constraints and the helper column and leaves the values as
they are.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261121_selling_price_source_enum"
down_revision = "current_schema_20261120_rename_pricing_tier_labels"
branch_labels = None
depends_on = None


_TABLE = "dim_erp_sku"
_SCHEMA = "core"

_ENUM_VALUES = ("platform_listing", "erp", "manual")


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table() -> bool:
    return _inspector().has_table(_TABLE, schema=_SCHEMA)


def _has_column(name: str) -> bool:
    return _has_table() and name in {
        column["name"] for column in _inspector().get_columns(_TABLE, schema=_SCHEMA)
    }


def _has_constraint(name: str) -> bool:
    if not _has_table():
        return False
    existing = _inspector().get_check_constraints(_TABLE, schema=_SCHEMA)
    return any(item.get("name") == name for item in existing)


def _exec(statement: str) -> None:
    """执行一条 DML。

    ⚠️ ``op.execute(sql_text, execution_options=...)`` 的第二个参数**不是**绑定参数，
    传绑定参数必须走 ``op.get_bind().execute(text, params)``。
    """
    op.get_bind().execute(sa.text(statement))


def upgrade() -> None:
    if not _has_table():
        return

    # 1) 清洗时间戳列
    if not _has_column("selling_price_source_cleaned_at"):
        op.add_column(
            _TABLE,
            sa.Column(
                "selling_price_source_cleaned_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema=_SCHEMA,
        )

    enum_list = ", ".join(f"'{value}'" for value in _ENUM_VALUES)

    # 2a) 有基准售价但来源为空/空串 → 'manual'（有人录入了这个价格，只是没记来源）
    _exec(
        f"""
        UPDATE {_SCHEMA}.{_TABLE}
           SET selling_price_source = 'manual',
               selling_price_source_cleaned_at = now()
         WHERE reference_selling_price IS NOT NULL
           AND (selling_price_source IS NULL OR BTRIM(selling_price_source) = '')
        """
    )

    # 2b) 没有基准售价且来源为空/空串 → NULL（没有价格就没有来源，不编造）
    _exec(
        f"""
        UPDATE {_SCHEMA}.{_TABLE}
           SET selling_price_source = NULL,
               selling_price_source_cleaned_at = now()
         WHERE reference_selling_price IS NULL
           AND selling_price_source IS NOT NULL
           AND BTRIM(selling_price_source) = ''
        """
    )

    # 2c) 其余自由文本 → 'manual'（判不出原意，落到最诚实的一档）
    _exec(
        f"""
        UPDATE {_SCHEMA}.{_TABLE}
           SET selling_price_source = 'manual',
               selling_price_source_cleaned_at = now()
         WHERE selling_price_source IS NOT NULL
           AND selling_price_source NOT IN ({enum_list})
        """
    )

    # 3) 回填确认日期：用 created_at（记录进入系统的时间）。
    #    ⚠️ 不用 updated_at —— 同步会重写它，会让所有历史价格看起来"刚确认过"。
    _exec(
        f"""
        UPDATE {_SCHEMA}.{_TABLE}
           SET selling_price_confirmed_at = created_at
         WHERE reference_selling_price IS NOT NULL
           AND selling_price_confirmed_at IS NULL
        """
    )

    # 4) 约束
    if not _has_constraint("ck_dim_erp_sku_selling_price_source"):
        op.create_check_constraint(
            "ck_dim_erp_sku_selling_price_source",
            _TABLE,
            f"selling_price_source IS NULL OR selling_price_source IN ({enum_list})",
            schema=_SCHEMA,
        )
    if not _has_constraint("ck_dim_erp_sku_selling_price_confirmed"):
        op.create_check_constraint(
            "ck_dim_erp_sku_selling_price_confirmed",
            _TABLE,
            "reference_selling_price IS NULL OR selling_price_confirmed_at IS NOT NULL",
            schema=_SCHEMA,
        )


def downgrade() -> None:
    if not _has_table():
        return

    if _has_constraint("ck_dim_erp_sku_selling_price_confirmed"):
        op.drop_constraint(
            "ck_dim_erp_sku_selling_price_confirmed",
            _TABLE,
            schema=_SCHEMA,
            type_="check",
        )
    if _has_constraint("ck_dim_erp_sku_selling_price_source"):
        op.drop_constraint(
            "ck_dim_erp_sku_selling_price_source", _TABLE, schema=_SCHEMA, type_="check"
        )

    if _has_column("selling_price_source_cleaned_at"):
        op.drop_column(_TABLE, "selling_price_source_cleaned_at", schema=_SCHEMA)

    # ⚠️ 来源的枚举化**不可逆**：历史自由文本已被归一，回滚只撤约束与辅助列。
