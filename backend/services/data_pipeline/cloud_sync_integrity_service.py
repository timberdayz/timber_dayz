"""云端同步链路的**完整性**巡检 —— 陈旧 / 收敛率 / 候选池平台覆盖 / 语义层可解析性。

背景
----
2026-11-07 的采集同步丢数事故里, 有三个信号**同时**存在, 而**一个都没人看见**:

1. **云端事实表停在 11-06**, 之后再没有新数据落库 —— 同步链断了或被拦了;
2. **行内身份收敛率恒为 0** —— 入库侧的枚举 bug 让收敛 100% 静默失效,
   不报错、不告警, 账本还记 "completed";
3. **候选池缺平台** —— ``miaoshou`` 的采集源账号(``business_role='collection_source'``)
   不在候选池里, 那条链的身份从一开始就解析不出来。

本模块把这三个信号变成**会自己响的巡检**, 并在 2026-11-10 追加第四项
(**语义层可解析性**, 见下面「四个检查」)。

它盯的是**云端那一侧**(: 哪个连接就巡检哪个)。
采集机侧用**云端 engine** 跑它, 就能回答「云端的数据还新鲜吗」——
这正是采集机本地跑 ``source_freshness_service`` 回答不了的问题
(那个盯的是**采集链**新鲜度, 本模块盯的是**同步链**新鲜度)。

三个检查
--------
① **云端同步新鲜度** —— 用 ``max(ingest_timestamp)`` 判定, 阈值比业务新鲜度**严格得多**
   (同步链断一天就该发现, 而不是等到业务数据过期 60 天)。
② **身份收敛率** —— 抽样云端事实表最新若干行, 算「行内身份能**唯一归属**到一个
   主数据账号」的比例。
   判据与同步侧的拦截器**共用同一份实现**
   (:func:`backend.services.shop_identity_reconciliation_service.row_identity_accounts`),
   不另写一份。
③ **候选池平台覆盖** —— 主数据里每个「在营经营店」的平台, 候选池里都必须有候选。
④ **语义层可解析性** —— 语义层里 ``shop_id`` 落成 ``unknown`` 的行, **按月分档**:
   对齐生效日之前的月份算「已知历史遗留」(不报警), 之后的月份占比超阈值才报警
   (批次 3.2; 这是「历史数据不修」策略的必要配套)。

落库
----
复用既有的 ``ops.pipeline_run_log`` / ``ops.pipeline_step_log``,
与 :mod:`backend.services.data_pipeline.source_freshness_service` 同一套口径
—— **不新增表、不加迁移**。
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.data_pipeline.source_freshness_service import (
    _chain_label,
    parse_source_table_name,
)
from backend.services.shop_identity_reconciliation_service import (
    load_identity_index,
    row_identity_accounts,
    row_identity_tokens,
)


logger = logging.getLogger(__name__)

__all__ = [
    "ALIGNMENT_EFFECTIVE_DATE_ENV",
    "CLOUD_SYNC_INTEGRITY_PIPELINE_NAME",
    "CLOUD_SYNC_INTEGRITY_STEP_NAME",
    "CandidatePoolRow",
    "CloudFreshnessRow",
    "CloudSyncIntegrityReport",
    "IDENTITY_CANDIDATES_MV",
    "IDENTITY_CANDIDATES_VIEW",
    "IdentityCandidatesCopyRow",
    "IdentityConvergenceRow",
    "LEGACY_COPY_DEFINITION_MARKERS",
    "SEMANTIC_RESOLUTION_TABLE",
    "SEMANTIC_UNKNOWN_RATE_THRESHOLD",
    "SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV",
    "SemanticResolutionRow",
    "SYNC_FRESHNESS_MAX_AGE_DAYS",
    "classify_semantic_resolution",
    "classify_sync_freshness",
    "collect_candidate_pool_coverage",
    "collect_cloud_freshness",
    "collect_identity_candidates_copy",
    "collect_identity_convergence",
    "collect_semantic_resolution",
    "record_cloud_sync_integrity_run",
    "resolve_alignment_effective_date",
    "resolve_semantic_unknown_rate_threshold",
    "run_cloud_sync_integrity_check",
]


CLOUD_SYNC_INTEGRITY_PIPELINE_NAME = "cloud_sync_integrity_check"
CLOUD_SYNC_INTEGRITY_STEP_NAME = "check_cloud_sync_integrity"

#: 「同步链」允许的最大滞后天数 —— 与业务新鲜度阈值**刻意分开**。
#:
#: 业务新鲜度(daily 365 天)回答的是「这批业务数据有多旧」;
#: 同步新鲜度回答的是「云端还有没有在接收数据」——
#: 同步链断掉一天就该发现, 不能等到业务数据过期 60 天。
SYNC_FRESHNESS_MAX_AGE_DAYS: dict[str, int] = {
    "daily": 2,
    "weekly": 8,
    "monthly": 35,
    "snapshot": 3,
}
DEFAULT_SYNC_MAX_AGE_DAYS = 7

#: 身份收敛率下限 —— 低于它就说明「行内身份认不出店铺」。
MIN_CONVERGENCE_RATE = 0.8

#: 每张表抽样多少行来算收敛率(只看最新的一批, 避免全表扫描)。
CONVERGENCE_SAMPLE_SIZE = 200

# --------------------------------------------------------------------------- #
# ④ 语义层可解析性(批次 3.2)
# --------------------------------------------------------------------------- #
#: 环境变量: 店铺身份登记信息**对齐生效日** (``YYYY-MM-DD``)。
#:
#: 为什么必须有它
#: --------------
#: 2026-11 的事故里, 云端有一批行的归属塌成了 ``unknown``。
#: 按业务决定(2026-11-06 / 2026-11-10)「**历史数据不修**」, 这批行永远留在那里。
#: ⇒ 如果巡检只看「整体 unknown 占比」, 它会**永远红** ⇒ 告警就废了。
#:
#: ⇒ 必须按月份分档:
#:   * 对齐生效日**之前**的月份 ⇒ 「已知历史遗留」, 不报警;
#:   * 对齐生效日**之后**的月份 ⇒ 本该全部认得出, unknown 占比超阈值就报警。
#:
#: ⚠ **未配置时**全部归「已知历史遗留」(宁可不报, 也不误报),
#: 同时在报告里标注 ``alignment_effective_date = null`` ⇒ 需要人工补配置。
ALIGNMENT_EFFECTIVE_DATE_ENV = "SHOP_IDENTITY_ALIGNMENT_EFFECTIVE_DATE"

#: 环境变量: 语义层 unknown 占比阈值(``0`` ~ ``1``)。
SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV = "SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD"

#: 语义层 unknown 占比默认阈值 —— 超过它就报警。
SEMANTIC_UNKNOWN_RATE_THRESHOLD = 0.05

# --------------------------------------------------------------------------- #
# ⑤ 候选集物化副本的口径健康(派生层口径收回的守护)
# --------------------------------------------------------------------------- #
#: 候选集**正本**(普通视图) —— 口径的唯一定义处。
IDENTITY_CANDIDATES_VIEW = "semantic.shop_identity_resolution_candidates"
#: 候选集**物化副本** —— 只允许「从正本取数」。
IDENTITY_CANDIDATES_MV = "semantic.shop_identity_resolution_candidates_v2_mv"

#: 副本定义里**出现即说明它在自算**的痕迹。
#: 副本一旦自算, 它与正本就会**静默**分叉: 不报错、只会表现为「某个店没人了」。
LEGACY_COPY_DEFINITION_MARKERS = (
    "core.shop_accounts",
    "core.shop_account_aliases",
    "active_shop_accounts",
    "regexp_replace",
)

#: 巡检的语义层表 —— 月度流量原子层(``shop_id`` 落 ``unknown`` 的地方)。
SEMANTIC_RESOLUTION_TABLE = "semantic.fact_analytics_monthly_atomic"

_SEMANTIC_RESOLUTION_SQL = """
SELECT date_trunc('month', metric_date)::date AS month_start,
       count(*)::int AS total_rows,
       count(*) FILTER (WHERE shop_id = 'unknown')::int AS unknown_rows
