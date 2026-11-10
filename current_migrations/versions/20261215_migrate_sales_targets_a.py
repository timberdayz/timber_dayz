"""第三批-C：把 ``a_class.sales_targets_a`` 的事实迁移到真 SSOT，然后删表。

背景
----
``a_class.sales_targets_a`` 是「店铺月度目标」的**派生副本**（252 行）：
它由 ``backend/services/target_sync_service.py`` 从
``a_class.sales_targets``（30 行父目标）+ ``a_class.target_breakdown``
（8361 行店铺分解）同步而来，运行时有三处读它：

- ``sql/api_modules/business_overview_comparison_module.sql``（数据对比）
- ``sql/api_modules/business_overview_operational_metrics_module.sql``（经营指标）
- ``backend/services/postgresql_dashboard_service.py``（四层 fallback 技术债）

**真 SSOT 就是 ``a_class.target_breakdown``**（``breakdown_type='shop'`` 的
「店铺月度档位」行）+ 其父目标 ``a_class.sales_targets``。副本与真源之间
还隔着一层「英文列/中文列双分支 try/except」的技术债。

仓库既有的「店铺月度档位」取值（**已查清，不新造**）
--------------------------------------------------
``a_class.target_breakdown.breakdown_type`` 的 CHECK 约束只允许三个值：
``shop`` / ``time`` / ``shop_time``。其中**店铺 × 月**档位是：

- ``breakdown_type = 'shop'``
- ``period_label = 'YYYY-MM'``（月份标签，如 ``'2026-01'``）
- ``period_start`` / ``period_end`` = 该月首末日

这套约定由 ``backend/services/shop_target_workbench_service.py``
的 ``_replace_breakdowns`` 写入（``period_label=request.year_month``），
库里 2026-01 ~ 2026-12 的 240 行就是这样写的。

本迁移做五件事
--------------
1. **规范化**：给 ``breakdown_type='shop'`` 且 ``period_label IS NULL`` 的历史行
   （2025-07/08/09 的 12 行）补上 ``period_label`` / ``period_start`` /
   ``period_end``（值取自其父目标 ``a_class.sales_targets.period_start``），
   让整张表都能按 ``platform_code | shop_id | period_label(年-月)`` 定位。
   **只补 NULL，不改已有值。**
   ⚠️ 2026-11-10 起**排除**「父目标 ``target_type='operation'`` 且
   ``metric_catalog_version IS NULL``」的历史行（只读快照，业务口径为「不该被改」），
   跳过的行数写进迁移日志 —— 详见 ``_normalize_shop_breakdown_periods`` 的说明。
2. **迁移事实**：把 ``a_class.sales_targets_a`` 的每一行
   （``目标销售额`` → ``target_amount``、``目标订单数`` → ``target_quantity``）
   upsert 进 ``a_class.target_breakdown`` 的「店铺月度档位」行。
3. **fail-closed 校验**：逐行核对「源表每一行都有值相等的目标行」，
   只要有一行对不上就**抛错中止**，绝不带着缺口删表。
4. **重建视图**：用 ``sql/api_modules/`` 下的资产文件重建两个 API 视图
   （视图定义的 SSOT 是资产文件，迁移不抄第二份）。
5. **删表**（fail-closed）：``DROP TABLE a_class.sales_targets_a``。

关于「哪个值算数」
-----------------
本迁移以**源表**为准：若同一 ``platform_code|shop_id|年月`` 键在
``target_breakdown`` 上已有行但金额/数量不同，就把目标行**改成源表的值**
（源表是要被迁移的事实）；目标行不存在时**新增**一行（父目标取同月
``target_type='shop'`` 且 ``status='active'`` 的那个；找不到父目标 ⇒
该行无法落库 ⇒ 第 3 步校验会中止迁移，不会静默丢数据）。

「店铺不在维度表里」的行怎么办（2026-11-09 生产演练新增）
----------------------------------------------------------
生产快照库演练发现：源表里有 9 行引用的 3 个店铺**从未登记在
``core.dim_shops``**（``shopee新加坡3C店`` / ``虾皮巴西（东朗照明主体）`` /
``Tiktok 2店``，均为 2025-07~09）。而 ``target_breakdown`` 有外键
``fk_breakdown_shop`` ⇒ 这些行**根本插不进去**，迁移会直接失败
（本地库因维度表完整而从未暴露这个问题）。

处理方式（既不丢数据，也不假装成功）：

1. **只跳过「本来就不可见」的行**：旧视图是从 ``mart.shop_month_kpi``
   出发 LEFT JOIN 目标数据的，而这几个店铺在真实业务表里**一行都没有**
   ⇒ 它们的目标从来就没出现在任何报表里。若某店铺**有**业务数据却不在
   维度表里，那是数据缺口 ⇒ **中止迁移**，交人工确认，绝不自动跳过。
2. **跳过的行进隔离区**：写入 ``core.data_quarantine``
   （``error_type='ORPHAN_SHOP_NOT_IN_DIM_SHOPS'``），不是悄悄丢掉；
   ``downgrade`` 会把它们原样放回源表。
3. **迁移日志显形**：打印被跳过的行数、店铺与金额。

数据安全性
----------
- 第 3 步校验不通过 ⇒ 迁移中止 ⇒ **表不会被删**、数据不会被丢；
- 被跳过的行进隔离区（可查、可回滚），且只在「无业务数据」时才允许跳；
- 视图先重建、再删表 ⇒ 删表后视图仍然可查（视图已不再依赖该表）；
- ``downgrade`` 会把表、序列、约束、索引按基线 DDL 重建，并从
  ``target_breakdown`` **与隔离区**反向回填（事实没有丢），同时把两个视图
  改回旧口径。
"""

