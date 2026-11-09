"""云端同步链路的**完整性**巡检 —— 陈旧 / 收敛率 / 候选池平台覆盖。

背景
----
2026-11-07 的采集同步丢数事故里, 有三个信号**同时**存在, 而**一个都没人看见**:

1. **云端事实表停在 11-06**, 之后再没有新数据落库 —— 同步链断了或被拦了;
2. **行内身份收敛率恒为 0** —— 入库侧的枚举 bug 让收敛 100% 静默失效,
   不报错、不告警, 账本还记 "completed";
3. **候选池缺平台** —— ``miaoshou`` 的采集源账号(``business_role='collection_source'``)
   不在候选池里, 那条链的身份从一开始就解析不出来。

本模块把这三个信号变成**会自己响的巡检**。

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

落库
----
复用既有的 ``ops.pipeline_run_log`` / ``ops.pipeline_step_log``,
与 :mod:`backend.services.data_pipeline.source_freshness_service` 同一套口径
—— **不新增表、不加迁移**。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
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


__all__ = [
    "CLOUD_SYNC_INTEGRITY_PIPELINE_NAME",
    "CLOUD_SYNC_INTEGRITY_STEP_NAME",
    "CandidatePoolRow",
    "CloudFreshnessRow",
    "CloudSyncIntegrityReport",
    "IdentityConvergenceRow",
    "SYNC_FRESHNESS_MAX_AGE_DAYS",
    "classify_sync_freshness",
    "collect_candidate_pool_coverage",
    "collect_cloud_freshness",
    "collect_identity_convergence",
    "record_cloud_sync_integrity_run",
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
        return _chain_label(
            parse_source_table_name(self.table_name)
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
class CloudSyncIntegrityReport:
    """一次巡检的完整结论。"""

    run_id: str
    started_at: datetime
    finished_at: datetime
    freshness_rows: list[CloudFreshnessRow] = field(default_factory=list)
    convergence_rows: list[IdentityConvergenceRow] = field(default_factory=list)
    candidate_pool_rows: list[CandidatePoolRow] = field(default_factory=list)

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
    def is_success(self) -> bool:
        """三项检查全过 ⇒ 巡检通过。"""
        return not (
            self.stale_rows or self.degraded_convergence_rows or self.missing_platform_rows
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
            detail = ",".join(
                row.platform_code for row in self.missing_platform_rows
            )
            parts.append(f"missing_candidate_platforms:{detail}")
        return ";".join(parts)

    def to_summary(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "checked_chains": len(self.freshness_rows),
            "stale_chains": len(self.stale_rows),
            "low_convergence_chains": len(self.degraded_convergence_rows),
            "missing_candidate_platforms": len(self.missing_platform_rows),
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
                'SELECT count(*)::bigint, max(ingest_timestamp) '
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
                'SELECT raw_data, platform_code '
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

    await db.commit()


async def run_cloud_sync_integrity_check(
    db: AsyncSession,
    *,
    trigger_source: str = "scheduler",
    record: bool = True,
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
    report.finished_at = datetime.now(timezone.utc)
    if record:
        await record_cloud_sync_integrity_run(db, report, trigger_source=trigger_source)
    return report
