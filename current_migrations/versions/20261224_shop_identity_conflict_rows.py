"""新建 ``ops.shop_identity_conflict_rows`` —— 同步侧「矛盾行台账」。

背景
----
批次 3.7 加了「双基准守卫」: 推送前把**本地**登记信息与**云端**登记信息比一次,
不一致的行**不写云端**、降级成可观测事件(落在 ``ops.pipeline_run_log``)。

但**行级**的明细只活在 ``ops.pipeline_run_log`` 的 ``context->'events'`` 里 ——
那是一段 jsonb 样本(最多 50 条)、且**整批去重**: 同一批被降级两次, 记两条
几乎一样的事件, 看不出「这一行到底被跳过几次、什么时候第一次被跳过」。

批次 4.3 要补的是**行级台账**
--------------------------
方案(``2026-11-10-shop-identity-future-proofing-and-observability.md`` §批次 4.3)
要求: 保持现有推进算法(**不**改成「停在第一个矛盾行」, 否则那条链会永久卡死),
但把**被跳过的矛盾行**记进台账并标注「已知历史遗留」, 另提供手工重发入口。

⇒ 本表就是那个台账: **一行 = 一个矛盾行**, 记清
「哪张表 / 哪个平台与域 / 哪个业务日期 / 行内那列的值 / 本地认出的账号 /
为什么判为矛盾(原因码) / 是历史遗留还是待人工 / 第一次与最近一次见到的时间 /
累计出现次数 / 人工处理状态与处理人」。

去重口径
--------
同一「(源表, 业务日期, 行内定位, 原因码)」再遇到时**更新**累计次数与最近见到时间,
**不**无限插新行 ⇒ 由唯一约束 ``uq_shop_identity_conflict_rows_dedup_key`` 兜底
(``dedup_key`` 就是那四项拼出来的稳定串)。

⚠️ **历史不修**: 本表只登记「被跳过 / 被降级」的行, **不回填、不改写**任何
历史事实行(``b_class.fact_*``)—— 一行字都不动。

安全边界
--------
只新建一张表 + 若干索引, 不改任何既有表 / 列 / 数据。
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "current_schema_20261224_shop_identity_conflict_rows"
down_revision = "current_schema_20261223_collection_source_identifiers"
branch_labels = None
depends_on = None


_TABLE = "shop_identity_conflict_rows"
_SCHEMA = "ops"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def upgrade() -> None:
    if _has_table(_TABLE, _SCHEMA):
        return

    op.create_table(
        _TABLE,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        # ── 去重键 ──────────────────────────────────────────────────────
        # 「(源表, 业务日期, 行内定位, 原因码)」的稳定拼接串。
        # 唯一约束建在它上面 ⇒ 同一矛盾行再次出现时只能**更新**, 不能插新行。
        sa.Column("dedup_key", sa.String(length=512), nullable=False),
        # ── 定位 ────────────────────────────────────────────────────────
        sa.Column("source_table_name", sa.String(length=255), nullable=False),
        sa.Column("platform_code", sa.String(length=32), nullable=True),
        sa.Column("data_domain", sa.String(length=64), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=True),
        sa.Column("row_locator", sa.String(length=255), nullable=False),
        sa.Column("source_row_id", sa.String(length=128), nullable=True),
        # ── 身份线索 ────────────────────────────────────────────────────
        sa.Column("identity_value", sa.String(length=255), nullable=True),
        sa.Column("identity_tokens", postgresql.JSONB(), nullable=True),
        sa.Column("resolved_account_id", sa.String(length=128), nullable=True),
        sa.Column("resolved_accounts", postgresql.JSONB(), nullable=True),
        sa.Column("cloud_accounts", postgresql.JSONB(), nullable=True),
        # ── 判定 ────────────────────────────────────────────────────────
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'pending_manual'"),
        ),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # ── 人工处理 ────────────────────────────────────────────────────
        sa.Column(
            "resolution_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("resolved_by", sa.String(length=128), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        # ── 审计 ────────────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        schema=_SCHEMA,
    )

    op.create_index(
        "ix_shop_identity_conflict_rows_dedup_key",
        _TABLE,
        ["dedup_key"],
        unique=True,
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_shop_identity_conflict_rows_status",
        _TABLE,
        ["status"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_shop_identity_conflict_rows_table_date",
        _TABLE,
        ["source_table_name", "business_date"],
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_shop_identity_conflict_rows_last_seen",
        _TABLE,
        ["last_seen_at"],
        schema=_SCHEMA,
    )


def downgrade() -> None:
    if not _has_table(_TABLE, _SCHEMA):
        return

    op.drop_index(
        "ix_shop_identity_conflict_rows_last_seen",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_shop_identity_conflict_rows_table_date",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_shop_identity_conflict_rows_status",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.drop_index(
        "ix_shop_identity_conflict_rows_dedup_key",
        table_name=_TABLE,
        schema=_SCHEMA,
    )
    op.drop_table(_TABLE, schema=_SCHEMA)
