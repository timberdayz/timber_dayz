"""
Data pipeline observability routes.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_async_db
from backend.services.data_pipeline.refresh_validation import find_missing_targets
from backend.services.data_pipeline.semantic_readiness_service import (
    collect_semantic_readiness,
)
from backend.services.data_pipeline.source_freshness_service import (
    collect_source_freshness,
)
from backend.services.semantic_coverage_audit_service import (
    SEMANTIC_COVERAGE_DOMAINS,
    SemanticCoverageAuditService,
    SemanticCoverageReport,
)
from backend.utils.api_response import success_response
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/data-pipeline", tags=["data-pipeline"])


def _object_exists_flag(name: Any, missing_names: set[str]) -> bool | None:
    """带 schema 前缀的名字是数据库对象，可核对存在性；其余返回 None（无法核对）。"""
    if not name or "." not in str(name):
        return None
    return str(name) not in missing_names


@router.get("/status")
async def get_pipeline_status(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT run_id, pipeline_name, status, trigger_source, started_at, completed_at, error_message
            FROM ops.pipeline_run_log
            ORDER BY id DESC
            LIMIT 20
            """
        )
    )
    runs = [dict(row) for row in result.mappings().all()]
    return success_response(
        data={
            "runs": runs,
        }
    )


@router.get("/freshness")
async def get_pipeline_freshness(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT target_name, target_type, last_started_at, last_succeeded_at, status, affected_rows, data_min_date, data_max_date
            FROM ops.data_freshness_log
            ORDER BY target_name
            """
        )
    )
    targets = [dict(row) for row in result.mappings().all()]

    # 存在性校验：freshness 只记录「上一次刷新当时的结果」，对象后来被删除/改名时
    # 状态仍是 success，监控因此「假绿」。这里实时核对对象是否还在，
    # 把「已注册但对象已不存在」的目标标成 missing。
    missing_targets = await find_missing_targets(
        db, [row.get("target_name") for row in targets]
    )
    for row in targets:
        target_name = row.get("target_name")
        if target_name in missing_targets:
            row["object_exists"] = False
            row["recorded_status"] = row.get("status")
            row["status"] = "missing"
        else:
            row["object_exists"] = _object_exists_flag(target_name, missing_targets)

    return success_response(
        data={
            "targets": targets,
            "missing_targets": sorted(missing_targets),
        }
    )


@router.get("/lineage")
async def get_pipeline_lineage(
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        text(
            """
            SELECT target_name, target_type, source_name, source_type, dependency_level, active, created_at
            FROM ops.data_lineage_registry
            WHERE active = TRUE
            ORDER BY target_name, dependency_level, source_name
            """
        )
    )
    edges = [dict(row) for row in result.mappings().all()]

    # 注册表里 active = TRUE 只说明「登记过」，不代表对象还在。
    # 这里实时核对目标与来源对象，暴露「注册还在、对象已删」的情况。
    missing_objects = await find_missing_targets(
        db,
        [row.get("target_name") for row in edges]
        + [row.get("source_name") for row in edges],
    )
    for row in edges:
        row["target_object_exists"] = _object_exists_flag(
            row.get("target_name"), missing_objects
        )
        row["source_object_exists"] = _object_exists_flag(
            row.get("source_name"), missing_objects
        )

    return success_response(
        data={
            "edges": edges,
            "missing_objects": sorted(missing_objects),
        }
    )


@router.get("/source-freshness")
async def get_source_freshness(
    db: AsyncSession = Depends(get_async_db),
):
    """源数据（业务事实表）新鲜度。

    与 ``/freshness`` 的分工：``/freshness`` 看的是「视图/接口上次刷新有没有成功」，
    这里看的是「业务数据本身有多旧」。断流的第一现场在后者——
    刷新链路可以全绿，而底下的业务数据已经几个月没更新过。
    """
    report = await collect_source_freshness(db)
    return success_response(
        data={
            "summary": report.to_summary(),
            "chains": [row.to_dict() for row in report.rows],
        }
    )


@router.get("/semantic-readiness")
async def get_semantic_readiness(
    granularity: str = Query("monthly", description="daily/weekly/monthly"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
    db: AsyncSession = Depends(get_async_db),
):
    """语义层就绪状态位（阶段 6）。

    回答「看板现在看到的数字，是不是最新采集的那一批」：
    采集落盘 -> 语义层就绪之间有约 70 秒窗口（2026-11-08 实测），
    这段时间里看板面对的是旧数据/空数据 => 显式给状态，而不是让人猜。

    状态：``fresh``（就绪）/ ``updating``（采集中或刷新中）/ ``stale``（超阈值）/
    ``unknown``（判不了）。

    采集侧的订单域来源巡检在
    ``GET /api/collection/config-order-source``（同一阶段的另一件事）。
    """
    readiness = await collect_semantic_readiness(
        db,
        granularity=granularity,
        platform=platform_code,
        shop_id=shop_id,
    )
    return success_response(data=readiness)


# ── 语义层标准字段覆盖率巡检（只读）────────────────────────────────
#
# 为什么要有这个端点
# ------------------
# ``semantic.fact_*_atomic`` 对数值型标准字段做了 ``COALESCE(x, 0)``:
# **解析失败被伪装成 0** ⇒ 运维只能跑脚本才知道「利润」「平台服务费」到底解析得出来吗。
# 本端点把服务层已有的巡检能力暴露成 HTTP, 让看板/运维脚本都能直接看。
#
# 只读保证
# --------
# 本端点只调用服务层的只读 ``audit()``(服务层只发 SELECT), 不写库、不改视图。
#
# 容错保证
# --------
# DB 不可用 / ``semantic`` 视图不存在 ⇒ **返回 200 + 空报告 + 一条 warning**,
# 绝不把调用方(看板轮询、运维脚本)带崩 —— 与服务层 ``_skipped_report`` 同一口径。
#
# 参数
# ----
# * ``domain``: ``orders`` / ``products`` / ``all``。
#   **不传时默认两个域都出**(= ``all``), 因为面板要同时看订单域与商品域的健康度。
#   传单个域则只出该域; 传未知值返回 400(这是**调用方参数写错**, 与 DB 故障不同,
#   不该静默吞掉)。
# * ``threshold``: 解析率告警阈值(0~1)。不传时沿用服务层默认
#   (``DEFAULT_RESOLUTION_THRESHOLD`` = 0.5)。


def _coverage_entry_to_dict(entry: Any) -> Dict[str, Any]:
    """把 ``SemanticCoverageEntry`` 转成可 JSON 序列化的 dict。"""
    return {
        "platform_code": entry.platform_code,
        "granularity": entry.granularity,
        "standard_field": entry.standard_field,
        "resolved_rows": entry.resolved_rows,
        "total_rows": entry.total_rows,
        "resolution_rate": entry.resolution_rate,
    }


def _coverage_group_to_dict(group: Any) -> Dict[str, Any]:
    """把 ``SemanticCoverageGroup`` 转成可 JSON 序列化的 dict。"""
    return {
        "platform_code": group.platform_code,
        "granularity": group.granularity,
        "total_rows": group.total_rows,
        "empty_shell_rows": group.empty_shell_rows,
        "payload_rows": group.payload_rows,
        "unresolved_rows": group.unresolved_rows,
        "unresolved_rate": group.unresolved_rate,
    }


def _coverage_platforms_to_list(report: SemanticCoverageReport) -> List[Dict[str, Any]]:
    """平台维度诊断 + 按平台的平均解析率。

    服务层给的是「哪些字段在所有粒度下都解析不出来」(缺口诊断);
    面板还要看「这个平台整体解析率多少」(健康度)⇒ 这里按 entries 聚合补上。
    """
    rates_by_platform: Dict[str, List[float]] = {}
    for entry in report.entries:
        rates_by_platform.setdefault(entry.platform_code, []).append(
            entry.resolution_rate
        )

    platforms: List[Dict[str, Any]] = []
    for summary in report.platforms:
        rates = rates_by_platform.get(summary.platform_code, [])
        average_rate = (sum(rates) / len(rates)) if rates else 0.0
        platforms.append(
            {
                "platform_code": summary.platform_code,
                "total_fields": summary.total_fields,
                "zero_fields": summary.zero_fields,
                "zero_rate": summary.zero_rate,
                "zero_standard_fields": list(summary.zero_standard_fields),
                # 按平台的平均解析率(跨粒度、跨字段)。
                "average_resolution_rate": average_rate,
                "field_count": len(rates),
                "healthy_field_count": sum(1 for rate in rates if rate > 0),
            }
        )
    return platforms


def _coverage_summary(report: SemanticCoverageReport) -> Dict[str, Any]:
    """域级整体健康度(面板顶部的概览卡片)。

    * ``health``: ``unknown``(没数据可判) / ``healthy`` / ``degraded``。
      只要有任何一个字段解析率为 0 ⇒ ``degraded`` —— 缺口必须被看见。
    """
    entries = report.entries
    threshold = report.threshold
    rates = [entry.resolution_rate for entry in entries]
    zero_rate_count = sum(1 for rate in rates if rate <= 0)
    below_threshold_count = sum(1 for rate in rates if rate < threshold)

    if not entries:
        health = "unknown"
    elif zero_rate_count == 0 and below_threshold_count == 0:
        health = "healthy"
    else:
        health = "degraded"

    return {
        "health": health,
        "platform_count": len({entry.platform_code for entry in entries}),
        "entry_count": len(entries),
        "zero_rate_entry_count": zero_rate_count,
        "below_threshold_entry_count": below_threshold_count,
        "average_resolution_rate": (sum(rates) / len(rates)) if rates else 0.0,
        "warning_count": len(report.warnings),
        "empty_shell_rows": report.empty_shell_rows,
        "unresolved_rows": report.unresolved_rows,
    }


def _coverage_report_to_dict(report: SemanticCoverageReport) -> Dict[str, Any]:
    """把整份巡检报告转成**可 JSON 序列化**的结构。

    服务层报告里含 tuple / Mapping / dataclass ⇒ 这里显式转成 list / dict,
    不依赖序列化层的兜底。
    """
    domain_spec = SEMANTIC_COVERAGE_DOMAINS.get(report.domain)
    return {
        "domain": report.domain,
        "relation": domain_spec.relation if domain_spec else "",
        "threshold": report.threshold,
        "generated_at": report.generated_at.isoformat(),
        "entries": [_coverage_entry_to_dict(entry) for entry in report.entries],
        "groups": [_coverage_group_to_dict(group) for group in report.groups],
        "platforms": _coverage_platforms_to_list(report),
        # key = "{platform_code}/{granularity}/{standard_field}"。
        "column_candidates": {
            str(key): list(values)
            for key, values in (report.column_candidates or {}).items()
        },
        "warnings": list(report.warnings),
        "summary": _coverage_summary(report),
    }


def _skipped_coverage_report(
    domain_name: str, threshold: float, exc: BaseException
) -> SemanticCoverageReport:
    """巡检整体失败(而非单个域失败)时的兜底报告。

    与服务层 ``_skipped_report`` 同一口径: 空报告 + 一条 warning, 不抛异常。
    """
    relation = ""
    spec = SEMANTIC_COVERAGE_DOMAINS.get(domain_name)
    if spec is not None:
        relation = spec.relation
    return SemanticCoverageReport(
        entries=(),
        empty_shell_rows=0,
        unresolved_rows=0,
        warnings=(
            f"语义覆盖率巡检跳过：{relation or domain_name} 不可用或查询失败"
            f"（{type(exc).__name__}）。",
        ),
        domain=domain_name,
        threshold=threshold,
    )


async def _reset_session_after_failure(db: AsyncSession) -> None:
    """把 session 从「事务已失败」状态里救回来。

    为什么需要它
    ------------
    PostgreSQL 里一条语句失败会让**整个事务进入 aborted 状态** ⇒ 后续再对同一个
    session 做任何操作都会抛 ``PendingRollbackError``。
    巡检失败(视图不存在 / DB 不可用)时正是这种状态 ⇒ 请求收尾时的
    ``session.commit()`` 会抛异常 ⇒ **HTTP 层就变成了 500**,
    「巡检失败不该把调用方带崩」的承诺就落空了。

    所以失败后先把事务回滚掉, 让收尾的 commit 干干净净 ⇒ 调用方拿到的是
    **200 + 空报告 + warning**。
    """
    try:
        await db.rollback()
    except Exception:  # noqa: BLE001 —— 回滚失败也不能影响本次响应
        logger.warning("[SemanticCoverage] 巡检事务回滚失败（已忽略）", exc_info=True)


async def _audit_coverage_domain(
    db: AsyncSession,
    service: SemanticCoverageAuditService,
    domain_name: str,
    threshold: float,
) -> SemanticCoverageReport:
    """对单个域做一次巡检, 并保证「失败也不抛异常」。"""
    try:
        report = await service.audit(db, domain=domain_name, threshold=threshold)
    except Exception as exc:  # noqa: BLE001 —— 巡检绝不能把调用方带崩
        # 服务层已吞掉 SQLAlchemyError; 这里兜住更外层的意外(例如会话已失效),
        # 保证 HTTP 层永远不 500。
        logger.warning(
            "[SemanticCoverage] 语义覆盖率巡检异常（%s）: %s", domain_name, exc
        )
        report = _skipped_coverage_report(domain_name, threshold, exc)

    if not report.entries:
        # 没拿到任何解析率条目 ⇒ 极可能是上面那次失败留下的 aborted 事务
        # ⇒ 回滚, 否则请求收尾的 commit 会把本次响应打成 500。
        await _reset_session_after_failure(db)
    return report


@router.get("/semantic-coverage")
async def get_semantic_coverage(
    domain: Optional[str] = Query(
        None,
        description="orders / products / all；不传则两个域都出（默认 all）",
    ),
    threshold: Optional[float] = Query(
        None,
        ge=0.0,
        le=1.0,
        description="解析率告警阈值（0~1）；不传沿用服务层默认 0.5",
    ),
    db: AsyncSession = Depends(get_async_db),
):
    """语义层标准字段覆盖率巡检（只读）。

    回答「某个标准字段（如 ``profit`` / ``platform_service_fee``）在源表里到底
    解析得出来吗、解析率多少、源表里真实列名叫啥」。

    * ``domain``: ``orders`` / ``products`` / ``all``；**不传默认两个域都出**。
    * ``threshold``: 解析率告警阈值（0~1）；不传沿用服务层默认 0.5。
    * **只读**：只发 SELECT, 不写库、不改视图。
    * **容错**：DB 不可用 / ``semantic`` 视图不存在时返回 **200 + 空报告 + warning**,
      不会把调用方带崩。
    """
    requested_domain = (domain or "all").strip().lower()
    if requested_domain not in {"all", *SEMANTIC_COVERAGE_DOMAINS}:
        # 参数写错是**调用方**的问题(与 DB 故障不同)⇒ 明确报 400, 不静默吞掉。
        raise HTTPException(
            status_code=400,
            detail=(
                f"未知的语义覆盖域：{domain}；"
                f"可选值：{', '.join(sorted(SEMANTIC_COVERAGE_DOMAINS))}, all"
            ),
        )

    if requested_domain == "all":
        target_domains = sorted(SEMANTIC_COVERAGE_DOMAINS)
    else:
        target_domains = [requested_domain]

    service = SemanticCoverageAuditService()
    effective_threshold = service.threshold if threshold is None else float(threshold)

    reports: List[Dict[str, Any]] = []
    for target_domain in target_domains:
        report = await _audit_coverage_domain(
            db, service, target_domain, effective_threshold
        )
        reports.append(_coverage_report_to_dict(report))

    return success_response(
        data={
            "domain": requested_domain,
            "threshold": effective_threshold,
            "reports": reports,
        }
    )