FROM semantic.fact_analytics_monthly_atomic
GROUP BY date_trunc('month', metric_date)::date
ORDER BY month_start
"""

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
  AND column_name IN ('ingest_timestamp', 'raw_data', 'platform_code')
GROUP BY table_name
HAVING count(DISTINCT column_name) = 3
"""

_EXPECTED_PLATFORMS_SQL = """
SELECT DISTINCT LOWER(TRIM(COALESCE(platform, ''))) AS platform_code
FROM core.shop_accounts
WHERE enabled IS TRUE
  AND business_role = 'operating_store'
  AND NULLIF(TRIM(COALESCE(platform, '')), '') IS NOT NULL
ORDER BY platform_code
"""

_CANDIDATE_POOL_SQL = """
SELECT platform_code, count(*)::bigint AS candidate_rows
FROM semantic.shop_identity_resolution_candidates
WHERE platform_code IS NOT NULL
GROUP BY platform_code
ORDER BY platform_code
"""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value < 0 or value > 1:
        return default
    return value


def sync_max_age_days_for(granularity: str | None) -> int:
    """该链允许的最大同步滞后天数(可用环境变量覆盖)。"""
    key = f"CLOUD_SYNC_INTEGRITY_MAX_AGE_{(granularity or 'default').upper()}"
    raw = os.getenv(key)
    if raw:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    if granularity and granularity in SYNC_FRESHNESS_MAX_AGE_DAYS:
        return SYNC_FRESHNESS_MAX_AGE_DAYS[granularity]
    return DEFAULT_SYNC_MAX_AGE_DAYS


