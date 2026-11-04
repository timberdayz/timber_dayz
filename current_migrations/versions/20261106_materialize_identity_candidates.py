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
1. 新建物化视图 ``semantic.shop_identity_resolution_candidates_v2_mv``
   （正文 = 候选集定义，从 ``core.shop_accounts`` / ``core.shop_account_aliases``
   现算，**自包含**，不引用任何视图 ⇒ 没有循环依赖）。
2. 把 ``semantic.shop_identity_resolution_candidates`` 改成**转发视图**
   （``SELECT * FROM ..._v2_mv``）。

⇒ **4 个下游原子层视图（fact_orders_atomic / fact_analytics_atomic /
fact_orders_monthly_atomic_mv / fact_analytics_monthly_atomic_mv）的正文
一个字都不用改** —— 它们引用的仍然是 ``semantic.shop_identity_resolution_candidates``。
口径零变化，不需要重建下游，不需要重新验证任何金额。

口径守护
--------
迁移在改造前先给旧候选视图算一个内容指纹（行数 + 全量内容 md5），
改造后对物化副本算同样的指纹，**不一致就直接抛错回滚** ⇒
「物化副本内容 == 改造前普通视图内容」由机器证明，不靠人眼比对。

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


revision = "current_schema_20261106_materialize_identity_candidates"
down_revision = "current_schema_20261105_create_atomic_materialized_views"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

#: 物化副本（正本）：候选集从 core 表现算，自包含
CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"
#: 转发视图：下游原子层继续引用它，正文不变
FORWARDING_VIEW = "semantic.shop_identity_resolution_candidates"
#: 20260805 schema baseline 建的旧版候选集物化视图（7 列，缺 identity_shop_region）
LEGACY_MV = "semantic.shop_identity_resolution_candidates_mv"

CANDIDATES_MV_ASSET = "sql/semantic/shop_identity_resolution_candidates_v2_mv.sql"
FORWARDING_VIEW_ASSET = "sql/semantic/shop_identity_resolution_candidates.sql"


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


def _execute_asset(rel_path: str) -> bool:
    """执行一个 SQL 资产文件（整文件一次执行）。

    迁移侧走 psycopg2（``op.get_bind().exec_driver_sql``），而 psycopg2 走
    PostgreSQL 的**简单查询协议** —— 一条 query 里可以带多条语句，
    由数据库自己按分号切分，**并且数据库自己认 dollar-quoted 块**
    （``DO $$ ... $$``、``$mv$ ... $mv$`` 都不会被切坏）。
    应用侧走 asyncpg，不支持多语句，所以那边必须自己切（见
    ``backend/services/data_pipeline/sql_loader.py``）。
    """
    sql_text = _asset_text(rel_path)
    if sql_text is None:
        return False
    op.get_bind().exec_driver_sql(sql_text)
    return True


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 口径基线：改造前把旧候选视图的内容指纹存下来
    if not _exists(FORWARDING_VIEW):
        print(
            "[WARN] 候选视图不存在，跳过口径比对：{view}".format(view=FORWARDING_VIEW)
        )
        before_fingerprint = None
    else:
        before_fingerprint = _fingerprint(FORWARDING_VIEW)

    # 2) 物化副本（正本）。资产缺失 → 跳过并告警，不阻断迁移：
    #    转发视图依赖它，缺了就保持旧形态（慢但正确）。
    if not _execute_asset(CANDIDATES_MV_ASSET):
        print("[WARN] 物化副本资产缺失，保持旧候选视图形态（慢但口径正确）")
        return

    # 3) 口径守护：物化副本内容必须与改造前逐字节一致
    if before_fingerprint is not None:
        after_fingerprint = _fingerprint(CANDIDATES_MV)
        if after_fingerprint != before_fingerprint:
            raise RuntimeError(
                "候选集物化副本与改造前内容不一致，拒绝继续：before={before} "
                "after={after}".format(
                    before=before_fingerprint, after=after_fingerprint
                )
            )

    # 4) 转发视图（下游 4 个原子层视图的正文不动）
    _execute_asset(FORWARDING_VIEW_ASSET)

    # 5) 删掉 20260805 baseline 建的旧版候选集物化视图（7 列、缺
    #    identity_shop_region、没有任何对象引用它）。
    #    **不带 CASCADE**：有依赖就让迁移失败（fail-closed），不静默删下游。
    if _exists(LEGACY_MV):
        bind.exec_driver_sql(
            "DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=LEGACY_MV)
        )


