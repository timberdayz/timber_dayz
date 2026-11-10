"""源数据（业务事实表）新鲜度巡检。

背景
----
``ops.data_freshness_log`` 记录的是「视图/接口上次刷新有没有成功」，
回答不了「业务数据本身有多旧」。2026-10-19 之后的那次断流正是被这一层掩盖的：
刷新链路连续上百次全绿，商品与服务两条业务链却停在几个月前的数据，
系统一声不响——**我们盯错了层**。

本模块补上源数据这一层：以 ``b_class.fact_*`` 业务事实表为巡检对象，
算出每条链的「最新业务日期 / 最新入库时间 / 落后多少天」，
按粒度给出允许的最大滞后，超过即判定为断流（``stale``）。

判定口径
--------
- ``fresh``          最新业务日期在允许滞后范围内
- ``stale``          最新业务日期超过允许滞后天数 ⇒ 断流，需要人工介入
- ``empty``          源表没有数据（可能本来就没开这条采集，只提示、不算断流）
- ``out_of_scope``   **曾采过、现已不在当前采集范围** ⇒ 单独一档，
  既不算断流（不拉高整体红灯）、也不算正常（台账里看得见）

滞后天数按粒度取默认值（可用环境变量覆盖）：
``daily`` / ``weekly`` 365 天（这两种粒度是**按需采集**，不能因为不天天采就报警）、
``monthly`` 60 天、``snapshot`` 10 天。

个别链有业务例外：``mart.product_day_kpi`` 只取 ``granularity='daily'`` 的行，
也就是说**商品日粒度直接决定商品经营看板的新鲜度**，因此商品日链单独收紧到 30 天。

「当前采集范围」从哪来（批次 3.3）
------------------------------
「这条链现在还在不在采」这件事以前**根本没有定义** ⇒ 红灯一刀切。
现在它有**唯一**口径：**数据库里实际生效的采集配置**
（``core.collection_configs`` + ``core.collection_config_shop_scopes``，
详见 :mod:`backend.services.data_pipeline.source_freshness_scope`）。
代码里的 ``DEFAULT_CONFIG_DATA_DOMAINS`` 只是**可选域全集**，只在数据库读不到时兜底，
且兜底会在结论里显式标注。

**阈值口径不变**：粒度默认 + 链级例外 + 环境变量覆盖，一条都没动。
分档只改**结论落在哪一档**，不改任何阈值数值。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.collection_contracts import get_order_source_provider
from backend.services.data_pipeline.source_freshness_notify import (
    dispatch_source_freshness_alerts,
    load_notified_stale_chains,
)
from backend.services.data_pipeline.source_freshness_scope import (
    SCOPE_STATUS_IN_SCOPE,
    SCOPE_STATUS_OUT_OF_SCOPE,
    SCOPE_STATUS_UNKNOWN,
    SCOPE_SOURCE_FALLBACK,
    CollectionScope,
    load_collection_scope,
)

__all__ = [
    "GRANULARITY_MAX_AGE_DAYS",
    "SOURCE_FRESHNESS_PIPELINE_NAME",
    "SOURCE_FRESHNESS_STATUS_EMPTY",
    "SOURCE_FRESHNESS_STATUS_FRESH",
    "SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE",
    "SOURCE_FRESHNESS_STATUS_STALE",
    "SourceFreshnessReport",
    "SourceFreshnessRow",
    "SourceTableIdentity",
    "classify_source_freshness",
    "collect_source_freshness",
    "max_age_days_for",
    "parse_source_table_name",
    "record_source_freshness_run",
    "resolve_scope_status",
    "run_source_freshness_check",
]

SOURCE_FRESHNESS_PIPELINE_NAME = "source_freshness_check"
SOURCE_FRESHNESS_STEP_NAME = "check_source_freshness"

#: 单条链的新鲜度结论。
SOURCE_FRESHNESS_STATUS_FRESH = "fresh"
SOURCE_FRESHNESS_STATUS_STALE = "stale"
SOURCE_FRESHNESS_STATUS_EMPTY = "empty"
#: 曾采过、现已不在当前采集范围（不拉高红灯，但台账里看得见）。
SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE = "out_of_scope"

#: 订单域的数据可能由**别的平台**的采集器写入（见 ``collection_contracts``）。
_ORDER_DATA_DOMAIN = "orders"

_PLATFORMS = ("shopee", "tiktok", "miaoshou")
_DOMAINS = ("orders", "products", "analytics", "services", "inventory", "traffic")
_GRANULARITIES = ("daily", "weekly", "monthly", "snapshot")

GRANULARITY_MAX_AGE_DAYS: dict[str, int] = {
    # 日/周粒度是「按需采集」：不天天采是正常的，不能因此报警，
    # 否则真正的断流会被噪音淹没。真正断流由月度链 + 商品日链抓住。
    "daily": 365,
    "weekly": 365,
    "monthly": 60,
    "snapshot": 10,
}
DEFAULT_MAX_AGE_DAYS = 60

# 业务例外：链名 → 允许滞后天数。
# 商品日粒度直接喂 ``mart.product_day_kpi``（只取 daily 行），
# 商品经营看板的新鲜度就是它决定的，因此单独收紧。
CHAIN_MAX_AGE_DAYS_OVERRIDES: dict[str, int] = {
    "shopee/products[daily]": 30,
    "tiktok/products[daily]": 30,
}

_SOURCE_TABLE_DISCOVERY_SQL = """
SELECT c.relname
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'b_class'
  AND c.relkind IN ('r', 'p')
  AND c.relname LIKE 'fact\\_%'