@dataclass
class CloudFreshnessRow:
    """单条云端事实链的同步新鲜度。"""

    table_name: str
    platform: str | None
    domain: str | None
    subdomain: str | None
    granularity: str | None
    row_count: int
    max_ingest_timestamp: datetime | None
    ingest_age_days: int | None
    max_age_days: int
    status: str

    @property
    def chain_label(self) -> str:
        return _chain_label(parse_source_table_name(self.table_name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "chain": self.chain_label,
            "platform": self.platform,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "granularity": self.granularity,
            "row_count": self.row_count,
            "max_ingest_timestamp": (
                self.max_ingest_timestamp.isoformat()
                if self.max_ingest_timestamp
                else None
            ),
            "ingest_age_days": self.ingest_age_days,
            "max_age_days": self.max_age_days,
            "status": self.status,
        }


@dataclass
class IdentityConvergenceRow:
    """单条云端事实链的**身份收敛率**。"""

    table_name: str
    platform: str | None
    granularity: str | None
    sampled_rows: int
    rows_with_identity: int
    converged_rows: int
    unresolved_rows: int
    conflicting_rows: int
    convergence_rate: float | None
    status: str

    @property
    def chain_label(self) -> str:
        return _chain_label(parse_source_table_name(self.table_name))

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "chain": self.chain_label,
            "platform": self.platform,
            "granularity": self.granularity,
            "sampled_rows": self.sampled_rows,
            "rows_with_identity": self.rows_with_identity,
            "converged_rows": self.converged_rows,
            "unresolved_rows": self.unresolved_rows,
            "conflicting_rows": self.conflicting_rows,
            "convergence_rate": self.convergence_rate,
            "status": self.status,
        }


@dataclass
class CandidatePoolRow:
    """候选池的平台覆盖情况。"""

    platform_code: str
    candidate_rows: int
    expected: bool
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_code": self.platform_code,
            "candidate_rows": self.candidate_rows,
            "expected": self.expected,
            "status": self.status,
        }


@dataclass
class SemanticResolutionRow:
    """语义层某一月的可解析性(``shop_id`` 有没有落成 ``unknown``)。"""

    month_start: date
    total_rows: int
    unknown_rows: int
    unknown_rate: float
    bucket: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "month_start": self.month_start.isoformat(),
            "total_rows": self.total_rows,
            "unknown_rows": self.unknown_rows,
            "unknown_rate": self.unknown_rate,
            "bucket": self.bucket,
            "status": self.status,
        }


@dataclass
class IdentityCandidatesCopyRow:
    """候选集物化副本的口径健康(副本是否还在「从正本取数」)。

    为什么要有这一项
    ----------------
    副本**曾经**手抄了一份正本的计算逻辑, 两边靠人工保持一致 ——
    一旦漂移, 漂移是**静默**的: 看板只会表现为「某个店没人了」, 不报任何错。

    ⇒ 副本必须**只从正本取数**, 而且这件事要**每小时**被确认一次,
    而不是靠「改口径的人记得重建副本」。
    """

    status: str
    copy_rows: int = 0
    source_rows: int = 0
    view_only_rows: int = 0
    copy_only_rows: int = 0
    reads_source: bool = False
    detail: str = ""

    @property
    def is_degraded(self) -> bool:
        """非 ``ok`` 都是问题(缺副本 / 自算 / 内容分叉 / 看不出来)。"""
        return self.status != "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "copy_rows": self.copy_rows,
            "source_rows": self.source_rows,
            "view_only_rows": self.view_only_rows,
            "copy_only_rows": self.copy_only_rows,
            "reads_source": self.reads_source,
            "detail": self.detail,
        }


