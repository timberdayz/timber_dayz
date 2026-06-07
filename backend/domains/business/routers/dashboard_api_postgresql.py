"""
Clean PostgreSQL-backed dashboard router.

This module exists to avoid coupling the new PostgreSQL cutover work to the
legacy `dashboard_api.py`, which currently contains historical encoding noise.
Once PostgreSQL coverage is sufficient, `main.py` can switch router binding via
feature flag.
"""

from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import get_current_user
from backend.models.database import AsyncSessionLocal, get_async_db
from backend.services.data_pipeline.dashboard_bootstrap import inspect_dashboard_assets
from backend.services.postgresql_dashboard_service import _normalize_period_start, get_postgresql_dashboard_service
from backend.utils.api_response import error_response, success_response
from backend.utils.error_codes import ErrorCode
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard-postgresql"])
_B_COST_ALLOWED_ROLES = {"admin", "manager", "finance"}
_DASHBOARD_SINGLEFLIGHT_LOCK_TTL = 60
_DASHBOARD_SINGLEFLIGHT_WAIT_TIMEOUT = 35.0
_STORE_ANALYSIS_ALLOWED_ROLES = {"admin", "manager", "operator"}
_BUSINESS_OVERVIEW_CANONICAL_ONLY = os.getenv(
    "BUSINESS_OVERVIEW_CANONICAL_ONLY",
    "true",
).lower() in {"1", "true", "yes", "on"}
_BUSINESS_OVERVIEW_LEGACY_QUERY_KEYS = {
    "month",
    "date",
    "date_value",
    "platform",
    "platforms",
    "shops",
    "start_date",
    "end_date",
}

_DASHBOARD_MODULE_ROUTE_PREFIXES = {
    "clearance_ranking": ("/api/dashboard/clearance-ranking",),
    "business_overview": (
        "/api/dashboard/business-overview/",
        "/api/dashboard/store-analysis/",
        "/api/dashboard/b-cost-analysis/",
    ),
}


def _normalize_cache_params(params: Dict[str, Any]) -> Dict[str, str]:
    return {k: "" if v is None else str(v) for k, v in params.items()}


def _reject_business_overview_legacy_params(request: Request) -> None:
    if not _BUSINESS_OVERVIEW_CANONICAL_ONLY:
        return
    legacy = [key for key in _BUSINESS_OVERVIEW_LEGACY_QUERY_KEYS if key in request.query_params]
    if not legacy:
        return
    raise HTTPException(
        status_code=422,
        detail={
            "message": "Business Overview API no longer accepts legacy query params.",
            "legacy_params": legacy,
            "required_params": ["granularity", "period_key"],
            "optional_params": ["platform_code", "shop_id"],
        },
    )


async def _refresh_dashboard_assets_report(request: Request) -> dict[str, Any] | None:
    app = getattr(request, "app", None)
    if app is None:
        return None

    async with AsyncSessionLocal() as session:
        report = await inspect_dashboard_assets(session)

    try:
        app.state.dashboard_assets_report = report
        app.state.dashboard_assets_ready = bool(report.get("ready"))
    except Exception:
        pass
    return report


