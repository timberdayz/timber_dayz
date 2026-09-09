"""Add company SPU and canonical ERP SKU master data."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260909_product_center_master_data"
down_revision = "current_schema_20260827_profit_basis_v2_breakdown"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dim_spu",
        sa.Column("spu", sa.String(128), primary_key=True),
        sa.Column("spu_name", sa.String(512), nullable=False),
        sa.Column("category_l1", sa.String(128)),
        sa.Column("category_l2", sa.String(128)),
        sa.Column("main_image_url", sa.String(1024)),
        sa.Column("biz_status", sa.String(32), nullable=False, server_default="candidate"),
        sa.Column("owner_user_id", sa.Integer),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("spu", name="uq_dim_spu_spu"),
        schema="core",
    )
    op.create_index("ix_dim_spu_status_owner", "dim_spu", ["biz_status", "owner_user_id"], schema="core")

    op.create_table(
        "dim_erp_sku",
        sa.Column("sku_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("sku_key", sa.String(255), nullable=False),
        sa.Column("erp_record_id", sa.String(255)),
        sa.Column("sku_name", sa.String(512)),
        sa.Column("specification", sa.String(512)),
        sa.Column("weight_kg", sa.Float),
        sa.Column("package_length_cm", sa.Float),
        sa.Column("package_width_cm", sa.Float),
        sa.Column("package_height_cm", sa.Float),
        sa.Column("units_per_carton", sa.Integer),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("source_file_id", sa.Integer),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("sku_key", name="uq_dim_erp_sku_sku_key"),
        schema="core",
    )
    op.create_index("ix_dim_erp_sku_status", "dim_erp_sku", ["status"], schema="core")
    op.create_index("ix_dim_erp_sku_erp_record", "dim_erp_sku", ["erp_record_id"], schema="core")

    op.create_table(
        "bridge_spu_sku",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("spu", sa.String(128), sa.ForeignKey("core.dim_spu.spu", ondelete="RESTRICT"), nullable=False),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("binding_status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_by", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_index(
        "uq_bridge_spu_sku_current",
        "bridge_spu_sku",
        ["sku_id"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("effective_to IS NULL AND binding_status = 'active'"),
    )
    op.create_index("ix_bridge_spu_sku_spu", "bridge_spu_sku", ["spu", "effective_to"], schema="core")

    op.create_table(
        "bridge_erp_sku_keys",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_system", sa.String(64), nullable=False),
        sa.Column("source_platform", sa.String(64)),
        sa.Column("source_shop_id", sa.String(256)),
        sa.Column("source_key_type", sa.String(64), nullable=False),
        sa.Column("source_key", sa.String(255), nullable=False),
        sa.Column("sku_id", sa.Integer, sa.ForeignKey("core.dim_erp_sku.sku_id", ondelete="CASCADE"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("source_file_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        schema="core",
    )
    op.create_index(
        "uq_bridge_erp_sku_key_current",
        "bridge_erp_sku_keys",
        ["source_system", "source_platform", "source_shop_id", "source_key_type", "source_key"],
        unique=True,
        schema="core",
        postgresql_where=sa.text("effective_to IS NULL AND active = true"),
    )
    op.create_index("ix_bridge_erp_sku_key_sku", "bridge_erp_sku_keys", ["sku_id"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_bridge_erp_sku_key_sku", table_name="bridge_erp_sku_keys", schema="core")
    op.drop_index("uq_bridge_erp_sku_key_current", table_name="bridge_erp_sku_keys", schema="core")
    op.drop_table("bridge_erp_sku_keys", schema="core")
    op.drop_index("ix_bridge_spu_sku_spu", table_name="bridge_spu_sku", schema="core")
    op.drop_index("uq_bridge_spu_sku_current", table_name="bridge_spu_sku", schema="core")
    op.drop_table("bridge_spu_sku", schema="core")
    op.drop_index("ix_dim_erp_sku_erp_record", table_name="dim_erp_sku", schema="core")
    op.drop_index("ix_dim_erp_sku_status", table_name="dim_erp_sku", schema="core")
    op.drop_table("dim_erp_sku", schema="core")
    op.drop_index("ix_dim_spu_status_owner", table_name="dim_spu", schema="core")
    op.drop_table("dim_spu", schema="core")