@dataclass
class CloudSyncIntegrityReport:
    """一次巡检的完整结论。"""

    run_id: str
    started_at: datetime
    finished_at: datetime
    freshness_rows: list[CloudFreshnessRow] = field(default_factory=list)
    convergence_rows: list[IdentityConvergenceRow] = field(default_factory=list)
    candidate_pool_rows: list[CandidatePoolRow] = field(default_factory=list)
    semantic_rows: list[SemanticResolutionRow] = field(default_factory=list)
    identity_candidates_copy: IdentityCandidatesCopyRow | None = None
    alignment_effective_date: date | None = None

    @property
    def stale_rows(self) -> list[CloudFreshnessRow]:
        return [row for row in self.freshness_rows if row.status == "stale"]

    @property
    def degraded_convergence_rows(self) -> list[IdentityConvergenceRow]:
        return [row for row in self.convergence_rows if row.status == "degraded"]

    @property
    def missing_platform_rows(self) -> list[CandidatePoolRow]:
        return [row for row in self.candidate_pool_rows if row.status == "missing"]

    @property
    def degraded_semantic_rows(self) -> list[SemanticResolutionRow]:
        """对齐生效日**之后**、unknown 占比超阈值的月份 —— 这些才是真问题。"""
        return [row for row in self.semantic_rows if row.status == "degraded"]

    @property
    def known_legacy_semantic_rows(self) -> list[SemanticResolutionRow]:
        """对齐生效日之前的月份 —— 已知历史遗留, **不报警**。"""
        return [row for row in self.semantic_rows if row.bucket == "known_legacy"]

    @property
    def is_success(self) -> bool:
        """五项检查全过 ⇒ 巡检通过。"""
        return not (
            self.stale_rows
            or self.degraded_convergence_rows
            or self.missing_platform_rows
            or self.degraded_semantic_rows
            or (
                self.identity_candidates_copy is not None
                and self.identity_candidates_copy.is_degraded
            )
        )

    def to_error_message(self) -> str | None:
        if self.is_success:
            return None
        parts: list[str] = []
        if self.stale_rows:
            detail = ",".join(
                f"{row.chain_label}({row.ingest_age_days}d>{row.max_age_days}d)"
                for row in self.stale_rows
            )
            parts.append(f"stale_cloud_chains:{detail}")
        if self.degraded_convergence_rows:
            detail = ",".join(
                f"{row.chain_label}({row.convergence_rate:.0%})"
                for row in self.degraded_convergence_rows
                if row.convergence_rate is not None
            )
            parts.append(f"low_identity_convergence:{detail}")
        if self.missing_platform_rows:
            detail = ",".join(row.platform_code for row in self.missing_platform_rows)
            parts.append(f"missing_candidate_platforms:{detail}")
        if self.degraded_semantic_rows:
            detail = ",".join(
                f"{row.month_start.isoformat()}({row.unknown_rate:.1%})"
                for row in self.degraded_semantic_rows
            )
            parts.append(f"semantic_unknown_after_alignment:{detail}")
        if (
            self.identity_candidates_copy is not None
            and self.identity_candidates_copy.is_degraded
        ):
            copy_row = self.identity_candidates_copy
            parts.append(
                f"identity_candidates_copy:{copy_row.status}:{copy_row.detail}"
            )
        return ";".join(parts)

    def to_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_chains": len(self.freshness_rows),
            "stale_chains": len(self.stale_rows),
            "low_convergence_chains": len(self.degraded_convergence_rows),
            "missing_candidate_platforms": len(self.missing_platform_rows),
            "semantic_months_checked": len(self.semantic_rows),
            "semantic_known_legacy_months": len(self.known_legacy_semantic_rows),
            "degraded_semantic_months": len(self.degraded_semantic_rows),
            "identity_candidates_copy_status": (
                self.identity_candidates_copy.status
                if self.identity_candidates_copy is not None
                else None
            ),
            "identity_candidates_copy_rows": (
                self.identity_candidates_copy.copy_rows
                if self.identity_candidates_copy is not None
                else None
            ),
            "alignment_effective_date": (
                self.alignment_effective_date.isoformat()
                if self.alignment_effective_date
                else None
            ),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


def classify_sync_freshness(
    *,
    row_count: int,
    max_ingest_timestamp: datetime | None,
    now: datetime,
    max_age_days: int,
) -> tuple[str, int | None]:
    """返回 ``(状态, 同步滞后天数)``。

    - ``fresh``  —— 云端还在持续接收数据;
    - ``stale``  —— 云端数据已经 ``max_age_days`` 天没更新 ⇒ 同步链断了;
    - ``empty``  —— 这张表压根没有数据(可能本来就没开这条采集, 只提示)。
    """
    if row_count <= 0:
        return "empty", None
    if max_ingest_timestamp is None:
        return "stale", None
    age_days = (now - max_ingest_timestamp).days
    if age_days > max_age_days:
        return "stale", age_days
    return "fresh", age_days


def classify_convergence(
    *,
    sampled_rows: int,
    rows_with_identity: int,
    converged_rows: int,
    min_rate: float,
) -> tuple[str, float | None]:
    """返回 ``(状态, 收敛率)``。

    分母只算「行内带了身份线索」的行 —— 没有身份线索的行(比如采集方代号)
    **无从判定**, 算进去只会稀释指标、淹没真正的告警。
    """
    if sampled_rows <= 0:
        return "empty", None
    if rows_with_identity <= 0:
        return "unknown", None
    rate = converged_rows / rows_with_identity
    if rate < min_rate:
        return "degraded", rate
    return "ok", rate


async def collect_cloud_freshness(
    db: AsyncSession,
    *,
    now: datetime | None = None,
) -> list[CloudFreshnessRow]:
    """巡检云端 ``b_class.fact_*`` 的同步新鲜度(按 ``max(ingest_timestamp)``)。"""
    now_utc = now or datetime.now(timezone.utc)
    if not now_utc.tzinfo:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    discovered = await db.execute(text(_SOURCE_TABLE_DISCOVERY_SQL))
    ready = await db.execute(text(_SOURCE_COLUMN_READY_SQL))
    ready_tables = {row[0] for row in ready.fetchall()}
    table_names = [row[0] for row in discovered.fetchall() if row[0] in ready_tables]

    rows: list[CloudFreshnessRow] = []
    for table_name in table_names:
        result = await db.execute(
            text(
                "SELECT count(*)::bigint, max(ingest_timestamp) "
                f'FROM b_class."{table_name}"'
            )
        )
        record = result.fetchone()
        row_count = int(record[0] or 0)
        max_ingest_timestamp = record[1]
        if max_ingest_timestamp is not None and not max_ingest_timestamp.tzinfo:
            max_ingest_timestamp = max_ingest_timestamp.replace(tzinfo=timezone.utc)

        identity = parse_source_table_name(table_name)
        max_age_days = sync_max_age_days_for(identity.granularity)
        status, ingest_age_days = classify_sync_freshness(
            row_count=row_count,
            max_ingest_timestamp=max_ingest_timestamp,
            now=now_utc,
            max_age_days=max_age_days,
        )
        rows.append(
            CloudFreshnessRow(
                table_name=table_name,
                platform=identity.platform,
                domain=identity.domain,
                subdomain=identity.subdomain,
                granularity=identity.granularity,
                row_count=row_count,
                max_ingest_timestamp=max_ingest_timestamp,
                ingest_age_days=ingest_age_days,
                max_age_days=max_age_days,
                status=status,
            )
        )
    rows.sort(key=lambda row: row.table_name)
    return rows


