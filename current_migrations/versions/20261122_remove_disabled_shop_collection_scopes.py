"""清理「已停用店铺」残留在采集配置里的 scope(配置实例 + 模板)。

背景
----
店铺被停用只改了 ``core.shop_accounts.enabled``, 而采集配置里引用它的
``core.collection_config_shop_scopes`` / ``core.collection_config_templates.
default_shop_scopes`` 是**独立的一份引用** ⇒ 停用后没人回头清理 ⇒

* 采集工作区里留下一行「点不动、也不说为什么」的幽灵店铺;
* 配置摘要 ``account_ids`` 一直带着这个死账号(顶部「店铺总览 19」与
  「身份/数据 18」对不上就是这么来的);
* 模板里也留着它 ⇒ ``_merge_template_scopes`` 会把它并进**新建**的配置,
  而保存时 ``_normalize_scope_rows_for_storage`` 的 ``extra_shop_ids`` 校验
  会直接 400 ⇒ **按该模板新建配置会失败**。

实测(开发库)
------------
``shopee_sg_eternalbloom_local`` 于 2026-11-05 13:23 被
``manual:fix_shop_identity_alignment`` 停用, 而它的 scope 建于同日 11:55
—— 差 1.5 小时, 没人清理 ⇒ 残留在:

* ``core.collection_config_shop_scopes``: config 31(monthly) / 39(daily)
* ``core.collection_config_templates``: template 16(daily) / 17(monthly)

为什么是「置 enabled=false」而不是物理删除
------------------------------------------
物理删除**不可逆** —— 删掉之后无法回答"这个店当初配了哪些数据域"。
置为不参与则:

* 采集不再调度它(执行侧 ``collection_config_execution`` 只取 enabled 的 scope);
* 摘要重算时自然被排除(``summarize_shop_scopes`` 只算 enabled 的);
* 展示层按「账号已停用」过滤 ⇒ 它不会出现在采集工作区;
* **可回滚** —— 店铺重新启用后, 把 enabled 改回 true 即可。

(用户下次保存该配置时, 前端提交的 scope 不含停用店 ⇒ 残影会被自然删除。)

摘要重算口径
------------
必须与 ``backend/services/collection_contracts.py::summarize_shop_scopes``
**逐字等价** —— 否则「迁移算出来的摘要」与「运行时保存算出来的摘要」会不一致。

⚠️ 为什么不直接 import 那个函数: 迁移应当是**冻结的快照**, 不能随业务代码漂移。
⇒ 这里内联一份**逐行同构**的实现, 并由守护测试
``backend/tests/data_pipeline/test_disabled_shop_collection_scope_migration.py``
断言两者在多组输入下**结果完全一致** —— 一旦业务侧口径变了, 测试立刻红。

内联实现依赖的唯一外部常量是 ``DATA_DOMAIN_SUB_TYPES``(数据域的子类型白名单),
这里以**快照**形式内嵌。守护测试会断言快照与业务侧当前值一致 ——
业务侧改了白名单而没同步这里, 测试立刻红(而不是等到下次迁移才出事)。
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261122_remove_disabled_shop_collection_scopes"
down_revision = "current_schema_20261121_selling_price_source_enum"
branch_labels = None
depends_on = None


_SCOPE_TABLE = "collection_config_shop_scopes"
_CONFIG_TABLE = "collection_configs"
_TEMPLATE_TABLE = "collection_config_templates"
_SCHEMA = "core"

#: ``backend.services.component_name_utils.DATA_DOMAIN_SUB_TYPES`` 的**快照**。
#:
#: ⚠️ 迁移不 import 业务模块(迁移应是冻结的快照), 但摘要口径又必须与
#: ``summarize_shop_scopes`` 一致 ⇒ 白名单也得内嵌一份。
#: 守护测试 ``test_inline_subtype_whitelist_matches_business`` 断言两者一致 ——
#: 业务侧改了白名单而这里没同步, 测试立刻红。
_DATA_DOMAIN_SUB_TYPES = {
    "orders": ["shopee", "tiktok"],
    "services": ["agent", "ai_assistant"],
}

#: 被停用的店铺在采集配置里的引用 —— 两处都要清
_DISABLE_SCOPE_SQL = """
UPDATE {schema}.{scope_table} AS s
SET enabled = FALSE,
    updated_at = now()
FROM {schema}.shop_accounts AS a
WHERE a.shop_account_id = s.shop_account_id
  AND a.enabled IS FALSE
  AND s.enabled IS TRUE
"""

#: 读取某个配置下**参与**的 scope(顺序与 Python 侧一致: 按 shop_account_id 排序)
_LOAD_ACTIVE_SCOPES_SQL = """
SELECT shop_account_id, data_domains, sub_domains, enabled
FROM {schema}.{scope_table}
WHERE config_id = :config_id AND enabled IS TRUE
ORDER BY shop_account_id
"""

#: 写回配置摘要
_WRITE_SUMMARY_SQL = """
UPDATE {schema}.{config_table}
SET account_ids = CAST(:account_ids AS json),
    data_domains = CAST(:data_domains AS json),
    sub_domains = CAST(:sub_domains AS json),
    updated_at = now()
