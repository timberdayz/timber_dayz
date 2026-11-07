"""把「探测命中平台错误页 / 登录页」的存量记录改判为「探测失败」。

背景
----
2026-11-07 实测事故：采集器打开的第一个页面是平台的 404 页

    https://seller.shopee.cn/404?cnsc_shop_id=1391124228

这个 URL **照样带着 ``cnsc_shop_id``** —— 而那个编号是**上一家店**的
（持久 profile 把上次会话停着的页面恢复了出来）。旧代码把它当成一次正常探测 ⇒
那个编号恰好被另一个账号占着 ⇒ 记成 ``conflict_detected``
⇒ 业务概览页弹出「采集期探测到 1 次店铺身份异常」。

**页面上压根没有店铺身份信息**，拿 URL 参数做绑定判定 = 制造假冲突。

处置
----
采集侧已改为：命中 404 / 错误页 / 登录页 ⇒ 记 ``status='failed'``
（``modules/apps/collection_center/executor_v2.py`` 的 ``_is_platform_error_page``）。
本迁移把**存量**里同一口径的错误判定改回来。

判据（与 Python 侧 ``_is_platform_error_page`` 逐字一致）
--------------------------------------------------------
URL 去掉 query 之后的 **path 最后一段** 命中以下之一：

    404 / 404.html / 404.htm / 404error / error / error.html / error.htm /
    errorpage / notfound / not-found / not_found / signin / login

或把 ``- _ .`` 去掉后以 ``404`` / ``error`` 开头。

只看**最后一段**是刻意的：``/datacenter/error_report`` 这类正常业务路径
不能被误判成错误页。

只**改判判定**，不删历史
----------------------
* 原状态与原「探测值」写回 ``raw_payload``
  （``reclassified_from_status`` / ``original_detected_platform_shop_id`` /
  ``original_detected_store_name`` / ``original_detected_region`` /
  ``original_candidate_shop_account_ids``）⇒ 可追溯、可回滚；
* ``detected_platform_shop_id`` / ``detected_store_name`` / ``detected_region``
  置 NULL，``candidate_shop_account_ids`` 置 ``[]``
  —— 与 2026-04 那 3 条登录页历史记录同口径（``failed`` 行本来就没有探测值）；
* ``failed`` **不在** ``PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES`` 里
  ⇒ 改判后不再计入「店铺身份异常」告警。

downgrade: 按 ``raw_payload`` 里留的原值改回原状态。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261129_reclassify_error_page_shop_discoveries"
down_revision = "current_schema_20261129_template_variant_kind"
branch_labels = None
depends_on = None


_TABLE = "core.platform_shop_discoveries"

#: 迁移自己的标识 —— 写进 ``raw_payload``，downgrade 据此精确回滚。
_MARKER = "current_schema_20261129_reclassify_error_page_shop_discoveries"

#: path 最后一段（显式清单）—— 与 Python 侧 ``_ERROR_PAGE_PATH_SEGMENTS`` 一致。
_ERROR_SEGMENTS = (
    "404",
    "404.html",
    "404.htm",
    "404error",
    "error",
    "error.html",
    "error.htm",
    "errorpage",
    "notfound",
    "not-found",
    "not_found",
    "signin",
    "login",
)


#: URL 去掉 query 后的 path 最后一段。
def _segment_sql(url_expr: str) -> str:
    """给定「URL 文本表达式」，返回「path 最后一段」的 SQL 表达式。"""
    return (
        "substring(\n"
        f"        split_part(coalesce({url_expr}, ''), '?', 1)\n"
        "        from '([^/]+)$'\n"
        "    )"
    )


#: 去掉 ``- _ .`` 后的归一段（Python 侧 ``last_segment.replace(...)``）。
def _normalized_sql(url_expr: str) -> str:
    """给定「URL 文本表达式」，返回「归一段」的 SQL 表达式。"""
    return (
        "regexp_replace(lower(coalesce("
        f"{_segment_sql(url_expr)}, '')), '[-_.]', '', 'g')"
    )


def _error_page_match_sql(url_expr: str = "d.raw_payload->>'current_url'") -> str:
    """构造「这个 URL 是错误页 / 登录页」的 SQL 表达式。

    默认按迁移 UPDATE 里的别名 ``d`` 取 ``raw_payload->>'current_url'``；
    守护测试会传入别的表达式（如 VALUES 表的 ``t.url``）来逐条比对口径。
    """
    segment = _segment_sql(url_expr)
    normalized = _normalized_sql(url_expr)
    explicit = ", ".join(f"'{value}'" for value in _ERROR_SEGMENTS)
    return (
        "(lower(coalesce({segment}, '')) in ({explicit}) "
        " or {normalized} like '404%' "
        " or {normalized} like 'error%')"
    ).format(segment=segment, explicit=explicit, normalized=normalized)


def apply_upgrade(bind) -> dict:
    """upgrade 的真实逻辑（守护测试直接调它）。"""
    stats = {"reclassified": 0}

    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} d
            SET status = 'failed',
                detected_store_name = NULL,
                detected_platform_shop_id = NULL,
                detected_region = NULL,
                candidate_shop_account_ids = '[]'::jsonb,
                raw_payload = coalesce(d.raw_payload, '{{}}'::jsonb)
                    || jsonb_build_object(
                        'probe_failed', true,
                        'reclassified_from_status', d.status,
                        'original_detected_store_name', d.detected_store_name,
                        'original_detected_platform_shop_id',
                            d.detected_platform_shop_id,
                        'original_detected_region', d.detected_region,
                        'original_candidate_shop_account_ids',
                            d.candidate_shop_account_ids,
                        'reclassified_at',
                            to_char(now() at time zone 'UTC',
                                    'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                        'reclassified_by', '{_MARKER}'
                    ),
                updated_at = now()
            WHERE d.status <> 'failed'
              AND d.raw_payload IS NOT NULL
              AND {_error_page_match_sql()}
            """
        )
    )
    stats["reclassified"] = int(result.rowcount or 0)

    return stats


def apply_downgrade(bind) -> dict:
    """downgrade 的真实逻辑（守护测试直接调它）。"""
    stats = {"restored": 0}

    result = bind.execute(
        sa.text(
            f"""
            UPDATE {_TABLE} d
            SET status = coalesce(
                    d.raw_payload->>'reclassified_from_status', d.status
                ),
                detected_store_name =
                    d.raw_payload->>'original_detected_store_name',
                detected_platform_shop_id =
                    d.raw_payload->>'original_detected_platform_shop_id',
                detected_region =
                    d.raw_payload->>'original_detected_region',
                candidate_shop_account_ids = case
                    when d.raw_payload->'original_candidate_shop_account_ids'
                         is null
                      or d.raw_payload->'original_candidate_shop_account_ids'
                         = 'null'::jsonb
                        then null
                    else d.raw_payload->'original_candidate_shop_account_ids'
                end,
                raw_payload = d.raw_payload - 'probe_failed'
                    - 'reclassified_from_status'
                    - 'original_detected_store_name'
                    - 'original_detected_platform_shop_id'
                    - 'original_detected_region'
                    - 'original_candidate_shop_account_ids'
                    - 'reclassified_at'
                    - 'reclassified_by',
                updated_at = now()
            WHERE d.raw_payload->>'reclassified_by' = '{_MARKER}'
            """
        )
    )
    stats["restored"] = int(result.rowcount or 0)

    return stats


def upgrade() -> None:
    bind = op.get_bind()
    apply_upgrade(bind)


def downgrade() -> None:
    bind = op.get_bind()
    apply_downgrade(bind)