async def collect_identity_convergence(
    db: AsyncSession,
    *,
    table_names: list[str] | None = None,
    sample_size: int | None = None,
    min_rate: float | None = None,
    identity_index: Any = None,
) -> list[IdentityConvergenceRow]:
    """抽样云端事实表, 算「行内身份能唯一归属到主数据账号」的比例。

    判据与同步侧拦截器**共用** ``row_identity_accounts`` —— 不另写一份,
    否则两边的口径迟早会分叉, 巡检就失去了"发现同步侧问题"的意义。

    ``identity_index`` 为 None 时从库里加载主数据索引(见
    :func:`backend.services.shop_identity_reconciliation_service.load_identity_index`)。
    """
    sample_size = sample_size or _env_int(
        "CLOUD_SYNC_INTEGRITY_SAMPLE_SIZE", CONVERGENCE_SAMPLE_SIZE
    )
    min_rate = (
        min_rate
        if min_rate is not None
        else _env_float(
            "CLOUD_SYNC_INTEGRITY_MIN_CONVERGENCE_RATE", MIN_CONVERGENCE_RATE
        )
    )

    if table_names is None:
        discovered = await db.execute(text(_SOURCE_TABLE_DISCOVERY_SQL))
        ready = await db.execute(text(_SOURCE_COLUMN_READY_SQL))
        ready_tables = {row[0] for row in ready.fetchall()}
        table_names = [
            row[0] for row in discovered.fetchall() if row[0] in ready_tables
        ]

    if identity_index is None:
        identity_index = await load_identity_index(db)

    rows: list[IdentityConvergenceRow] = []
    for table_name in table_names:
        result = await db.execute(
            text(
                "SELECT raw_data, platform_code "
                f'FROM b_class."{table_name}" '
                "ORDER BY ingest_timestamp DESC "
                f"LIMIT {int(sample_size)}"
            )
        )
        sampled = result.fetchall()

        sampled_rows = 0
        rows_with_identity = 0
        converged_rows = 0
        unresolved_rows = 0
        conflicting_rows = 0
        for record in sampled:
            sampled_rows += 1
            raw_data = record[0]
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except (TypeError, ValueError):
                    raw_data = {}
            row = {"raw_data": raw_data if isinstance(raw_data, dict) else {}}
            platform_code = str(record[1] or "")

            if not row_identity_tokens(row):
                # 行内没有身份线索 ⇒ 无从判定, 不进分母
                continue
            rows_with_identity += 1
            accounts = row_identity_accounts(row, identity_index, platform_code)
            if len(accounts) == 1:
                converged_rows += 1
            elif not accounts:
                unresolved_rows += 1
            else:
                conflicting_rows += 1

        identity = parse_source_table_name(table_name)
        status, rate = classify_convergence(
            sampled_rows=sampled_rows,
            rows_with_identity=rows_with_identity,
            converged_rows=converged_rows,
            min_rate=min_rate,
        )
        rows.append(
            IdentityConvergenceRow(
                table_name=table_name,
                platform=identity.platform,
                granularity=identity.granularity,
                sampled_rows=sampled_rows,
                rows_with_identity=rows_with_identity,
                converged_rows=converged_rows,
                unresolved_rows=unresolved_rows,
                conflicting_rows=conflicting_rows,
                convergence_rate=rate,
                status=status,
            )
        )
    rows.sort(key=lambda row: row.table_name)
    return rows


async def collect_candidate_pool_coverage(
    db: AsyncSession,
) -> list[CandidatePoolRow]:
    """检查候选池是否覆盖了主数据里每个「在营经营店」的平台。

    候选池缺平台 ⇒ 那条链的身份**从一开始就解析不出来**
    (2026-11 实测: ``miaoshou`` 的采集源账号不在候选池里,
    于是 inventory 链 4,111 行的身份全部泄漏成单一 ``xihong``)。
    """
    expected_result = await db.execute(text(_EXPECTED_PLATFORMS_SQL))
    expected = {row[0] for row in expected_result.fetchall() if row[0]}

    pool_result = await db.execute(text(_CANDIDATE_POOL_SQL))
    pool = {row[0]: int(row[1] or 0) for row in pool_result.fetchall()}

    rows: list[CandidatePoolRow] = []
    for platform_code in sorted(expected | set(pool)):
        candidate_rows = pool.get(platform_code, 0)
        is_expected = platform_code in expected
        status = "ok"
        if is_expected and candidate_rows <= 0:
            status = "missing"
        elif not is_expected and candidate_rows > 0:
            # 候选池里有主数据没有的平台 —— 不危险, 但值得知道
            status = "extra"
        rows.append(
            CandidatePoolRow(
                platform_code=platform_code,
                candidate_rows=candidate_rows,
                expected=is_expected,
                status=status,
            )
        )
    return rows