async def _require_dashboard_assets_ready(request: Request) -> None:
    def _resolve_dashboard_module_name(path: str) -> str | None:
        for module_name, prefixes in _DASHBOARD_MODULE_ROUTE_PREFIXES.items():
            if any(path.startswith(prefix) for prefix in prefixes):
                return module_name
        return None

    report = getattr(getattr(request, "app", None), "state", None)
    report = getattr(report, "dashboard_assets_report", None)
    if not isinstance(report, dict):
        report = await _refresh_dashboard_assets_report(request)
        if not isinstance(report, dict):
            return

    module_name = _resolve_dashboard_module_name(getattr(request, "url", None).path if getattr(request, "url", None) else request.scope.get("path", ""))
    modules = report.get("modules")
    module_report = modules.get(module_name) if isinstance(modules, dict) and module_name else None

    if isinstance(module_report, dict):
        if module_report.get("status") not in {"ready", "refreshing"}:
            report = await _refresh_dashboard_assets_report(request) or report
            modules = report.get("modules")
            module_report = modules.get(module_name) if isinstance(modules, dict) and module_name else module_report
        if isinstance(module_report, dict) and module_report.get("status") in {"ready", "refreshing"}:
            return
        detail: dict[str, Any] = {
            "message": "PostgreSQL dashboard assets are not ready. Run deploy-time bootstrap and retry.",
            "module_name": module_name,
            "status": module_report.get("status"),
            "ready": module_report.get("ready"),
            "assets_drift": module_report.get("assets_drift"),
            "core_missing_objects": module_report.get("core_missing_objects"),
            "refresh_missing_objects": module_report.get("refresh_missing_objects"),
            "asset_fingerprint_expected": module_report.get("asset_fingerprint_expected"),
            "asset_fingerprint_applied": module_report.get("asset_fingerprint_applied"),
            "refresh_fingerprint_expected": module_report.get("refresh_fingerprint_expected"),
            "refresh_fingerprint_applied": module_report.get("refresh_fingerprint_applied"),
            "hint": {
                "bootstrap_command": f"python scripts/bootstrap_postgresql_dashboard.py --module {module_name}",
                "startup_policy": "runtime only inspects readiness; SQL asset publish happens at deploy time",
            },
        }
        raise HTTPException(status_code=503, detail=detail)

    if report.get("ready") is True:
        return

    detail = {
        "message": "PostgreSQL dashboard assets are not ready. Run deploy-time bootstrap and retry.",
        "ready": report.get("ready"),
        "missing_schemas": report.get("missing_schemas"),
        "missing_objects": report.get("missing_objects"),
        "assets_drift": report.get("assets_drift"),
        "hint": {
            "bootstrap_command": "python scripts/bootstrap_postgresql_dashboard.py --module all",
            "startup_policy": "runtime only inspects readiness; SQL asset publish happens at deploy time",
        },
    }
    raise HTTPException(status_code=503, detail=detail)


@router.get("/assets/status")
async def get_dashboard_assets_status(request: Request):
    report = await _refresh_dashboard_assets_report(request)
    ready = bool(report.get("ready")) if isinstance(report, dict) else False
    return success_response(data={"ready": bool(ready), "report": report})

def _isoformat_utc_now_seconds() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return f"{now.isoformat()}Z"


def _normalize_business_overview_period_key(granularity: str, value: str) -> str:
    period_start = _normalize_period_start(value)
    normalized_granularity = (granularity or "monthly").strip().lower()
    if normalized_granularity == "daily":
        return period_start.isoformat()
    if normalized_granularity == "weekly":
        week_start = period_start - timedelta(days=period_start.weekday())
        return week_start.isoformat()
    if normalized_granularity == "monthly":
        month_start = date_cls(period_start.year, period_start.month, 1)
        return month_start.isoformat()
    raise ValueError("granularity must be daily, weekly or monthly")


def _detect_business_overview_empty_period(data: Any) -> bool:
    if data == []:
        return True
    if not isinstance(data, dict):
        return False
    bootstrap_keys = {"kpi", "comparison", "operational_metrics", "traffic_ranking", "shop_racing"}
    if bootstrap_keys.issubset(data.keys()):
        return (
            _detect_business_overview_empty_period(data.get("kpi"))
            and _detect_business_overview_empty_period(data.get("comparison"))
            and _detect_business_overview_empty_period(data.get("traffic_ranking"))
            and _detect_business_overview_empty_period(data.get("shop_racing"))
            and _detect_business_overview_empty_period(data.get("operational_metrics"))
        )
    if "monthly_target" in data and "monthly_total_achieved" in data:
        ignored_keys = {"meta"}
        for key, value in data.items():
            if key in ignored_keys:
                continue
            if value not in {0, 0.0, None}:
                return False
        return True
    if {"gmv", "order_count", "visitor_count", "profit"}.issubset(data.keys()):
        return (
            (data.get("gmv") in {0, 0.0})
            and (data.get("order_count") in {0})
            and (data.get("visitor_count") in {0})
            and (data.get("profit") in {0, 0.0})
            and (data.get("conversion_rate") is None)
            and (data.get("avg_order_value") is None)
            and (data.get("attach_rate") is None)
        )
    metrics = data.get("metrics")
    if isinstance(metrics, dict) and metrics:
        for metric in metrics.values():
            if not isinstance(metric, dict):
                return False
            if metric.get("change") is not None:
                return False
            for key in ("today", "yesterday", "average"):
                if metric.get(key) not in {0, 0.0, None}:
                    return False
        return True
    return False