import json
from pathlib import Path

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261215_migrate_sales_targets_a"
down_revision = "current_schema_20261214_unify_operating_costs_columns"
branch_labels = None
depends_on = None


REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_TABLE = "a_class.sales_targets_a"

#: 需要重建的视图 → 资产文件（相对仓库根）
VIEW_ASSETS = (
    (
        "api.business_overview_comparison_module",
        "sql/api_modules/business_overview_comparison_module.sql",
    ),
    (
        "api.business_overview_operational_metrics_module",
        "sql/api_modules/business_overview_operational_metrics_module.sql",
    ),
)

#: 目标行与源行的匹配条件（platform_code | shop_id | 年月）
_MATCH_CONDITION = """
                tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label = s."年月"
              AND lower(trim(COALESCE(tb.platform_code, '')))
                  = lower(trim(COALESCE(s.platform_code, '')))
              AND tb.shop_id = s."店铺ID"
"""


def _driver_connection():
    """拿到原生 psycopg2 连接。

    ``Connection.connection`` 是**属性**（不是方法）；真正的驱动连接在它的
    ``driver_connection`` 上，后面**不能加括号**。
    """
    pool_conn = op.get_bind().connection
    return getattr(pool_conn, "driver_connection", pool_conn)


def _exec_sql_text(sql_text: str) -> None:
    """执行一段原生 SQL（**可以含多条语句**）。"""
    with _driver_connection().cursor() as cursor:
        cursor.execute(sql_text)


def _table_exists(table: str, schema: str = "a_class") -> bool:
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


def _table_exists_qualified(full_name: str) -> bool:
    """``schema.table`` 形式的表存在性判断。"""
    schema, _, table = full_name.partition(".")
    return sa.inspect(op.get_bind()).has_table(table, schema=schema)


#: 店铺维度 SSOT（``target_breakdown`` 的外键指向它）
_SHOP_DIMENSION = "core.dim_shops"

#: 被跳过的行在隔离区里的标记（downgrade 靠它原样放回）
_ORPHAN_ERROR_TYPE = "ORPHAN_SHOP_NOT_IN_DIM_SHOPS"
_ORPHAN_SOURCE_FILE = "a_class.sales_targets_a"


def _migratable_source_filter(alias: str = "s") -> str:
    """源表里「店铺在维度表中存在」的条件（可直接嵌进 WHERE）。

    ``a_class.target_breakdown`` 对 ``(platform_code, shop_id)`` 有外键
    ``fk_breakdown_shop`` ⇒ 维度表里没有的店铺**根本无法落库**。
    这里用**完全相等**判断，与外键的判定口径保持一致（不做 lower/trim，
    否则会出现「谓词认为可落库、外键却拒绝」的错位）。
    """
    return """
        EXISTS (
            SELECT 1
            FROM core.dim_shops d
            WHERE d.platform_code = {alias}.platform_code
              AND d.shop_id = {alias}."店铺ID"
        )
        """.format(
        alias=alias
    )