def resolve_alignment_effective_date() -> date | None:
    """读「店铺身份登记信息对齐生效日」(环境变量)。

    解析不出来(没配 / 格式不对)⇒ 返回 ``None`` ⇒
    语义层可解析性巡检会把所有月份归入「已知历史遗留」(**不报警**),
    同时在报告里留下 ``alignment_effective_date = null`` ⇒ 需要人工补配置。
    """
    raw = (os.getenv(ALIGNMENT_EFFECTIVE_DATE_ENV) or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning(
            "[CloudSyncIntegrity] %s 格式非法(应为 YYYY-MM-DD): %r",
            ALIGNMENT_EFFECTIVE_DATE_ENV,
            raw,
        )
        return None


def resolve_semantic_unknown_rate_threshold() -> float:
    """读语义层 unknown 占比阈值(环境变量可覆盖)。"""
    raw = (os.getenv(SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV) or "").strip()
    if not raw:
        return SEMANTIC_UNKNOWN_RATE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "[CloudSyncIntegrity] %s 格式非法: %r，沿用默认值 %s",
            SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV,
            raw,
            SEMANTIC_UNKNOWN_RATE_THRESHOLD,
        )
        return SEMANTIC_UNKNOWN_RATE_THRESHOLD
    if not 0.0 <= value <= 1.0:
        logger.warning(
            "[CloudSyncIntegrity] %s 超出 0~1 范围: %r，沿用默认值 %s",
            SEMANTIC_UNKNOWN_RATE_THRESHOLD_ENV,
            raw,
            SEMANTIC_UNKNOWN_RATE_THRESHOLD,
        )
        return SEMANTIC_UNKNOWN_RATE_THRESHOLD
    return value


def classify_semantic_resolution(
    *,
    month_start: date,
    total_rows: int,
    unknown_rows: int,
    alignment_effective_date: date | None,
    threshold: float,
) -> tuple[str, str, float]:
    """返回 ``(分档, 状态, unknown 占比)``。

    分档规则
    --------
    * 对齐生效日**之前**的月份 ⇒ ``known_legacy``(已知历史遗留)—— **不报警**。
      这是「历史不修」策略的必然结果: 那些行永远留在那里, 报警就永远红 ⇒ 告警废了。
    * 对齐生效日**之后**的月份 ⇒ ``post_alignment``;
      unknown 占比 > 阈值 ⇒ ``degraded``(报警)。
    * **未配置对齐生效日** ⇒ 全部归 ``known_legacy``(宁可不报, 也不误报)。
    """
    unknown_rate = (unknown_rows / total_rows) if total_rows else 0.0
    if alignment_effective_date is None:
        return "known_legacy", "ok", unknown_rate
    boundary = alignment_effective_date.replace(day=1)
    if month_start < boundary:
        return "known_legacy", "ok", unknown_rate
    if unknown_rate > threshold:
        return "post_alignment", "degraded", unknown_rate
    return "post_alignment", "ok", unknown_rate


async def collect_semantic_resolution(
    db: AsyncSession,
    *,
    alignment_effective_date: date | None = None,
    threshold: float = SEMANTIC_UNKNOWN_RATE_THRESHOLD,
) -> list[SemanticResolutionRow]:
    """按月统计语义层的可解析性(``shop_id`` 落 ``unknown`` 的行数 / 占比)。

    语义层表不存在(不同环境)⇒ 返回空列表, 不让巡检失败。
    """
    exists = await db.execute(
        text("SELECT to_regclass(:name)"), {"name": SEMANTIC_RESOLUTION_TABLE}
    )
    if exists.scalar_one_or_none() is None:
        return []

    result = await db.execute(text(_SEMANTIC_RESOLUTION_SQL))
    rows: list[SemanticResolutionRow] = []
    for record in result.fetchall():
        month_start = record[0]
        total_rows = int(record[1] or 0)
        unknown_rows = int(record[2] or 0)
        bucket, status, unknown_rate = classify_semantic_resolution(
            month_start=month_start,
            total_rows=total_rows,
            unknown_rows=unknown_rows,
            alignment_effective_date=alignment_effective_date,
            threshold=threshold,
        )
        rows.append(
            SemanticResolutionRow(
                month_start=month_start,
                total_rows=total_rows,
                unknown_rows=unknown_rows,
                unknown_rate=unknown_rate,
                bucket=bucket,
                status=status,
            )
        )
    return rows


