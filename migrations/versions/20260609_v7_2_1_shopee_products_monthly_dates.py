"""Repair Shopee products monthly business-date template rules.

Revision ID: 20260609_v721_shopee_products_dates
Revises: 20260610_sales_targets_a_platform
Create Date: 2026-06-09
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260609_v721_shopee_products_dates"
down_revision = "20260610_sales_targets_a_platform"
branch_labels = None
depends_on = None


TEMPLATE_ID = 296
FIELD_PARSE_RULES = [
    {
        "target_field": "metric_date",
        "source_column": "__file_date_from__",
        "value_kind": "single_date",
        "date_format": "yyyy-mm-dd",
        "strict": True,
    },
    {
        "target_field": "period_start_date",
        "source_column": "__file_date_from__",
        "value_kind": "single_date",
        "date_format": "yyyy-mm-dd",
        "strict": True,
    },
    {
        "target_field": "period_end_date",
        "source_column": "__file_date_to__",
        "value_kind": "single_date",
        "date_format": "yyyy-mm-dd",
        "strict": True,
    },
]
DEDUPLICATION_FIELDS = [
    "商品编号",
    "商品",
    "规格编号",
    "规格名称",
    "全球商品货号",
    "metric_date",
]


def _table_exists(connection, schema_name: str, table_name: str) -> bool:
    result = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = :schema_name
              AND table_name = :table_name
            LIMIT 1
            """
        ),
        {"schema_name": schema_name, "table_name": table_name},
    )
    return result.scalar() is not None


def upgrade() -> None:
    connection = op.get_bind()
    field_parse_rules = json.dumps(FIELD_PARSE_RULES, ensure_ascii=False)
    deduplication_fields = json.dumps(DEDUPLICATION_FIELDS, ensure_ascii=False)

    if _table_exists(connection, "core", "field_mapping_templates"):
        connection.execute(
            sa.text(
                """
                UPDATE core.field_mapping_templates
                SET field_parse_rules = CAST(:field_parse_rules AS jsonb),
                    deduplication_fields = CAST(:deduplication_fields AS jsonb),
                    updated_at = NOW()
                WHERE id = :template_id
                """
            ),
            {
                "template_id": TEMPLATE_ID,
                "field_parse_rules": field_parse_rules,
                "deduplication_fields": deduplication_fields,
            },
        )

    if _table_exists(connection, "core", "field_mapping_template_versions"):
        connection.execute(
            sa.text(
                """
                UPDATE core.field_mapping_template_versions
                SET deduplication_fields = CAST(:deduplication_fields AS jsonb),
                    updated_at = NOW()
                WHERE legacy_template_ids @> CAST(:legacy_template_ids AS jsonb)
                """
            ),
            {
                "legacy_template_ids": json.dumps([TEMPLATE_ID]),
                "deduplication_fields": deduplication_fields,
            },
        )

    if _table_exists(connection, "core", "field_mapping_template_variants"):
        connection.execute(
            sa.text(
                """
                UPDATE core.field_mapping_template_variants
                SET field_parse_rules = CAST(:field_parse_rules AS jsonb),
                    updated_at = NOW()
                WHERE source_legacy_template_id = :template_id
                """
            ),
            {
                "template_id": TEMPLATE_ID,
                "field_parse_rules": field_parse_rules,
            },
        )


def downgrade() -> None:
    """Data repair migration; intentionally not reverted."""
    return None
