"""
Dashboard 缓存预热服务（4c8g 单机优化）

在 Backend 启动后或定时任务中对 P1 业务概览 Question 进行限流预热，
减轻首访或高峰时对 Metabase/DB 的压力。配置通过环境变量读取，禁止硬编码敏感信息。
"""

import os
import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Tuple
from modules.core.logger import get_logger

logger = get_logger(__name__)

# P1 业务概览 Question 名称列表（与 proposal 一致）；可通过 ENV METABASE_WARMUP_P1_QUESTIONS 覆盖
_DEFAULT_P1_QUESTIONS = [
    "business_overview_kpi",
    "business_overview_comparison",
    "business_overview_shop_racing",
    "business_overview_traffic_ranking",
    "business_overview_inventory_backlog",
    "business_overview_operational_metrics",
    "clearance_ranking",
]

# question_name -> (cache_type, 默认参数字典；值可为 callable() 表示运行时计算)
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


def get_p1_question_list() -> List[str]:
    """
    从环境变量 METABASE_WARMUP_P1_QUESTIONS 读取（逗号分隔），
    未配置时使用默认 P1 列表。禁止在业务代码中散落硬编码 Question ID。
    """
    env_val = os.getenv("METABASE_WARMUP_P1_QUESTIONS", "").strip()
    if env_val:
        return [q.strip() for q in env_val.split(",") if q.strip()]
    return list(_DEFAULT_P1_QUESTIONS)


async def run_dashboard_cache_warmup() -> Dict[str, Any]:
    """
    执行 Dashboard P1 缓存预热：串行、限流（一次只打一个 Question），
    Metabase 不可用时跳过本轮并记录日志；单次失败不阻塞，仅打告警日志。

    Returns:
        {"skipped": True, "reason": "..."} 或 {"ok": N, "failed": M, "errors": [...]}
    """
    from backend.services.cache_service import get_cache_service
    from backend.services.metabase_question_service import (
        get_metabase_service,
        MetabaseUnavailableError,
    )

    cache_service = get_cache_service()
    if not cache_service.redis_client:
        logger.warning("[CacheWarmup] Redis 未启用，跳过预热")
        return {"skipped": True, "reason": "redis_unavailable"}

    service = get_metabase_service()
    questions = get_p1_question_list()
    if not questions:
        logger.info("[CacheWarmup] P1 列表为空，跳过预热")
        return {"skipped": True, "reason": "empty_p1_list"}

    ok = 0
    failed = 0
    errors: List[str] = []
    for question_name in questions:
        if question_name not in _WARMUP_SPEC:
            errors.append(f"unknown_spec:{question_name}")
            failed += 1
            continue
        cache_type, raw_params = _WARMUP_SPEC[question_name]
        params = _resolve_params(raw_params)
        cache_params = _normalize_cache_params(params)
        metabase_params = {k: v for k, v in params.items() if v is not None}
        try:
            result = await service.query_question(question_name, metabase_params)
            response = {
                "success": True,
                "data": result,
                "message": "操作成功",
            }
            await cache_service.set(cache_type, response, **cache_params)
            ok += 1
        except MetabaseUnavailableError as e:
            logger.warning(
                f"[CacheWarmup] Metabase 不可用或熔断，跳过本轮预热(已预热 {ok} 项): {e}"
            )
            return {"skipped": True, "reason": "metabase_unavailable", "ok_so_far": ok}
        except Exception as e:
            logger.warning(
                f"[CacheWarmup] 预热失败 question={question_name}: {e}",
                exc_info=True,
            )
            errors.append(f"{question_name}:{str(e)}")
            failed += 1
    logger.info(f"[CacheWarmup] 完成: ok={ok}, failed={failed}")
    return {"ok": ok, "failed": failed, "errors": errors}