async def collect_identity_candidates_copy(
    db: AsyncSession,
) -> IdentityCandidatesCopyRow | None:
    """检查候选集物化副本是不是还在「从正本取数」。

    返回 ``None`` 表示这个环境**没有候选池**(不适用), 不算问题。

    判据(按优先级)
    --------------
    1. ``missing``  —— 有正本却没有副本;
    2. ``drifted``  —— 副本的**定义**不是「从正本取数」(它在自算) ⇒ 会静默分叉;
    3. ``diverged`` —— 定义对, 但副本与正本的**内容**已经不一致;
    4. ``ok``       —— 定义与内容都对。
    """
    view_exists = await db.execute(
        text("SELECT to_regclass(:name)"), {"name": IDENTITY_CANDIDATES_VIEW}
    )
    if view_exists.scalar_one_or_none() is None:
        return None

    copy_exists = await db.execute(
        text("SELECT to_regclass(:name)"), {"name": IDENTITY_CANDIDATES_MV}
    )
    if copy_exists.scalar_one_or_none() is None:
        return IdentityCandidatesCopyRow(
            status="missing",
            detail="候选集物化副本不存在(正本在、副本不在)",
        )

    definition_row = await db.execute(
        text("SELECT pg_get_viewdef(to_regclass(:name), true)"),
        {"name": IDENTITY_CANDIDATES_MV},
    )
    definition = str(definition_row.scalar_one_or_none() or "")
    reads_source = IDENTITY_CANDIDATES_VIEW in definition
    legacy_markers = [
        marker
        for marker in LEGACY_COPY_DEFINITION_MARKERS
        if marker.lower() in definition.lower()
    ]

    copy_rows = 0
    source_rows = 0
    view_only_rows = 0
    copy_only_rows = 0
    try:
        counts = await db.execute(
            text(
                "SELECT (SELECT count(*)::int FROM {view}), "
                "(SELECT count(*)::int FROM {copy})".format(
                    view=IDENTITY_CANDIDATES_VIEW, copy=IDENTITY_CANDIDATES_MV
                )
            )
        )
        # ⚠️ result 只能取一次 —— 第二次 ``one()`` 会抛 "This result object is closed"。
        counts_row = counts.one()
        source_rows = int(counts_row[0] or 0)
        copy_rows = int(counts_row[1] or 0)

        diff = await db.execute(
            text(
                """
                SELECT
                    (SELECT count(*)::int FROM (
                        SELECT * FROM {view} EXCEPT ALL SELECT * FROM {copy}
                    ) a) AS view_only,
                    (SELECT count(*)::int FROM (
                        SELECT * FROM {copy} EXCEPT ALL SELECT * FROM {view}
                    ) b) AS copy_only
                """.format(
                    view=IDENTITY_CANDIDATES_VIEW, copy=IDENTITY_CANDIDATES_MV
                )
            )
        )
        diff_row = diff.one()
        view_only_rows = int(diff_row[0] or 0)
        copy_only_rows = int(diff_row[1] or 0)
    except Exception as exc:  # noqa: BLE001 - 看不出来也要报出来, 不能当没事发生
        logger.warning(
            "[CloudSyncIntegrity] 候选集副本内容比对失败: %s", exc, exc_info=True
        )
        return IdentityCandidatesCopyRow(
            status="unknown",
            reads_source=reads_source,
            detail="候选集副本内容比对失败: {exc}".format(exc=exc),
        )

    if legacy_markers or not reads_source:
        detail = "候选集副本仍在自算逻辑(未从正本取数): {markers}".format(
            markers=",".join(legacy_markers) or "definition_does_not_reference_source"
        )
        return IdentityCandidatesCopyRow(
            status="drifted",
            copy_rows=copy_rows,
            source_rows=source_rows,
            view_only_rows=view_only_rows,
            copy_only_rows=copy_only_rows,
            reads_source=reads_source,
            detail=detail,
        )

    if view_only_rows or copy_only_rows:
        return IdentityCandidatesCopyRow(
            status="diverged",
            copy_rows=copy_rows,
            source_rows=source_rows,
            view_only_rows=view_only_rows,
            copy_only_rows=copy_only_rows,
            reads_source=True,
            detail=(
                "候选集副本与正本内容不一致: "
                "正本多 {a} 行、副本多 {b} 行".format(
                    a=view_only_rows, b=copy_only_rows
                )
            ),
        )

    return IdentityCandidatesCopyRow(
        status="ok",
        copy_rows=copy_rows,
        source_rows=source_rows,
        view_only_rows=0,
        copy_only_rows=0,
        reads_source=True,
        detail="候选集副本从正本取数, 内容一致({n} 行)".format(n=copy_rows),
    )