def _apply_business_overview_empty_period_meta(meta: dict[str, Any], data: Any) -> dict[str, Any]:
    warnings = meta.get("warnings")
    if not isinstance(warnings, list):
        meta["warnings"] = []
    meta.setdefault("data_status", "ok")
    meta.setdefault("is_empty_period", False)

    if _detect_business_overview_empty_period(data):
        meta["data_status"] = "empty_period"
        meta["is_empty_period"] = True
        warning = "empty_period: no rows matched for the requested period"
        if warning not in meta["warnings"]:
            meta["warnings"].append(warning)
    return meta


def _wrap_business_overview_envelope(
    *,
    module_payload: Any,
    granularity: str,
    period_key: str,
    platform_code: Optional[str],
    shop_id: Optional[str] = None,
    cache_status: Optional[str] = None,
) -> dict[str, Any]:
    if isinstance(module_payload, dict) and {"meta", "data"}.issubset(module_payload.keys()):
        meta = module_payload.get("meta") if isinstance(module_payload.get("meta"), dict) else {}
        data = module_payload.get("data")
        module_payload["meta"] = _apply_business_overview_empty_period_meta(meta, data)
        return module_payload

    meta: dict[str, Any] = {
        "granularity": granularity,
        "period_key": period_key,
        "platform_code": platform_code,
        "shop_id": shop_id,
        "generated_at": _isoformat_utc_now_seconds(),
        "cache": {
            "status": cache_status,
            "hit": True if cache_status == "HIT" else False if cache_status in {"MISS", "BYPASS"} else None,
        },
        "warnings": [],
        "data_status": "ok",
        "is_empty_period": False,
    }
    _apply_business_overview_empty_period_meta(meta, module_payload)
    return {"meta": meta, "data": module_payload}


def _build_business_overview_meta(
    *,
    granularity: str,
    period_key: str,
    platform_code: Optional[str],
    shop_id: Optional[str] = None,
    cache_status: Optional[str] = None,
) -> dict[str, Any]:
    return {
        "granularity": granularity,
        "period_key": period_key,
        "platform_code": platform_code,
        "shop_id": shop_id,
        "generated_at": _isoformat_utc_now_seconds(),
        "cache": {
            "status": cache_status,
            "hit": True if cache_status == "HIT" else False if cache_status in {"MISS", "BYPASS"} else None,
        },
        "warnings": [],
        "data_status": "ok",
        "is_empty_period": False,
    }


def _normalize_period_month_for_cache(period_month: Optional[str]) -> Optional[str]:
    if period_month is None:
        return None
    try:
        normalized = _normalize_period_start(period_month)
        month_start = date_cls(normalized.year, normalized.month, 1)
        return month_start.isoformat()
    except Exception:
        return period_month


async def _resolve_cached_payload(
    request: Request,
    cache_type: str,
    cache_params: Dict[str, Any],
    producer,
):
    if request and hasattr(request.app.state, "cache_service"):
        cache_service = request.app.state.cache_service
        cached = await cache_service.get(cache_type, **cache_params)
        if cached is not None:
            return cached, "HIT"
        payload = await cache_service.get_or_set_singleflight(
            cache_type,
            producer,
            lock_ttl=_DASHBOARD_SINGLEFLIGHT_LOCK_TTL,
            wait_timeout=_DASHBOARD_SINGLEFLIGHT_WAIT_TIMEOUT,
            **cache_params,
        )
        return payload, "MISS"
    payload = await producer()
    return payload, "BYPASS"


def _extract_user_role_codes(current_user: Any) -> set[str]:
    role_codes: set[str] = set()
    for role in getattr(current_user, "roles", []) or []:
        if isinstance(role, str):
            role_codes.add(role.lower())
            continue
        role_code = getattr(role, "role_code", None)
        role_name = getattr(role, "role_name", None)
        if role_code:
            role_codes.add(str(role_code).lower())
        if role_name:
            role_codes.add(str(role_name).lower())
    return role_codes


def _require_b_cost_role(current_user: Any) -> Any:
    if getattr(current_user, "is_superuser", False):
        return current_user
    if _extract_user_role_codes(current_user) & _B_COST_ALLOWED_ROLES:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


async def _get_b_cost_authorized_user(current_user: Any = Depends(get_current_user)) -> Any:
    return _require_b_cost_role(current_user)


def _require_store_analysis_role(current_user: Any) -> Any:
    if getattr(current_user, "is_superuser", False):
        return current_user
    if _extract_user_role_codes(current_user) & _STORE_ANALYSIS_ALLOWED_ROLES:
        return current_user
    raise HTTPException(status_code=403, detail="Insufficient permissions")


