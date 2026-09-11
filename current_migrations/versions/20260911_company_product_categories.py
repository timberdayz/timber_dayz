"""Add the company-owned two-level product category dictionary."""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20260911_company_product_categories"
down_revision = "current_schema_20260911_logistics_bill_allocation_lineage"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str, schema: str) -> bool:
    return _inspector().has_table(name, schema=schema)


def _has_column(table: str, schema: str, column: str) -> bool:
    return _has_table(table, schema) and column in {
        item["name"] for item in _inspector().get_columns(table, schema=schema)
    }


def _has_foreign_key(table: str, schema: str, name: str) -> bool:
    return any(
        foreign_key.get("name") == name
        for foreign_key in _inspector().get_foreign_keys(table, schema=schema)
    )


def upgrade() -> None:
    if not _has_table("dim_product_categories", "core"):
        op.create_table(
            "dim_product_categories",
            sa.Column("category_code", sa.String(64), primary_key=True),
            sa.Column("parent_category_code", sa.String(64), nullable=True),
            sa.Column("level", sa.Integer(), nullable=False),
            sa.Column("name_zh", sa.String(128), nullable=False),
            sa.Column("name_en", sa.String(128), nullable=True),
            sa.Column("category_path", sa.String(512), nullable=True),
            sa.Column("status", sa.String(16), nullable=False, server_default="active"),
            sa.Column("version", sa.String(32), nullable=False, server_default="v1"),
            sa.Column("effective_from", sa.Date(), nullable=False, server_default=sa.func.current_date()),
            sa.Column("effective_to", sa.Date(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["parent_category_code"], ["core.dim_product_categories.category_code"], ondelete="RESTRICT"),
            sa.CheckConstraint("level IN (1, 2)", name="ck_dim_product_categories_level"),
            sa.CheckConstraint("(level = 1 AND parent_category_code IS NULL) OR (level = 2 AND parent_category_code IS NOT NULL)", name="ck_dim_product_categories_parent"),
            schema="core",
        )
    op.create_index("ix_dim_product_categories_parent_status", "dim_product_categories", ["parent_category_code", "status"], schema="core", if_not_exists=True)
    op.create_index("ix_dim_product_categories_level_status", "dim_product_categories", ["level", "status"], schema="core", if_not_exists=True)
    op.execute(
        sa.text(
            """
            INSERT INTO core.dim_product_categories
                (category_code, parent_category_code, level, name_zh, name_en, category_path, status, version, effective_from)
            VALUES
                ('HOME_LIVING', NULL, 1, '家居生活', 'Home & Living', '家居生活', 'active', 'v1', CURRENT_DATE),
                ('HOME_STORAGE', 'HOME_LIVING', 2, '收纳整理', 'Storage & Organization', '家居生活/收纳整理', 'active', 'v1', CURRENT_DATE),
                ('HOME_KITCHEN', 'HOME_LIVING', 2, '厨房餐饮', 'Kitchen & Dining', '家居生活/厨房餐饮', 'active', 'v1', CURRENT_DATE),
                ('BEAUTY_PERSONAL_CARE', NULL, 1, '美妆个护', 'Beauty & Personal Care', '美妆个护', 'active', 'v1', CURRENT_DATE),
                ('BEAUTY_TOOLS', 'BEAUTY_PERSONAL_CARE', 2, '美妆工具', 'Beauty Tools', '美妆个护/美妆工具', 'active', 'v1', CURRENT_DATE),
                ('SPORTS_OUTDOORS', NULL, 1, '运动户外', 'Sports & Outdoors', '运动户外', 'active', 'v1', CURRENT_DATE),
                ('SPORTS_FITNESS', 'SPORTS_OUTDOORS', 2, '运动健身', 'Fitness', '运动户外/运动健身', 'active', 'v1', CURRENT_DATE),
                ('PET_SUPPLIES', NULL, 1, '宠物用品', 'Pet Supplies', '宠物用品', 'active', 'v1', CURRENT_DATE),
                ('PET_DAILY', 'PET_SUPPLIES', 2, '宠物日用品', 'Pet Daily Supplies', '宠物用品/宠物日用品', 'active', 'v1', CURRENT_DATE)
            ON CONFLICT (category_code) DO NOTHING
            """
        )
    )
    for column in (
        sa.Column("category_l1_code", sa.String(64), nullable=True),
        sa.Column("category_l2_code", sa.String(64), nullable=True),
        sa.Column("logistics_damage_rate", sa.Float(), nullable=True),
        sa.Column("return_loss_rate", sa.Float(), nullable=True),
    ):
        if not _has_column("dim_spu", "core", column.name):
            op.add_column("dim_spu", column, schema="core")
    if not _has_foreign_key("dim_spu", "core", "fk_dim_spu_category_l1"):
        op.create_foreign_key("fk_dim_spu_category_l1", "dim_spu", "dim_product_categories", ["category_l1_code"], ["category_code"], source_schema="core", referent_schema="core", ondelete="RESTRICT")
    if not _has_foreign_key("dim_spu", "core", "fk_dim_spu_category_l2"):
        op.create_foreign_key("fk_dim_spu_category_l2", "dim_spu", "dim_product_categories", ["category_l2_code"], ["category_code"], source_schema="core", referent_schema="core", ondelete="RESTRICT")
    for column in (
        sa.Column("expected_logistics_cost", sa.Float(), nullable=True),
        sa.Column("expected_storage_cost", sa.Float(), nullable=True),
    ):
        if not _has_column("dim_erp_sku", "core", column.name):
            op.add_column("dim_erp_sku", column, schema="core")


def downgrade() -> None:
    op.drop_constraint("fk_dim_spu_category_l2", "dim_spu", schema="core", type_="foreignkey")
    op.drop_constraint("fk_dim_spu_category_l1", "dim_spu", schema="core", type_="foreignkey")
    op.drop_column("dim_erp_sku", "expected_storage_cost", schema="core")
    op.drop_column("dim_erp_sku", "expected_logistics_cost", schema="core")
    op.drop_column("dim_spu", "return_loss_rate", schema="core")
    op.drop_column("dim_spu", "logistics_damage_rate", schema="core")
    op.drop_column("dim_spu", "category_l2_code", schema="core")
    op.drop_column("dim_spu", "category_l1_code", schema="core")
    op.drop_index("ix_dim_product_categories_level_status", table_name="dim_product_categories", schema="core")
    op.drop_index("ix_dim_product_categories_parent_status", table_name="dim_product_categories", schema="core")
    op.drop_table("dim_product_categories", schema="core")
