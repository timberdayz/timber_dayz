"""Add semantic field contracts for template governance.

Revision ID: 20260618_semantic_field_contracts
Revises: 20260618_catalog_file_status_64
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260618_semantic_field_contracts"
down_revision = "20260618_catalog_file_status_64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "semantic_field_contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=True),
        sa.Column("data_domain", sa.String(length=64), nullable=False),
        sa.Column("granularity", sa.String(length=32), nullable=True),
        sa.Column("sub_domain", sa.String(length=64), nullable=True),
        sa.Column("semantic_key", sa.String(length=128), nullable=False),
        sa.Column("importance", sa.String(length=16), nullable=False),
        sa.Column("consumer", sa.String(length=128), server_default="business_overview", nullable=False),
        sa.Column("impact_description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "importance IN ('required', 'optional', 'ignored')",
            name="ck_semantic_field_contract_importance",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "platform",
            "data_domain",
            "granularity",
            "sub_domain",
            "semantic_key",
            "consumer",
            name="uq_semantic_field_contract_dimension",
        ),
        schema="core",
    )
    op.create_index(
        "ix_semantic_field_contract_lookup",
        "semantic_field_contracts",
        ["platform", "data_domain", "granularity", "sub_domain", "consumer", "enabled"],
        schema="core",
    )

    contracts = sa.table(
        "semantic_field_contracts",
        sa.column("platform", sa.String),
        sa.column("data_domain", sa.String),
        sa.column("granularity", sa.String),
        sa.column("sub_domain", sa.String),
        sa.column("semantic_key", sa.String),
        sa.column("importance", sa.String),
        sa.column("consumer", sa.String),
        sa.column("impact_description", sa.Text),
        sa.column("enabled", sa.Boolean),
        schema="core",
    )
    op.bulk_insert(
        contracts,
        [
            *[
                {
                    "platform": None,
                    "data_domain": "orders",
                    "granularity": granularity,
                    "sub_domain": None,
                    "semantic_key": semantic_key,
                    "importance": importance,
                    "consumer": "business_overview",
                    "impact_description": impact,
                    "enabled": True,
                }
                for granularity in ("weekly", "monthly")
                for semantic_key, importance, impact in (
                    ("order_id", "required", "业务概览订单数无法计算"),
                    ("shop_id", "required", "业务概览无法按店铺归属订单"),
                    ("order_date", "required", "业务概览无法按期间归集订单"),
                    ("sales_volume", "required", "业务概览销售数量无法计算"),
                    ("paid_amount", "required", "业务概览销售额和转化率无法计算"),
                    ("profit", "required", "业务概览利润指标无法计算"),
                    ("estimated_settlement_amount", "optional", None),
                    ("settlement_time", "optional", None),
                    ("cost_profit_rate", "optional", None),
                )
            ],
            *[
                {
                    "platform": None,
                    "data_domain": "analytics",
                    "granularity": granularity,
                    "sub_domain": None,
                    "semantic_key": semantic_key,
                    "importance": importance,
                    "consumer": "business_overview",
                    "impact_description": impact,
                    "enabled": True,
                }
                for granularity in ("daily", "monthly")
                for semantic_key, importance, impact in (
                    ("metric_date", "required", "业务概览流量无法按日期归集"),
                    ("shop_id", "required", "业务概览无法按店铺归属流量"),
                    ("visitor_count", "required", "业务概览UV无法计算"),
                    ("page_views", "required", "业务概览PV无法计算"),
                    ("conversion_rate", "optional", None),
                    ("order_count", "optional", None),
                    ("gmv", "optional", None),
                )
            ],
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_semantic_field_contract_lookup", table_name="semantic_field_contracts", schema="core")
    op.drop_table("semantic_field_contracts", schema="core")
