"""Add per-platform ROI advertising configuration (Stage 1).

The ROI layer answers "if I advertise this SKU, what is the break-even ROI and
what should I type into the platform console?".  Two of the inputs are
platform-level, not SKU-level:

* ``roi_safety_margin``  -- how far above break-even we suggest (default 20%,
  the low end of the 12%-25% industry range).
* ``target_roi_ceiling`` -- the maximum ROI the platform console accepts.  This
  is a hard constraint: a suggested ROI above it cannot be executed.
* ``target_roi_floor``   -- reserved; the platform's minimum allowed ROI.
  Recorded only, it does not participate in clamping yet.

The migration is idempotent: every column and constraint is guarded by an
existence check, so re-running it on an already-migrated database is a no-op.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261113_add_platform_roi_config"
down_revision = "current_schema_20261112_realign_identity_candidates_anchor"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def _has_constraint(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and any(
        constraint.get("name") == name
        for constraint in _inspector().get_check_constraints(table, schema=schema)
    )


#: 平台后台可填的目标 ROI 上限。TikTok 的投放后台上限是 20，Shopee 是 50。
#: 迁移只回填**明确知道**的两个平台；其余平台保持列默认值 50，
#: 运营可以在「定价设置」里改。
PLATFORM_TARGET_ROI_CEILING = {
    "tiktok": 20,
    "shopee": 50,
}


def upgrade() -> None:
    if not _has_table("dim_platforms", "core"):
        return

    if not _has_column("dim_platforms", "core", "roi_safety_margin"):
        op.add_column(
            "dim_platforms",
            sa.Column(
                "roi_safety_margin",
                sa.Numeric(6, 4),
                nullable=False,
                server_default=sa.text("0.20"),
            ),
            schema="core",
        )
    if not _has_column("dim_platforms", "core", "target_roi_ceiling"):
        op.add_column(
            "dim_platforms",
            sa.Column(
                "target_roi_ceiling",
                sa.Numeric(10, 2),
                nullable=False,
                server_default=sa.text("50"),
            ),
            schema="core",
        )
    if not _has_column("dim_platforms", "core", "target_roi_floor"):
        op.add_column(
            "dim_platforms",
            sa.Column(
                "target_roi_floor",
                sa.Numeric(10, 2),
                nullable=False,
                server_default=sa.text("1"),
            ),
            schema="core",
        )

    bind = op.get_bind()
    for platform_code, ceiling in PLATFORM_TARGET_ROI_CEILING.items():
        bind.execute(
            sa.text(
                "UPDATE core.dim_platforms SET target_roi_ceiling = :ceiling "
                "WHERE platform_code = :code"
            ),
            {"code": platform_code, "ceiling": ceiling},
        )

    for name, expr in (
        (
            "ck_dim_platforms_roi_safety_margin_range",
            "roi_safety_margin >= 0 AND roi_safety_margin < 1",
        ),
        ("ck_dim_platforms_target_roi_ceiling_range", "target_roi_ceiling >= 1"),
        ("ck_dim_platforms_target_roi_floor_range", "target_roi_floor >= 1"),
    ):
        if not _has_constraint("dim_platforms", "core", name):
            op.create_check_constraint(name, "dim_platforms", expr, schema="core")


def downgrade() -> None:
    if not _has_table("dim_platforms", "core"):
        return

    for name in (
        "ck_dim_platforms_target_roi_floor_range",
        "ck_dim_platforms_target_roi_ceiling_range",
        "ck_dim_platforms_roi_safety_margin_range",
    ):
        if _has_constraint("dim_platforms", "core", name):
            op.drop_constraint(name, "dim_platforms", schema="core", type_="check")

    for column in ("target_roi_floor", "target_roi_ceiling", "roi_safety_margin"):
        if _has_column("dim_platforms", "core", column):
            op.drop_column("dim_platforms", column, schema="core")
