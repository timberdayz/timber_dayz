"""给刷新队列加「业务域分道」和「待重试时间」两列。

背景
----
生产实测（2026-11-05，刷新队列 614 条任务）：

- 失败率 **23%**（144/614），其中 **products 域 59%**（56/137）；
- 失败任务**永不重试** —— ``status='failed'`` 就是终态，只能靠人工点重试；
- 而商品域的失败会**连累整条刷新链**：一次失败让整条任务被判失败 ⇒
  商品经营分析的转化率从 6 月底到 11 月初长期停在旧数据；
- 队列是**单通道**的：一个慢域（最慢 250.5 秒）把其它域全堵在后面。

本迁移加两列，为「按域分道并发 + 失败自动带退避重排队」打底：

- ``domain``
  业务域（``orders`` / ``analytics`` / ``products`` / ``inventory`` /
  ``services``），缺域的进 ``default`` 共享道。
  用途：领取任务时**排除本域已在跑的任务** ⇒ 同域串行、不同域可并行。
- ``next_retry_at``
  待重试时间。领取条件 =
  ``status='pending' AND (next_retry_at IS NULL OR next_retry_at <= now())``。
  用途：失败后带**指数退避**自动重排队，不必人工介入。

为什么复用 ``pending`` 而不加新状态值
------------------------------------
``core.refresh_queue_tasks`` 上有 CHECK 约束
``chk_refresh_queue_tasks_status``，只允许
``pending / running / completed / failed / skipped``。
加新状态值要同时改约束、ORM 与所有查询，风险大且收益小。
「待重试」用 ``pending`` + ``next_retry_at`` 表达，语义完全够用。

为什么 ``attempt_count`` 不归零
-------------------------------
归零 = 无限重排队。失败次数**只增不减**，人工重试才归零
（``retry_failed_task``），这样「同一条任务最多自动重试 N 次」才有上界。

回填
----
历史行的 ``domain`` 从 ``context_json->>'data_domain'`` 反推，并做别名归一
（``traffic`` → ``analytics``，见 ``modules/core/data_domains.py``）。
生产 614 条里 607 条带 ``data_domain``（覆盖 99%），剩下 7 条归 ``default``。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261111_add_refresh_queue_domain_and_retry"
down_revision = "current_schema_20261110_create_products_atomic_materialized_view"
branch_labels = None
depends_on = None


TABLE = "refresh_queue_tasks"
SCHEMA = "core"

#: 有刷新目标图的业务域（与 ``refresh_registry._REFRESHABLE_DOMAINS`` 保持一致）
REFRESHABLE_DOMAINS = ("orders", "analytics", "products", "inventory", "services")

#: 历史别名 → canonical（与 ``modules/core/data_domains.LEGACY_DATA_DOMAIN_ALIASES`` 一致）
DOMAIN_ALIASES = {"traffic": "analytics"}


def _table_exists(connection) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT to_regclass(:qualified) IS NOT NULL"),
            {"qualified": "core.refresh_queue_tasks"},
        ).scalar()
    )


def _columns(connection) -> set[str]:
    return set(
        connection.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema_name AND table_name = :table_name"
            ),
            {"schema_name": SCHEMA, "table_name": TABLE},
        )
        .scalars()
        .all()
    )


def _index_exists(connection, index_name: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT to_regclass(:qualified) IS NOT NULL"),
            {"qualified": "core.{index}".format(index=index_name)},
        ).scalar()
    )


def _canonical_domain_expression() -> str:
    """构造把 ``context_json->>'data_domain'`` 归一成本列取值的 SQL 片段。

    归一规则（与 ``modules/core/data_domains.normalize_data_domain`` 对齐）：

    - 去空白 + 转小写；
    - 历史别名 ``traffic`` → ``analytics``；
    - 不在五个业务域里的一律归 ``default``。
    """
    alias_cases = " ".join(
        "WHEN '{alias}' THEN '{canonical}'".format(alias=alias, canonical=canonical)
        for alias, canonical in DOMAIN_ALIASES.items()
    )
    return (
        "CASE lower(trim(coalesce(context_json->>'data_domain', ''))) "
        "WHEN '' THEN 'default' "
        "{alias_cases} "
        "WHEN 'orders' THEN 'orders' "
        "WHEN 'analytics' THEN 'analytics' "
        "WHEN 'products' THEN 'products' "
        "WHEN 'inventory' THEN 'inventory' "
        "WHEN 'services' THEN 'services' "
        "ELSE 'default' END".format(alias_cases=alias_cases)
    )


def upgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection):
        # 表还不存在（首次部署走 ORM 建表）—— 交给 ORM，这里不建。
        return

    existing = _columns(connection)
    if "domain" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "domain",
                sa.String(length=32),
                nullable=False,
                server_default="default",
            ),
            schema=SCHEMA,
        )
    if "next_retry_at" not in existing:
        op.add_column(
            TABLE,
            sa.Column(
                "next_retry_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
            schema=SCHEMA,
        )

    # 回填历史行的业务域（幂等：已回填的行再跑一次也是同样的值）。
    connection.execute(
        sa.text(
            "UPDATE core.refresh_queue_tasks SET domain = {expression}".format(
                expression=_canonical_domain_expression()
            )
        )
    )

    if not _index_exists(connection, "ix_refresh_queue_tasks_status_domain"):
        connection.execute(
            sa.text(
                "CREATE INDEX ix_refresh_queue_tasks_status_domain "
                "ON core.refresh_queue_tasks (status, domain)"
            )
        )
    if not _index_exists(connection, "ix_refresh_queue_tasks_retry_due"):
        connection.execute(
            sa.text(
                "CREATE INDEX ix_refresh_queue_tasks_retry_due "
                "ON core.refresh_queue_tasks (status, next_retry_at)"
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    if not _table_exists(connection):
        return

    for index_name in (
        "ix_refresh_queue_tasks_retry_due",
        "ix_refresh_queue_tasks_status_domain",
    ):
        if _index_exists(connection, index_name):
            connection.execute(
                sa.text("DROP INDEX IF EXISTS core.{index}".format(index=index_name))
            )

    existing = _columns(connection)
    for column in ("next_retry_at", "domain"):
        if column in existing:
            op.drop_column(TABLE, column, schema=SCHEMA)