async def record_cloud_sync_integrity_run(
    db: AsyncSession,
    report: CloudSyncIntegrityReport,
    *,
    trigger_source: str = "scheduler",
) -> None:
    """把巡检结论写进既有的 ops 监控表(不新增表、不加迁移)。"""
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
            "pipeline_name": CLOUD_SYNC_INTEGRITY_PIPELINE_NAME,
            "status": run_status,
            "trigger_source": trigger_source,
            "started_at": report.started_at,
            "completed_at": report.finished_at,
            "error_message": report.to_error_message(),
            "context": json.dumps(report.to_summary(), ensure_ascii=False),
        },
    )

    for row in report.freshness_rows:
        status = {"fresh": "success", "stale": "failed", "empty": "skipped"}.get(
            row.status, "success"
        )
        error_message = None
        if row.status == "stale":
            error_message = (
                f"stale_cloud_chain: {row.chain_label} 已 "
                f"{row.ingest_age_days} 天没有新数据入库（上限 {row.max_age_days} 天）"
            )
        elif row.status == "empty":
            error_message = f"empty_cloud_table: {row.chain_label} 没有任何数据"
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
                "step_name": "check_cloud_freshness",
                "target_name": row.table_name,
                "status": status,
                "started_at": report.started_at,
                "completed_at": report.finished_at,
                "affected_rows": row.row_count,
                "error_message": error_message,
                "details": json.dumps(row.to_dict(), ensure_ascii=False),
            },
        )

    for row in report.convergence_rows:
        status = {
            "ok": "success",
            "degraded": "failed",
            "empty": "skipped",
            "unknown": "skipped",
        }.get(row.status, "success")
        error_message = None
        if row.status == "degraded":
            error_message = (
                f"low_identity_convergence: {row.chain_label} 收敛率 "
                f"{(row.convergence_rate or 0):.0%}"
                f"（未归属 {row.unresolved_rows} 行 / 矛盾 {row.conflicting_rows} 行）"
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
                "step_name": "check_identity_convergence",
                "target_name": row.table_name,
                "status": status,
                "started_at": report.started_at,
                "completed_at": report.finished_at,
                "affected_rows": row.converged_rows,
                "error_message": error_message,
                "details": json.dumps(row.to_dict(), ensure_ascii=False),
            },
        )

    for row in report.candidate_pool_rows:
        status = {"ok": "success", "missing": "failed", "extra": "skipped"}.get(
            row.status, "success"
        )
        error_message = None
        if row.status == "missing":
            error_message = (
                f"missing_candidate_platform: {row.platform_code} "
                "在主数据里和在营经营店, 但候选池里没有任何候选"
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
                "step_name": "check_candidate_pool",
                "target_name": row.platform_code,
                "status": status,
                "started_at": report.started_at,
                "completed_at": report.finished_at,
                "affected_rows": row.candidate_rows,
                "error_message": error_message,
                "details": json.dumps(row.to_dict(), ensure_ascii=False),
            },
        )

    if report.identity_candidates_copy is not None:
        copy_row = report.identity_candidates_copy
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
                "step_name": "check_identity_candidates_copy",
                "target_name": IDENTITY_CANDIDATES_MV,
                "status": "failed" if copy_row.is_degraded else "success",
                "started_at": report.started_at,
                "completed_at": report.finished_at,
                "affected_rows": copy_row.copy_rows,
                "error_message": copy_row.detail if copy_row.is_degraded else None,
                "details": json.dumps(copy_row.to_dict(), ensure_ascii=False),
            },
        )

    await db.commit()


async def run_cloud_sync_integrity_check(
    db: AsyncSession,
    *,
    trigger_source: str = "scheduler",
    record: bool = True,
    alignment_effective_date: date | None = None,
    semantic_unknown_rate_threshold: float | None = None,
) -> CloudSyncIntegrityReport:
    """巡检 + 落库, 返回结论。"""
    started_at = datetime.now(timezone.utc)
    report = CloudSyncIntegrityReport(
        run_id=f"cloud_sync_integrity_{uuid.uuid4().hex[:12]}",
        started_at=started_at,
        finished_at=started_at,
    )
    report.freshness_rows = await collect_cloud_freshness(db, now=started_at)
    report.convergence_rows = await collect_identity_convergence(
        db,
        table_names=[row.table_name for row in report.freshness_rows],
    )
    report.candidate_pool_rows = await collect_candidate_pool_coverage(db)
    # ④ 语义层可解析性 —— 分界日之前的月份算「已知历史遗留」, 不报警。
    if alignment_effective_date is None:
        alignment_effective_date = resolve_alignment_effective_date()
    if semantic_unknown_rate_threshold is None:
        semantic_unknown_rate_threshold = resolve_semantic_unknown_rate_threshold()
    report.alignment_effective_date = alignment_effective_date
    report.semantic_rows = await collect_semantic_resolution(
        db,
        alignment_effective_date=alignment_effective_date,
        threshold=semantic_unknown_rate_threshold,
    )
    # ⑤ 候选集副本口径健康 —— 副本必须在「从正本取数」, 否则会静默分叉。
    report.identity_candidates_copy = await collect_identity_candidates_copy(db)
    report.finished_at = datetime.now(timezone.utc)
    if record:
        await record_cloud_sync_integrity_run(db, report, trigger_source=trigger_source)
    return report
