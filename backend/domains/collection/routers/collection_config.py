"""
Collection config and collection account APIs.

Split from `collection.py` to keep endpoint groups focused.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.collection import (
    CollectionAccountGroupRegionResponse,
    CollectionAccountGroupResponse,
    CollectionAccountResponse,
    CollectionConfigBatchCreate,
    CollectionConfigBulkApplyTimeSelectionRequest,
    CollectionConfigBulkApplyTimeSelectionResponse,
    CollectionConfigFutureBatchCreateRequest,
    CollectionConfigFutureBatchCreateResponse,
    CollectionConfigBulkAdvanceRequest,
    CollectionConfigBulkAdvanceResponse,
    CollectionConfigBulkRunRequest,
    CollectionConfigBulkRunResponse,
    CollectionConfigTemplateBackfillResponse,
    CollectionConfigBatchRemediationCreatedItem,
    CollectionConfigBatchRemediationRequest,
    CollectionConfigBatchRemediationResponse,
    CollectionConfigBatchRemediationSkippedItem,
    CollectionConfigBatchResponse,
    CollectionConfigCoverageItem,
    CollectionConfigCoverageResponse,
    CollectionConfigCoverageSummary,
    CollectionConfigCreate,
    CollectionConfigResponse,
    CollectionConfigTemplateCreate,
    CollectionConfigTemplateSummaryResponse,
    CollectionConfigTemplateUpdate,
    CollectionConfigUpdate,
    TimeSelectionPayload,
)
from backend.schemas.common import SuccessResponse
from backend.services.collection_contracts import (
    DEFAULT_GRANULARITY_DATE_RANGE_TYPE,
    TIME_PRESET_TO_GRANULARITY,
    build_date_range_from_time_selection,
    build_time_window_preview,
    build_legacy_collection_date_fields,
    build_default_sub_domains,
    derive_granularity_from_time_selection,
    get_recommended_config_domains,
    get_supported_config_data_domains,
    normalize_config_domain_subtypes,
    normalize_time_selection,
    resolve_shop_capabilities,
    summarize_shop_scopes,
)
from modules.core.db import (
    CollectionConfig,
    CollectionConfigShopScope,
    CollectionConfigTemplate,
    MainAccount,
    ShopAccount,
    ShopAccountCapability,
)
from modules.core.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(tags=["collection-config"], dependencies=[Depends(require_admin)])


def _build_collection_config_record(
    *,
    config_name: str,
    config: CollectionConfigCreate,
) -> CollectionConfig:
    now = datetime.now(timezone.utc)
    summary = summarize_shop_scopes(config.shop_scopes)
    return CollectionConfig(
        name=config_name,
        platform=config.platform,
        main_account_id=config.main_account_id,
        account_ids=summary["account_ids"],
        data_domains=summary["data_domains"],
        sub_domains=summary["sub_domains"],
        granularity=config.granularity,
        date_range_type=config.date_range_type,
        custom_date_start=config.custom_date_start,
        custom_date_end=config.custom_date_end,
        schedule_enabled=config.schedule_enabled,
        schedule_cron=config.schedule_cron,
        retry_count=config.retry_count,
        execution_mode=config.execution_mode,
        created_at=now,
        updated_at=now,
    )


def _resolve_config_granularity(config: CollectionConfig) -> str:
    if config.granularity in {"daily", "weekly", "monthly"}:
        return config.granularity
    if config.date_range_type in TIME_PRESET_TO_GRANULARITY:
        return TIME_PRESET_TO_GRANULARITY[config.date_range_type]
    return "daily"


def _config_targets_shop(
    config: CollectionConfig,
    *,
    shop_account_id: str,
    platform_shop_ids: Dict[str, List[str]],
) -> bool:
    if config.account_ids:
        return shop_account_id in config.account_ids
    return shop_account_id in platform_shop_ids.get(config.platform, [])


def _build_batch_remediation_name(
    *,
    platform: str,
    shop_account_id: str,
    granularity: str,
) -> str:
    return f"batch-remediate-{granularity}-{platform}-{shop_account_id}"


def _build_config_response(config: CollectionConfig) -> CollectionConfigResponse:
    response = CollectionConfigResponse.model_validate(config)
    if response.time_selection:
        try:
            response.time_window_preview = build_time_window_preview(
                response.time_selection.model_dump(exclude_none=True)
            )
        except Exception as exc:
            logger.warning(
                "Failed to build collection time window preview for config %s: %s",
                getattr(config, "id", None),
                exc,
            )
    return response


def _normalize_template_scope_rows(
    *,
    raw_shop_scopes: List,
    account_map: Dict[str, CollectionAccountResponse],
    valid_domains: List[str],
    allow_disabled: bool = False,
) -> List[dict]:
    normalized_rows: List[dict] = []
    seen_shop_ids: set[str] = set()

    for raw_scope in raw_shop_scopes or []:
        scope = _normalize_scope_payload(raw_scope)
        shop_account_id = str(scope.get("shop_account_id") or "").strip()
        if not shop_account_id:
            raise HTTPException(status_code=400, detail="shop_account_id is required")
        if shop_account_id not in account_map:
            raise HTTPException(status_code=400, detail=f"unknown shop scope: {shop_account_id}")
        if shop_account_id in seen_shop_ids:
            raise HTTPException(status_code=400, detail=f"duplicate shop scope: {shop_account_id}")
        seen_shop_ids.add(shop_account_id)

        account = account_map[shop_account_id]
        capabilities = resolve_shop_capabilities(
            account.capabilities,
            shop_type=account.shop_type,
        )
        enabled = bool(scope.get("enabled", True))
        raw_domains = [str(domain or "").strip() for domain in scope.get("data_domains") or []]
        data_domains = [domain for domain in raw_domains if domain]

        if enabled and not data_domains and not allow_disabled:
            raise HTTPException(
                status_code=400,
                detail=f"shop scope requires at least one data domain: {shop_account_id}",
            )
        if data_domains:
            invalid_domains = sorted(domain for domain in data_domains if domain not in valid_domains)
            if invalid_domains:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid data domain for {shop_account_id}: {', '.join(invalid_domains)}",
                )
            unsupported_domains = sorted(domain for domain in data_domains if not capabilities.get(domain, False))
            if unsupported_domains:
                raise HTTPException(
                    status_code=400,
                    detail=f"unsupported data domain for {shop_account_id}: {', '.join(unsupported_domains)}",
                )

        normalized_rows.append(
            {
                "shop_account_id": shop_account_id,
                "data_domains": data_domains,
                "sub_domains": normalize_config_domain_subtypes(
                    data_domains=data_domains,
                    sub_domains=scope.get("sub_domains"),
                )
                or None,
                "enabled": enabled,
            }
        )

    return sorted(normalized_rows, key=lambda item: item["shop_account_id"])


def _merge_template_scopes(default_scopes: List[dict], overrides: List[dict]) -> List[dict]:
    override_map = {scope["shop_account_id"]: scope for scope in overrides or []}
    result: List[dict] = []
    for default_scope in default_scopes or []:
        override = override_map.get(default_scope["shop_account_id"])
        merged = {
            "shop_account_id": default_scope["shop_account_id"],
            "data_domains": list(default_scope.get("data_domains") or []),
            "sub_domains": dict(default_scope.get("sub_domains") or {}),
            "enabled": bool(default_scope.get("enabled", True)),
        }
        if override:
            merged["enabled"] = bool(override.get("enabled", True))
            if override.get("data_domains") is not None:
                merged["data_domains"] = list(override.get("data_domains") or [])
            if override.get("sub_domains") is not None:
                merged["sub_domains"] = dict(override.get("sub_domains") or {})
        result.append(merged)
    return result


def _compute_scope_overrides(default_scopes: List[dict], actual_scopes: List[dict]) -> List[dict]:
    default_map = {scope["shop_account_id"]: scope for scope in default_scopes or []}
    overrides: List[dict] = []
    for actual_scope in actual_scopes or []:
        default_scope = default_map.get(actual_scope["shop_account_id"])
        if not default_scope:
            overrides.append(actual_scope)
            continue
        if (
            bool(actual_scope.get("enabled", True)) != bool(default_scope.get("enabled", True))
            or list(actual_scope.get("data_domains") or []) != list(default_scope.get("data_domains") or [])
            or dict(actual_scope.get("sub_domains") or {}) != dict(default_scope.get("sub_domains") or {})
        ):
            overrides.append(actual_scope)
    return overrides


async def _persist_batch_shop_scopes(
    db: AsyncSession,
    *,
    config: CollectionConfig,
    merged_scopes: List[dict],
    shop_overrides: Optional[List[dict]] = None,
) -> None:
    config.shop_scopes.clear()
    await db.flush()
    now = datetime.now(timezone.utc)
    for scope in merged_scopes:
        config.shop_scopes.append(
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id=scope["shop_account_id"],
                data_domains=scope["data_domains"],
                sub_domains=scope["sub_domains"],
                enabled=scope["enabled"],
                created_at=now,
                updated_at=now,
            )
        )

    active_scopes = [scope for scope in merged_scopes if scope.get("enabled", True)]
    summary = summarize_shop_scopes(active_scopes)
    config.account_ids = summary["account_ids"]
    config.data_domains = summary["data_domains"]
    config.sub_domains = summary["sub_domains"]
    if shop_overrides is not None:
        config.batch_shop_overrides = shop_overrides
    config.updated_at = now


def _get_config_time_selection(config: CollectionConfig) -> Optional[dict]:
    response = _build_config_response(config)
    return response.time_selection.model_dump(exclude_none=True) if response.time_selection else None


def _build_batch_response(
    config: CollectionConfig,
    *,
    template: Optional[CollectionConfigTemplate] = None,
) -> CollectionConfigBatchResponse:
    payload = _build_config_response(config).model_dump()
    stored_overrides = list(config.batch_shop_overrides or [])
    template_scope_ids = {
        str(scope.get("shop_account_id") or "").strip()
        for scope in (template.default_shop_scopes or [])
        if str(scope.get("shop_account_id") or "").strip()
    } if template is not None else set()
    batch_scope_ids = {
        str(scope.get("shop_account_id") or "").strip()
        for scope in (payload.get("shop_scopes") or [])
        if str(scope.get("shop_account_id") or "").strip()
    }
    if not stored_overrides and template is not None:
        stored_overrides = _compute_scope_overrides(
            template.default_shop_scopes or [],
            payload.get("shop_scopes") or [],
        )
    payload.update(
        {
            "template_id": config.template_id,
            "batch_key": config.batch_key,
            "status": config.batch_status or "draft",
            "note": config.batch_note,
            "shop_overrides": stored_overrides,
            "missing_template_shop_scope_ids": sorted(template_scope_ids - batch_scope_ids),
            "stale_template_shop_scope_ids": sorted(batch_scope_ids - template_scope_ids),
        }
    )
    return CollectionConfigBatchResponse.model_validate(payload)


def _build_template_summary(
    template: CollectionConfigTemplate,
    batches: List[CollectionConfig],
    active_accounts: Optional[List[CollectionAccountResponse]] = None,
) -> CollectionConfigTemplateSummaryResponse:
    active_shop_ids = sorted([account.id for account in active_accounts or []])
    template_scope_ids = sorted(
        [
            str(scope.get("shop_account_id") or "").strip()
            for scope in template.default_shop_scopes or []
            if str(scope.get("shop_account_id") or "").strip()
        ]
    )
    active_shop_set = set(active_shop_ids)
    template_scope_set = set(template_scope_ids)
    payload = {
        "id": template.id,
        "name": template.name,
        "platform": template.platform,
        "main_account_id": template.main_account_id,
        "granularity": template.granularity,
        "default_date_range_type": template.default_date_range_type,
        "default_execution_mode": template.default_execution_mode,
        "default_schedule_enabled": template.default_schedule_enabled,
        "default_schedule_cron": template.default_schedule_cron,
        "default_retry_count": template.default_retry_count,
        "default_shop_scopes": template.default_shop_scopes or [],
        "active_shop_count": len(active_shop_ids),
        "template_shop_count": len(template_scope_ids),
        "missing_shop_scope_ids": sorted(active_shop_set - template_scope_set),
        "stale_shop_scope_ids": sorted(template_scope_set - active_shop_set),
        "batch_count": len(batches),
        "batches": [_build_batch_response(batch, template=template).model_dump() for batch in batches],
        "is_active": template.is_active,
        "created_at": template.created_at,
        "updated_at": template.updated_at,
    }
    return CollectionConfigTemplateSummaryResponse.model_validate(payload)


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value))


def _end_of_month(value: date) -> date:
    next_month = value.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def _shift_date_window(*, granularity: str, start_value: date, end_value: date) -> tuple[date, date]:
    if granularity == "daily":
        return start_value + timedelta(days=1), end_value + timedelta(days=1)
    if granularity == "weekly":
        return start_value + timedelta(days=7), end_value + timedelta(days=7)
    if granularity == "monthly":
        next_month_start = (start_value.replace(day=28) + timedelta(days=4)).replace(day=1)
        return next_month_start, _end_of_month(next_month_start)
    raise HTTPException(status_code=400, detail=f"unsupported granularity: {granularity}")


def _advance_config_window_fields(config: CollectionConfig) -> None:
    time_selection = _get_config_time_selection(config)
    if not time_selection:
        raise HTTPException(status_code=400, detail="config does not have a valid time selection")

    date_range = build_date_range_from_time_selection(time_selection)
    current_start = _parse_date(date_range["start_date"])
    current_end = _parse_date(date_range["end_date"])
    next_start, next_end = _shift_date_window(
        granularity=config.granularity,
        start_value=current_start,
        end_value=current_end,
    )

    config.date_range_type = "custom"
    config.custom_date_start = next_start
    config.custom_date_end = next_end
    config.batch_key = _next_batch_key(granularity=config.granularity, start_value=next_start)
    if getattr(config, "batch_status", None) != "disabled":
        config.batch_status = "active"
    config.updated_at = datetime.now(timezone.utc)


def _next_batch_key(*, granularity: str, start_value: date) -> str:
    if granularity == "daily":
        return start_value.isoformat()
    if granularity == "weekly":
        iso_year, iso_week, _ = start_value.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if granularity == "monthly":
        return start_value.strftime("%Y-%m")
    raise HTTPException(status_code=400, detail=f"unsupported granularity: {granularity}")


def _legacy_batch_key_for_config(config: CollectionConfig) -> str:
    if config.batch_key:
        return str(config.batch_key)[:32]
    if config.custom_date_start:
        return _next_batch_key(granularity=config.granularity, start_value=config.custom_date_start)
    base = f"{config.granularity}-{config.id}"
    return base[:32]


def _select_current_config_records(configs: List[CollectionConfig]) -> List[CollectionConfig]:
    grouped: Dict[tuple[str, str, str], List[CollectionConfig]] = {}
    for config in configs:
        key = (
            str(config.platform or ""),
            str(config.main_account_id or ""),
            str(config.granularity or ""),
        )
        grouped.setdefault(key, []).append(config)

    selected: List[CollectionConfig] = []
    for bucket in grouped.values():
        bucket.sort(
            key=lambda item: (
                0 if str(getattr(item, "batch_status", "") or "").lower() == "active" else 1,
                -(getattr(item, "updated_at", None).timestamp() if getattr(item, "updated_at", None) else 0),
                -(getattr(item, "id", 0) or 0),
            )
        )
        selected.append(bucket[0])

    return sorted(
        selected,
        key=lambda item: (
            str(item.platform or ""),
            str(item.main_account_id or ""),
            str(item.granularity or ""),
            getattr(item, "id", 0) or 0,
        ),
    )


def _apply_time_selection_to_config(
    config: CollectionConfig,
    *,
    time_selection: dict,
    granularity: str,
    time_window_preview: dict,
) -> None:
    legacy_fields = build_legacy_collection_date_fields(time_selection)
    config.granularity = granularity
    config.date_range_type = legacy_fields["date_range_type"]
    config.custom_date_start = legacy_fields["custom_date_start"]
    config.custom_date_end = legacy_fields["custom_date_end"]
    if time_window_preview.get("start_date"):
        config.batch_key = _next_batch_key(
            granularity=granularity,
            start_value=_parse_date(time_window_preview["start_date"]),
        )
    if getattr(config, "batch_status", None) != "disabled":
        config.batch_status = "active"
    config.updated_at = datetime.now(timezone.utc)


def _compact_default_date_range_type(value: str) -> str:
    normalized_value = str(value or "").strip()
    if normalized_value != "custom":
        try:
            time_selection = normalize_time_selection(date_range_type=normalized_value)
            if time_selection:
                return build_legacy_collection_date_fields(time_selection)["date_range_type"]
        except ValueError:
            pass
    return normalized_value




def _normalize_scope_payload(scope) -> dict:
    return scope.model_dump(exclude_none=True) if hasattr(scope, "model_dump") else dict(scope or {})


def _normalize_scope_rows_for_storage(
    *,
    platform: str,
    main_account_id: str,
    raw_shop_scopes: List,
    account_map: Dict[str, CollectionAccountResponse],
) -> List[dict]:
    expected_shop_ids = set(account_map.keys())
    provided_shop_ids = {
        str(_normalize_scope_payload(scope).get("shop_account_id") or "").strip()
        for scope in raw_shop_scopes or []
    }

    missing_shop_ids = sorted(shop_id for shop_id in expected_shop_ids if shop_id not in provided_shop_ids)
    extra_shop_ids = sorted(shop_id for shop_id in provided_shop_ids if shop_id and shop_id not in expected_shop_ids)

    if missing_shop_ids:
        raise HTTPException(
            status_code=400,
            detail=f"missing active shop scopes: {', '.join(missing_shop_ids)}",
        )
    if extra_shop_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                f"shop scopes outside selected main account {main_account_id}: "
                f"{', '.join(extra_shop_ids)}"
            ),
        )

    valid_domains = set(get_supported_config_data_domains(platform))
    normalized_rows: List[dict] = []
    seen_shop_ids: set[str] = set()

    for raw_scope in raw_shop_scopes or []:
        scope = _normalize_scope_payload(raw_scope)
        shop_account_id = str(scope.get("shop_account_id") or "").strip()
        if not shop_account_id:
            raise HTTPException(status_code=400, detail="shop_account_id is required")
        if shop_account_id in seen_shop_ids:
            raise HTTPException(status_code=400, detail=f"duplicate shop scope: {shop_account_id}")
        seen_shop_ids.add(shop_account_id)

        if scope.get("enabled", True) is False:
            raise HTTPException(
                status_code=400,
                detail=f"active shop scope cannot be disabled: {shop_account_id}",
            )

        account = account_map[shop_account_id]
        capabilities = resolve_shop_capabilities(
            account.capabilities,
            shop_type=account.shop_type,
        )

        raw_domains = [str(domain or "").strip() for domain in scope.get("data_domains") or []]
        domains = [domain for domain in raw_domains if domain]
        if not domains:
            raise HTTPException(
                status_code=400,
                detail=f"shop scope requires at least one data domain: {shop_account_id}",
            )

        invalid_domains = sorted(domain for domain in domains if domain not in valid_domains)
        if invalid_domains:
            raise HTTPException(
                status_code=400,
                detail=f"invalid data domain for {shop_account_id}: {', '.join(invalid_domains)}",
            )

        unsupported_domains = sorted(domain for domain in domains if not capabilities.get(domain, False))
        if unsupported_domains:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported data domain for {shop_account_id}: {', '.join(unsupported_domains)}",
            )

        normalized_sub_domains = normalize_config_domain_subtypes(
            data_domains=domains,
            sub_domains=scope.get("sub_domains"),
        ) or None

        normalized_rows.append(
            {
                "shop_account_id": shop_account_id,
                "data_domains": domains,
                "sub_domains": normalized_sub_domains,
                "enabled": True,
            }
        )

    return sorted(normalized_rows, key=lambda item: item["shop_account_id"])


async def _sync_runtime_schedule(config: CollectionConfig) -> Dict[str, Optional[str]]:
    from backend.services.collection_scheduler import (
        APSCHEDULER_AVAILABLE,
        CollectionScheduler,
        sync_config_schedule_state,
    )

    should_register = bool(config.is_active and config.schedule_enabled and config.schedule_cron)
    if not APSCHEDULER_AVAILABLE:
        if should_register:
            raise HTTPException(status_code=503, detail="scheduler service unavailable")
        return {"job_registered": False, "job_id": None, "next_run_time": None}

    try:
        if not should_register and CollectionScheduler._instance is None:
            return {"job_registered": False, "job_id": None, "next_run_time": None}
        return await sync_config_schedule_state(config)
    except Exception as exc:
        logger.error("Failed to sync runtime schedule for config %s: %s", config.id, exc)
        raise HTTPException(status_code=500, detail=f"failed to sync schedule: {exc}") from exc


async def _load_collection_accounts(
    db: AsyncSession,
    *,
    platform: Optional[str] = None,
    main_account_id: Optional[str] = None,
) -> List[CollectionAccountResponse]:
    try:
        stmt = select(ShopAccount).where(ShopAccount.enabled == True)
        if platform:
            stmt = stmt.where(ShopAccount.platform == platform)
        if main_account_id:
            stmt = stmt.where(ShopAccount.main_account_id == main_account_id)
        stmt = stmt.order_by(
            ShopAccount.platform,
            ShopAccount.main_account_id,
            ShopAccount.shop_region,
            ShopAccount.shop_account_id,
        )
        shop_accounts = (await db.execute(stmt)).scalars().all()

        main_accounts = (
            await db.execute(select(MainAccount).where(MainAccount.enabled == True))
        ).scalars().all()
        main_account_map = {
            (record.platform, record.main_account_id): record for record in main_accounts
        }

        capability_rows = (await db.execute(select(ShopAccountCapability))).scalars().all()
        capability_map: Dict[int, Dict[str, bool]] = defaultdict(dict)
        for row in capability_rows:
            capability_map[row.shop_account_id][row.data_domain] = bool(row.enabled)

        result: List[CollectionAccountResponse] = []
        for shop_account in shop_accounts:
            main_account = main_account_map.get(
                (shop_account.platform, shop_account.main_account_id)
            )
            if main_account is None:
                logger.warning(
                    "Skip collection account %s because linked main account %s/%s is not enabled",
                    shop_account.shop_account_id,
                    shop_account.platform,
                    shop_account.main_account_id,
                )
                continue
            capabilities = resolve_shop_capabilities(
                capability_map.get(shop_account.id),
                shop_type=shop_account.shop_type,
            )
            result.append(
                CollectionAccountResponse(
                    id=shop_account.shop_account_id,
                    name=shop_account.store_name or shop_account.shop_account_id,
                    platform=shop_account.platform,
                    shop_id=shop_account.shop_region,
                    shop_region=shop_account.shop_region,
                    status="active" if shop_account.enabled else "inactive",
                    shop_type=shop_account.shop_type,
                    main_account_id=shop_account.main_account_id,
                    main_account_name=main_account.main_account_name if main_account else None,
                    capabilities=capabilities,
                )
            )
        return result
    except Exception:
        from backend.services.account_loader_service import get_account_loader_service

        account_loader = get_account_loader_service()
        accounts = await account_loader.load_all_accounts_async(db, platform=platform)
        result = [
            CollectionAccountResponse(
                id=account.get("account_id", "unknown"),
                name=account.get("store_name", account.get("account_id", "unknown")),
                platform=account.get("platform", "unknown"),
                shop_id=account.get("shop_region"),
                shop_region=account.get("shop_region"),
                status="active" if account.get("enabled", False) else "inactive",
                shop_type=account.get("shop_type"),
                main_account_id=account.get("main_account_id") or account.get("parent_account"),
                main_account_name=account.get("main_account_name"),
                capabilities=resolve_shop_capabilities(
                    account.get("capabilities"),
                    shop_type=account.get("shop_type"),
                ),
            )
            for account in accounts
        ]
        if main_account_id:
            result = [
                account
                for account in result
                if (account.main_account_id or "") == main_account_id
            ]
        return result


@router.get("/configs", response_model=List[CollectionConfigResponse])
async def list_configs(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    date_range_type: Optional[str] = Query(None, description="Filter by date range type"),
    execution_mode: Optional[str] = Query(None, description="Filter by execution mode"),
    schedule_enabled: Optional[bool] = Query(None, description="Filter by schedule enabled"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(CollectionConfig).options(selectinload(CollectionConfig.shop_scopes))

    if platform:
        stmt = stmt.where(CollectionConfig.platform == platform)
    if main_account_id:
        stmt = stmt.where(CollectionConfig.main_account_id == main_account_id)
    if date_range_type:
        stmt = stmt.where(CollectionConfig.date_range_type == date_range_type)
    if execution_mode:
        stmt = stmt.where(CollectionConfig.execution_mode == execution_mode)
    if schedule_enabled is not None:
        stmt = stmt.where(CollectionConfig.schedule_enabled == schedule_enabled)

    if is_active is not None:
        stmt = stmt.where(CollectionConfig.is_active == is_active)

    stmt = stmt.order_by(desc(CollectionConfig.created_at))
    result = await db.execute(stmt)
    return [_build_config_response(config) for config in result.scalars().all()]


@router.post("/configs", response_model=CollectionConfigResponse)
async def create_config(
    config: CollectionConfigCreate,
    db: AsyncSession = Depends(get_async_db),
):
    accounts = await _load_collection_accounts(
        db,
        platform=config.platform,
        main_account_id=config.main_account_id,
    )
    account_map = {account.id: account for account in accounts}
    normalized_scopes = _normalize_scope_rows_for_storage(
        platform=config.platform,
        main_account_id=config.main_account_id,
        raw_shop_scopes=config.shop_scopes,
        account_map=account_map,
    )
    summary = summarize_shop_scopes(normalized_scopes)

    config_name = config.name
    if not config_name:
        domains_str = "-".join(sorted(summary["data_domains"]))
        base_name = f"{config.platform}-{config.main_account_id}-{domains_str}"
        stmt = select(CollectionConfig).where(
            CollectionConfig.name.like(f"{base_name}-v%"),
            CollectionConfig.platform == config.platform,
            CollectionConfig.main_account_id == config.main_account_id,
        )
        existing_configs = (await db.execute(stmt)).scalars().all()
        existing_versions: List[int] = []
        for record in existing_configs:
            if not record.name.startswith(base_name + "-v"):
                continue
            try:
                existing_versions.append(int(record.name[len(base_name) + 2 :]))
            except ValueError:
                continue
        next_version = max(existing_versions, default=0) + 1
        config_name = f"{base_name}-v{next_version}"
        logger.info("Auto-generated collection config name: %s", config_name)
    else:
        stmt = select(CollectionConfig).where(
            CollectionConfig.name == config_name,
            CollectionConfig.platform == config.platform,
            CollectionConfig.main_account_id == config.main_account_id,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="config name already exists")

    db_config = _build_collection_config_record(config_name=config_name, config=config)

    time_selection = normalize_time_selection(
        time_selection=config.time_selection.model_dump(exclude_none=True)
        if config.time_selection
        else None,
        date_range_type=config.date_range_type,
        custom_date_start=config.custom_date_start,
        custom_date_end=config.custom_date_end,
    )
    if time_selection:
        db_config.granularity = derive_granularity_from_time_selection(
            time_selection,
            config.granularity,
        )
        legacy_fields = build_legacy_collection_date_fields(time_selection)
        db_config.date_range_type = legacy_fields["date_range_type"]
        db_config.custom_date_start = legacy_fields["custom_date_start"]
        db_config.custom_date_end = legacy_fields["custom_date_end"]

    db.add(db_config)
    await db.flush()

    for scope in normalized_scopes:
        db.add(
            CollectionConfigShopScope(
                config_id=db_config.id,
                shop_account_id=scope["shop_account_id"],
                data_domains=scope["data_domains"],
                sub_domains=scope["sub_domains"],
                enabled=scope["enabled"],
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
    await db.flush()
    await _sync_runtime_schedule(db_config)
    await db.commit()
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == db_config.id)
    )
    db_config = result.scalar_one()

    logger.info(
        "Created collection config %s (%s) with %s domains",
        db_config.name,
        db_config.platform,
        len(db_config.data_domains),
    )
    return _build_config_response(db_config)


@router.post(
    "/configs/batch-remediate",
    response_model=CollectionConfigBatchRemediationResponse,
)
async def batch_remediate_configs(
    payload: CollectionConfigBatchRemediationRequest,
    db: AsyncSession = Depends(get_async_db),
):
    accounts = await _load_collection_accounts(db, platform=payload.platform)
    account_map = {account.id: account for account in accounts}

    missing_accounts = [
        shop_account_id
        for shop_account_id in payload.shop_account_ids
        if shop_account_id not in account_map
    ]
    if missing_accounts:
        raise HTTPException(
            status_code=404,
            detail=f"shop accounts not found: {', '.join(missing_accounts)}",
        )

    active_shop_ids_by_platform: Dict[str, List[str]] = defaultdict(list)
    for account in accounts:
        active_shop_ids_by_platform[account.platform].append(account.id)

    configs = (
        await db.execute(
            select(CollectionConfig).where(CollectionConfig.is_active == True)
        )
    ).scalars().all()

    created_configs: List[CollectionConfigBatchRemediationCreatedItem] = []
    skipped_shops: List[CollectionConfigBatchRemediationSkippedItem] = []

    for shop_account_id in payload.shop_account_ids:
        account = account_map[shop_account_id]

        already_covered = any(
            _resolve_config_granularity(config) == payload.granularity
            and _config_targets_shop(
                config,
                shop_account_id=shop_account_id,
                platform_shop_ids=active_shop_ids_by_platform,
            )
            for config in configs
        )
        if already_covered:
            skipped_shops.append(
                CollectionConfigBatchRemediationSkippedItem(
                    shop_account_id=shop_account_id,
                    reason="already_covered",
                )
            )
            continue

        data_domains = get_recommended_config_domains(
            account.capabilities or {},
            shop_type=account.shop_type,
        )
        sub_domains = build_default_sub_domains(data_domains) or None
        config_name = _build_batch_remediation_name(
            platform=account.platform,
            shop_account_id=shop_account_id,
            granularity=payload.granularity,
        )

        duplicate = (
            await db.execute(
                select(CollectionConfig).where(
                    CollectionConfig.name == config_name,
                    CollectionConfig.platform == account.platform,
                    CollectionConfig.main_account_id == account.main_account_id,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            config_name = f"{config_name}-{int(datetime.now(timezone.utc).timestamp())}"

        record = CollectionConfig(
            name=config_name,
            platform=account.platform,
            main_account_id=account.main_account_id or "",
            account_ids=[shop_account_id],
            data_domains=data_domains,
            sub_domains=sub_domains,
            granularity=payload.granularity,
            date_range_type=DEFAULT_GRANULARITY_DATE_RANGE_TYPE[payload.granularity],
            schedule_enabled=False,
            retry_count=3,
            execution_mode="headless",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(record)
        await db.flush()
        db.add(
            CollectionConfigShopScope(
                config_id=record.id,
                shop_account_id=shop_account_id,
                data_domains=data_domains,
                sub_domains=sub_domains,
                enabled=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        configs.append(record)
        created_configs.append(
            CollectionConfigBatchRemediationCreatedItem(
                config_id=record.id,
                config_name=record.name,
                shop_account_id=shop_account_id,
                granularity=payload.granularity,
            )
        )

    await db.commit()

    return CollectionConfigBatchRemediationResponse(
        granularity=payload.granularity,
        created_configs=created_configs,
        skipped_shops=skipped_shops,
    )


@router.get("/configs/{config_id}", response_model=CollectionConfigResponse)
async def get_config(
    config_id: int = Path(..., description="Config ID"),
    db: AsyncSession = Depends(get_async_db),
):
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == config_id)
    )
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")
    return _build_config_response(config)


@router.put("/configs/{config_id}", response_model=CollectionConfigResponse)
async def update_config(
    config_id: int,
    update_data: CollectionConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(
            select(CollectionConfig)
            .options(
                selectinload(CollectionConfig.shop_scopes),
                selectinload(CollectionConfig.template),
            )
            .where(CollectionConfig.id == config_id)
        )
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    update_dict = update_data.model_dump(exclude_unset=True)
    scope_payload = update_dict.pop("shop_scopes", None)
    selected_main_account_id = update_dict.get("main_account_id") or config.main_account_id
    if scope_payload is not None:
        accounts = await _load_collection_accounts(
            db,
            platform=config.platform,
            main_account_id=selected_main_account_id,
        )
        account_map = {account.id: account for account in accounts}
        normalized_scopes = _normalize_scope_rows_for_storage(
            platform=config.platform,
            main_account_id=selected_main_account_id,
            raw_shop_scopes=scope_payload,
            account_map=account_map,
        )
        summary = summarize_shop_scopes(normalized_scopes)
        config.account_ids = summary["account_ids"]
        config.data_domains = summary["data_domains"]
        config.sub_domains = summary["sub_domains"]

    time_selection_input = update_dict.pop("time_selection", None)
    nullable_fields = {"schedule_cron", "custom_date_start", "custom_date_end", "sub_domains"}
    for key, value in update_dict.items():
        if value is not None or key in nullable_fields:
            setattr(config, key, value)

    if "batch_status" in update_dict:
        config.is_active = update_dict["batch_status"] != "disabled"

    time_selection = normalize_time_selection(
        time_selection=time_selection_input,
        date_range_type=None
        if time_selection_input is not None
        else (update_dict.get("date_range_type") or config.date_range_type),
        custom_date_start=None
        if time_selection_input is not None
        else (update_dict.get("custom_date_start") or config.custom_date_start),
        custom_date_end=None
        if time_selection_input is not None
        else (update_dict.get("custom_date_end") or config.custom_date_end),
    )
    if time_selection:
        config.granularity = derive_granularity_from_time_selection(
            time_selection,
            update_dict.get("granularity") or config.granularity,
        )
        legacy_fields = build_legacy_collection_date_fields(time_selection)
        config.date_range_type = legacy_fields["date_range_type"]
        config.custom_date_start = legacy_fields["custom_date_start"]
        config.custom_date_end = legacy_fields["custom_date_end"]

    if scope_payload is not None:
        config.shop_scopes.clear()
        await db.flush()
        for scope in normalized_scopes:
            config.shop_scopes.append(
                CollectionConfigShopScope(
                    config_id=config.id,
                    shop_account_id=scope["shop_account_id"],
                    data_domains=scope["data_domains"],
                    sub_domains=scope["sub_domains"],
                    enabled=scope["enabled"],
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
        if config.template_id and getattr(config, "template", None):
            config.batch_shop_overrides = _compute_scope_overrides(
                config.template.default_shop_scopes or [],
                normalized_scopes,
            )

    config.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await _sync_runtime_schedule(config)
    await db.commit()
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == config.id)
    )
    config = result.scalar_one()

    logger.info("Updated collection config: %s", config.name)
    return _build_config_response(config)


@router.delete("/configs/{config_id}", response_model=SuccessResponse[None])
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    name = config.name
    config.schedule_enabled = False
    config.schedule_cron = None
    await _sync_runtime_schedule(config)
    await db.delete(config)
    await db.commit()
    logger.info("Deleted collection config: %s (id=%s)", name, config_id)
    return SuccessResponse(success=True, message="config deleted", data=None)


async def _load_template_or_404(db: AsyncSession, template_id: int) -> CollectionConfigTemplate:
    template = (
        await db.execute(
            select(CollectionConfigTemplate).where(CollectionConfigTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="template not found")
    return template


async def _load_template_batches(db: AsyncSession, template_ids: List[int]) -> Dict[int, List[CollectionConfig]]:
    if not template_ids:
        return {}
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.template_id.in_(template_ids))
        .order_by(desc(CollectionConfig.batch_key), desc(CollectionConfig.updated_at))
    )
    grouped: Dict[int, List[CollectionConfig]] = defaultdict(list)
    for batch in result.scalars().all():
        grouped[int(batch.template_id)].append(batch)
    return grouped


async def _build_batch_record_from_template(
    *,
    db: AsyncSession,
    template: CollectionConfigTemplate,
    batch_create: CollectionConfigBatchCreate,
) -> CollectionConfig:
    accounts = await _load_collection_accounts(
        db,
        platform=template.platform,
        main_account_id=template.main_account_id,
    )
    account_map = {account.id: account for account in accounts}
    overrides = _normalize_template_scope_rows(
        raw_shop_scopes=batch_create.shop_overrides,
        account_map=account_map,
        valid_domains=get_supported_config_data_domains(template.platform),
        allow_disabled=True,
    )
    merged_scopes = _merge_template_scopes(template.default_shop_scopes or [], overrides)
    active_scopes = [scope for scope in merged_scopes if scope.get("enabled", True)]
    if not active_scopes:
        raise HTTPException(status_code=400, detail="batch requires at least one enabled shop scope")

    duplicate = (
        await db.execute(
            select(CollectionConfig).where(
                CollectionConfig.template_id == template.id,
                CollectionConfig.batch_key == batch_create.batch_key,
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="batch key already exists")

    time_selection = normalize_time_selection(
        time_selection=batch_create.time_selection.model_dump(exclude_none=True)
    )
    legacy_fields = build_legacy_collection_date_fields(time_selection)
    summary = summarize_shop_scopes(active_scopes)
    now = datetime.now(timezone.utc)
    record = CollectionConfig(
        template_id=template.id,
        name=batch_create.batch_key,
        platform=template.platform,
        main_account_id=template.main_account_id,
        account_ids=summary["account_ids"],
        data_domains=summary["data_domains"],
        sub_domains=summary["sub_domains"],
        granularity=template.granularity,
        date_range_type=legacy_fields["date_range_type"],
        custom_date_start=legacy_fields["custom_date_start"],
        custom_date_end=legacy_fields["custom_date_end"],
        execution_mode=template.default_execution_mode,
        schedule_enabled=template.default_schedule_enabled,
        schedule_cron=template.default_schedule_cron,
        retry_count=template.default_retry_count,
        batch_key=batch_create.batch_key,
        batch_status=batch_create.status,
        batch_note=batch_create.note,
        batch_shop_overrides=overrides,
        is_active=batch_create.status != "disabled",
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    await db.flush()

    for scope in merged_scopes:
        db.add(
            CollectionConfigShopScope(
                config_id=record.id,
                shop_account_id=scope["shop_account_id"],
                data_domains=scope["data_domains"],
                sub_domains=scope["sub_domains"],
                enabled=scope["enabled"],
                created_at=now,
                updated_at=now,
            )
        )
    await db.flush()
    return record


@router.get("/config-templates", response_model=List[CollectionConfigTemplateSummaryResponse])
async def list_config_templates(
    platform: Optional[str] = Query(None),
    main_account_id: Optional[str] = Query(None),
    granularity: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(CollectionConfigTemplate).where(CollectionConfigTemplate.is_active == True)
    if platform:
        stmt = stmt.where(CollectionConfigTemplate.platform == platform)
    if main_account_id:
        stmt = stmt.where(CollectionConfigTemplate.main_account_id == main_account_id)
    if granularity:
        stmt = stmt.where(CollectionConfigTemplate.granularity == granularity)
    templates = (await db.execute(stmt.order_by(CollectionConfigTemplate.updated_at.desc()))).scalars().all()
    batches_by_template = await _load_template_batches(db, [template.id for template in templates])
    result: List[CollectionConfigTemplateSummaryResponse] = []
    for template in templates:
        accounts = await _load_collection_accounts(
            db,
            platform=template.platform,
            main_account_id=template.main_account_id,
        )
        result.append(
            _build_template_summary(
                template,
                batches_by_template.get(template.id, []),
                active_accounts=accounts,
            )
        )
    return result


@router.post("/config-templates", response_model=CollectionConfigTemplateSummaryResponse)
async def create_config_template(
    payload: CollectionConfigTemplateCreate,
    db: AsyncSession = Depends(get_async_db),
):
    accounts = await _load_collection_accounts(
        db,
        platform=payload.platform,
        main_account_id=payload.main_account_id,
    )
    account_map = {account.id: account for account in accounts}
    default_scopes = _normalize_template_scope_rows(
        raw_shop_scopes=payload.default_shop_scopes,
        account_map=account_map,
        valid_domains=get_supported_config_data_domains(payload.platform),
    )

    existing = (
        await db.execute(
            select(CollectionConfigTemplate).where(
                CollectionConfigTemplate.platform == payload.platform,
                CollectionConfigTemplate.main_account_id == payload.main_account_id,
                CollectionConfigTemplate.granularity == payload.granularity,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="template already exists")

    template = CollectionConfigTemplate(
        name=payload.name,
        platform=payload.platform,
        main_account_id=payload.main_account_id,
        granularity=payload.granularity,
        default_date_range_type=_compact_default_date_range_type(payload.default_date_range_type),
        default_execution_mode=payload.default_execution_mode,
        default_schedule_enabled=payload.default_schedule_enabled,
        default_schedule_cron=payload.default_schedule_cron,
        default_retry_count=payload.default_retry_count,
        default_shop_scopes=default_scopes,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    accounts = await _load_collection_accounts(
        db,
        platform=template.platform,
        main_account_id=template.main_account_id,
    )
    return _build_template_summary(template, [], active_accounts=accounts)


@router.put("/config-templates/{template_id}", response_model=CollectionConfigTemplateSummaryResponse)
async def update_config_template(
    template_id: int,
    payload: CollectionConfigTemplateUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    template = await _load_template_or_404(db, template_id)
    update_dict = payload.model_dump(exclude_unset=True)
    if "default_shop_scopes" in update_dict:
        accounts = await _load_collection_accounts(
            db,
            platform=template.platform,
            main_account_id=template.main_account_id,
        )
        account_map = {account.id: account for account in accounts}
        template.default_shop_scopes = _normalize_template_scope_rows(
            raw_shop_scopes=update_dict.pop("default_shop_scopes"),
            account_map=account_map,
            valid_domains=get_supported_config_data_domains(template.platform),
        )
    for key, value in update_dict.items():
        if key == "default_date_range_type":
            value = _compact_default_date_range_type(value)
        setattr(template, key, value)
    template.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(template)
    batches = (await _load_template_batches(db, [template.id])).get(template.id, [])
    accounts = await _load_collection_accounts(
        db,
        platform=template.platform,
        main_account_id=template.main_account_id,
    )
    return _build_template_summary(template, batches, active_accounts=accounts)


@router.post("/config-templates/{template_id}/batches", response_model=CollectionConfigBatchResponse)
async def create_config_batch(
    template_id: int,
    payload: CollectionConfigBatchCreate,
    db: AsyncSession = Depends(get_async_db),
):
    template = await _load_template_or_404(db, template_id)
    accounts = await _load_collection_accounts(
        db,
        platform=template.platform,
        main_account_id=template.main_account_id,
    )
    account_map = {account.id: account for account in accounts}
    overrides = _normalize_template_scope_rows(
        raw_shop_scopes=payload.shop_overrides,
        account_map=account_map,
        valid_domains=get_supported_config_data_domains(template.platform),
        allow_disabled=True,
    )
    merged_scopes = _merge_template_scopes(template.default_shop_scopes or [], overrides)
    active_scopes = [scope for scope in merged_scopes if scope.get("enabled", True)]
    if not active_scopes:
        raise HTTPException(status_code=400, detail="batch requires at least one enabled shop scope")

    duplicate = (
        await db.execute(
            select(CollectionConfig).where(
                CollectionConfig.template_id == template.id,
                CollectionConfig.batch_key == payload.batch_key,
            )
        )
    ).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="batch key already exists")

    time_selection = normalize_time_selection(
        time_selection=payload.time_selection.model_dump(exclude_none=True)
    )
    legacy_fields = build_legacy_collection_date_fields(time_selection)
    summary = summarize_shop_scopes(active_scopes)
    now = datetime.now(timezone.utc)
    config = CollectionConfig(
        template_id=template.id,
        name=payload.batch_key,
        platform=template.platform,
        main_account_id=template.main_account_id,
        account_ids=summary["account_ids"],
        data_domains=summary["data_domains"],
        sub_domains=summary["sub_domains"],
        granularity=template.granularity,
        date_range_type=legacy_fields["date_range_type"],
        custom_date_start=legacy_fields["custom_date_start"],
        custom_date_end=legacy_fields["custom_date_end"],
        execution_mode=template.default_execution_mode,
        schedule_enabled=template.default_schedule_enabled,
        schedule_cron=template.default_schedule_cron,
        retry_count=template.default_retry_count,
        batch_key=payload.batch_key,
        batch_status=payload.status,
        batch_note=payload.note,
        batch_shop_overrides=overrides,
        is_active=payload.status != "disabled",
        created_at=now,
        updated_at=now,
    )
    db.add(config)
    await db.flush()

    for scope in merged_scopes:
        db.add(
            CollectionConfigShopScope(
                config_id=config.id,
                shop_account_id=scope["shop_account_id"],
                data_domains=scope["data_domains"],
                sub_domains=scope["sub_domains"],
                enabled=scope["enabled"],
                created_at=now,
                updated_at=now,
            )
        )

    await db.commit()
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == config.id)
    )
    config = result.scalar_one()
    return _build_batch_response(config, template=template)


@router.post("/config-batches/{config_id}/clone-next", response_model=CollectionConfigBatchResponse)
async def clone_next_config_batch(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes), selectinload(CollectionConfig.template))
            .where(CollectionConfig.id == config_id)
        )
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")
    if not config.template_id or not config.template:
        raise HTTPException(status_code=400, detail="config is not managed by a template")

    time_selection = _get_config_time_selection(config)
    if not time_selection:
        raise HTTPException(status_code=400, detail="config does not have a valid time selection")
    date_range = build_date_range_from_time_selection(time_selection)
    current_start = _parse_date(date_range["start_date"])
    current_end = _parse_date(date_range["end_date"])
    next_start, next_end = _shift_date_window(
        granularity=config.template.granularity,
        start_value=current_start,
        end_value=current_end,
    )
    next_batch_key = _next_batch_key(granularity=config.template.granularity, start_value=next_start)

    existing = (
        await db.execute(
            select(CollectionConfig).where(
                CollectionConfig.template_id == config.template_id,
                CollectionConfig.batch_key == next_batch_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="next batch already exists")

    actual_scopes = [
        {
            "shop_account_id": scope.shop_account_id,
            "data_domains": list(scope.data_domains or []),
            "sub_domains": dict(scope.sub_domains or {}),
            "enabled": bool(scope.enabled),
        }
        for scope in config.shop_scopes
    ]
    overrides = _compute_scope_overrides(config.template.default_shop_scopes or [], actual_scopes)
    create_payload = CollectionConfigBatchCreate(
        batch_key=next_batch_key,
        time_selection=TimeSelectionPayload(
            mode="custom",
            start_date=next_start.isoformat(),
            end_date=next_end.isoformat(),
        ),
        status="draft",
        note=config.batch_note,
        shop_overrides=list(config.batch_shop_overrides or overrides),
    )
    return await create_config_batch(config.template_id, create_payload, db)


@router.post("/configs/{config_id}/advance-current", response_model=CollectionConfigBatchResponse)
async def advance_current_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes), selectinload(CollectionConfig.template))
            .where(CollectionConfig.id == config_id)
        )
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    _advance_config_window_fields(config)
    await db.commit()
    await db.refresh(config)
    return _build_batch_response(config, template=getattr(config, "template", None))


@router.post("/config-batches/{config_id}/reapply-template", response_model=CollectionConfigBatchResponse)
async def reapply_template_defaults_for_batch(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes), selectinload(CollectionConfig.template))
            .where(CollectionConfig.id == config_id)
        )
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")
    if not config.template_id or not config.template:
        raise HTTPException(status_code=400, detail="config is not managed by a template")

    overrides = list(config.batch_shop_overrides or [])
    merged_scopes = _merge_template_scopes(config.template.default_shop_scopes or [], overrides)
    await _persist_batch_shop_scopes(db, config=config, merged_scopes=merged_scopes, shop_overrides=overrides)
    await db.commit()
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == config.id)
    )
    config = result.scalar_one()
    return _build_batch_response(config, template=config.template)


@router.post("/configs/advance-current-granularity", response_model=CollectionConfigBulkAdvanceResponse)
async def bulk_advance_current_granularity(
    payload: CollectionConfigBulkAdvanceRequest,
    db: AsyncSession = Depends(get_async_db),
):
    stmt = (
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes), selectinload(CollectionConfig.template))
        .where(
            CollectionConfig.granularity == payload.granularity,
            CollectionConfig.is_active == True,
        )
        .order_by(CollectionConfig.platform, CollectionConfig.main_account_id, CollectionConfig.id)
    )
    if payload.platform:
        stmt = stmt.where(CollectionConfig.platform == payload.platform)
    if payload.main_account_ids:
        stmt = stmt.where(CollectionConfig.main_account_id.in_(payload.main_account_ids))

    configs = (await db.execute(stmt)).scalars().all()
    affected_config_ids: List[int] = []
    skipped_config_ids: List[int] = []

    for config in configs:
        try:
            _advance_config_window_fields(config)
            affected_config_ids.append(config.id)
        except HTTPException:
            skipped_config_ids.append(config.id)

    await db.commit()
    return CollectionConfigBulkAdvanceResponse(
        affected_config_ids=affected_config_ids,
        skipped_config_ids=skipped_config_ids,
    )


@router.post(
    "/configs/apply-time-selection-current-granularity",
    response_model=CollectionConfigBulkApplyTimeSelectionResponse,
)
async def apply_time_selection_current_granularity(
    payload: CollectionConfigBulkApplyTimeSelectionRequest,
    db: AsyncSession = Depends(get_async_db),
):
    time_selection = normalize_time_selection(
        time_selection=payload.time_selection.model_dump(exclude_none=True)
    )
    resolved_granularity = derive_granularity_from_time_selection(
        time_selection,
        payload.granularity,
    )
    if resolved_granularity != payload.granularity:
        raise HTTPException(
            status_code=400,
            detail=(
                "time selection granularity does not match request granularity: "
                f"{resolved_granularity} != {payload.granularity}"
            ),
        )

    time_window_preview = build_time_window_preview(time_selection)
    stmt = (
        select(CollectionConfig)
        .where(
            CollectionConfig.granularity == payload.granularity,
            CollectionConfig.is_active == True,
        )
        .order_by(
            CollectionConfig.platform,
            CollectionConfig.main_account_id,
            desc(CollectionConfig.updated_at),
            desc(CollectionConfig.id),
        )
    )
    if payload.platform:
        stmt = stmt.where(CollectionConfig.platform == payload.platform)
    if payload.main_account_ids:
        stmt = stmt.where(CollectionConfig.main_account_id.in_(payload.main_account_ids))

    configs = _select_current_config_records(list((await db.execute(stmt)).scalars().all()))
    updated_config_ids: List[int] = []
    skipped_config_ids: List[int] = []

    for config in configs:
        try:
            _apply_time_selection_to_config(
                config,
                time_selection=time_selection,
                granularity=payload.granularity,
                time_window_preview=time_window_preview,
            )
            updated_config_ids.append(config.id)
        except Exception as exc:
            logger.warning("Failed to apply time selection to config %s: %s", config.id, exc)
            skipped_config_ids.append(config.id)

    await db.commit()
    return CollectionConfigBulkApplyTimeSelectionResponse(
        updated_config_count=len(updated_config_ids),
        skipped_config_count=len(skipped_config_ids),
        updated_config_ids=updated_config_ids,
        skipped_config_ids=skipped_config_ids,
        time_window_preview=time_window_preview,
    )


@router.post("/configs/run-current-granularity", response_model=CollectionConfigBulkRunResponse)
async def bulk_run_current_granularity(
    payload: CollectionConfigBulkRunRequest,
    db: AsyncSession = Depends(get_async_db),
):
    from backend.domains.collection.routers.collection_tasks import (
        _build_config_run_response_payload,
    )
    from backend.services.collection_config_run_service import CollectionConfigRunService

    stmt = (
        select(CollectionConfig)
        .where(
            CollectionConfig.granularity == payload.granularity,
            CollectionConfig.is_active == True,
        )
        .order_by(
            CollectionConfig.platform,
            CollectionConfig.main_account_id,
            desc(CollectionConfig.updated_at),
            desc(CollectionConfig.id),
        )
    )
    if payload.platform:
        stmt = stmt.where(CollectionConfig.platform == payload.platform)
    if payload.main_account_ids:
        stmt = stmt.where(CollectionConfig.main_account_id.in_(payload.main_account_ids))

    configs = _select_current_config_records(list((await db.execute(stmt)).scalars().all()))

    run_service = CollectionConfigRunService(db)
    runs = []
    skipped_config_ids: List[int] = []
    for config in configs:
        run, created = await run_service.enqueue_config_run(config, trigger_type="manual")
        if created:
            runs.append(_build_config_run_response_payload(run))
        else:
            skipped_config_ids.append(config.id)

    return CollectionConfigBulkRunResponse(
        created_run_count=len(runs),
        skipped_config_count=len(skipped_config_ids),
        runs=runs,
        skipped_config_ids=skipped_config_ids,
    )


@router.post(
    "/config-batches/{config_id}/create-future-batches",
    response_model=CollectionConfigFutureBatchCreateResponse,
)
async def create_future_config_batches(
    config_id: int,
    payload: CollectionConfigFutureBatchCreateRequest,
    db: AsyncSession = Depends(get_async_db),
):
    batch = (
        await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes))
            .where(CollectionConfig.id == config_id)
        )
    ).scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="batch not found")
    if not batch.template_id:
        raise HTTPException(status_code=400, detail="legacy config cannot create future batches")

    template = await _load_template_or_404(db, int(batch.template_id))
    time_selection = _get_config_time_selection(batch)
    if not time_selection:
        raise HTTPException(status_code=400, detail="batch time selection unavailable")

    date_range = build_date_range_from_time_selection(time_selection)
    start_value = _parse_date(date_range["start_date"])
    end_value = _parse_date(date_range["end_date"])
    base_overrides = list(batch.batch_shop_overrides or [])
    created_batches: List[CollectionConfigBatchResponse] = []
    skipped_batch_keys: List[str] = []

    for _ in range(payload.periods):
        start_value, end_value = _shift_date_window(
            granularity=batch.granularity,
            start_value=start_value,
            end_value=end_value,
        )
        batch_key = _next_batch_key(granularity=batch.granularity, start_value=start_value)
        existing = (
            await db.execute(
                select(CollectionConfig).where(
                    CollectionConfig.template_id == batch.template_id,
                    CollectionConfig.batch_key == batch_key,
                )
            )
        ).scalar_one_or_none()
        if existing:
            skipped_batch_keys.append(batch_key)
            continue

        create_payload = CollectionConfigBatchCreate(
            batch_key=batch_key,
            time_selection=TimeSelectionPayload(
                mode="custom",
                start_date=start_value.isoformat(),
                end_date=end_value.isoformat(),
            ),
            status="draft",
            note=batch.batch_note,
            shop_overrides=base_overrides,
        )
        new_batch = await _build_batch_record_from_template(db=db, template=template, batch_create=create_payload)
        result = await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes))
            .where(CollectionConfig.id == new_batch.id)
        )
        created_batches.append(_build_batch_response(result.scalar_one(), template=template))

    await db.commit()
    return CollectionConfigFutureBatchCreateResponse(
        created_batches=created_batches,
        skipped_batch_keys=skipped_batch_keys,
    )


@router.post(
    "/config-template-backfill",
    response_model=CollectionConfigTemplateBackfillResponse,
)
async def backfill_legacy_config_templates(
    db: AsyncSession = Depends(get_async_db),
):
    legacy_configs = (
        await db.execute(
            select(CollectionConfig)
            .options(selectinload(CollectionConfig.shop_scopes))
            .where(CollectionConfig.template_id.is_(None))
            .order_by(CollectionConfig.main_account_id, CollectionConfig.granularity, CollectionConfig.id)
        )
    ).scalars().all()

    created_template_count = 0
    attached_batch_count = 0
    skipped_config_ids: List[int] = []
    template_cache: Dict[tuple[str, str, str], CollectionConfigTemplate] = {}

    for config in legacy_configs:
        if not config.main_account_id or not config.granularity:
            skipped_config_ids.append(config.id)
            continue

        cache_key = (config.platform, config.main_account_id, config.granularity)
        template = template_cache.get(cache_key)
        if template is None:
            template = (
                await db.execute(
                    select(CollectionConfigTemplate).where(
                        CollectionConfigTemplate.platform == config.platform,
                        CollectionConfigTemplate.main_account_id == config.main_account_id,
                        CollectionConfigTemplate.granularity == config.granularity,
                    )
                )
            ).scalar_one_or_none()

        if template is None:
            default_shop_scopes = [
                {
                    "shop_account_id": scope.shop_account_id,
                    "data_domains": list(scope.data_domains or []),
                    "sub_domains": dict(scope.sub_domains or {}),
                    "enabled": bool(scope.enabled),
                }
                for scope in config.shop_scopes
            ]
            template = CollectionConfigTemplate(
                name=f"{config.platform}-{config.main_account_id}-{config.granularity}",
                platform=config.platform,
                main_account_id=config.main_account_id,
                granularity=config.granularity,
                default_date_range_type=config.date_range_type,
                default_execution_mode=config.execution_mode,
                default_schedule_enabled=config.schedule_enabled,
                default_schedule_cron=config.schedule_cron,
                default_retry_count=config.retry_count,
                default_shop_scopes=default_shop_scopes,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(template)
            await db.flush()
            created_template_count += 1
            template_cache[cache_key] = template

        config.template_id = template.id
        config.batch_key = _legacy_batch_key_for_config(config)
        config.batch_status = config.batch_status or "active"
        config.batch_note = config.batch_note or "legacy backfill"
        if config.batch_shop_overrides is None:
            config.batch_shop_overrides = _compute_scope_overrides(
                template.default_shop_scopes or [],
                [
                    {
                        "shop_account_id": scope.shop_account_id,
                        "data_domains": list(scope.data_domains or []),
                        "sub_domains": dict(scope.sub_domains or {}),
                        "enabled": bool(scope.enabled),
                    }
                    for scope in config.shop_scopes
                ],
            )
        config.updated_at = datetime.now(timezone.utc)
        attached_batch_count += 1

    await db.commit()
    return CollectionConfigTemplateBackfillResponse(
        created_template_count=created_template_count,
        attached_batch_count=attached_batch_count,
        skipped_config_ids=skipped_config_ids,
    )


@router.get("/accounts", response_model=List[CollectionAccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,
):
    if request and hasattr(request.app.state, "cache_service"):
        try:
            cache_service = request.app.state.cache_service
            cached_data = await cache_service.get(
                "accounts_list",
                platform=platform or "",
                main_account_id=main_account_id or "",
            )
            if cached_data is not None and isinstance(cached_data, list):
                logger.debug(
                    "[Cache] collection accounts hit: platform=%s main_account_id=%s",
                    platform,
                    main_account_id,
                )
                return [CollectionAccountResponse(**item) for item in cached_data]
        except Exception as exc:
            logger.warning("[Cache] failed to read collection account cache: %s", exc)

    try:
        result = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        logger.info("Returned collection account list: %s records", len(result))

        if request and hasattr(request.app.state, "cache_service"):
            try:
                cache_service = request.app.state.cache_service
                await cache_service.set(
                    "accounts_list",
                    [item.model_dump() for item in result],
                    ttl=300,
                    platform=platform or "",
                    main_account_id=main_account_id or "",
                )
            except Exception as exc:
                logger.warning("[Cache] failed to write collection account cache: %s", exc)

        return result
    except Exception:
        logger.exception("Failed to load collection accounts")
        raise HTTPException(status_code=500, detail="failed to load collection accounts")


@router.get("/accounts/grouped", response_model=List[CollectionAccountGroupResponse])
async def list_grouped_accounts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        grouped: Dict[tuple[str, str], Dict[str, object]] = {}

        for account in accounts:
            group_key = (account.platform, account.main_account_id or "")
            if group_key not in grouped:
                grouped[group_key] = {
                    "platform": account.platform,
                    "main_account_id": account.main_account_id or "",
                    "main_account_name": account.main_account_name,
                    "regions": defaultdict(list),
                }
            grouped[group_key]["regions"][account.shop_region or ""].append(account)

        result: List[CollectionAccountGroupResponse] = []
        for _, group in sorted(grouped.items(), key=lambda item: item[0]):
            regions = []
            for region_key, shops in sorted(group["regions"].items(), key=lambda item: item[0]):
                regions.append(
                    CollectionAccountGroupRegionResponse(
                        shop_region=region_key or None,
                        shops=sorted(shops, key=lambda item: item.id),
                    )
                )
            result.append(
                CollectionAccountGroupResponse(
                    platform=group["platform"],
                    main_account_id=group["main_account_id"],
                    main_account_name=group["main_account_name"],
                    regions=regions,
                )
            )
        return result
    except Exception:
        logger.exception("Failed to load grouped collection accounts")
        raise HTTPException(status_code=500, detail="failed to load grouped collection accounts")


@router.get("/config-coverage", response_model=CollectionConfigCoverageResponse)
async def get_config_coverage(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        coverage_by_shop = {
            account.id: {"daily": False, "weekly": False, "monthly": False}
            for account in accounts
        }
        active_shop_ids_by_platform: Dict[str, List[str]] = defaultdict(list)
        for account in accounts:
            active_shop_ids_by_platform[account.platform].append(account.id)

        stmt = select(CollectionConfig).where(CollectionConfig.is_active == True)
        if platform:
            stmt = stmt.where(CollectionConfig.platform == platform)
        if main_account_id:
            stmt = stmt.where(CollectionConfig.main_account_id == main_account_id)
        configs = (await db.execute(stmt.order_by(CollectionConfig.platform, CollectionConfig.id))).scalars().all()

        for config in configs:
            granularity = _resolve_config_granularity(config)
            if config.account_ids:
                target_shop_ids = [shop_id for shop_id in config.account_ids if shop_id in coverage_by_shop]
            else:
                target_shop_ids = active_shop_ids_by_platform.get(config.platform, [])
            for shop_id in target_shop_ids:
                coverage_by_shop[shop_id][granularity] = True

        items: List[CollectionConfigCoverageItem] = []
        for account in accounts:
            coverage = coverage_by_shop.get(account.id, {"daily": False, "weekly": False, "monthly": False})
            missing = [name for name, covered in coverage.items() if not covered]
            recommended_domains = get_recommended_config_domains(
                account.capabilities or {},
                shop_type=account.shop_type,
            )
            is_partially_covered = 0 < len(missing) < 3
            items.append(
                CollectionConfigCoverageItem(
                    shop_account_id=account.id,
                    shop_account_name=account.name,
                    platform=account.platform,
                    main_account_id=account.main_account_id or "",
                    main_account_name=account.main_account_name,
                    shop_region=account.shop_region,
                    shop_type=account.shop_type,
                    daily_covered=coverage["daily"],
                    weekly_covered=coverage["weekly"],
                    monthly_covered=coverage["monthly"],
                    missing_granularities=missing,
                    partial_covered=is_partially_covered,
                    fully_covered=len(missing) == 0,
                    is_partially_covered=is_partially_covered,
                    recommended_domains=recommended_domains,
                )
            )

        summary = CollectionConfigCoverageSummary(
            total_shop_count=len(items),
            fully_covered_count=sum(1 for item in items if item.fully_covered),
            partial_covered_count=sum(1 for item in items if item.partial_covered),
            daily_covered_count=sum(1 for item in items if item.daily_covered),
            weekly_covered_count=sum(1 for item in items if item.weekly_covered),
            monthly_covered_count=sum(1 for item in items if item.monthly_covered),
            daily_missing_count=sum(1 for item in items if not item.daily_covered),
            weekly_missing_count=sum(1 for item in items if not item.weekly_covered),
            monthly_missing_count=sum(1 for item in items if not item.monthly_covered),
        )

        return CollectionConfigCoverageResponse(summary=summary, items=items)
    except Exception:
        logger.exception("Failed to build collection config coverage")
        raise HTTPException(status_code=500, detail="failed to build collection config coverage")


@router.get("/accounts", response_model=List[CollectionAccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,
):
    if request and hasattr(request.app.state, "cache_service"):
        try:
            cache_service = request.app.state.cache_service
            cached_data = await cache_service.get(
                "accounts_list",
                platform=platform or "",
                main_account_id=main_account_id or "",
            )
            if cached_data is not None and isinstance(cached_data, list):
                logger.debug(
                    "[Cache] collection accounts hit: platform=%s main_account_id=%s",
                    platform,
                    main_account_id,
                )
                return [CollectionAccountResponse(**item) for item in cached_data]
        except Exception as exc:
            logger.warning("[Cache] failed to read collection account cache: %s", exc)

    try:
        result = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        logger.info("Returned collection account list: %s records", len(result))

        if request and hasattr(request.app.state, "cache_service"):
            try:
                cache_service = request.app.state.cache_service
                await cache_service.set(
                    "accounts_list",
                    [item.model_dump() for item in result],
                    ttl=300,
                    platform=platform or "",
                    main_account_id=main_account_id or "",
                )
            except Exception as exc:
                logger.warning("[Cache] failed to write collection account cache: %s", exc)

        return result
    except Exception:
        logger.exception("Failed to load collection accounts")
        raise HTTPException(status_code=500, detail="failed to load collection accounts")


@router.get("/accounts/grouped", response_model=List[CollectionAccountGroupResponse])
async def list_grouped_accounts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        grouped: Dict[tuple[str, str], Dict[str, object]] = {}

        for account in accounts:
            group_key = (account.platform, account.main_account_id or "")
            if group_key not in grouped:
                grouped[group_key] = {
                    "platform": account.platform,
                    "main_account_id": account.main_account_id or "",
                    "main_account_name": account.main_account_name,
                    "regions": defaultdict(list),
                }
            grouped[group_key]["regions"][account.shop_region or ""].append(account)

        result: List[CollectionAccountGroupResponse] = []
        for _, group in sorted(grouped.items(), key=lambda item: item[0]):
            regions = []
            for region_key, shops in sorted(group["regions"].items(), key=lambda item: item[0]):
                regions.append(
                    CollectionAccountGroupRegionResponse(
                        shop_region=region_key or None,
                        shops=sorted(shops, key=lambda item: item.id),
                    )
                )
            result.append(
                CollectionAccountGroupResponse(
                    platform=group["platform"],
                    main_account_id=group["main_account_id"],
                    main_account_name=group["main_account_name"],
                    regions=regions,
                )
            )
        return result
    except Exception:
        logger.exception("Failed to load grouped collection accounts")
        raise HTTPException(status_code=500, detail="failed to load grouped collection accounts")


@router.get("/config-coverage", response_model=CollectionConfigCoverageResponse)
async def get_config_coverage(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    main_account_id: Optional[str] = Query(None, description="Filter by main account"),
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(
            db,
            platform=platform,
            main_account_id=main_account_id,
        )
        coverage_by_shop = {
            account.id: {"daily": False, "weekly": False, "monthly": False}
            for account in accounts
        }
        active_shop_ids_by_platform: Dict[str, List[str]] = defaultdict(list)
        for account in accounts:
            active_shop_ids_by_platform[account.platform].append(account.id)

        stmt = select(CollectionConfig).where(CollectionConfig.is_active == True)
        if platform:
            stmt = stmt.where(CollectionConfig.platform == platform)
        if main_account_id:
            stmt = stmt.where(CollectionConfig.main_account_id == main_account_id)
        configs = (await db.execute(stmt.order_by(CollectionConfig.platform, CollectionConfig.id))).scalars().all()

        for config in configs:
            granularity = _resolve_config_granularity(config)
            if config.account_ids:
                target_shop_ids = [shop_id for shop_id in config.account_ids if shop_id in coverage_by_shop]
            else:
                target_shop_ids = active_shop_ids_by_platform.get(config.platform, [])
            for shop_id in target_shop_ids:
                coverage_by_shop[shop_id][granularity] = True

        items: List[CollectionConfigCoverageItem] = []
        for account in accounts:
            coverage = coverage_by_shop.get(account.id, {"daily": False, "weekly": False, "monthly": False})
            missing = [name for name, covered in coverage.items() if not covered]
            recommended_domains = get_recommended_config_domains(
                account.capabilities or {},
                shop_type=account.shop_type,
            )
            is_partially_covered = 0 < len(missing) < 3
            items.append(
                CollectionConfigCoverageItem(
                    shop_account_id=account.id,
                    shop_account_name=account.name,
                    platform=account.platform,
                    main_account_id=account.main_account_id or "",
                    main_account_name=account.main_account_name,
                    shop_region=account.shop_region,
                    shop_type=account.shop_type,
                    daily_covered=coverage["daily"],
                    weekly_covered=coverage["weekly"],
                    monthly_covered=coverage["monthly"],
                    missing_granularities=missing,
                    partial_covered=is_partially_covered,
                    fully_covered=len(missing) == 0,
                    is_partially_covered=is_partially_covered,
                    recommended_domains=recommended_domains,
                )
            )

        summary = CollectionConfigCoverageSummary(
            total_shop_count=len(items),
            fully_covered_count=sum(1 for item in items if item.fully_covered),
            partial_covered_count=sum(1 for item in items if item.partial_covered),
            daily_covered_count=sum(1 for item in items if item.daily_covered),
            weekly_covered_count=sum(1 for item in items if item.weekly_covered),
            monthly_covered_count=sum(1 for item in items if item.monthly_covered),
            daily_missing_count=sum(1 for item in items if not item.daily_covered),
            weekly_missing_count=sum(1 for item in items if not item.weekly_covered),
            monthly_missing_count=sum(1 for item in items if not item.monthly_covered),
        )

        return CollectionConfigCoverageResponse(summary=summary, items=items)
    except Exception:
        logger.exception("Failed to build collection config coverage")
        raise HTTPException(status_code=500, detail="failed to build collection config coverage")
