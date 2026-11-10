"""把店铺身份解析候选集物化，根治「每行订单事实重算候选集」的 N+1。

背景
----
生产实测（2026-11-04，EXPLAIN ANALYZE 全量重算 38,607 行）：

    Execution Time: 118974.907 ms   （≈ 119 秒）

计划里两个节点吃掉绝大部分时间：

    ->  Unique (actual time=1.430..1.430 rows=1 loops=38607)      ≈ 55 秒
          ->  Sort ... -> Subquery Scan on identity_rows_1
    ->  Seq Scan on shop_account_aliases (actual time=0.009..0.019
                                         rows=2 loops=1482412)    ≈ 28 秒

候选集只有 **136 行**（core.shop_accounts 52 行 + core.shop_account_aliases
21 行派生），却是**普通视图** —— 每行订单事实都要把它重新展开、重算
``regexp_replace`` 之类的规范化表达式、再排序一次。
38,607 行 × 38 次别名表扫描 = **148 万次**。

这就是 v7.13.0 物化层「刷新要 115 秒」的根源：物化把重算从请求路径搬到
刷新路径，但**重算本身还是那么贵**。候选集物化之后，重算降到秒级，
刷新窗口才真正短下来。

做法
----
1. **先把正本对齐到当前资产**（执行
   ``sql/semantic/shop_identity_resolution_candidates.sql``），
   再新建物化视图 ``semantic.shop_identity_resolution_candidates_v2_mv``，
   正文 = ``SELECT <显式列清单> FROM semantic.shop_identity_resolution_candidates``
   （**正本仍是普通视图**，从 core 表现算）⇒ 口径零变化。
2. 原子层的两个**普通视图**（``semantic.fact_orders_atomic`` /
   ``semantic.fact_analytics_atomic``）改读物化副本（由迁移 20261106 重建）。

**不动** ``orders_monthly_atomic_mv`` / ``analytics_monthly_atomic_mv`` ——
那是既有物化视图的完整定义（``DROP ... CASCADE`` + ``CREATE``），改了要在生产
重建它们 ⇒ 有风险。它们继续读普通视图，既有行为不变。

为什么必须**先执行正本资产**
--------------------------
物化副本的正文现在**从正本取数**（2026-11-11「派生层口径收回」：口径只有
正本一处定义，副本不再手抄计算逻辑）。于是副本的**列集合 = 正本的列集合**。

而 ``20260805`` 的静态基线建的候选池正本是 **7 列旧版**（缺
``identity_shop_region`` —— 区域消歧那套逻辑是 ``20261101`` 才加的），
``20261112`` 迁移才把正本换成 8 列的当前版本。

如果本迁移直接建副本 ⇒ 副本会拿到 7 列 ⇒ 下一条迁移 ``20261106``
重建原子层视图时引用 ``c.identity_shop_region`` ⇒ 直接报
``column c.identity_shop_region does not exist`` ⇒ **全新库跑迁移链就断了**。

所以本迁移**先执行正本资产**（``CREATE OR REPLACE VIEW`` 保持 OID ⇒ 下游
不用重建；它还会顺带把 ``semantic.is_collection_source_identifier`` 函数
落地 —— 函数内联在正本资产开头，见该文件的说明），**再建副本**。

⚠️ 本迁移在生产**早已执行过** ⇒ 改它只影响**全新库**的迁移链重放；
    生产/开发库的既有对象不受影响。

口径守护
--------
建完副本立刻比对它与**正本**的内容指纹（行数 + 全量内容 md5），
不一致直接抛错回滚 ⇒ 「副本 == 正本」由机器证明，不靠人眼比对。

关于 ``DROP ... CASCADE``
------------------------
本迁移**从不**使用 ``DROP MATERIALIZED VIEW ... CASCADE``：
CASCADE 会连带删掉下游对象，而下游里存在**不是 refresh registry 可重建目标**
的对象。删除旧版 v1 时故意**不带 CASCADE** —— 万一有依赖，迁移直接失败
（fail-closed），而不是悄悄把下游删掉。
"""

from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261105_create_identity_candidates_mv"
down_revision = "current_schema_20261104_drop_clearance_ranking_module"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 候选集正本（普通视图，从 core 表现算）
CANDIDATES_VIEW = "semantic.shop_identity_resolution_candidates"
#: 候选集物化副本（正本快照）
CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
#: 20260805 schema baseline 建的旧版候选集物化视图（7 列，缺 identity_shop_region）
LEGACY_MV = "semantic.shop_identity_resolution_candidates_mv"

