"""把「核心字段清单」落到版本级, 并把解析规则上移到版本级(批次 E)。

背景
----
批次 E 之前,「哪些字段是核心字段」散在三个地方:

1. ``core.field_mapping_template_versions.deduplication_fields``
   —— 一串字符串, 既当「要哪些数据」又当「哪些参与去重」;
2. ``header_bindings[].hash_participates``
   —— 从 ``deduplication_fields`` **派生**的投影(不是独立开关);
   —— [*] 批次 E(D2): **本次下线**, 存量数据里的这个键一并清掉;
3. ``core.semantic_field_contracts.importance``
   —— 域级「缺失算不算阻断」。

三份口径对不上 ⇒ 用户在前端勾的与后端算的不是一回事。

本次改动
--------
1. ``core.field_mapping_template_versions`` 新增两列:

   * ``core_fields JSONB`` —— 核心字段清单(版本级), 结构::

         [{"semantic_key": str|null, "raw_name": str|null,
           "required": bool, "in_hash": bool}, ...]

     一份清单同时决定: 落库建列 / data_hash 指纹 / 「缺失算不算阻断」。

   * ``field_parse_rules JSONB`` —— 解析规则上移到版本级(E-8),
     审一次全变体生效。变体上的同名列保留为「变体级覆盖」(NULL 时继承版本级)。

2. 回填 ``core_fields``: 从 ``deduplication_fields`` + ``header_bindings`` 推导。

推导规则(与 ``backend/services/core_fields_service.py`` **逐条一致**)
------------------------------------------------------------------
对 ``deduplication_fields`` 里的每个条目 ``F``:

* **规范语义键**: 若 ``F`` 在规范键表里 ⇒ ``semantic_key = F``、``raw_name = NULL``;
  否则在同版本的 ``header_bindings`` 里找 ``source_header``/``raw_name`` 等于 ``F``
  且 ``semantic_key`` 非空、``semantic_review_status`` 不是 ``confirmed_non_semantic``、
  ``semantic_review_source`` 不是 ``inferred`` 的绑定 ⇒ ``semantic_key = 该键``、
  ``raw_name = F``; 都没有 ⇒ ``semantic_key = NULL``、``raw_name = F``。
* **required**: ``semantic_key`` 命中域级契约 ``importance='required'`` 时为真。
* **in_hash**: 一律为真(现有 ``deduplication_fields`` 就是 hash 字段表)。

为什么 ``semantic_key`` 与 ``raw_name`` 要并存
---------------------------------------------
hash 身份 = **``raw_name`` 优先, 没有才用 ``semantic_key``**。

这条规则与改动前的 ``deduplication_fields`` **逐字等价** ⇒
切换到 ``core_fields`` 不会改任何一行的 ``data_hash``
(证据见 ``scripts/replay_core_fields_hash.py`` 的离线回放报告:
28 个版本静态比对全部一致, 真实文件回放 hash 变化 0 行)。

如果只保留 ``semantic_key``, 物理列名的条目会被强行塞进语义解析,
解析不到就被丢掉 ⇒ hash 变了 ⇒ 历史行全部变成「没见过的数据」。

为什么迁移里要内嵌规范键表
--------------------------
迁移必须**自包含**(不能 import backend), 所以规范键表在这里内嵌一份。
它与 ``backend.services.semantic_field_registry`` 的漂移由守护测试
``backend/tests/data_pipeline/test_core_fields_guardrails.py`` 锁住。

幂等
----
``ADD COLUMN IF NOT EXISTS`` + 回填用 ``WHERE core_fields IS NULL`` ⇒ 可重复执行。
downgrade: 清空回填值并删除两列。
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "current_schema_20261125_template_versions_core_fields"
down_revision = "current_schema_20261124_semantic_field_alias_conflict_status"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_VERSIONS = f"{_SCHEMA}.field_mapping_template_versions"
_LEGACY = f"{_SCHEMA}.field_mapping_templates"
_FAMILIES = f"{_SCHEMA}.field_mapping_template_families"
_VARIANTS = f"{_SCHEMA}.field_mapping_template_variants"
_CONTRACTS = f"{_SCHEMA}.semantic_field_contracts"

#: 规范语义键表(批次 E 当时的快照)。
#:
#: 迁移必须自包含 ⇒ 这里内嵌一份; 与注册表的漂移由守护测试锁住。
_CANONICAL_SEMANTIC_KEYS = (
    "bounce_rate",
    "click_rate",
    "clicks",
    "conversion_rate",
    "gmv",
    "gmv_band",
    "impressions",
    "item_status",
    "line_id",
    "live_attributed_gmv",
    "live_gmv",
    "live_indirect_gmv",
    "metric_date",
    "order_count",
    "order_date",
    "order_id",
    "page_views",
    "paid_amount",
    "period_end_date",
    "period_end_time",
    "period_start_date",
    "period_start_time",
    "platform_commission",
    "platform_sku",
    "product_id",
    "product_name",
    "product_visitor_count",
    "profit",
    "purchase_amount",
    "sales_amount",
    "sales_volume",
    "service_id",
    "shop_id",
    "sku_id",
    "sku_order_count",
    "total_transaction_amount",
    "video_attributed_gmv",
    "video_gmv",
    "video_indirect_gmv",
    "visitor_count",
    "warehouse_name",
)


def _canonical_keys_sql() -> str:
    values = ", ".join(f"'{key}'" for key in _CANONICAL_SEMANTIC_KEYS)
    return f"SELECT unnest(ARRAY[{values}]::text[])"


def _derive_core_fields_sql() -> str:
    """按版本推导 ``core_fields`` 的 SQL。

    刻意写成**纯 SQL**(不 import backend), 与
    ``backend/services/core_fields_service.py::derive_core_fields`` 逐条对应。
    """
    return f"""
    WITH canonical AS ({_canonical_keys_sql()}),
    version_rows AS (
        SELECT v.id AS version_id,
               f.data_domain,
               f.granularity,
               COALESCE(v.deduplication_fields, '[]'::jsonb) AS dedup_fields,
               COALESCE(v.header_bindings, '[]'::jsonb) AS bindings
        FROM {_VERSIONS} v
        JOIN {_FAMILIES} f ON f.id = v.family_id
    ),
    exploded AS (
        SELECT vr.version_id,
               vr.data_domain,
               vr.granularity,
               vr.bindings,
               entry.ord,
               btrim(entry.value #>> '{{}}') AS raw_field
        FROM version_rows vr
        CROSS JOIN LATERAL jsonb_array_elements(vr.dedup_fields)
            WITH ORDINALITY AS entry(value, ord)
    ),
    resolved AS (
        SELECT e.version_id,
               e.data_domain,
               e.granularity,
               e.ord,
               e.raw_field,
               CASE
                   WHEN e.raw_field = '' THEN NULL
                   WHEN e.raw_field IN (SELECT * FROM canonical) THEN e.raw_field
                   ELSE (
                       SELECT b ->> 'semantic_key'
                       FROM jsonb_array_elements(e.bindings) AS b
                       WHERE COALESCE(b ->> 'source_header', b ->> 'raw_name', '') = e.raw_field
                         AND b ->> 'semantic_key' IS NOT NULL
                         AND COALESCE(b ->> 'semantic_review_status', '') NOT IN ('confirmed_non_semantic')
                         AND COALESCE(b ->> 'semantic_review_source', '') <> 'inferred'
                       LIMIT 1
                   )
               END AS semantic_key
        FROM exploded e
    ),
    required_keys AS (
        SELECT DISTINCT data_domain, granularity, semantic_key
        FROM {_CONTRACTS}
        WHERE importance = 'required'
    )
    SELECT r.version_id,
           jsonb_agg(
               jsonb_build_object(
                   'semantic_key', r.semantic_key,
                   'raw_name',
                       CASE
                           WHEN r.semantic_key IS NULL THEN r.raw_field
                           WHEN r.raw_field = r.semantic_key THEN NULL
                           ELSE r.raw_field
                       END,
                   'required',
                       CASE
                           WHEN r.semantic_key IS NULL THEN false
                           WHEN EXISTS (
                               SELECT 1 FROM required_keys rk
                               WHERE rk.semantic_key = r.semantic_key
                                 AND rk.data_domain = r.data_domain
                                 AND (rk.granularity = r.granularity
                                      OR COALESCE(rk.granularity, '') = '')
                           ) THEN true
                           ELSE false
                       END,
                   'in_hash', true
               )
               ORDER BY r.ord
           ) AS core_fields
    FROM resolved r
    WHERE r.raw_field <> ''
    GROUP BY r.version_id
    """


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {
        "core_fields_backfilled": 0,
        "parse_rules_backfilled": 0,
        "hash_participates_cleaned": 0,
    }

    bind.execute(
        sa.text(f"ALTER TABLE {_VERSIONS} ADD COLUMN IF NOT EXISTS core_fields JSONB")
    )
    bind.execute(
        sa.text(
            f"ALTER TABLE {_VERSIONS} ADD COLUMN IF NOT EXISTS field_parse_rules JSONB"
        )
    )

    # ── legacy 编辑面也加一列 core_fields(与版本级同构) ─────────────────
    # 权威副本在版本级; legacy 行是**编辑面**(用户在工作台勾选后先落这里,
    # 投影时写进版本)。**不回填** —— 没存就是「用户还没勾过」,
    # 读侧会退回版本级清单。
    bind.execute(
        sa.text(f"ALTER TABLE {_LEGACY} ADD COLUMN IF NOT EXISTS core_fields JSONB")
    )

    # ── 清理存量绑定上的 ``hash_participates``(D2 下线) ──────────────────
    # 该键是 ``deduplication_fields`` 的派生投影(声明了但没接线),
    # 现在「参与去重」由 ``core_fields[].in_hash`` 表达 ⇒ 绑定上不再重复声明。
    #
    # 用 ``jsonb - 'key'`` 逐个元素删键; 数组里混有非对象元素时原样保留。
    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_VERSIONS}
            SET header_bindings = (
                    SELECT COALESCE(
                        jsonb_agg(
                            CASE
                                WHEN jsonb_typeof(item) = 'object'
                                    THEN item - 'hash_participates'
                                ELSE item
                            END
                            ORDER BY ordinality
                        ),
                        '[]'::jsonb
                    )
                FROM jsonb_array_elements(header_bindings)
                     WITH ORDINALITY AS items(item, ordinality)
                ),
                updated_at = now()
            WHERE header_bindings IS NOT NULL
              AND header_bindings::text LIKE '%hash_participates%'
            """
        )
    )
    stats["hash_participates_cleaned"] = int(result.rowcount or 0)

    # ── 回填 core_fields ────────────────────────────────────────────────
    derived = bind.execute(sa.text(_derive_core_fields_sql())).mappings().all()
    for row in derived:
        core_fields = row["core_fields"]
        if not core_fields:
            continue
        result = bind.execute(
            sa.text(
                f"""
                UPDATE {_VERSIONS}
                SET core_fields = CAST(:core_fields AS jsonb),
                    updated_at = now()
                WHERE id = :version_id
                  AND core_fields IS NULL
                """
            ),
            {
                "core_fields": json.dumps(core_fields, ensure_ascii=False),
                "version_id": int(row["version_id"]),
            },
        )
        stats["core_fields_backfilled"] += int(result.rowcount or 0)

    # 没有 deduplication_fields 的版本也写一份空清单(语义统一)
    bind.execute(
        sa.text(
            f"""
            UPDATE {_VERSIONS}
            SET core_fields = '[]'::jsonb
            WHERE core_fields IS NULL
            """
        )
    )

    # ── 回填版本级解析规则(取该版本第一个有规则的变体) ──────────────────
    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_VERSIONS} v
            SET field_parse_rules = src.field_parse_rules,
                updated_at = now()
            FROM (
                SELECT DISTINCT ON (template_version_id)
                       template_version_id, field_parse_rules
                FROM {_VARIANTS}
                WHERE field_parse_rules IS NOT NULL
                ORDER BY template_version_id, id
            ) AS src
            WHERE src.template_version_id = v.id
              AND v.field_parse_rules IS NULL
            """
        )
    )
    stats["parse_rules_backfilled"] = int(result.rowcount or 0)

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑(守护测试直接调它)。"""
    stats = {"core_fields_cleared": 0}
    bind.execute(
        sa.text(
            f"""
            UPDATE {_VERSIONS}
            SET core_fields = NULL,
                field_parse_rules = NULL
            WHERE core_fields IS NOT NULL
               OR field_parse_rules IS NOT NULL
            """
        )
    )
    bind.execute(sa.text(f"ALTER TABLE {_VERSIONS} DROP COLUMN IF EXISTS core_fields"))
    bind.execute(
        sa.text(f"ALTER TABLE {_VERSIONS} DROP COLUMN IF EXISTS field_parse_rules")
    )
    bind.execute(sa.text(f"ALTER TABLE {_LEGACY} DROP COLUMN IF EXISTS core_fields"))
    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