def _orphan_source_rows() -> list:
    """返回「店铺不在维度表里」的源行（这些行无法落库）。"""
    rows = (
        op.get_bind()
        .execute(
            sa.text(
                """
            SELECT s.platform_code,
                   s."店铺ID" AS shop_id,
                   s."年月" AS period_label,
                   s."目标销售额" AS target_amount,
                   s."目标订单数" AS target_quantity
            FROM a_class.sales_targets_a s
            WHERE NOT EXISTS (
                SELECT 1
                FROM core.dim_shops d
                WHERE d.platform_code = s.platform_code
                  AND d.shop_id = s."店铺ID"
            )
            ORDER BY s.platform_code, s."店铺ID", s."年月"
            """
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


def _verify_orphans_are_invisible(orphans: list) -> None:
    """被跳过的店铺必须**没有任何真实业务数据**，否则中止迁移。

    旧视图是从 ``mart.shop_month_kpi`` 出发 LEFT JOIN 目标数据的 ⇒
    「没有业务数据的店铺」的目标从来就没在任何报表里出现过，跳过不丢可见数据。

    反过来：某店铺**有**业务数据却不在维度表里 ⇒ 这是数据缺口（多半是
    维度表漏登记），必须人工确认 ⇒ fail-closed 中止，绝不自动跳过。
    """
    shop_ids = sorted({row["shop_id"] for row in orphans})
    if not shop_ids:
        return

    id_list = ", ".join("'{}'".format(sid.replace("'", "''")) for sid in shop_ids)
    for table in ("mart.shop_month_kpi", "mart.shop_day_kpi"):
        if not _table_exists_qualified(table):
            continue
        count = int(
            _scalar(
                "SELECT COUNT(*) FROM {t} m WHERE m.shop_id IN ({ids})".format(
                    t=table, ids=id_list
                )
            )
            or 0
        )
        if count:
            raise RuntimeError(
                "以下店铺不在 {dim} 里（无法落库），但它们**有真实业务数据**（{t} 命中 "
                "{n} 行），属于数据缺口而非历史残留，拒绝自动跳过；"
                "请先补齐维度表登记或人工确认这些目标的去向，再重跑迁移。"
                "店铺：{shops}".format(
                    dim=_SHOP_DIMENSION,
                    t=table,
                    n=count,
                    shops=", ".join(shop_ids),
                )
            )


def _quarantine_orphan_rows(orphans: list) -> int:
    """把被跳过的行写进隔离区（不悄悄丢，可查可回滚）。"""
    if not orphans:
        return 0
    if not _table_exists_qualified("core.data_quarantine"):
        print(
            "[WARN] core.data_quarantine 不存在，被跳过的 {n} 行无法落隔离区".format(
                n=len(orphans)
            )
        )
        return 0

    error_msg = "店铺未登记在 {dim}（外键 fk_breakdown_shop 不允许落库）".format(
        dim=_SHOP_DIMENSION
    )
    # [*] 2026-11-09 幂等性修复：先把**同源同类型**的旧隔离记录清掉。
    # 否则「降级 → 再升级」会把同一批行再写一遍，隔离区越滚越大
    # （生产演练实测：9 行 → 18 行）。
    op.get_bind().execute(
        sa.text(
            """
            DELETE FROM core.data_quarantine
             WHERE source_file = :source_file
               AND error_type = :error_type
            """
        ),
        {
            "source_file": _ORPHAN_SOURCE_FILE,
            "error_type": _ORPHAN_ERROR_TYPE,
        },
    )
    for row in orphans:
        payload = {
            "店铺ID": row["shop_id"],
            "年月": row["period_label"],
            "目标销售额": row["target_amount"],
            "目标订单数": row["target_quantity"],
        }
        payload_text = json.dumps(payload, ensure_ascii=False, default=str)
        op.get_bind().execute(
            sa.text(
                """
                INSERT INTO core.data_quarantine (
                    source_file,
                    catalog_file_id,
                    row_number,
                    row_data,
                    error_type,
                    error_msg,
                    platform_code,
                    shop_id,
                    data_domain,
                    platform,
                    is_resolved,
                    raw_data
                )
                VALUES (
                    :source_file,
                    NULL,
                    NULL,
                    :row_data,
                    :error_type,
                    :error_msg,
                    :platform_code,
                    :shop_id,
                    'targets',
                    :platform,
                    false,
                    CAST(:raw_data AS jsonb)
                )
                """
            ),
            {
                "source_file": _ORPHAN_SOURCE_FILE,
                "row_data": payload_text,
                "error_type": _ORPHAN_ERROR_TYPE,
                "error_msg": error_msg,
                "platform_code": row["platform_code"],
                "shop_id": row["shop_id"],
                "platform": row["platform_code"],
                "raw_data": payload_text,
            },
        )
    return len(orphans)


def _scalar(sql: str):
    return op.get_bind().execute(sa.text(sql)).scalar_one()


def _rebuild_view(view_name: str, asset_rel_path: str) -> bool:
    """用 ``sql/`` 下的资产文件重建视图。

    资产缺失 ⇒ **中止**（fail-closed）。不能只告警：视图没切到新口径，
    ``sales_targets_a`` 就还被人依赖着，后面 ``DROP TABLE`` 会以
    「other objects depend on it」这种看不懂的报错收场。
    """
    asset_path = REPO_ROOT / asset_rel_path
    if not asset_path.is_file():
        raise RuntimeError(
            "视图资产文件缺失，拒绝继续迁移（否则删表时才会以"
            "「other objects depend on it」报错）：{path}（仓库根 {root}）".format(
                path=asset_rel_path, root=REPO_ROOT
            )
        )
    _exec_sql_text(asset_path.read_text(encoding="utf-8-sig"))
    return True


def _rebuild_views() -> None:
    for view_name, asset_rel_path in VIEW_ASSETS:
        _rebuild_view(view_name, asset_rel_path)


# --------------------------------------------------------------------------
# 1) 规范化「店铺月度档位」的 period_label / period_start / period_end
# --------------------------------------------------------------------------
def _normalize_shop_breakdown_periods() -> int:
    """给 period_label 为空的店铺档位行补上月份标签（只补 NULL，不改已有值）。

    [*] 2026-11-10（业务拍板）：**历史 operation 型档位行不该被改**。

    为什么
    ------
    父目标 ``target_type='operation'`` 且 ``metric_catalog_version IS NULL``
    的档位行，是只读触发器 ``a_class.enforce_operation_breakdown_contract``
    保护的历史快照（``20260808``/``20260810`` 建，链上第 3 个执行）：

    .. code-block:: sql

        IF FOUND AND parent_target.target_type = 'operation' THEN
            IF parent_target.metric_catalog_version IS NULL THEN
                RAISE EXCEPTION 'historical operation breakdowns are read-only';

    原先的回填谓词只按 ``breakdown_type='shop' AND period_label IS NULL`` 过滤，
    **没有 target_type 过滤** ⇒ 会去改这些行 ⇒ 老库升级时在这一步抛错、链断
    （实测报错就是 'historical operation breakdowns are read-only'）。

    口径决策（产品，2026-11-10）
    --------------------------
    这些历史行**本来就不该被补** ``period_label`` / ``period_start`` / ``period_end``
    ⇒ 正确做法是**显式跳过并记日志**（而不是去解锁触发器、或把行改掉）。
    口径材料：``docs/reports/2026-11-10-老库升级路径-只读触发器冲突口径决策材料.md``。

    ⇒ 本函数只回填「父目标不是无版本的 operation 型」的档位行，
    跳过的行数写进迁移日志（不静默漏改，避免被误读成"数据漏改"）。

    ⚠️ 已应用迁移不可变条款
    ----------------------
    ``20260914_warehouse_platform_profit.py:3`` 写明「Previous migration files
    remain immutable」。本次**显式豁免**并记录理由：

    - 豁免范围：仅本函数（``_normalize_shop_breakdown_periods``）的**回填范围与日志**；
    - 理由：老库升级路径在该迁移处**必然失败**（触发器与回填相交），
      而业务口径已拍板为「这些行不该被改」⇒ 唯一能同时满足
      「升级能走通」与「不改历史数据」的做法就是把回填范围收窄到可改的行；
    - 影响面：**只影响尚未应用本迁移的库**（老库升级路径）；已应用本迁移的库
      （含生产）alembic 不会重跑 ⇒ 行为完全不变；
    - 数据影响：operation 型无版本父目标下的档位行**保持原样**（不被回填）。
    """
    # ① 先算「原谓词会命中多少行」⇒ 与实际回填数的差值就是被跳过的行数
    candidate_result = op.get_bind().execute(
        sa.text(
            """
            SELECT count(*)
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON tb.target_id = st.id
            WHERE tb.breakdown_type = 'shop'
              AND tb.period_label IS NULL
              AND st.period_start IS NOT NULL
            """
        )
    )
    candidates = int(candidate_result.scalar_one() or 0)

    # ② 只回填「可改」的行：父目标不是「无版本的 operation 型」
    #    （IS DISTINCT FROM 处理 target_type 为 NULL 的情况）
    result = op.get_bind().execute(
        sa.text(
            """
            UPDATE a_class.target_breakdown tb
            SET period_label = to_char(COALESCE(tb.period_start, st.period_start), 'YYYY-MM'),
                period_start = COALESCE(tb.period_start, st.period_start),
                period_end = COALESCE(tb.period_end, st.period_end)
            FROM a_class.sales_targets st
            WHERE tb.target_id = st.id
              AND tb.breakdown_type = 'shop'
              AND tb.period_label IS NULL
              AND st.period_start IS NOT NULL
              AND (
                    st.target_type IS DISTINCT FROM 'operation'
                    OR st.metric_catalog_version IS NOT NULL
              )
            RETURNING tb.id
            """
        )
    )
    updated = len(result.fetchall())
    skipped = max(0, candidates - updated)
    if skipped:
        print(
            "[20261215] 跳过（业务口径：历史 operation 型档位行不改）{n} 行 —— "
            "父目标 target_type='operation' 且 metric_catalog_version IS NULL"
            "（只读历史快照；本次回填范围已收窄）".format(n=skipped)
        )
    return updated


# --------------------------------------------------------------------------
# 2) 迁移事实
# --------------------------------------------------------------------------
def _migrate_facts() -> dict:
    """把源表的事实 upsert 进 ``a_class.target_breakdown``。"""
    updated = (
        op.get_bind()
        .execute(
            sa.text(
                """
            UPDATE a_class.target_breakdown tb
            SET target_amount = s."目标销售额",
                target_quantity = s."目标订单数",
                updated_at = NOW()
            FROM a_class.sales_targets st, a_class.sales_targets_a s
            WHERE tb.target_id = st.id
              AND tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label = s."年月"
              AND lower(trim(COALESCE(tb.platform_code, '')))
                  = lower(trim(COALESCE(s.platform_code, '')))
              AND tb.shop_id = s."店铺ID"
              AND (tb.target_amount IS DISTINCT FROM s."目标销售额"
                   OR tb.target_quantity IS DISTINCT FROM s."目标订单数")
            """
            )
        )
        .rowcount
    )

    inserted = (
        op.get_bind()
        .execute(
            sa.text(
                """
            WITH parent AS (
                SELECT DISTINCT ON (date_trunc('month', st.period_start))
                       st.id,
                       date_trunc('month', st.period_start) AS month
                FROM a_class.sales_targets st
                WHERE st.target_type = 'shop'
                  AND st.status = 'active'
                ORDER BY date_trunc('month', st.period_start), st.id
            )
            INSERT INTO a_class.target_breakdown (
                target_id,
                breakdown_type,
                platform_code,
                shop_id,
                period_start,
                period_end,
                period_label,
                target_amount,
                target_quantity,
                achieved_amount,
                achieved_quantity,
                achievement_rate,
                target_profit_amount,
                achieved_profit_amount,
                target_profit_basis_amount
            )
            SELECT p.id,
                   'shop',
                   s.platform_code,
                   s."店铺ID",
                   p.month::date,
                   (p.month + interval '1 month - 1 day')::date,
                   s."年月",
                   s."目标销售额",
                   s."目标订单数",
                   0,
                   0,
                   0,
                   0,
                   0,
                   0
            FROM a_class.sales_targets_a s
            JOIN parent p
              ON p.month = to_date(s."年月" || '-01', 'YYYY-MM-DD')
            WHERE {migratable}
              AND NOT EXISTS (
                SELECT 1
                FROM a_class.target_breakdown tb
                JOIN a_class.sales_targets st ON st.id = tb.target_id
                WHERE {match}
            )
            """.format(
                    match=_MATCH_CONDITION, migratable=_migratable_source_filter()
                )
            )
        )
        .rowcount
    )

    return {"updated": int(updated or 0), "inserted": int(inserted or 0)}


# --------------------------------------------------------------------------
# 3) fail-closed 校验
# --------------------------------------------------------------------------
def _verify_fact_coverage() -> None:
    """**可落库的**源行必须在目标表里有"值相等"的对应行，否则中止迁移。

    「可落库」= 店铺在 ``core.dim_shops`` 里（外键 ``fk_breakdown_shop`` 的要求）。
    不满足的源行走隔离区（见 :func:`_quarantine_orphan_rows`），不算丢数据。
    """
    missing = _scalar(
        """
        SELECT COUNT(*)
        FROM a_class.sales_targets_a s
        WHERE {migratable}
          AND NOT EXISTS (
            SELECT 1
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE {match}
              AND tb.target_amount = s."目标销售额"
              AND tb.target_quantity = s."目标订单数"
        )
        """.format(
            match=_MATCH_CONDITION, migratable=_migratable_source_filter()
        )
    )
    if missing:
        raise RuntimeError(
            "a_class.sales_targets_a 有 {rows} 行未能在 a_class.target_breakdown "
            "找到值相等的「店铺月度档位」行, 拒绝删表; "
            "请先人工确认这些事实的落库位置, 再重跑迁移。".format(rows=missing)
        )


def _verify_view_keys(expected_keys: int) -> None:
    """两个 API 视图读到的「店铺 × 月」键数必须与**可落库**的源行数一致。"""
    view_rows = _scalar(
        """
        SELECT COUNT(*)
        FROM (
            SELECT DISTINCT
                tb.platform_code,
                tb.shop_id,
                tb.period_label
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label ~ '^\\d{4}-\\d{2}$'
        ) t
        """
    )
    if int(view_rows) != int(expected_keys):
        raise RuntimeError(
            "迁移后的「店铺 × 月」键数({view}) 与可落库的源行数({src}) 不一致, "
            "拒绝删表; 请先人工确认口径差异。".format(view=view_rows, src=expected_keys)
        )


def _verify_monthly_totals() -> None:
    """按月的金额/数量合计必须与**可落库**的源表逐月一致（防止重复行导致的翻倍）。"""
    # 注意：这里用 __TOKEN__ 替换而不是 str.format —— SQL 里的正则
    # ``'^\\d{4}-\\d{2}$'`` 含大括号，format 会把它当成占位符而报错。
    sql_text = """
        WITH src AS (
            SELECT "年月" AS ym,
                   SUM("目标销售额") AS amt,
                   SUM("目标订单数") AS qty
            FROM a_class.sales_targets_a s
            WHERE __MIGRATABLE__
            GROUP BY 1
        ),
        tgt AS (
            SELECT tb.period_label AS ym,
                   SUM(tb.target_amount) AS amt,
                   SUM(tb.target_quantity) AS qty
            FROM a_class.target_breakdown tb
            JOIN a_class.sales_targets st ON st.id = tb.target_id
            WHERE tb.breakdown_type = 'shop'
              AND st.target_type = 'shop'
              AND st.status = 'active'
              AND tb.period_label ~ '^\\d{4}-\\d{2}$'
            GROUP BY 1
        )
        SELECT COUNT(*)
        FROM (
            SELECT COALESCE(src.ym, tgt.ym) AS ym
            FROM src
            FULL OUTER JOIN tgt ON tgt.ym = src.ym
            WHERE src.amt IS DISTINCT FROM tgt.amt
               OR src.qty IS DISTINCT FROM tgt.qty
        ) d
        """.replace(
        "__MIGRATABLE__", _migratable_source_filter()
    )
    diff = _scalar(sql_text)
    if int(diff):
        raise RuntimeError(
            "迁移后按月合计与源表有 {months} 个月不一致, 拒绝删表; "
            "请先人工确认是否存在重复行。".format(months=diff)
        )


# --------------------------------------------------------------------------
# 4) 删表（fail-closed）
# --------------------------------------------------------------------------
def _drop_legacy_table() -> None:
    if not _table_exists("sales_targets_a"):
        return
    op.execute("DROP TABLE IF EXISTS a_class.sales_targets_a")


# --------------------------------------------------------------------------
# downgrade：重建表 + 回填 + 恢复旧视图
# --------------------------------------------------------------------------
_LEGACY_TABLE_DDL = """
CREATE TABLE a_class.sales_targets_a (
    id bigint NOT NULL,
    "店铺ID" character varying(256) NOT NULL,
    "年月" character varying(7) NOT NULL,
    "目标销售额" numeric(15,2) DEFAULT 0.0 NOT NULL,
    "目标订单数" integer DEFAULT 0 NOT NULL,
    "创建时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    "更新时间" timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    platform_code character varying(32) DEFAULT 'unknown'::character varying NOT NULL
)
"""

_OLD_COMPARISON_VIEW_SQL = """
CREATE OR REPLACE VIEW api.business_overview_comparison_module AS
WITH daily AS (
    SELECT
        'daily'::varchar AS granularity,
        period_date AS period_start,
        period_date AS period_end,
        period_date AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        COALESCE(page_views, visitor_count) AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_day_kpi
),
weekly AS (
    SELECT
        'weekly'::varchar AS granularity,
        period_week AS period_start,
        (period_week + INTERVAL '6 day')::date AS period_end,
        period_week AS period_key,
        platform_code,
        shop_id,
        gmv AS sales_amount,
        order_count AS sales_quantity,
        COALESCE(page_views, visitor_count) AS traffic,
        conversion_rate,
        avg_order_value,
        attach_rate,
        profit,
        NULL::numeric AS target_sales_amount,
        NULL::numeric AS target_sales_quantity
    FROM mart.shop_week_kpi
),
monthly_target AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
        "店铺ID" AS shop_id,
        COALESCE(SUM("目标销售额"), 0) AS target_sales_amount,
        COALESCE(SUM("目标订单数"), 0) AS target_sales_quantity
    FROM a_class.sales_targets_a
    GROUP BY
        to_date("年月" || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(platform_code, ''))),
        "店铺ID"
),
monthly AS (
    SELECT
        'monthly'::varchar AS granularity,
        m.period_month AS period_start,
        (m.period_month + INTERVAL '1 month - 1 day')::date AS period_end,
        m.period_month AS period_key,
        m.platform_code,
        m.shop_id,
        m.gmv AS sales_amount,
        m.order_count AS sales_quantity,
        COALESCE(m.page_views, m.visitor_count) AS traffic,
        m.conversion_rate,
        m.avg_order_value,
        m.attach_rate,
        m.profit,
        t.target_sales_amount,
        t.target_sales_quantity
    FROM mart.shop_month_kpi m
    LEFT JOIN monthly_target t
        ON m.period_month = t.period_month
       AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
       AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
)
SELECT * FROM daily
UNION ALL
SELECT * FROM weekly
UNION ALL
SELECT * FROM monthly;
"""

_OLD_OPERATIONAL_METRICS_VIEW_SQL = """
CREATE OR REPLACE VIEW api.business_overview_operational_metrics_module AS
WITH base_month_kpi AS (
    SELECT
        m.period_month,
        m.platform_code,
        m.shop_id,
        m.gmv,
        m.order_count,
        m.profit,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN m.period_month
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN (m.period_month + INTERVAL '1 month - 1 day')::date
            ELSE CURRENT_DATE
        END AS anchor_date,
        CASE
            WHEN CURRENT_DATE < m.period_month THEN 0::numeric
            WHEN CURRENT_DATE > (m.period_month + INTERVAL '1 month - 1 day')::date THEN 100::numeric
            ELSE ROUND(
                ((CURRENT_DATE - m.period_month + 1)::numeric * 100.0) /
                NULLIF(((m.period_month + INTERVAL '1 month - 1 day')::date - m.period_month + 1)::numeric, 0),
                2
            )
        END AS time_progress_pct
    FROM mart.shop_month_kpi m
),
monthly_targets AS (
    SELECT
        to_date("年月" || '-01', 'YYYY-MM-DD') AS period_month,
        LOWER(TRIM(COALESCE(platform_code, ''))) AS platform_code,
        "店铺ID" AS shop_id,
        SUM("目标销售额") AS monthly_target
    FROM a_class.sales_targets_a
    GROUP BY
        to_date("年月" || '-01', 'YYYY-MM-DD'),
        LOWER(TRIM(COALESCE(platform_code, ''))),
        "店铺ID"
),
monthly_costs AS (
    SELECT
        COALESCE(o.period_month, l.period_month) AS period_month,
        COALESCE(o.platform_code, l.platform_code) AS platform_code,
        COALESCE(o.shop_id, l.shop_id) AS shop_id,
        COALESCE(o.other_operating_cost, 0) AS other_operating_cost,
        COALESCE(l.pre_commission_labor_cost, 0) AS pre_commission_labor_cost,
        COALESCE(l.performance_labor_cost, 0) AS performance_labor_cost,
        COALESCE(l.commission_labor_cost, 0) AS commission_labor_cost,
        COALESCE(l.total_labor_cost, 0) AS total_labor_cost,
        COALESCE(o.other_operating_cost, 0) + COALESCE(l.total_labor_cost, 0) AS estimated_expenses,
        COALESCE(l.cost_status, 'legacy') AS cost_status
    FROM semantic.shop_month_other_operating_cost o
    FULL OUTER JOIN mart.shop_month_labor_cost l
        ON o.period_month = l.period_month
       AND o.platform_code = l.platform_code
       AND COALESCE(o.shop_id, '') = COALESCE(l.shop_id, '')
)
SELECT
    m.period_month,
    m.platform_code,
    m.shop_id,
    t.monthly_target AS monthly_target,
    m.gmv AS monthly_total_achieved,
    ds.gmv AS today_sales,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND(m.gmv::numeric * 100.0 / t.monthly_target, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN 0
        ELSE NULL
    END AS monthly_achievement_rate,
    CASE
        WHEN t.monthly_target IS NULL OR m.gmv IS NULL THEN NULL
        WHEN t.monthly_target > 0 THEN ROUND((m.gmv::numeric * 100.0 / t.monthly_target) - m.time_progress_pct, 2)
        WHEN t.monthly_target = 0 AND m.gmv = 0 THEN ROUND(0 - m.time_progress_pct, 2)
        ELSE NULL
    END AS time_gap,
    m.profit AS estimated_gross_profit,
    c.other_operating_cost,
    c.pre_commission_labor_cost,
    c.performance_labor_cost,
    c.commission_labor_cost,
    c.total_labor_cost,
    c.cost_status,
    c.estimated_expenses AS estimated_expenses,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        ELSE (m.profit - c.estimated_expenses)
    END AS operating_result,
    CASE
        WHEN m.profit IS NULL OR c.estimated_expenses IS NULL THEN NULL
        WHEN (m.profit - c.estimated_expenses) > 0 THEN '盈利'
        ELSE '亏损'
    END AS operating_result_text,
    m.order_count AS monthly_order_count,
    ds.order_count AS today_order_count
FROM base_month_kpi m
LEFT JOIN monthly_targets t
    ON m.period_month = t.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(t.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(t.shop_id, '')
LEFT JOIN monthly_costs c
    ON m.period_month = c.period_month
   AND LOWER(COALESCE(m.platform_code, '')) = COALESCE(c.platform_code, '')
   AND COALESCE(m.shop_id, '') = COALESCE(c.shop_id, '')
LEFT JOIN mart.shop_day_kpi ds
    ON ds.period_date = m.anchor_date
   AND ds.platform_code = m.platform_code
   AND COALESCE(ds.shop_id, '') = COALESCE(m.shop_id, '');
"""


def _restore_legacy_table() -> None:
    """按基线 DDL 重建表 + 序列 + 约束 + 索引，并从 target_breakdown 回填事实。"""
    if not _table_exists("sales_targets_a"):
        _exec_sql_text(_LEGACY_TABLE_DDL)
        _exec_sql_text(
            """
            CREATE SEQUENCE IF NOT EXISTS a_class.sales_targets_a_id_seq
            START WITH 1 INCREMENT BY 1
            """
        )
        _exec_sql_text(
            """
            ALTER SEQUENCE a_class.sales_targets_a_id_seq OWNED BY a_class.sales_targets_a.id
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE a_class.sales_targets_a
            ALTER COLUMN id SET DEFAULT nextval('a_class.sales_targets_a_id_seq'::regclass)
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE ONLY a_class.sales_targets_a
            ADD CONSTRAINT sales_targets_a_pkey PRIMARY KEY (id)
            """
        )
        _exec_sql_text(
            """
            ALTER TABLE ONLY a_class.sales_targets_a
            ADD CONSTRAINT uq_sales_targets_a_platform_shop_month
            UNIQUE (platform_code, "店铺ID", "年月")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_a_platform_shop
            ON a_class.sales_targets_a (platform_code, "店铺ID")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_a_platform_month
            ON a_class.sales_targets_a (platform_code, "年月")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_shop
            ON a_class.sales_targets_a ("店铺ID")
            """
        )
        _exec_sql_text(
            """
            CREATE INDEX IF NOT EXISTS ix_sales_targets_month
            ON a_class.sales_targets_a ("年月")
            """
        )

    _exec_sql_text(
        """
        INSERT INTO a_class.sales_targets_a (
            platform_code,
            "店铺ID",
            "年月",
            "目标销售额",
            "目标订单数",
            "创建时间",
            "更新时间"
        )
        SELECT LOWER(TRIM(COALESCE(tb.platform_code, ''))),
               tb.shop_id,
               tb.period_label,
               SUM(tb.target_amount),
               SUM(tb.target_quantity),
               MIN(tb.created_at),
               NOW()
        FROM a_class.target_breakdown tb
        JOIN a_class.sales_targets st ON st.id = tb.target_id
        WHERE tb.breakdown_type = 'shop'
          AND st.target_type = 'shop'
          AND st.status = 'active'
          AND tb.period_label ~ '^\\d{4}-\\d{2}$'
        GROUP BY
            LOWER(TRIM(COALESCE(tb.platform_code, ''))),
            tb.shop_id,
            tb.period_label
        ON CONFLICT (platform_code, "店铺ID", "年月") DO UPDATE SET
            "目标销售额" = EXCLUDED."目标销售额",
            "目标订单数" = EXCLUDED."目标订单数",
            "更新时间" = NOW()
        """
    )

    # 被 upgrade 跳过的行（店铺不在维度表里）从隔离区原样放回 ⇒ 事实不丢。
    if _table_exists_qualified("core.data_quarantine"):
        restored = (
            op.get_bind()
            .execute(
                sa.text(
                    """
                INSERT INTO a_class.sales_targets_a (
                    platform_code,
                    "店铺ID",
                    "年月",
                    "目标销售额",
                    "目标订单数",
                    "创建时间",
                    "更新时间"
                )
                SELECT q.platform_code,
                       q.row_data::json ->> '店铺ID',
                       q.row_data::json ->> '年月',
                       (q.row_data::json ->> '目标销售额')::numeric,
                       (q.row_data::json ->> '目标订单数')::integer,
                       COALESCE(q.created_at, NOW()),
                       NOW()
                FROM core.data_quarantine q
                WHERE q.source_file = :source_file
                  AND q.error_type = :error_type
                ON CONFLICT (platform_code, "店铺ID", "年月") DO NOTHING
                """
                ),
                {
                    "source_file": _ORPHAN_SOURCE_FILE,
                    "error_type": _ORPHAN_ERROR_TYPE,
                },
            )
            .rowcount
        )
        print(
            "[20261215] 从隔离区放回被跳过的行：{rows}".format(rows=int(restored or 0))
        )

        # [*] 2026-11-09 幂等性修复：行已经回到它该在的表里了，隔离区的副本
        # 必须删掉 —— 否则「降级 → 再升级」会把同一批行写两遍，
        # 隔离区从 9 行涨到 18 行（生产演练实测）。
        cleared = (
            op.get_bind()
            .execute(
                sa.text(
                    """
                DELETE FROM core.data_quarantine
                 WHERE source_file = :source_file
                   AND error_type = :error_type
                """
                ),
                {
                    "source_file": _ORPHAN_SOURCE_FILE,
                    "error_type": _ORPHAN_ERROR_TYPE,
                },
            )
            .rowcount
        )
        print(
            "[20261215] 清理隔离区中已放回的副本：{rows}".format(rows=int(cleared or 0))
        )


def upgrade() -> None:
    if not _table_exists("sales_targets_a"):
        # 已经下线过：只保证视图是新口径（幂等）。
        _rebuild_views()
        return

    source_rows = int(_scalar("SELECT COUNT(*) FROM a_class.sales_targets_a"))
    print("[20261215] a_class.sales_targets_a 源行数：{rows}".format(rows=source_rows))

    # 店铺不在维度表里的源行：外键不允许落库 ⇒ 只能跳过，但必须显形。
    orphans = _orphan_source_rows()
    migratable_rows = source_rows - len(orphans)
    if orphans:
        # 只允许跳过「本来就不可见」的行（有业务数据 ⇒ 数据缺口 ⇒ 中止）。
        _verify_orphans_are_invisible(orphans)
        quarantined = _quarantine_orphan_rows(orphans)
        print(
            "[20261215] [WARN] {n} 行引用的店铺未登记在 {dim}，无法落库"
            "（外键 fk_breakdown_shop），已写入隔离区 core.data_quarantine"
            "（error_type={err}）".format(
                n=len(orphans),
                dim=_SHOP_DIMENSION,
                err=_ORPHAN_ERROR_TYPE,
            )
        )
        for shop in sorted({row["shop_id"] for row in orphans}):
            amount = sum(
                float(row["target_amount"] or 0)
                for row in orphans
                if row["shop_id"] == shop
            )
            print(
                "[20261215] [WARN]   店铺 {shop}：{rows} 行 / 目标金额合计 {amt}".format(
                    shop=shop,
                    rows=sum(1 for row in orphans if row["shop_id"] == shop),
                    amt=amount,
                )
            )
        print(
            "[20261215] 可落库源行数：{rows}（隔离 {q} 行）".format(
                rows=migratable_rows, q=quarantined
            )
        )

    normalized = _normalize_shop_breakdown_periods()
    print(
        "[20261215] 规范化「店铺月度档位」period_label 行数：{rows}".format(
            rows=normalized
        )
    )

    stats = _migrate_facts()
    print(
        "[20261215] 事实迁移：新增 {ins} 行 / 更新 {upd} 行".format(
            ins=stats["inserted"], upd=stats["updated"]
        )
    )

    # fail-closed：校验不过就中止，表不会被删。
    _verify_fact_coverage()
    _verify_view_keys(migratable_rows)
    _verify_monthly_totals()

    # 视图先切到新口径（不再依赖待删表），再删表。
    _rebuild_views()
    _drop_legacy_table()
    print("[20261215] a_class.sales_targets_a 已删除")


def downgrade() -> None:
    _restore_legacy_table()
    _exec_sql_text(_OLD_COMPARISON_VIEW_SQL)
    _exec_sql_text(_OLD_OPERATIONAL_METRICS_VIEW_SQL)
    print("[20261215] a_class.sales_targets_a 已重建并回填，两个 API 视图已恢复旧口径")