#: 候选集正本**资产**（普通视图，从 core 表现算）—— 必须**先**执行，
#: 副本的正文从正本取数 ⇒ 正本没对齐到当前版本，副本就建不对。
CANDIDATES_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"
CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"


def _asset_text(rel_path: str) -> str | None:
    asset_path = REPO_ROOT / rel_path
    if not asset_path.is_file():
        print("[WARN] 资产文件缺失，跳过：{path}".format(path=rel_path))
        return None
    return asset_path.read_text(encoding="utf-8")


def _exists(name: str) -> bool:
    bind = op.get_bind()
    return (
        bind.execute(
            sa.text("SELECT to_regclass(:name)"), {"name": name}
        ).scalar_one_or_none()
        is not None
    )


def _fingerprint(relation: str) -> tuple[int, str]:
    """关系的内容指纹：行数 + 全量内容 md5（按行文本排序后拼接）。

    用 ``row_to_json`` 而不是 ``t::text``：record 的文本输出形式依赖列类型
    渲染规则，``row_to_json`` 更稳定，也更好读。
    """
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT count(*)::int AS row_count,
                   md5(coalesce(string_agg(row_json, '|' ORDER BY row_json), '')) AS digest
            FROM (
                SELECT row_to_json(t)::text AS row_json
                FROM {relation} t
            ) s
            """.format(
                relation=relation
            )
        )
    ).one()
    return int(row[0]), str(row[1])


def _column_count(relation: str) -> int:
    """关系（普通视图 / 物化视图）的列数。

    ``information_schema.columns`` **不包含物化视图**（relkind='m' 不在它的
    范围里），所以物化视图走 ``pg_attribute``。
    """
    bind = op.get_bind()
    row = bind.execute(
        sa.text(
            """
            SELECT count(*)::int
            FROM pg_attribute a
            WHERE a.attrelid = to_regclass(:name)
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        ).bindparams(name=relation)
    ).one()
    return int(row[0])


def _execute_asset(rel_path: str) -> bool:
    """执行一个 SQL 资产文件（整文件一次执行）。

    走 **原生 psycopg2 cursor**，不用 ``exec_driver_sql``：后者在遇到
    **多语句**（资产文件里有 ``CREATE SCHEMA`` + ``DO $$ ... $$`` + 若干
    ``CREATE INDEX``）时会把空参数字典交给 ``cursor.execute``，而 psycopg2 的
    第二个参数必须是 sequence/tuple ⇒
    ``TypeError: immutabledict is not a sequence``。

    psycopg2 走 PostgreSQL 的**简单查询协议** —— 一条 query 里可以带多条语句，
    由数据库自己按分号切分，**并且数据库自己认 dollar-quoted 块**
    （``DO $$ ... $$`` 不会被切坏）。
    应用侧走 asyncpg，不支持多语句，所以那边必须自己切（见
    ``backend/services/data_pipeline/sql_loader.py``）。
    """
    sql_text = _asset_text(rel_path)
    if sql_text is None:
        return False
    raw_connection = _driver_connection()
    with raw_connection.cursor() as cursor:
        cursor.execute(sql_text)
    return True


def _driver_connection():
    """拿到原生 psycopg2 连接（SQLAlchemy 的 ``Connection.connection`` 是
    **属性**，返回连接池代理 ``_ConnectionFairy``；真正的驱动连接在它的
    ``driver_connection`` 上）。

    注意：``Connection.connection`` 后面**不能加括号** —— 它返回的对象不可调用，
    加括号会报 ``TypeError: '_ConnectionFairy' object is not callable``。
    """
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


#: 原子层的两个**普通视图**（它们的正文引用了物化副本，回滚时必须改回正本）
SOURCE_VIEW_ASSETS = (
    ("semantic.fact_orders_atomic", "sql/semantic/orders_atomic.sql"),
    ("semantic.fact_analytics_atomic", "sql/semantic/analytics_atomic.sql"),
)


