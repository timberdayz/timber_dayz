"""
Collection config and collection account APIs.

Split from `collection.py` to keep endpoint groups focused.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies.auth import require_admin
from backend.models.database import get_async_db
from backend.schemas.collection import (
    CollectionAccountGroupRegionResponse,
    CollectionAccountGroupResponse,
    CollectionAccountResponse,
    CollectionConfigBatchRemediationCreatedItem,
    CollectionConfigBatchRemediationRequest,
    CollectionConfigBatchRemediationResponse,
    CollectionConfigBatchRemediationSkippedItem,
    CollectionConfigCoverageItem,
    CollectionConfigCoverageResponse,
    CollectionConfigCoverageSummary,
    CollectionConfigCreate,
    CollectionConfigResponse,
    CollectionConfigUpdate,
)
from backend.schemas.common import SuccessResponse
from backend.services.collection_contracts import (
    DEFAULT_GRANULARITY_DATE_RANGE_TYPE,
    TIME_PRESET_TO_GRANULARITY,
    build_legacy_collection_date_fields,
    build_default_sub_domains,
    derive_granularity_from_time_selection,
    get_default_shop_capabilities,
    get_recommended_config_domains,
    get_supported_config_data_domains,
    normalize_domain_subtypes,
    normalize_time_selection,
    resolve_shop_capabilities,
)
from modules.core.db import CollectionConfig, MainAccount, ShopAccount, ShopAccountCapability
from modules.core.logger import get_logger


logger = get_logger(__name__)

router = APIRouter(tags=["collection-config"], dependencies=[Depends(require_admin)])


def _build_collection_config_record(
    *,
    config_name: str,
    config: CollectionConfigCreate,
) -> CollectionConfig:
    now = datetime.now(timezone.utc)
    return CollectionConfig(
        name=config_name,
        platform=config.platform,
        account_ids=config.account_ids,
        data_domains=config.data_domains,
        sub_domains=normalize_domain_subtypes(
            data_domains=config.data_domains,
            sub_domains=config.sub_domains,
        )
        or None,
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


async def _load_collection_accounts(
    db: AsyncSession,
    *,
    platform: Optional[str] = None,
) -> List[CollectionAccountResponse]:
    try:
        stmt = select(ShopAccount).where(ShopAccount.enabled == True)
        if platform:
            stmt = stmt.where(ShopAccount.platform == platform)
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
        return [
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


@router.get("/configs", response_model=List[CollectionConfigResponse])
async def list_configs(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_async_db),
):
    stmt = select(CollectionConfig)

    if platform:
        stmt = stmt.where(CollectionConfig.platform == platform)

    if is_active is not None:
        stmt = stmt.where(CollectionConfig.is_active == is_active)

    stmt = stmt.order_by(desc(CollectionConfig.created_at))
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/configs", response_model=CollectionConfigResponse)
async def create_config(
    config: CollectionConfigCreate,
    db: AsyncSession = Depends(get_async_db),
):
    config_name = config.name
    if not config_name:
        domains_str = "-".join(sorted(config.data_domains))
        base_name = f"{config.platform}-{domains_str}"
        stmt = select(CollectionConfig).where(
            CollectionConfig.name.like(f"{base_name}-v%"),
            CollectionConfig.platform == config.platform,
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
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="config name already exists")

    valid_domains = get_supported_config_data_domains(config.platform)
    for domain in config.data_domains:
        if domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"invalid data domain: {domain}")

    if len(config.account_ids) == 0:
        logger.info("Collection config %s applies to all active shop accounts", config_name)

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
    await db.commit()
    await db.refresh(db_config)

    logger.info(
        "Created collection config %s (%s) with %s domains",
        db_config.name,
        db_config.platform,
        len(db_config.data_domains),
    )
    return db_config


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
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            config_name = f"{config_name}-{int(datetime.now(timezone.utc).timestamp())}"

        record = CollectionConfig(
            name=config_name,
            platform=account.platform,
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
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")
    return CollectionConfigResponse.model_validate(config)


@router.put("/configs/{config_id}", response_model=CollectionConfigResponse)
async def update_config(
    config_id: int,
    update_data: CollectionConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
):
    config = (
        await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    ).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=404, detail="config not found")

    update_dict = update_data.model_dump(exclude_unset=True)
    effective_domains = update_dict.get("data_domains") or config.data_domains or []
    valid_domains = get_supported_config_data_domains(config.platform)
    for domain in effective_domains:
        if domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"invalid data domain: {domain}")

    if "sub_domains" in update_dict:
        update_dict["sub_domains"] = normalize_domain_subtypes(
            data_domains=effective_domains,
            sub_domains=update_dict.get("sub_domains"),
        ) or None

    time_selection_input = update_dict.pop("time_selection", None)
    for key, value in update_dict.items():
        if value is not None:
            setattr(config, key, value)

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

    config.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(config)

    logger.info("Updated collection config: %s", config.name)
    return config


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
    await db.delete(config)
    await db.commit()
    logger.info("Deleted collection config: %s (id=%s)", name, config_id)
    return SuccessResponse(success=True, message="config deleted", data=None)


@router.get("/accounts", response_model=List[CollectionAccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="Filter by platform"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,
):
    if request and hasattr(request.app.state, "cache_service"):
        try:
            cache_service = request.app.state.cache_service
            cached_data = await cache_service.get("accounts_list", platform=platform or "")
            if cached_data is not None and isinstance(cached_data, list):
                logger.debug("[Cache] collection accounts hit: platform=%s", platform)
                return [CollectionAccountResponse(**item) for item in cached_data]
        except Exception as exc:
            logger.warning("[Cache] failed to read collection account cache: %s", exc)

    try:
        result = await _load_collection_accounts(db, platform=platform)
        logger.info("Returned collection account list: %s records", len(result))

        if request and hasattr(request.app.state, "cache_service"):
            try:
                cache_service = request.app.state.cache_service
                await cache_service.set(
                    "accounts_list",
                    [item.model_dump() for item in result],
                    ttl=300,
                    platform=platform or "",
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
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(db, platform=platform)
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
    db: AsyncSession = Depends(get_async_db),
):
    try:
        accounts = await _load_collection_accounts(db, platform=platform)
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
