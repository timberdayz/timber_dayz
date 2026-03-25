"""
Dashboard 缓存预热服务（4c8g 单机优化）

在 Backend 启动后或定时任务中对 P1 PostgreSQL Dashboard 主链进行限流预热，
减轻首访或高峰时对 PostgreSQL 的压力。配置通过环境变量读取，禁止硬编码敏感信息。
"""

import os
import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from modules.core.logger import get_logger
from backend.services.cache_service import get_cache_service
from backend.services.postgresql_dashboard_service import get_postgresql_dashboard_service

logger = get_logger(__name__)

# P1 业务概览预热入口列表；可通过 ENV POSTGRESQL_DASHBOARD_WARMUP_TARGETS 覆盖
_DEFAULT_P1_TARGETS = [
    "business_overview_kpi",
    "business_overview_comparison",
    "business_overview_shop_racing",
    "business_overview_traffic_ranking",
    "business_overview_inventory_backlog",
    "business_overview_operational_metrics",
    "clearance_ranking",
]

# target_name -> (cache_type, 默认参数字典；值可为 callable() 表示运行时计算)
_WARMUP_SPEC: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "business_overview_kpi": (
        "dashboard_kpi",
        {"month": lambda: _current_month(), "platform": None},
    ),
    "business_overview_comparison": (
        "dashboard_comparison",
        {
            "granularity": "monthly",
            "date": lambda: _current_month(),
            "platforms": None,
            "shops": None,
        },
    ),
    "business_overview_shop_racing": (
        "dashboard_shop_racing",
        {
            "granularity": "monthly",
            "date": lambda: _current_month(),
            "group_by": "shop",
            "platforms": None,
        },
    ),
    "business_overview_traffic_ranking": (
        "dashboard_traffic_ranking",
        {
            "granularity": "monthly",
            "dimension": "visitor",
            "date_value": lambda: _current_month(),
            "platforms": None,
            "shops": None,
        },
    ),
    "business_overview_inventory_backlog": (
        "dashboard_inventory_backlog",
        {"days": None, "platforms": None, "shops": None},
    ),
    "business_overview_operational_metrics": (
        "dashboard_operational_metrics",
        {"month": lambda: _current_month(), "platform": None},
    ),
    "clearance_ranking": (
        "dashboard_clearance_ranking",
        {
            "start_date": lambda: _current_month(),
            "end_date": lambda: _month_end(),
            "platforms": None,
            "shops": None,
            "limit": 10,
        },
    ),
}


def _current_month() -> str:
    """当前月份月初 YYYY-MM-01"""
    t = date.today()
    return t.replace(day=1).isoformat()


def _month_end() -> str:
    """当前月最后一天 YYYY-MM-DD"""
    t = date.today()
    # 下月1日 - 1 天
    if t.month == 12:
        next_first = date(t.year + 1, 1, 1)
    else:
        next_first = date(t.year, t.month + 1, 1)
    from datetime import timedelta
    return (next_first - timedelta(days=1)).isoformat()


def _resolve_params(raw: Dict[str, Any]) -> Dict[str, Any]:
    """将 value 中的 callable 替换为调用结果"""
    out: Dict[str, Any] = {}
    for k, v in raw.items():
        if callable(v):
            out[k] = v()
        else:
            out[k] = v
    return out


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    """与 dashboard_api 一致：None 转为空字符串，保证缓存 key 一致"""
    return {k: "" if v is None else str(v) for k, v in params.items()}


def get_p1_target_list() -> List[str]:
    """
    从环境变量 POSTGRESQL_DASHBOARD_WARMUP_TARGETS 读取（逗号分隔），
    未配置时使用默认 P1 列表。禁止在业务代码中散落硬编码 dashboard target 标识。
    """
    env_val = os.getenv("POSTGRESQL_DASHBOARD_WARMUP_TARGETS", "").strip()
    if env_val:
        return [q.strip() for q in env_val.split(",") if q.strip()]
    return list(_DEFAULT_P1_TARGETS)


async def run_dashboard_cache_warmup() -> Dict[str, Any]:
    """
    执行 Dashboard P1 缓存预热：串行、限流（一次只预热一个入口），
    仅预热 PostgreSQL service。

    Returns:
        {"skipped": True, "reason": "..."} 或 {"ok": N, "failed": M, "errors": [...]}
    """
    cache_service = get_cache_service()
    if not cache_service.redis_client:
        logger.warning("[CacheWarmup] Redis 未启用，跳过预热")
        return {"skipped": True, "reason": "redis_unavailable"}

    targets = get_p1_target_list()
    if not targets:
        logger.info("[CacheWarmup] P1 列表为空，跳过预热")
        return {"skipped": True, "reason": "empty_p1_list"}

    use_postgresql = os.getenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not use_postgresql:
        raise RuntimeError("Legacy non-PostgreSQL warmup path has been retired")

    postgresql_service = get_postgresql_dashboard_service()

    ok = 0
    failed = 0
    errors: List[str] = []
    for target_name in targets:
        if target_name not in _WARMUP_SPEC:
            errors.append(f"unknown_spec:{target_name}")
            failed += 1
            continue
        cache_type, raw_params = _WARMUP_SPEC[target_name]
        params = _resolve_params(raw_params)
        cache_params = _normalize_cache_params(params)
        try:
            result = await _query_postgresql_dashboard(postgresql_service, target_name, params)
            response = {
                "success": True,
                "data": result,
                "message": "操作成功",
            }
            await cache_service.set(cache_type, response, **cache_params)
            ok += 1
        except Exception as e:
            logger.warning(
                f"[CacheWarmup] 预热失败 target={target_name}: {e}",
                exc_info=True,
            )
            errors.append(f"{target_name}:{str(e)}")
            failed += 1
    logger.info(f"[CacheWarmup] 完成: ok={ok}, failed={failed}")
    return {"ok": ok, "failed": failed, "errors": errors}


async def _query_postgresql_dashboard(service, target_name: str, params: Dict[str, Any]) -> Any:
    if target_name == "business_overview_kpi":
        return await service.get_business_overview_kpi(
            month=params.get("month"),
            platform=params.get("platform"),
        )
    if target_name == "business_overview_comparison":
        return await service.get_business_overview_comparison(
            granularity=params.get("granularity"),
            target_date=params.get("date"),
            platform=_first_csv_value(params.get("platforms")),
        )
    if target_name == "business_overview_shop_racing":
        return await service.get_business_overview_shop_racing(
            granularity=params.get("granularity"),
            target_date=params.get("date"),
            group_by=params.get("group_by", "shop"),
        )
    if target_name == "business_overview_traffic_ranking":
        return await service.get_business_overview_traffic_ranking(
            granularity=params.get("granularity"),
            target_date=params.get("date_value") or params.get("date"),
            dimension=params.get("dimension", "visitor"),
        )
    if target_name == "business_overview_inventory_backlog":
        days = params.get("days")
        return await service.get_business_overview_inventory_backlog(min_days=int(days) if days else 30)
    if target_name == "business_overview_operational_metrics":
        return await service.get_business_overview_operational_metrics(
            month=params.get("month"),
            platform=params.get("platform"),
        )
    if target_name == "clearance_ranking":
        limit = params.get("limit")
        return await service.get_clearance_ranking(limit=int(limit) if limit else 10)
    raise ValueError(f"unsupported_postgresql_warmup_target:{target_name}")


def _first_csv_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.split(",", 1)[0].strip() or None