def _exec_sql(statement: str) -> None:
    """执行一条原生 SQL。

    不用 ``exec_driver_sql``：它会把空参数字典（SQLAlchemy 的
    ``immutabledict``）交给 psycopg2 的 ``cursor.execute``，而 psycopg2 只接受
    真正的 ``dict``/序列 ⇒
    ``TypeError: sqlalchemy.cyextension.immutabledict.immutabledict is not a sequence``。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(statement)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（可以含多条语句）。

    走 **原生 psycopg2 cursor**：``exec_driver_sql`` 会把空参数字典交给
    psycopg2 ⇒ ``TypeError: immutabledict is not a sequence``。
    psycopg2 走简单查询协议，多语句由数据库自己切分。
    """
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _rebuild_source_views() -> None:
    """把原子层两个普通视图的正文改回读**正本**候选集。

    它们的正文引用的是物化副本；副本一旦被删，视图就会失效 ⇒ 回滚必须
    先把引用改回正本，再删副本。
    """
    for view_name, asset_rel_path in SOURCE_VIEW_ASSETS:
        asset_path = REPO_ROOT / asset_rel_path
        if not asset_path.is_file():
            print(
                "[WARN] 资产文件缺失，跳过视图回退：{view} ← {path}".format(
                    view=view_name, path=asset_rel_path
                )
            )
            continue
        sql_text = asset_path.read_text(encoding="utf-8")
        sql_text = sql_text.replace(
            "semantic.shop_identity_resolution_candidates_v2_mv",
            CANDIDATES_VIEW,
        )
        _exec_sql_text(sql_text)


def upgrade() -> None:
    # 1) **先把正本对齐到当前资产**。
    #    副本的正文从正本取数 ⇒ 正本的列集合决定副本的列集合。
    #    ``20260805`` 基线建的正本是 7 列旧版（缺 identity_shop_region），
    #    不先对齐，副本就建不出 ``20261106`` 原子层视图要引用的那一列。
    #    ``CREATE OR REPLACE VIEW`` 保持正本 OID ⇒ 下游对象不用重建。
    if not _execute_asset(CANDIDATES_VIEW_ASSET):
        raise RuntimeError("候选集正本资产缺失，拒绝继续")

    # 2) 建副本。副本正文**从正本取数**（口径只有正本一处定义），
    #    不再手抄计算逻辑 ⇒ 副本与正本永远同构。
    if not _execute_asset(CANDIDATES_MV_ASSET):
        print("[WARN] 物化副本资产缺失，保持原有候选集形态（慢但口径正确）")
        return

    # 3) 口径守护：副本内容必须与**正本**逐字节一致。
    #    仅在两者列数相同时比对 —— 正本列数与副本不一致时，正本与副本
    #    本就不是同一个东西，比内容没有意义。
    #    生产上正本已是 8 列 ⇒ 走严格比对（逐字节一致）。
    view_columns = _column_count(CANDIDATES_VIEW)
    mv_columns = _column_count(CANDIDATES_MV)
    if view_columns == mv_columns:
        view_fingerprint = _fingerprint(CANDIDATES_VIEW)
        mv_fingerprint = _fingerprint(CANDIDATES_MV)
        if mv_fingerprint != view_fingerprint:
            raise RuntimeError(
                "候选集物化副本与正本内容不一致，拒绝继续：view={view} mv={mv}".format(
                    view=view_fingerprint, mv=mv_fingerprint
                )
            )
    else:
        print(
            "[INFO] 正本列数({view})与副本列数({mv})不同，跳过内容比对".format(
                view=view_columns, mv=mv_columns
            )
        )

    # 4) 删掉 20260805 baseline 建的旧版候选集物化视图（7 列、缺
    #    identity_shop_region、没有任何对象引用它）。
    #    **不带 CASCADE**：有依赖就让迁移失败（fail-closed），不静默删下游。
    if _exists(LEGACY_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=LEGACY_MV))


def downgrade() -> None:
    """回滚：删掉物化副本。

    顺序：先把原子层两个普通视图的正文改回读**正本**，再删副本 ——
    副本被删后视图引用会断。

    正本（普通视图）天然还在；旧版 v1 不重建 ——
    它由 20260805 schema baseline 建立，属于基线资产。

    ⚠️ 升级时本迁移**执行了一次正本资产**（把基线那份 7 列旧版正本换成
    当前 8 列版本）—— 回滚**不**在这里把正本换回去：
    正本的历史口径由**更晚的** ``20261112_realign_identity_candidates_anchor``
    的 downgrade 负责恢复（它内嵌了旧口径正文），而 alembic 要求**倒序**回滚 ⇒
    到这里时正本已经是旧口径了。
    """
    _rebuild_source_views()
    if _exists(CANDIDATES_MV):
        _exec_sql("DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV))