async def _get_store_analysis_authorized_user(current_user: Any = Depends(get_current_user)) -> Any:
    return _require_store_analysis_role(current_user)


@router.get("/business-overview/kpi")
async def get_business_overview_kpi_postgresql(
    request: Request,
    granularity: Optional[str] = Query(None, description="daily/weekly/monthly"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        granularity_value = granularity if isinstance(granularity, str) else None
        effective_granularity = (granularity_value or "monthly").strip().lower()
        effective_platform_code = platform_code
        effective_date = period_key
        params = {
            "granularity": effective_granularity,
            "period_key": effective_date,
            "platform_code": effective_platform_code,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_kpi(
                month=effective_date,
                platform=effective_platform_code,
                granularity=effective_granularity,
                target_date=effective_date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_kpi",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            period_key = _normalize_business_overview_period_key(effective_granularity, effective_date)
            payload["meta"] = _build_business_overview_meta(
                granularity=effective_granularity,
                period_key=period_key,
                platform_code=effective_platform_code,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except HTTPException:
        raise
    except HTTPException:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL KPI query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/comparison")
async def get_business_overview_comparison_postgresql(
    request: Request,
    granularity: str = Query(..., description="daily/weekly/monthly"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        effective_platform_code = platform_code
        effective_period_key = period_key
        params = {
            "granularity": granularity,
            "period_key": effective_period_key,
            "platform_code": effective_platform_code,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_comparison(
                granularity=granularity,
                target_date=effective_period_key,
                platform=effective_platform_code,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_comparison",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            normalized_period_key = _normalize_business_overview_period_key(granularity, effective_period_key)
            payload["meta"] = _build_business_overview_meta(
                granularity=granularity,
                period_key=normalized_period_key,
                platform_code=effective_platform_code,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except HTTPException:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL comparison query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/bootstrap")
async def get_business_overview_bootstrap_postgresql(
    request: Request,
    granularity: Optional[str] = Query(None, description="daily/weekly/monthly"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        granularity_value = granularity if isinstance(granularity, str) else None
        effective_granularity = (granularity_value or "monthly").strip().lower()
        effective_platform_code = platform_code
        effective_date = period_key

        period = _normalize_period_start(effective_date)
        effective_operational_month = date_cls(period.year, period.month, 1).isoformat()

        params = {
            "granularity": effective_granularity,
            "period_key": effective_date,
            "platform_code": effective_platform_code,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            started = time.perf_counter()
            kpi_started = time.perf_counter()
            kpi_result = await service.get_business_overview_kpi(
                month=effective_date,
                platform=effective_platform_code,
                granularity=effective_granularity,
                target_date=effective_date,
            )
            kpi_ms = (time.perf_counter() - kpi_started) * 1000.0

            comparison_started = time.perf_counter()
            comparison_result = await service.get_business_overview_comparison(
                granularity=effective_granularity,
                target_date=effective_date,
                platform=effective_platform_code,
            )
            comparison_ms = (time.perf_counter() - comparison_started) * 1000.0

            operational_started = time.perf_counter()
            operational_result = await service.get_business_overview_operational_metrics(
                month=effective_operational_month,
                platform=effective_platform_code,
            )
            operational_ms = (time.perf_counter() - operational_started) * 1000.0

            traffic_started = time.perf_counter()
            traffic_ranking_result = await service.get_business_overview_traffic_ranking(
                granularity=effective_granularity,
                target_date=effective_date,
                dimension="shop",
                platform=effective_platform_code,
            )
            traffic_ms = (time.perf_counter() - traffic_started) * 1000.0

            shop_racing_started = time.perf_counter()
            shop_racing_result = await service.get_business_overview_shop_racing(
                granularity=effective_granularity,
                target_date=effective_date,
                group_by="shop",
                platform=effective_platform_code,
            )
            shop_racing_ms = (time.perf_counter() - shop_racing_started) * 1000.0
            total_ms = (time.perf_counter() - started) * 1000.0

            # Observability: break down slow bootstrap into its subcalls.
            # Keep threshold consistent with middleware's "slow request" concept.
            if total_ms >= 1000 or max(kpi_ms, comparison_ms, operational_ms, traffic_ms, shop_racing_ms) >= 1000:
                logger.warning(
                    "[slow_breakdown] /api/dashboard/business-overview/bootstrap "
                    f"total={total_ms:.2f}ms kpi={kpi_ms:.2f}ms comparison={comparison_ms:.2f}ms "
                    f"operational={operational_ms:.2f}ms traffic_ranking={traffic_ms:.2f}ms "
                    f"shop_racing={shop_racing_ms:.2f}ms "
                    f"granularity={effective_granularity} period_key={effective_date} month={effective_operational_month} "
                    f"platform={effective_platform_code or ''}"
                )
            return json.loads(
                success_response(
                    data={
                        "kpi": kpi_result,
                        "comparison": comparison_result,
                        "operational_metrics": operational_result,
                        "traffic_ranking": traffic_ranking_result,
                        "shop_racing": shop_racing_result,
                    }
                ).body.decode()
            )

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_business_overview_bootstrap",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            period_key = _normalize_business_overview_period_key(effective_granularity, effective_date)
            payload["meta"] = _build_business_overview_meta(
                granularity=effective_granularity,
                period_key=period_key,
                platform_code=effective_platform_code,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except HTTPException:
        raise
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL business overview bootstrap query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


# annual-summary removed pre-launch
async def get_annual_summary_kpi_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_kpi(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_kpi",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary KPI query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/shop-racing")
async def get_business_overview_shop_racing_postgresql(
    request: Request,
    granularity: str = Query(..., description="granularity"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    group_by: str = Query("shop", description="grouping dimension"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        effective_platform = platform_code
        effective_period_key = period_key
        params = {
            "granularity": granularity,
            "period_key": effective_period_key,
            "group_by": group_by,
            "platform_code": effective_platform,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_shop_racing(
                granularity=granularity,
                target_date=effective_period_key,
                group_by=group_by,
                platform=effective_platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_shop_racing",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            normalized_period_key = _normalize_business_overview_period_key(granularity, effective_period_key)
            payload["meta"] = _build_business_overview_meta(
                granularity=granularity,
                period_key=normalized_period_key,
                platform_code=effective_platform,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility shop racing query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/traffic-ranking")
async def get_business_overview_traffic_ranking_postgresql(
    request: Request,
    granularity: str = Query(..., description="granularity"),
    dimension: str = Query("visitor", description="ranking dimension"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        target_date = period_key
        effective_platform = platform_code
        params = {
            "granularity": granularity,
            "dimension": dimension,
            "period_key": target_date,
            "platform_code": effective_platform,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_traffic_ranking(
                granularity=granularity,
                target_date=target_date,
                dimension=dimension,
                platform=effective_platform,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_traffic_ranking",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            period_key = _normalize_business_overview_period_key(granularity, target_date)
            payload["meta"] = _build_business_overview_meta(
                granularity=granularity,
                period_key=period_key,
                platform_code=effective_platform,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility traffic ranking query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/inventory-backlog")
async def get_business_overview_inventory_backlog_postgresql(
    request: Request,
    days: Optional[int] = Query(30, description="minimum turnover days"),
    limit: int = Query(20, ge=1, le=200, description="row limit"),
    granularity: Optional[str] = Query(None, description="daily/weekly/monthly"),
    date: Optional[str] = Query(None, description="anchor date"),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"days": days, "limit": limit, "granularity": granularity, "date": date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_inventory_backlog(
                min_days=days or 30,
                limit=limit,
                granularity=granularity,
                target_date=date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_inventory_backlog",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL inventory backlog query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/business-overview/operational-metrics")
async def get_business_overview_operational_metrics_postgresql(
    request: Request,
    granularity: Optional[str] = Query(None, description="canonical granularity (only monthly supported)"),
    period_key: str = Query(..., description="canonical period key (ISO date)"),
    platform_code: Optional[str] = Query(None, description="canonical platform code"),
    shop_id: Optional[str] = Query(None, description="canonical shop id"),
):
    try:
        await _require_dashboard_assets_ready(request)
        _reject_business_overview_legacy_params(request)
        if granularity and str(granularity).strip().lower() != "monthly":
            raise ValueError("granularity must be monthly")
        effective_platform_code = platform_code
        effective_month = _normalize_business_overview_period_key("monthly", period_key)
        params = {
            "granularity": "monthly",
            "period_key": effective_month,
            "platform_code": effective_platform_code,
            "shop_id": shop_id,
        }
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_business_overview_operational_metrics(
                month=effective_month,
                platform=effective_platform_code,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_operational_metrics",
            cache_params,
            _produce_payload,
        )
        if isinstance(payload, dict) and payload.get("success") is True and "data" in payload:
            period_key = _normalize_business_overview_period_key("monthly", effective_month)
            payload["meta"] = _build_business_overview_meta(
                granularity="monthly",
                period_key=period_key,
                platform_code=effective_platform_code,
                shop_id=shop_id,
                cache_status=cache_status,
            )
            if isinstance(payload.get("meta"), dict):
                _apply_business_overview_empty_period_meta(payload["meta"], payload.get("data"))
                if effective_platform_code and isinstance(payload.get("data"), dict):
                    data_meta = payload["data"].get("meta") if isinstance(payload["data"], dict) else None
                    warnings = payload["meta"].get("warnings")
                    if not isinstance(warnings, list):
                        payload["meta"]["warnings"] = []
                        warnings = payload["meta"]["warnings"]
                    if isinstance(data_meta, dict) and isinstance(data_meta.get("warnings"), list):
                        for warning in data_meta["warnings"]:
                            if warning not in warnings:
                                warnings.append(warning)
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL compatibility operational metrics query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


@router.get("/store-analysis/capabilities")
async def get_store_analysis_capabilities_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_capabilities(platform=platform, shop_id=shop_id)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_capabilities",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis capabilities query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/shops")
async def get_store_analysis_shops_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_shops(platform=platform)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_shops",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis shops query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/overview")
async def get_store_analysis_overview_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    granularity: str = Query(..., description="daily/weekly/monthly/quarterly/yearly"),
    date: str = Query(..., description="anchor date"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id, "granularity": granularity, "date": date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_overview(
                platform=platform,
                shop_id=shop_id,
                granularity=granularity,
                target_date=date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_overview",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis overview query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/comparison")
async def get_store_analysis_comparison_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    granularity: str = Query(..., description="daily/weekly/monthly/quarterly/yearly"),
    date: str = Query(..., description="anchor date"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id, "granularity": granularity, "date": date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_comparison(
                platform=platform,
                shop_id=shop_id,
                granularity=granularity,
                target_date=date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_comparison",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis comparison query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/top-products")
async def get_store_analysis_top_products_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    granularity: str = Query(..., description="daily/weekly/monthly/quarterly/yearly"),
    date: str = Query(..., description="anchor date"),
    limit: int = Query(10, ge=1, le=50, description="top product count"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id, "granularity": granularity, "date": date, "limit": limit}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_top_products(
                platform=platform,
                shop_id=shop_id,
                granularity=granularity,
                target_date=date,
                limit=limit,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_top_products",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis top products query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/traffic-summary")
async def get_store_analysis_traffic_summary_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    granularity: str = Query(..., description="daily/weekly/monthly/quarterly/yearly"),
    date: str = Query(..., description="anchor date"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id, "granularity": granularity, "date": date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_traffic_summary(
                platform=platform,
                shop_id=shop_id,
                granularity=granularity,
                target_date=date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_traffic_summary",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis traffic summary query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/store-analysis/traffic-trend")
async def get_store_analysis_traffic_trend_postgresql(
    request: Request,
    platform: str = Query(..., description="single platform code"),
    shop_id: str = Query(..., description="shop id"),
    granularity: str = Query(..., description="daily/weekly/monthly/quarterly/yearly"),
    date: str = Query(..., description="anchor date"),
    _current_user: Any = Depends(_get_store_analysis_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"platform": platform, "shop_id": shop_id, "granularity": granularity, "date": date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_store_analysis_traffic_trend(
                platform=platform,
                shop_id=shop_id,
                granularity=granularity,
                target_date=date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "store_analysis_traffic_trend",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"Store analysis traffic trend query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"鏌ヨ澶辫触: {str(e)}", status_code=500)


@router.get("/b-cost-analysis/overview")
async def get_b_cost_analysis_overview_postgresql(
    request: Request,
    period_month: str = Query(..., description="month in YYYY-MM or YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="single platform code"),
    shop_id: Optional[str] = Query(None, description="shop id filter"),
    _current_user: Any = Depends(_get_b_cost_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"period_month": period_month, "platform": platform, "shop_id": shop_id}
        cache_params = _normalize_cache_params(
            {
                "period_month": _normalize_period_month_for_cache(period_month),
                "platform": platform,
                "shop_id": shop_id,
            }
        )

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_b_cost_analysis_overview(
                period_month=period_month,
                platform=platform,
                shop_id=shop_id,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "b_cost_analysis_overview",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL b cost analysis overview query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, "查询失败", status_code=500)


@router.get("/b-cost-analysis/shop-month")
async def get_b_cost_analysis_shop_month_postgresql(
    request: Request,
    period_month: str = Query(..., description="month in YYYY-MM or YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="single platform code"),
    shop_id: Optional[str] = Query(None, description="shop id filter"),
    _current_user: Any = Depends(_get_b_cost_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"period_month": period_month, "platform": platform, "shop_id": shop_id}
        cache_params = _normalize_cache_params(
            {
                "period_month": _normalize_period_month_for_cache(period_month),
                "platform": platform,
                "shop_id": shop_id,
            }
        )

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_b_cost_analysis_shop_month(
                period_month=period_month,
                platform=platform,
                shop_id=shop_id,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "b_cost_analysis_shop_month",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL b cost analysis shop month query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, "查询失败", status_code=500)


@router.get("/b-cost-analysis/order-detail")
async def get_b_cost_analysis_order_detail_postgresql(
    request: Request,
    period_month: str = Query(..., description="month in YYYY-MM or YYYY-MM-DD"),
    platform: Optional[str] = Query(None, description="single platform code"),
    shop_id: Optional[str] = Query(None, description="shop id filter"),
    page: int = Query(1, description="page number"),
    page_size: int = Query(20, le=200, description="page size"),
    _current_user: Any = Depends(_get_b_cost_authorized_user),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {
            "period_month": period_month,
            "platform": platform,
            "shop_id": shop_id,
            "page": page,
            "page_size": page_size,
        }
        cache_params = _normalize_cache_params(
            {
                **params,
                "period_month": _normalize_period_month_for_cache(period_month),
            }
        )

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_b_cost_analysis_order_detail(
                period_month=period_month,
                platform=platform,
                shop_id=shop_id,
                page=page,
                page_size=page_size,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "b_cost_analysis_order_detail",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL b cost analysis order detail query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, "查询失败", status_code=500)


@router.get("/clearance-ranking")
async def get_clearance_ranking_postgresql(
    request: Request,
    limit: int = Query(100, description="row limit"),
    granularity: Optional[str] = Query(None, description="daily/weekly/monthly"),
    date: Optional[str] = Query(None, description="anchor date"),
    month: Optional[str] = Query(None, description="legacy month alias"),
):
    try:
        await _require_dashboard_assets_ready(request)
        target_date = date or month
        params = {"limit": limit, "granularity": granularity, "date": target_date}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_clearance_ranking(
                limit=limit,
                granularity=granularity,
                target_date=target_date,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "dashboard_clearance_ranking",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except HTTPException:
        raise
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL clearance ranking query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


# annual-summary removed pre-launch
async def get_annual_summary_trend_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_trend(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_trend",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary trend query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


# annual-summary removed pre-launch
async def get_annual_summary_platform_share_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_platform_share(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_platform_share",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary platform share query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


# annual-summary removed pre-launch
async def get_annual_summary_by_shop_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_by_shop(granularity=granularity, period=period)
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_by_shop",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary by shop query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)


# annual-summary removed pre-launch
async def get_annual_summary_target_completion_postgresql(
    request: Request,
    granularity: str = Query(..., description="monthly|yearly"),
    period: str = Query(..., description="YYYY-MM or YYYY"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        await _require_dashboard_assets_ready(request)
        params = {"granularity": granularity, "period": period}
        cache_params = _normalize_cache_params(params)

        async def _produce_payload():
            service = get_postgresql_dashboard_service()
            result = await service.get_annual_summary_target_completion(
                db=db,
                granularity=granularity,
                period=period,
            )
            return json.loads(success_response(data=result).body.decode())

        payload, cache_status = await _resolve_cached_payload(
            request,
            "annual_summary_target_completion",
            cache_params,
            _produce_payload,
        )
        return JSONResponse(content=payload, headers={"X-Cache": cache_status})
    except ValueError as e:
        return error_response(ErrorCode.PARAMETER_INVALID, str(e), status_code=400)
    except Exception as e:
        logger.error(f"PostgreSQL annual summary target completion query failed: {e}", exc_info=True)
        return error_response(ErrorCode.DATABASE_QUERY_ERROR, f"查询失败: {str(e)}", status_code=500)
