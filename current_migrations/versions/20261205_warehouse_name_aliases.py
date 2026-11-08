"""Add the warehouse-name alias table and the warehouse column to inventory state.

Why
---
The inventory collector writes the **raw Miaoshou warehouse name** into
``mart.inventory_state.warehouse_name`` (production values: ``新加坡``,
``马来仓``, ``菲律宾1店-儿童书包``, ``菲律宾仓库（维修工具）``,
``菲律宾3店-时尚箱包``), while the commercial side works with the canonical
warehouse code from ``core.dim_warehouses`` (``SG-01`` / ``MY-01`` /
``PH-01-CHILD`` / ``PH-REPAIR`` / ``PH-03-FASHION``).

The two spellings do **not** match — the canonical names carry a trailing
``仓`` that the raw names do not have.  So the mapping cannot be guessed by
string surgery: guessing wrong would attribute stock to the wrong warehouse,
and a wrong warehouse means a wrong age, a wrong tier and a wrong price floor.

This migration therefore introduces the mapping as **explicit rows**:

1. ``core.dim_warehouse_name_aliases`` — ``(source_warehouse_name ->
   warehouse_code)``, seeded from the canonical warehouse dimension so the
   five production warehouse names resolve to exactly one code each;
2. ``mart.inventory_state.warehouse_code`` — the resolved code, backfilled
   from the alias table.

Rows whose warehouse name is **not** in the alias table keep a NULL
``warehouse_code``.  That is deliberate: an unmapped warehouse must stay
visible as "unresolved" instead of silently landing in some other warehouse.
Those rows still take part in the SKU-level aggregate, so no data is lost.

Idempotency
-----------
Every step is guarded by a ``_has_table`` / ``_has_column`` check and the
backfill only fills NULLs, so re-running ``upgrade()`` is a no-op.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261205_warehouse_name_aliases"
down_revision = "current_schema_20261203_semantic_alias_normalized_refresh"
branch_labels = None
depends_on = None


_ALIAS_TABLE = "dim_warehouse_name_aliases"
_ALIAS_SCHEMA = "core"
_STATE_TABLE = "inventory_state"
_STATE_SCHEMA = "mart"

#: Production-observed Miaoshou warehouse names → canonical warehouse code.
#:
#: These five pairs were verified one-to-one against the production database:
#: every raw name in ``mart.inventory_state`` maps to exactly one code and
#: every code is reached by exactly one raw name.
_SEED_ALIASES = (
    ("新加坡", "SG-01"),
    ("马来仓", "MY-01"),
    ("菲律宾1店-儿童书包", "PH-01-CHILD"),
    ("菲律宾仓库（维修工具）", "PH-REPAIR"),
    ("菲律宾3店-时尚箱包", "PH-03-FASHION"),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    if not _has_table(table, schema):
        return False
    return name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def _exec(statement: str, params: dict | None = None) -> None:
    """Execute one DML statement.

    ⚠️ ``op.execute(sql_text, execution_options=...)`` — the second argument is
    **not** bound parameters; binding must go through
    ``op.get_bind().execute(text, params)``.
    """
    op.get_bind().execute(sa.text(statement), params or {})


def _seed_aliases() -> None:
    """Seed the alias rows, skipping any that already exist.

    Only rows whose target warehouse code actually exists in
    ``core.dim_warehouses`` are seeded: a mapping pointing at a warehouse that
    does not exist would fail the foreign key and would be meaningless anyway.
    """
    for source_name, warehouse_code in _SEED_ALIASES:
        _exec(
            """
            INSERT INTO core.dim_warehouse_name_aliases
                (source_warehouse_name, warehouse_code, source)
            SELECT :source_name, :warehouse_code, 'seed_from_dim_warehouses'
            WHERE EXISTS (
                SELECT 1 FROM core.dim_warehouses d
                 WHERE d.warehouse_code = :warehouse_code
            )
              AND NOT EXISTS (
                SELECT 1 FROM core.dim_warehouse_name_aliases a
                 WHERE a.source_warehouse_name = :source_name
            )
            """,
            {"source_name": source_name, "warehouse_code": warehouse_code},
        )


def upgrade() -> None:
    # 1) the alias table itself
    if not _has_table(_ALIAS_TABLE, _ALIAS_SCHEMA):
        op.create_table(
            _ALIAS_TABLE,
            sa.Column(
                "source_warehouse_name",
                sa.String(length=255),
                primary_key=True,
                nullable=False,
            ),
            sa.Column(
                "warehouse_code",
                sa.String(length=128),
                sa.ForeignKey(
                    f"{_ALIAS_SCHEMA}.dim_warehouses.warehouse_code",
                    ondelete="CASCADE",
                ),
                nullable=False,
            ),
            sa.Column("source", sa.String(length=128), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            schema=_ALIAS_SCHEMA,
        )
        op.create_index(
            "ix_dim_warehouse_name_aliases_code",
            _ALIAS_TABLE,
            ["warehouse_code"],
            schema=_ALIAS_SCHEMA,
        )

    # 2) seed the alias rows (needs both tables to exist)
    if _has_table("dim_warehouses", _ALIAS_SCHEMA):
        _seed_aliases()

    # 3) the resolved code on the inventory state rows
    if not _has_table(_STATE_TABLE, _STATE_SCHEMA):
        return

    if not _has_column(_STATE_TABLE, _STATE_SCHEMA, "warehouse_code"):
        op.add_column(
            _STATE_TABLE,
            sa.Column("warehouse_code", sa.String(length=128), nullable=True),
            schema=_STATE_SCHEMA,
        )
        op.create_index(
            "ix_inventory_state_warehouse_code",
            _STATE_TABLE,
            ["warehouse_code"],
            schema=_STATE_SCHEMA,
        )

    # 4) backfill from the alias table — NULL only, so re-running is safe
    if _has_table(_ALIAS_TABLE, _ALIAS_SCHEMA):
        _exec(
            """
            UPDATE mart.inventory_state s
               SET warehouse_code = a.warehouse_code
              FROM core.dim_warehouse_name_aliases a
             WHERE a.source_warehouse_name = s.warehouse_name
               AND s.warehouse_code IS NULL
            """
        )


def downgrade() -> None:
    if _has_column(_STATE_TABLE, _STATE_SCHEMA, "warehouse_code"):
        op.drop_index(
            "ix_inventory_state_warehouse_code",
            table_name=_STATE_TABLE,
            schema=_STATE_SCHEMA,
        )
        op.drop_column(
            _STATE_TABLE,
            "warehouse_code",
            schema=_STATE_SCHEMA,
        )

    if _has_table(_ALIAS_TABLE, _ALIAS_SCHEMA):
        op.drop_index(
            "ix_dim_warehouse_name_aliases_code",
            table_name=_ALIAS_TABLE,
            schema=_ALIAS_SCHEMA,
        )
        op.drop_table(_ALIAS_TABLE, schema=_ALIAS_SCHEMA)