def downgrade() -> None:
    """回滚：转发视图改回「从 core 表现算」，并删掉物化副本。

    候选集的旧定义（从 core 表现算）**内联**在这里，不从资产文件读 ——
    因为 ``sql/semantic/shop_identity_resolution_candidates.sql`` 在本次迁移里
    已经被改成转发视图形态，资产文件里没有旧定义了。
    内联副本只服务回滚；正本在 git 历史（v7.13.1 的同名资产文件）。
    """
    op.get_bind().exec_driver_sql(
        """
        CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS
        WITH active_shop_accounts AS (
            SELECT
                sa.id AS shop_account_pk,
                LOWER(COALESCE(sa.platform, '')) AS platform_code,
                NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '') AS resolved_shop_account_id,
                NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '') AS candidate_platform_shop_id,
                NULLIF(TRIM(COALESCE(sa.store_name, '')), '') AS candidate_store_label,
                NULLIF(TRIM(COALESCE(sa.shop_region, '')), '') AS candidate_shop_region,
                COALESCE(
                    NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
                    NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
                    sa.id::text
                ) AS resolved_shop_id
            FROM core.shop_accounts sa
        ),
        identity_rows AS (
            SELECT
                platform_code,
                resolved_shop_id,
                resolved_shop_account_id,
                'platform_shop_id'::varchar AS resolution_method,
                1 AS resolution_priority,
                LOWER(candidate_platform_shop_id) AS identity_value_normalized,
                candidate_platform_shop_id AS identity_source_value,
                candidate_shop_region AS identity_shop_region
            FROM active_shop_accounts
            WHERE candidate_platform_shop_id IS NOT NULL

            UNION ALL

            SELECT
                platform_code,
                resolved_shop_id,
                resolved_shop_account_id,
                'shop_account_id'::varchar AS resolution_method,
                2 AS resolution_priority,
                LOWER(resolved_shop_account_id) AS identity_value_normalized,
                resolved_shop_account_id AS identity_source_value,
                candidate_shop_region AS identity_shop_region
            FROM active_shop_accounts
            WHERE resolved_shop_account_id IS NOT NULL

            UNION ALL

            SELECT
                asa.platform_code,
                asa.resolved_shop_id,
                asa.resolved_shop_account_id,
                'alias_match'::varchar AS resolution_method,
                3 AS resolution_priority,
                LOWER(TRIM(saa.alias_normalized)) AS identity_value_normalized,
                saa.alias_value AS identity_source_value,
                NULLIF(TRIM(COALESCE(saa.shop_region, '')), '') AS identity_shop_region
            FROM active_shop_accounts asa
            INNER JOIN core.shop_account_aliases saa
              ON saa.shop_account_id = asa.shop_account_pk
             AND saa.is_active = TRUE
            WHERE NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL

            UNION ALL

            SELECT
                platform_code,
                resolved_shop_id,
                resolved_shop_account_id,
                'store_name_match'::varchar AS resolution_method,
                4 AS resolution_priority,
                REGEXP_REPLACE(
                    LOWER(
                        TRIM(BOTH FROM REGEXP_REPLACE(
                            TRIM(BOTH FROM COALESCE(active_shop_accounts.candidate_store_label, '')),
                            '^(shopee|tiktok\\s*shop|tiktok|tk|miaoshou|amazon|lazada)\\s*',
                            '',
                            'i'
                        ))
                    ),
                    '[\\s_()/-]+',
                    '',
                    'g'
                ) AS identity_value_normalized,
                candidate_store_label AS identity_source_value,
                candidate_shop_region AS identity_shop_region
            FROM active_shop_accounts
            WHERE candidate_store_label IS NOT NULL
        )
        SELECT
            platform_code,
            identity_value_normalized,
            identity_source_value,
            resolved_shop_id,
            resolved_shop_account_id,
            resolution_method,
            resolution_priority,
            identity_shop_region
        FROM identity_rows
        WHERE NULLIF(TRIM(COALESCE(identity_value_normalized, '')), '') IS NOT NULL
        """
    )

    if _exists(CANDIDATES_MV):
        op.get_bind().exec_driver_sql(
            "DROP MATERIALIZED VIEW IF EXISTS {mv}".format(mv=CANDIDATES_MV)
        )