ORDER BY c.relname
"""

_SOURCE_COLUMN_READY_SQL = """
SELECT table_name
FROM information_schema.columns
WHERE table_schema = 'b_class'
  AND column_name IN ('metric_date', 'ingest_timestamp')
GROUP BY table_name
HAVING count(DISTINCT column_name) = 2
"""


@dataclass(frozen=True)
class SourceTableIdentity:
    """一条源数据链的身份（平台 / 业务域 / 子域 / 粒度）。"""

    table_name: str
    platform: str | None = None
    domain: str | None = None
    subdomain: str | None = None
    granularity: str | None = None


def _chain_label(identity: SourceTableIdentity) -> str:
    """链名：平台/业务域/子域[粒度]，用于阈值匹配与告警文案。"""
    parts = [
        part
        for part in (identity.platform, identity.domain, identity.subdomain)
        if part
    ]
    label = "/".join(parts) if parts else identity.table_name
    if identity.granularity:
        label = f"{label}[{identity.granularity}]"
    return label


@dataclass
class SourceFreshnessRow:
    """单条源数据链的新鲜度画像。"""

    table_name: str
    platform: str | None
    domain: str | None
    subdomain: str | None
    granularity: str | None
    row_count: int
    max_metric_date: date | None
    max_ingest_timestamp: datetime | None
    business_age_days: int | None
    ingest_age_days: int | None
    max_age_days: int
    status: str
    scope_status: str = SCOPE_STATUS_UNKNOWN

    @property
    def chain_label(self) -> str:
        return _chain_label(
            SourceTableIdentity(
                table_name=self.table_name,
                platform=self.platform,
                domain=self.domain,
                subdomain=self.subdomain,
                granularity=self.granularity,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "chain": self.chain_label,
            "platform": self.platform,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "granularity": self.granularity,
            "row_count": self.row_count,
            "max_metric_date": (
                self.max_metric_date.isoformat() if self.max_metric_date else None
            ),
            "max_ingest_timestamp": (
                self.max_ingest_timestamp.isoformat()
                if self.max_ingest_timestamp
                else None
            ),
            "business_age_days": self.business_age_days,
            "ingest_age_days": self.ingest_age_days,
            "max_age_days": self.max_age_days,
            "status": self.status,
            "scope_status": self.scope_status,
        }


@dataclass
class SourceFreshnessReport:
    """一次巡检的完整结论。"""

    run_id: str
    started_at: datetime
    finished_at: datetime
    rows: list[SourceFreshnessRow] = field(default_factory=list)
    scope_source: str = SCOPE_SOURCE_FALLBACK
    scope_detail: str = ""
    notified_stale_chains: list[str] = field(default_factory=list)

    @property
    def fresh_rows(self) -> list[SourceFreshnessRow]:
        return [row for row in self.rows if row.status == SOURCE_FRESHNESS_STATUS_FRESH]

    @property
    def stale_rows(self) -> list[SourceFreshnessRow]:
        return [row for row in self.rows if row.status == SOURCE_FRESHNESS_STATUS_STALE]

    @property
    def empty_rows(self) -> list[SourceFreshnessRow]:
        return [row for row in self.rows if row.status == SOURCE_FRESHNESS_STATUS_EMPTY]

    @property
    def out_of_scope_rows(self) -> list[SourceFreshnessRow]:
        """曾采过、现已不在当前采集范围的链（**不**拉高整体红灯）。"""
        return [
            row
            for row in self.rows
            if row.status == SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE
        ]

    @property
    def is_success(self) -> bool:
        """没有任何一条链断流 ⇒ 巡检通过。

        「已停采的链」**不算**断流：它单独成档，不把整体红灯拉起来。
        """
        return not self.stale_rows

    def to_error_message(self) -> str | None:
        if not self.stale_rows:
            return None
        detail = ",".join(
            f"{row.chain_label}({row.business_age_days}d>{row.max_age_days}d)"
            for row in self.stale_rows
        )
        return f"stale_source_chains:{detail}"

    def to_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_chains": len(self.rows),
            "fresh_chains": len(self.fresh_rows),
            "stale_chains": len(self.stale_rows),
            "empty_chains": len(self.empty_rows),
            # 「曾采过、现已停采」的链单独一档：不算断流、也不算正常。
            "out_of_scope_chains": len(self.out_of_scope_rows),
            "stale_chain_labels": [row.chain_label for row in self.stale_rows],
            "out_of_scope_chain_labels": [
                row.chain_label for row in self.out_of_scope_rows
            ],
            # 采集范围来源：database = 读到数据库；fallback_default_domains = 兜底。
            "scope_source": self.scope_source,
            "scope_detail": self.scope_detail,
            "notified_stale_chains": list(self.notified_stale_chains),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


def parse_source_table_name(table_name: str) -> SourceTableIdentity:
    """从表名解析出平台 / 业务域 / 子域 / 粒度。

    规则：``fact_<platform>_<domain>[_<subdomain...>]_<granularity>``。
    平台与业务域都从已知词表里认；认不出来的部分归入子域，
    保证「一条链到底多久没更新」不会因为命名不规范而丢失。
    """
    bare = table_name.split(".")[-1]
    if not bare.startswith("fact_"):
        return SourceTableIdentity(table_name=table_name)

    rest = bare[len("fact_") :]
    granularity: str | None = None
    for candidate in _GRANULARITIES:
        suffix = f"_{candidate}"
        if rest.endswith(suffix):
            granularity = candidate
            rest = rest[: -len(suffix)]
            break

    tokens = [token for token in rest.split("_") if token]
    platform: str | None = None
    if tokens and tokens[0] in _PLATFORMS:
        platform = tokens[0]
        tokens = tokens[1:]

    domain: str | None = None
    subdomain: str | None = None
    domain_index = next(
        (index for index, token in enumerate(tokens) if token in _DOMAINS),
        None,
    )
    if domain_index is not None:
        domain = tokens[domain_index]
        trailing = tokens[domain_index + 1 :]
        subdomain = "_".join(trailing) if trailing else None

    return SourceTableIdentity(
        table_name=table_name,
        platform=platform,
        domain=domain,
        subdomain=subdomain,
        granularity=granularity,
    )


def _chain_overrides() -> dict[str, int]:
    """环境变量覆盖的链级阈值（JSON 字典）。"""
    raw = os.getenv("SOURCE_FRESHNESS_MAX_AGE_CHAINS")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    overrides: dict[str, int] = {}
    for key, value in parsed.items():
        try:
            overrides[str(key)] = max(1, int(value))
        except (TypeError, ValueError):
            continue
    return overrides


def max_age_days_for(granularity: str | None, chain_label: str | None = None) -> int:
    """该链允许的最大滞后天数。

    优先级：链级环境变量 > 链级内置例外 > 粒度环境变量 > 粒度默认值。
    """
    overrides = _chain_overrides()
    if chain_label:
        if chain_label in overrides:
            return overrides[chain_label]
        if chain_label in CHAIN_MAX_AGE_DAYS_OVERRIDES:
            return CHAIN_MAX_AGE_DAYS_OVERRIDES[chain_label]
    key = f"SOURCE_FRESHNESS_MAX_AGE_{(granularity or 'default').upper()}"
    raw = os.getenv(key)
    if raw:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    if granularity and granularity in GRANULARITY_MAX_AGE_DAYS:
        return GRANULARITY_MAX_AGE_DAYS[granularity]
    return DEFAULT_MAX_AGE_DAYS


def resolve_scope_status(scope: CollectionScope, identity: SourceTableIdentity) -> str:
    """这条链与「当前采集范围」是什么关系。

    返回 ``in_scope`` / ``out_of_scope`` / ``unknown``。

    ⚠️ **判不了就落 unknown**（仓库原则：歧义宁可落 ``unknown`` 报警，也不猜一个）：

    - 平台或业务域解析不出来 ⇒ ``unknown``；
    - 该平台**没有任何生效采集配置** ⇒ ``unknown``
      （空环境 / 还没配置，不等于「停采」）；
    - 该平台有生效配置，但这条链的域不在里面 ⇒ ``out_of_scope``
      （曾采过、现已停采）。

    订单域有个例外：``shopee`` / ``tiktok`` 的订单数据实际由 ``miaoshou`` 采集器写入
    （见 ``backend/services/collection_contracts.py`` 的 ``ORDER_SOURCE_PROVIDER_BY_PLATFORM``）
    ⇒ 订单域要按**真正采集它的那个平台**的范围来判，否则会把还在正常更新的
    订单链误判成「已停采」。
    """
    if not identity.platform or not identity.domain:
        return SCOPE_STATUS_UNKNOWN

    domain = identity.domain
    if domain in scope.domains_for(identity.platform):
        return SCOPE_STATUS_IN_SCOPE

    if domain == _ORDER_DATA_DOMAIN:
        provider = get_order_source_provider(identity.platform)
        if provider and domain in scope.domains_for(provider):
            return SCOPE_STATUS_IN_SCOPE

    if scope.has_platform(identity.platform):
        return SCOPE_STATUS_OUT_OF_SCOPE
    return SCOPE_STATUS_UNKNOWN


def classify_source_freshness(
    *,
    row_count: int,
    max_metric_date: date | None,
    now_date: date,
    max_age_days: int,
    scope_status: str = SCOPE_STATUS_UNKNOWN,
) -> tuple[str, int | None]:
    """返回 ``(状态, 业务滞后天数)``。

    ``scope_status`` 只影响**结论落在哪一档**，**不改任何阈值数值**：

    - ``out_of_scope``（曾采过、现已停采）⇒ 单独一档，
      既不是 ``stale``（不拉高红灯）、也不是 ``fresh``（不算正常）；
    - 其它取值（含默认 ``unknown``）⇒ 行为与改造前**完全一致**。
    """
    if row_count <= 0:
        # 「从未被采过的链」一直是 empty ⇒ skipped，不进 partial_failed。
        return SOURCE_FRESHNESS_STATUS_EMPTY, None
    if max_metric_date is None:
        if scope_status == SCOPE_STATUS_OUT_OF_SCOPE:
            return SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE, None
        return SOURCE_FRESHNESS_STATUS_STALE, None
    business_age_days = (now_date - max_metric_date).days
    if scope_status == SCOPE_STATUS_OUT_OF_SCOPE:
        return SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE, business_age_days
    if business_age_days > max_age_days:
        return SOURCE_FRESHNESS_STATUS_STALE, business_age_days
    return SOURCE_FRESHNESS_STATUS_FRESH, business_age_days


def _build_aggregate_sql(table_names: list[str]) -> str:
    statements = []
    for name in table_names:
        statements.append(
            "SELECT '{table}'::text AS table_name, count(*)::bigint AS row_count, "
            "max(metric_date) AS max_metric_date, "
            "max(ingest_timestamp) AS max_ingest_timestamp "
            'FROM b_class."{table}"'.format(table=name)
        )
    return "\nUNION ALL\n".join(statements)


def _parse_date(value: Any) -> date | None:
    """解析日期 —— [*] 批次 C-4: 委派给唯一实现。

    这里取的是**数据库里的 metric_date**(本来就是 ISO), 没有日/月歧义,
    所以走 :func:`modules.services.smart_date_parser.parse_iso_date`。
    """
    from modules.services.smart_date_parser import parse_iso_date

    return parse_iso_date(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text_value = str(value).strip()
    if not text_value:
        return None
    normalized = text_value.replace(" ", "T", 1)
    # PostgreSQL 的 timestamptz 文本形如 "+00"/"-05"，补成 ISO 的 "+00:00"。
    if len(normalized) >= 3 and normalized[-3] in "+-" and normalized[-2:].isdigit():
        normalized = normalized[:-2] + normalized[-2:] + ":00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def collect_source_freshness(
    db: AsyncSession,
    *,
    now: datetime | None = None,
    scope: CollectionScope | None = None,
) -> SourceFreshnessReport:
    """巡检所有 ``b_class.fact_*`` 源表，算出每条链的新鲜度。

    ``scope`` 允许调用方注入（测试 / 复用）；不给就从**数据库**读当前采集范围
    （读不到时兜底，并在结论里标注用的是兜底）。
    """
    started_at = now or datetime.now(timezone.utc)
    run_id = f"source_freshness_{uuid.uuid4().hex[:12]}"

    if scope is None:
        scope = await load_collection_scope(db)

    discovered = await db.execute(text(_SOURCE_TABLE_DISCOVERY_SQL))
    ready_result = await db.execute(text(_SOURCE_COLUMN_READY_SQL))
    ready_tables = {row[0] for row in ready_result.fetchall()}

    table_names = [row[0] for row in discovered.fetchall() if row[0] in ready_tables]

    rows: list[SourceFreshnessRow] = []
    if table_names:
        aggregate = await db.execute(text(_build_aggregate_sql(table_names)))
        now_date = started_at.date()
        now_utc = (
            started_at if started_at.tzinfo else started_at.replace(tzinfo=timezone.utc)
        )
        for record in aggregate.fetchall():
            table_name = record[0]
            identity = parse_source_table_name(table_name)
            chain_label = _chain_label(identity)
            row_count = int(record[1] or 0)
            max_metric_date = _parse_date(record[2])
            max_ingest_timestamp = _parse_datetime(record[3])
            limit_days = max_age_days_for(identity.granularity, chain_label)
            scope_status = resolve_scope_status(scope, identity)
            status, business_age_days = classify_source_freshness(
                row_count=row_count,
                max_metric_date=max_metric_date,
                now_date=now_date,
                max_age_days=limit_days,
                scope_status=scope_status,
            )
            ingest_age_days = (
                (now_utc - max_ingest_timestamp).days
                if max_ingest_timestamp is not None
                else None
            )
            rows.append(
                SourceFreshnessRow(
                    table_name=table_name,
                    platform=identity.platform,
                    domain=identity.domain,
                    subdomain=identity.subdomain,
                    granularity=identity.granularity,
                    row_count=row_count,
                    max_metric_date=max_metric_date,
                    max_ingest_timestamp=max_ingest_timestamp,
                    business_age_days=business_age_days,
                    ingest_age_days=ingest_age_days,
                    max_age_days=limit_days,
                    status=status,
                    scope_status=scope_status,
                )
            )

    rows.sort(key=lambda row: row.table_name)
    return SourceFreshnessReport(
        run_id=run_id,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        rows=rows,
        scope_source=scope.source,
        scope_detail=scope.detail,
    )


async def record_source_freshness_run(
    db: AsyncSession,
    report: SourceFreshnessReport,
    *,
    trigger_source: str = "scheduler",
) -> None:
    """把巡检结论写进既有的 ops 监控表（不新增表、不加迁移）。"""
    run_status = "success" if report.is_success else "partial_failed"
    await db.execute(
        text(
            """
            INSERT INTO ops.pipeline_run_log (
                run_id, pipeline_name, status, trigger_source,
                started_at, completed_at, error_message, context
            ) VALUES (
                :run_id, :pipeline_name, :status, :trigger_source,
                :started_at, :completed_at, :error_message, CAST(:context AS jsonb)
            )
            """
        ),
        {
            "run_id": report.run_id,
            "pipeline_name": SOURCE_FRESHNESS_PIPELINE_NAME,
            "status": run_status,
            "trigger_source": trigger_source,
            "started_at": report.started_at,
            "completed_at": report.finished_at,
            "error_message": report.to_error_message(),
            "context": json.dumps(
                {
                    **report.to_summary(),
                    "chains": [row.to_dict() for row in report.rows],
                },
                ensure_ascii=False,
            ),
        },
    )

    for row in report.rows:
        step_status = {
            SOURCE_FRESHNESS_STATUS_FRESH: "success",
            SOURCE_FRESHNESS_STATUS_STALE: "failed",
            SOURCE_FRESHNESS_STATUS_EMPTY: "skipped",
            # 已停采的链：不是失败（不拉高红灯），但也不是成功 ⇒ skipped + 留痕。
            SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE: "skipped",
        }.get(row.status, "success")
        error_message = None
        if row.status == SOURCE_FRESHNESS_STATUS_STALE:
            error_message = (
                f"stale_source_chain: {row.chain_label} 落后 {row.business_age_days} 天"
                f"（上限 {row.max_age_days} 天）"
            )
        elif row.status == SOURCE_FRESHNESS_STATUS_EMPTY:
            error_message = f"empty_source_table: {row.chain_label} 没有任何数据"
        elif row.status == SOURCE_FRESHNESS_STATUS_OUT_OF_SCOPE:
            error_message = (
                f"out_of_scope_source_chain: {row.chain_label} 曾采过、"
                "现已不在当前采集范围（不计入断流）"
            )
        await db.execute(
            text(
                """
                INSERT INTO ops.pipeline_step_log (
                    run_id, step_name, target_name, status,
                    started_at, completed_at, affected_rows, error_message, details
                ) VALUES (
                    :run_id, :step_name, :target_name, :status,
                    :started_at, :completed_at, :affected_rows, :error_message,
                    CAST(:details AS jsonb)
                )
                """
            ),
            {
                "run_id": report.run_id,
                "step_name": SOURCE_FRESHNESS_STEP_NAME,
                "target_name": row.table_name,
                "status": step_status,
                "started_at": report.started_at,
                "completed_at": report.finished_at,
                "affected_rows": row.row_count,
                "error_message": error_message,
                "details": json.dumps(row.to_dict(), ensure_ascii=False),
            },
        )

    await db.commit()


async def run_source_freshness_check(
    db: AsyncSession,
    *,
    trigger_source: str = "scheduler",
) -> SourceFreshnessReport:
    """巡检 + 落库 + **通知出口**，返回结论。

    通知出口（批次 3.3）
    ------------------
    断流**必须有人看见**：以前这里只写台账，没有任何出口 ⇒ 红灯永远没人看。
    现在复用现成通道（站内信 + webhook/钉钉），并且**同一问题连续多轮只通知一次**
    （去重状态写在 ``ops.pipeline_run_log.context.notified_stale_chains``）。

    顺序很关键：
    1. 先巡检；
    2. 再读上一轮「已通知过的链」；
    3. 只对**本轮新出现**的断流发通知；
    4. 最后写运行日志（里面带上本轮的已通知集合，供下一轮去重）。
    """
    report = await collect_source_freshness(db)

    previously_notified = await load_notified_stale_chains(
        db, pipeline_name=SOURCE_FRESHNESS_PIPELINE_NAME
    )
    current_stale = {row.chain_label for row in report.stale_rows}
    new_problems = sorted(
        label for label in current_stale if label not in previously_notified
    )

    dispatched: set[str] = set()
    if new_problems:
        dispatched = await dispatch_source_freshness_alerts(db, report, new_problems)

    # 仍然断流、且此前已通知过的链 ⇒ 继续保持「已通知」状态（不再重复轰炸）；
    # 本轮新通知成功的链 ⇒ 加进来。
    report.notified_stale_chains = sorted(
        (previously_notified & current_stale) | dispatched
    )

    await record_source_freshness_run(db, report, trigger_source=trigger_source)
    return report