WHERE id = :config_id
"""

#: 模板的 default_shop_scopes(JSONB 数组) —— 把停用店那一项置为 enabled=false
#:
#: ⚠️ ``elem->>'shop_account_id'`` 只能作用在 **object** 上 ⇒ 用
#: ``jsonb_typeof(elem) = 'object'`` 守卫: 万一数组里混进了非对象元素,
#: 跳过它即可, 不该让整条迁移崩掉(崩掉 = 整个部署被卡住)。
_DISABLE_TEMPLATE_SQL = """
UPDATE {schema}.{template_table} AS t
SET default_shop_scopes = (
        SELECT COALESCE(jsonb_agg(
            CASE
                WHEN jsonb_typeof(elem) = 'object'
                 AND elem->>'shop_account_id' IN (
                    SELECT shop_account_id
                    FROM {schema}.shop_accounts
                    WHERE enabled IS FALSE
                ) THEN jsonb_set(elem, '{{enabled}}', 'false'::jsonb, true)
                ELSE elem
            END
        ), '[]'::jsonb)
        FROM jsonb_array_elements(COALESCE(t.default_shop_scopes, '[]'::jsonb)) AS elem
    ),
    updated_at = now()
WHERE EXISTS (
    SELECT 1
    FROM jsonb_array_elements(COALESCE(t.default_shop_scopes, '[]'::jsonb)) AS elem
    WHERE jsonb_typeof(elem) = 'object'
      AND elem->>'shop_account_id' IN (
        SELECT shop_account_id
        FROM {schema}.shop_accounts
        WHERE enabled IS FALSE
    )
)
"""


#: 找出「有 scope 指向已停用店铺」的配置 —— 必须**先查后改**
#: (改完就分不出谁受影响了)
_AFFECTED_CONFIG_IDS_SQL = """
SELECT DISTINCT s.config_id
FROM {schema}.{scope_table} AS s
JOIN {schema}.shop_accounts AS a
  ON a.shop_account_id = s.shop_account_id
WHERE a.enabled IS FALSE AND s.enabled IS TRUE
"""


def _bind():
    return op.get_bind()


def _fmt(sql: str) -> str:
    return sql.format(
        schema=_SCHEMA,
        scope_table=_SCOPE_TABLE,
        config_table=_CONFIG_TABLE,
        template_table=_TEMPLATE_TABLE,
    )


def _as_string_list(raw: object) -> list:
    """与 ``collection_contracts._as_string_list`` 等价。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, Iterable) and not isinstance(raw, (bytes, bytearray, dict)):
        values = list(raw)
    else:
        return []

    normalized = []
    seen = set()
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _normalize_domain_subtypes(*, data_domains: list, sub_domains: object) -> dict:
    """与 ``collection_contracts.normalize_domain_subtypes`` 等价。

    权威版按 ``DATA_DOMAIN_SUB_TYPES`` 白名单过滤 subtype, 并且只处理
    **出现在该 scope 的 data_domains 里**的 domain —— 这两条都必须照抄,
    否则「迁移算出来的摘要」与「运行时保存算出来的摘要」会分叉。
    """
    normalized: dict = {}
    raw_mapping: dict = {}

    if isinstance(sub_domains, dict):
        raw_mapping.update(sub_domains)

    legacy_values = _as_string_list(sub_domains) if not isinstance(sub_domains, dict) else []

    for domain in data_domains or []:
        allowed_subtypes = _DATA_DOMAIN_SUB_TYPES.get(domain, [])
        if not allowed_subtypes:
            continue

        requested = (
            _as_string_list(raw_mapping.get(domain))
            if domain in raw_mapping
            else legacy_values
        )
        filtered = [item for item in requested if item in allowed_subtypes]
        if filtered:
            normalized[domain] = filtered

    return normalized


def summarize_active_scopes(rows) -> dict:
    """汇总 scope —— 与 ``summarize_shop_scopes`` **逐行同构**。

    ``rows`` 必须是 dict 列表, 键与权威版一致:
    ``shop_account_id`` / ``data_domains`` / ``sub_domains`` / ``enabled``。
    同构 ⇒ 等价性可以被守护测试直接断言, 不靠"看起来一样"。
    """
    account_ids: list = []
    data_domains: list = []
    domain_seen = set()
    merged_sub_domains: dict = {}

    for raw_scope in rows or []:
        scope = (
            raw_scope.model_dump(exclude_none=True)
            if hasattr(raw_scope, "model_dump")
            else dict(raw_scope or {})
        )
        if not bool(scope.get("enabled", True)):
            continue

        shop_account_id = str(scope.get("shop_account_id") or "").strip()
        if shop_account_id:
            account_ids.append(shop_account_id)

        normalized_domains = _as_string_list(scope.get("data_domains"))
        normalized_mapping = _normalize_domain_subtypes(
            data_domains=normalized_domains,
            sub_domains=scope.get("sub_domains"),
        )
        for domain in normalized_domains:
            if domain not in domain_seen:
                domain_seen.add(domain)
                data_domains.append(domain)

        for domain, subtypes in normalized_mapping.items():
            merged = merged_sub_domains.setdefault(domain, [])
            for subtype in subtypes:
                if subtype not in merged:
                    merged.append(subtype)

    return {
        "account_ids": account_ids,
        "data_domains": data_domains,
        "sub_domains": merged_sub_domains or None,
    }


