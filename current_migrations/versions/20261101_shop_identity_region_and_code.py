"""Add shop identity region dimension and internal standard code.

对齐 spec docs/superpowers/specs/2026-11-01-shop-identity-and-session-reuse-design.md
的 D10 / D12：

- core.shop_account_aliases 增加 shop_region，使同平台同一别名可以在不同区域
  分别绑定到不同店铺账号（三个同名 FIORO 店铺的唯一锚点是 shop_account_id，
  区域是消歧维度）。
- 别名唯一约束改为 UNIQUE NULLS NOT DISTINCT，避免存量 NULL 区域行互不冲突。
- core.shop_account_aliases.platform 统一小写。
- core.shop_accounts 增加 internal_code（内部标准名，如 FIORO_SG）。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261101_shop_identity_region_and_code"
down_revision = "current_schema_20261028_drop_deprecated_traffic_fact_tables"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str, schema: str = "core") -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table, schema=schema):
        return False
    return column in {c["name"] for c in inspector.get_columns(table, schema=schema)}


def _constraint_exists(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    for schema in ("core",):
        for table in ("shop_account_aliases", "shop_accounts"):
            for c in inspector.get_unique_constraints(table, schema=schema):
                if c.get("name") == name:
                    return True
    return False


def upgrade() -> None:
    # 第 1 步：平台大小写归一（必须先做，避免下一步加约束时冲突）。
    # 保留 is_active=true 且 is_primary=true 的那条；另一条降级为非 active 非 primary。
    op.execute(
        """
        UPDATE core.shop_account_aliases a
           SET is_active = false,
               is_primary = false
         WHERE a.platform IN ('Shopee', 'Tiktok')
           AND EXISTS (
                SELECT 1 FROM core.shop_account_aliases b
                 WHERE b.platform = lower(a.platform)
                   AND b.alias_normalized = a.alias_normalized
                   AND b.is_active = true
                   AND b.id <> a.id
           )
        """
    )
    op.execute("UPDATE core.shop_account_aliases SET platform = lower(platform) WHERE platform IN ('Shopee', 'Tiktok')")

    # 第 2 步：别名表加区域维度。
    if not _has_column("shop_account_aliases", "shop_region"):
        op.add_column(
            "shop_account_aliases",
            sa.Column("shop_region", sa.String(50), nullable=True),
            schema="core",
        )

    # 第 3 步：换唯一约束（NULLS NOT DISTINCT）。
    op.execute("ALTER TABLE core.shop_account_aliases DROP CONSTRAINT IF EXISTS uq_shop_account_aliases_active_alias")
    op.execute(
        """
        ALTER TABLE core.shop_account_aliases
          ADD CONSTRAINT uq_shop_account_aliases_active_alias
          UNIQUE NULLS NOT DISTINCT (platform, alias_normalized, shop_region, is_active)
        """
    )

    # 第 4 步：内部标准名列。
    if not _has_column("shop_accounts", "internal_code"):
        op.add_column(
            "shop_accounts",
            sa.Column("internal_code", sa.String(100), nullable=True),
            schema="core",
        )
        op.execute(
            """
            ALTER TABLE core.shop_accounts
              ADD CONSTRAINT uq_shop_accounts_platform_internal_code
              UNIQUE (platform, internal_code)
            """
        )

    # 第 5 步：别名表按店铺账号回填区域（能回填的回填，回填不了的留 NULL = 不限区域）。
    op.execute(
        """
        UPDATE core.shop_account_aliases a
           SET shop_region = s.shop_region
          FROM core.shop_accounts s
         WHERE s.id = a.shop_account_id
           AND a.shop_region IS NULL
           AND s.shop_region IS NOT NULL
           AND btrim(s.shop_region) <> ''
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE core.shop_accounts DROP CONSTRAINT IF EXISTS uq_shop_accounts_platform_internal_code")
    op.execute("ALTER TABLE core.shop_accounts DROP COLUMN IF EXISTS internal_code")
    op.execute("ALTER TABLE core.shop_account_aliases DROP CONSTRAINT IF EXISTS uq_shop_account_aliases_active_alias")
    op.execute(
        """
        ALTER TABLE core.shop_account_aliases
          ADD CONSTRAINT uq_shop_account_aliases_active_alias
          UNIQUE (platform, alias_normalized, is_active)
        """
    )
    op.execute("ALTER TABLE core.shop_account_aliases DROP COLUMN IF EXISTS shop_region")
