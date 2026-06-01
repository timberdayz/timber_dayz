"""add template family/version/variant tables

Revision ID: 20260531_add_template_family_version_variant
Revises: 20260530_hr_schema_alignment_cleanup
Create Date: 2026-05-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260531_add_template_family_version_variant"
down_revision = "20260530_hr_schema_alignment_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_mapping_template_families",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("data_domain", sa.String(length=64), nullable=False),
        sa.Column("granularity", sa.String(length=32), nullable=True),
        sa.Column("account", sa.String(length=128), nullable=True),
        sa.Column("sub_domain", sa.String(length=64), nullable=True),
        sa.Column("governance_status", sa.String(length=32), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("active_version_id", sa.Integer(), nullable=True),
        sa.Column("source_mode", sa.String(length=32), nullable=False, server_default=sa.text("'legacy_projection'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "platform",
            "data_domain",
            "sub_domain",
            "granularity",
            "account",
            name="uq_template_family_dimension",
        ),
        schema="core",
    )
    op.create_index(
        "ix_template_family_dimension",
        "field_mapping_template_families",
        ["platform", "data_domain", "sub_domain", "granularity", "account"],
        schema="core",
    )

    op.create_table(
        "field_mapping_template_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("template_name", sa.String(length=256), nullable=True),
        sa.Column("deduplication_fields", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("header_bindings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("legacy_template_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.UniqueConstraint("family_id", "version_no", name="uq_template_version_family_version_no"),
        schema="core",
    )
    op.create_index(
        "ix_template_version_family_status",
        "field_mapping_template_versions",
        ["family_id", "status"],
        schema="core",
    )
    op.create_index(
        "ix_core_field_mapping_template_versions_family_id",
        "field_mapping_template_versions",
        ["family_id"],
        schema="core",
    )

    op.create_table(
        "field_mapping_template_variants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_version_id", sa.Integer(), nullable=False),
        sa.Column("variant_key", sa.String(length=128), nullable=False),
        sa.Column("match_priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("header_row", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sheet_name_pattern", sa.String(length=128), nullable=True),
        sa.Column("required_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parse_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("field_parse_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_legacy_template_id", sa.Integer(), nullable=True),
        sa.Column("template_name", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
        sa.UniqueConstraint("template_version_id", "variant_key", name="uq_template_variant_version_key"),
        sa.CheckConstraint("header_row >= 0 AND header_row <= 100", name="ck_template_variant_header_row_range"),
        schema="core",
    )
    op.create_index(
        "ix_template_variant_version_priority",
        "field_mapping_template_variants",
        ["template_version_id", "match_priority"],
        schema="core",
    )
    op.create_index(
        "ix_core_field_mapping_template_variants_template_version_id",
        "field_mapping_template_variants",
        ["template_version_id"],
        schema="core",
    )
    op.create_index(
        "ix_template_variant_source_legacy_id",
        "field_mapping_template_variants",
        ["source_legacy_template_id"],
        schema="core",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_template_variant_source_legacy_id",
        table_name="field_mapping_template_variants",
        schema="core",
    )
    op.drop_index(
        "ix_core_field_mapping_template_variants_template_version_id",
        table_name="field_mapping_template_variants",
        schema="core",
    )
    op.drop_index(
        "ix_template_variant_version_priority",
        table_name="field_mapping_template_variants",
        schema="core",
    )
    op.drop_table("field_mapping_template_variants", schema="core")

    op.drop_index(
        "ix_core_field_mapping_template_versions_family_id",
        table_name="field_mapping_template_versions",
        schema="core",
    )
    op.drop_index(
        "ix_template_version_family_status",
        table_name="field_mapping_template_versions",
        schema="core",
    )
    op.drop_table("field_mapping_template_versions", schema="core")

    op.drop_index(
        "ix_template_family_dimension",
        table_name="field_mapping_template_families",
        schema="core",
    )
    op.drop_table("field_mapping_template_families", schema="core")