def _recalc_config_summary(bind, config_id: int) -> None:
    rows = bind.execute(
        sa.text(_fmt(_LOAD_ACTIVE_SCOPES_SQL)),
        {"config_id": config_id},
    ).all()
    summary = summarize_active_scopes(
        [
            {
                "shop_account_id": str(row[0]),
                "data_domains": row[1],
                "sub_domains": row[2],
                "enabled": bool(row[3]),
            }
            for row in rows
        ]
    )
    bind.execute(
        sa.text(_fmt(_WRITE_SUMMARY_SQL)),
        {
            "account_ids": json.dumps(summary["account_ids"]),
            "data_domains": json.dumps(summary["data_domains"]),
            "sub_domains": (
                json.dumps(summary["sub_domains"])
                if summary["sub_domains"] is not None
                else None
            ),
            "config_id": config_id,
        },
    )


def apply_cleanup(bind) -> dict:
    """真正的清理逻辑 —— ``upgrade()`` 与守护测试**共用同一份**。

    ``bind`` 只需支持 ``.execute(text, params)`` ⇒ alembic 的 Connection、
    SQLAlchemy 的同步 Session 都行(守护测试用 ``AsyncSession.run_sync`` 喂进来)。

    返回 ``{"affected_config_ids": [...], "disabled_scope_count": N}``。
    """
    # ① 先记下受影响的配置 —— 必须**先记后改**, 改完就分不出谁受影响了
    affected_config_ids = sorted(
        {
            int(row[0])
            for row in bind.execute(
                sa.text(_fmt(_AFFECTED_CONFIG_IDS_SQL))
            ).all()
        }
    )

    # ② 配置实例里的 scope 置为不参与
    disabled = bind.execute(sa.text(_fmt(_DISABLE_SCOPE_SQL))).rowcount

    # ③ 受影响的配置重算摘要(account_ids / data_domains / sub_domains)
    for config_id in affected_config_ids:
        _recalc_config_summary(bind, config_id)

    # ④ 模板里的默认 scope 同样去残影
    bind.execute(sa.text(_fmt(_DISABLE_TEMPLATE_SQL)))

    # ⑤ 自检: 不该再有「启用的 scope 指向已停用店铺」
    remaining = bind.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM {schema}.{scope_table} AS s
            JOIN {schema}.shop_accounts AS a
              ON a.shop_account_id = s.shop_account_id
            WHERE a.enabled IS FALSE AND s.enabled IS TRUE
            """.format(schema=_SCHEMA, scope_table=_SCOPE_TABLE)
        )
    ).scalar()
    if remaining:
        raise RuntimeError(
            "仍有 {0} 条启用的 scope 指向已停用店铺，拒绝提交".format(int(remaining))
        )

    return {
        "affected_config_ids": affected_config_ids,
        "disabled_scope_count": int(disabled or 0),
    }


def apply_restore(bind) -> dict:
    """回滚逻辑 —— 见 :func:`downgrade` 的说明。"""
    restored = bind.execute(
        sa.text(
            """
            UPDATE {schema}.{scope_table} AS s
            SET enabled = TRUE,
                updated_at = now()
            FROM {schema}.shop_accounts AS a
            WHERE a.shop_account_id = s.shop_account_id
              AND a.enabled IS FALSE
              AND s.enabled IS FALSE
              AND s.data_domains IS NOT NULL
            RETURNING s.config_id
            """.format(schema=_SCHEMA, scope_table=_SCOPE_TABLE)
        )
    ).all()

    affected_config_ids = sorted({int(row[0]) for row in restored})
    for config_id in affected_config_ids:
        _recalc_config_summary(bind, config_id)

    return {
        "affected_config_ids": affected_config_ids,
        "restored_count": len(restored),
    }


def upgrade() -> None:
    result = apply_cleanup(_bind())
    print(
        "[OK] 已把 {0} 个配置里指向停用店铺的 scope 置为不参与，并重算摘要".format(
            len(result["affected_config_ids"])
        )
    )


def downgrade() -> None:
    """恢复被置为「不参与」的 scope。

    ⚠️ **只恢复 scope 的 enabled 标记** —— 不恢复店铺本身(它仍然停用)。

    ⚠️ **已知副作用**: 店铺被停用**之前**就已经是 disabled 的 scope 也会被
    一起恢复(表里没有"迁移改过哪些行"的标记位, 没法只还原自己动过的)。
    ⇒ 回滚后采集工作区会重新出现幽灵行 —— 这是**预期**:
    回滚意味着回到「没人清理」的状态。
    """
    result = apply_restore(_bind())
    print(
        "[OK] 已恢复 {0} 条 scope 的参与标记，并重算 {1} 个配置的摘要".format(
            result["restored_count"], len(result["affected_config_ids"])
        )
    )
