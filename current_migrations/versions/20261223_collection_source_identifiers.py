"""新建 ``core.collection_source_identifiers`` —— 采集方标识的**登记载体**。

背景
----
``b_class.fact_*`` 事实表的 ``shop_id`` 列装的是**采集层写进来的原始标识**
（详见 ``modules/core/fact_identity_columns.py`` 的定性）。其中有一类是
**采集方代号** —— 表示「这批数据来自哪个采集器」，**不是**店铺身份：

* ``xihong``          —— 妙手采集账号 ``miaoshou_real_001`` 的 store_name
* ``miaoshou_real_001`` —— 妙手采集账号 ID
* ``unknown`` / ``none`` / ``''`` —— 占位键

这些标识一旦混进身份候选集，就会被主数据候选池反查成一个**伪店铺**
（``core.dim_shops`` 里确实注册了 ``miaoshou / miaoshou_real_001 / xihong``
这一行）⇒ 库存的 4,111 行全部挂在一个不存在的店上，按店拆永远只有一个。

为什么要有这张表（SSOT）
-----------------------
「采集方代号不算身份」这条规则以前写在**每条链路各自的 SQL** 里：
``sql/semantic/orders_atomic.sql`` 有一份字面量、
``sql/semantic/inventory_snapshot.sql`` 干脆没有 ——
属于**多处复制**，新加一条链路就会漏掉一次。

本表把清单收敛成**一处登记**：
``semantic.resolve_shop_identity``（全站唯一的身份解析入口）读它剔除采集方代号
⇒ 所有链路（含未来新增的）自动继承，不需要各自记得写排除。

与 Python 权威定义的关系
-----------------------
* **唯一定义处** = ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``
* 本表的初始行 = 从那份定义播种（下面的 ``_SEED_IDENTIFIERS`` 与它逐条一致）
* 守护测试 ``backend/tests/test_inventory_warehouse_identity_ssot.py``
  断言「表内容 == Python 常量」⇒ 任何一侧漂移都会被抓到

安全边界
--------
只新建一张表 + 播种若干行, 不改任何既有表 / 列 / 数据。
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261223_collection_source_identifiers"
down_revision = "current_schema_20261222_cloud_sync_receive_log_identity_rows"
branch_labels = None
depends_on = None


_TABLE = "collection_source_identifiers"
_SCHEMA = "core"

#: 采集方标识清单 —— 与 ``modules/core/fact_identity_columns.py::COLLECTION_SOURCE_IDS``
#: **逐条一致**（改一侧必须同时改另一侧；守护测试会断言两者相等）。
_SEED_IDENTIFIERS = (
    (
        "xihong",
        "妙手采集账号 miaoshou_real_001 的 store_name（伪店铺名，不是店铺）",
    ),
    (
        "miaoshou_real_001",
        "妙手采集账号 ID（数据来源，不是店铺）",
    ),
    (
        "unknown",
        "占位键：未取到任何店铺标识",
    ),
    (
        "none",
        "占位键：采集文件里的空标识",
    ),
    (
        "",
        "空字符串：未取到任何店铺标识",
    ),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _exec(statement: str, params: dict | None = None) -> None:
    """Execute one DML statement.

    ⚠️ ``op.execute(sql_text, execution_options=...)`` 的第二个参数**不是**绑定参数；
    绑定必须走 ``op.get_bind().execute(text, params)``。
    """
    op.get_bind().execute(sa.text(statement), params or {})


def _seed_identifiers() -> None:
    """播种清单行, 已存在的跳过（可重复执行）。"""
    for identifier, description in _SEED_IDENTIFIERS:
        _exec(
            """
            INSERT INTO core.collection_source_identifiers (identifier, description)
            SELECT :identifier, :description
            WHERE NOT EXISTS (
                SELECT 1 FROM core.collection_source_identifiers c
                 WHERE c.identifier = :identifier
            )
            """,
            {"identifier": identifier, "description": description},
        )


def upgrade() -> None:
    if not _has_table(_TABLE, _SCHEMA):
        op.create_table(
            _TABLE,
            sa.Column(
                "identifier",
                sa.String(length=64),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("description", sa.String(length=255), nullable=True),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            schema=_SCHEMA,
        )
    _seed_identifiers()


def downgrade() -> None:
    if _has_table(_TABLE, _SCHEMA):
        op.drop_table(_TABLE, schema=_SCHEMA)
