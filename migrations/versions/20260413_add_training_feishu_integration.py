"""add training feishu integration fields

Revision ID: 20260413_training_feishu_integration
Revises: 20260413_merge_training_heads
Create Date: 2026-04-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_training_feishu_integration"
down_revision = "20260413_merge_training_heads"
branch_labels = None
depends_on = None

CORE_SCHEMA = "core"


def _table_names(connection, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return set(inspector.get_table_names(schema=schema_name))
    except Exception:
        return set()


def _column_names(connection, table_name: str, schema_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    try:
        return {column["name"] for column in inspector.get_columns(table_name, schema=schema_name)}
    except Exception:
        return set()


def upgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, CORE_SCHEMA)

    if "training_programs" in table_names:
        columns = _column_names(connection, "training_programs", CORE_SCHEMA)
        for column_name, column in (
            ("learning_url", sa.Column("learning_url", sa.String(length=1024), nullable=True)),
            ("exam_url", sa.Column("exam_url", sa.String(length=1024), nullable=True)),
            ("materials_url", sa.Column("materials_url", sa.String(length=1024), nullable=True)),
            ("external_course_id", sa.Column("external_course_id", sa.String(length=128), nullable=True)),
            ("external_exam_id", sa.Column("external_exam_id", sa.String(length=128), nullable=True)),
        ):
            if column_name not in columns:
                op.add_column("training_programs", column, schema=CORE_SCHEMA)

    if "training_feishu_configs" not in table_names:
        op.create_table(
            "training_feishu_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("provider_code", sa.String(length=32), nullable=False, server_default=sa.text("'feishu'")),
            sa.Column("app_id", sa.String(length=128), nullable=False),
            sa.Column("app_secret_encrypted", sa.Text(), nullable=True),
            sa.Column("tenant_key", sa.String(length=128), nullable=True),
            sa.Column("base_url", sa.String(length=255), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("updated_by_user_id", sa.BigInteger(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["updated_by_user_id"], [f"{CORE_SCHEMA}.dim_users.user_id"]),
            sa.UniqueConstraint("provider_code", name="uq_training_feishu_configs_provider_code"),
            schema=CORE_SCHEMA,
        )


def downgrade() -> None:
    connection = op.get_bind()
    table_names = _table_names(connection, CORE_SCHEMA)
    if "training_feishu_configs" in table_names:
        op.drop_table("training_feishu_configs", schema=CORE_SCHEMA)
