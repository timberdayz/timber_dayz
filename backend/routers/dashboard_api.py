from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

from fastapi.responses import JSONResponse


def get_metabase_service():  # pragma: no cover
    raise RuntimeError("get_metabase_service is not wired; tests should monkeypatch it")


async def _resolve_cached_payload_singleflight(
    request,
    *,
    cache_key: str,
    cache_params: dict[str, str] | None,
    producer: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    cache_service = getattr(getattr(request, "app", None), "state", None)
    cache_service = getattr(cache_service, "cache_service", None)
    if cache_service is None:
        return await producer()

    payload = await cache_service.get_or_set_singleflight(
        cache_key,
        cache_params or {},
        producer,
    )
    return payload


def _json_response(payload: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content=payload)


async def get_business_overview_kpi(
    request,
    month: Optional[str] = None,
    platform: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    platforms: Optional[str] = None,
    shops: Optional[str] = None,
):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        params = {"month": month, "platform": platform}
        result = await service.query_question("business_overview_kpi", {k: v for k, v in params.items() if v is not None})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="business_overview_kpi",
        cache_params={"month": str(month or ""), "platform": str(platform or "")},
        producer=_producer,
    )
    return _json_response(payload)


async def get_business_overview_comparison(
    request,
    granularity: str,
    date: str,
    platforms: Optional[str] = None,
    shops: Optional[str] = None,
):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        params = {"granularity": granularity, "date": date, "platforms": platforms, "shops": shops}
        result = await service.query_question("business_overview_comparison", {k: v for k, v in params.items() if v is not None})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="business_overview_comparison",
        cache_params={"granularity": granularity, "date": date},
        producer=_producer,
    )
    return _json_response(payload)


async def get_business_overview_shop_racing(
    request,
    granularity: str,
    date: str,
    group_by: str,
    platforms: Optional[str] = None,
):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        params = {"granularity": granularity, "date": date, "group_by": group_by, "platforms": platforms}
        result = await service.query_question("business_overview_shop_racing", {k: v for k, v in params.items() if v is not None})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="business_overview_shop_racing",
        cache_params={"granularity": granularity, "date": date, "group_by": group_by},
        producer=_producer,
    )
    return _json_response(payload)


async def get_business_overview_traffic_ranking(
    request,
    granularity: str,
    dimension: str,
    date_value: str,
    platforms: Optional[str] = None,
    shops: Optional[str] = None,
):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        params = {
            "granularity": granularity,
            "dimension": dimension,
            "date_value": date_value,
            "platforms": platforms,
            "shops": shops,
        }
        result = await service.query_question("business_overview_traffic_ranking", {k: v for k, v in params.items() if v is not None})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="business_overview_traffic_ranking",
        cache_params={"granularity": granularity, "dimension": dimension, "date": date_value},
        producer=_producer,
    )
    return _json_response(payload)


async def get_annual_summary_kpi(request, db, granularity: str, period: str):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        result = await service.query_question("annual_summary_kpi", {"granularity": granularity, "period": period})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="annual_summary_kpi",
        cache_params={"granularity": granularity, "period": period},
        producer=_producer,
    )
    return _json_response(payload)


async def get_annual_summary_trend(request, granularity: str, period: str):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        result = await service.query_question("annual_summary_trend", {"granularity": granularity, "period": period})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="annual_summary_trend",
        cache_params={"granularity": granularity, "period": period},
        producer=_producer,
    )
    return _json_response(payload)


async def get_annual_summary_platform_share(request, granularity: str, period: str):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        service = get_metabase_service()
        result = await service.query_question("annual_summary_platform_share", {"granularity": granularity, "period": period})
        return {"success": True, "data": result, "message": "ok"}

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="annual_summary_platform_share",
        cache_params={"granularity": granularity, "period": period},
        producer=_producer,
    )
    return _json_response(payload)


async def get_annual_summary_by_shop(request, db, granularity: str, period: str):
    async def _producer() -> dict[str, Any]:  # pragma: no cover
        raise RuntimeError("annual summary by shop producer not wired")

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="annual_summary_by_shop",
        cache_params={"granularity": granularity, "period": period},
        producer=_producer,
    )
    return _json_response(payload)


async def get_annual_summary_target_completion(request, db, granularity: str, period: str):
    async def _producer() -> dict[str, Any]:
        # If cache isn't available, run a minimal fallback query flow used by tests.
        params = {"period": period}
        try:
            result = await db.execute("SELECT target_sales_amount, target_order_count FROM mart.targets WHERE period = :period", params)
            row = result.fetchone()
            target_gmv = float(row[0] or 0)
            target_orders = int(row[1] or 0)
        except Exception:
            await db.rollback()
            fallback_sql = (
                'SELECT "目标销售额" AS target_gmv, "目标订单数" AS target_orders '
                'FROM mart.targets_cn WHERE "年月" = :period'
            )
            result = await db.execute(fallback_sql, params)
            row = result.fetchone()
            target_gmv = float(row[0] or 0)
            target_orders = int(row[1] or 0)

        achieved = await get_metabase_service().query_question(
            "annual_summary_kpi",
            {"granularity": granularity, "period": period},
        )
        achieved_gmv = float((achieved or {}).get("gmv") or 0)
        achievement_rate = (achieved_gmv / target_gmv * 100.0) if target_gmv else None

        payload = {
            "success": True,
            "data": {
                "target_gmv": target_gmv,
                "target_orders": target_orders,
                "achieved_gmv": achieved_gmv,
                "achievement_rate_gmv": achievement_rate,
            },
            "message": "ok",
        }
        return payload

    payload = await _resolve_cached_payload_singleflight(
        request,
        cache_key="annual_summary_target_completion",
        cache_params={"granularity": granularity, "period": period},
        producer=_producer,
    )
    return _json_response(payload)
