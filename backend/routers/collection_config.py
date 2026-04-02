"""
数据采集模块 - 配置管理与账号 API

拆分自 collection.py，包含采集配置 CRUD 和账号列表端点。
"""

from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import desc, select

from backend.models.database import get_async_db
from modules.core.db import CollectionConfig, ShopAccount, ShopAccountCapability
from modules.core.logger import get_logger
from backend.schemas.collection import (
    CollectionConfigCreate,
    CollectionConfigUpdate,
    CollectionConfigResponse,
    CollectionAccountResponse,
)
from backend.schemas.common import SuccessResponse
from backend.services.collection_contracts import (
    build_legacy_collection_date_fields,
    derive_granularity_from_time_selection,
    get_supported_config_data_domains,
    normalize_domain_subtypes,
    normalize_time_selection,
)

logger = get_logger(__name__)

router = APIRouter(tags=["数据采集-配置"])


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
        ) or None,
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


@router.get("/configs", response_model=List[CollectionConfigResponse])
async def list_configs(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    is_active: Optional[bool] = Query(None, description="按状态筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取采集配置列表"""
    stmt = select(CollectionConfig)

    if platform:
        stmt = stmt.where(CollectionConfig.platform == platform)

    if is_active is not None:
        stmt = stmt.where(CollectionConfig.is_active == is_active)

    stmt = stmt.order_by(desc(CollectionConfig.created_at))
    result = await db.execute(stmt)
    configs = result.scalars().all()
    return configs


@router.post("/configs", response_model=CollectionConfigResponse)
async def create_config(
    config: CollectionConfigCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """创建采集配置(v4.7.0 - 支持自动生成配置名)"""
    config_name = config.name
    if not config_name:
        domains_str = "-".join(sorted(config.data_domains))
        base_name = f"{config.platform}-{domains_str}"

        stmt = select(CollectionConfig).where(
            CollectionConfig.name.like(f"{base_name}-v%"),
            CollectionConfig.platform == config.platform
        )
        result = await db.execute(stmt)
        existing_configs = result.scalars().all()

        existing_versions = []
        for cfg in existing_configs:
            if cfg.name.startswith(base_name + "-v"):
                try:
                    version_str = cfg.name[len(base_name)+2:]
                    existing_versions.append(int(version_str))
                except ValueError:
                    pass

        next_version = max(existing_versions, default=0) + 1
        config_name = f"{base_name}-v{next_version}"

        logger.info(f"Auto-generated config name: {config_name}")
    else:
        stmt = select(CollectionConfig).where(
            CollectionConfig.name == config_name,
            CollectionConfig.platform == config.platform
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            raise HTTPException(status_code=400, detail="配置名称已存在")

    valid_domains = get_supported_config_data_domains(config.platform)
    for domain in config.data_domains:
        if domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"无效的数据域: {domain}")

    if len(config.account_ids) == 0:
        logger.info(f"Config uses all active accounts for platform: {config.platform}")

    db_config = _build_collection_config_record(
        config_name=config_name,
        config=config,
    )

    time_selection = normalize_time_selection(
        time_selection=config.time_selection.model_dump(exclude_none=True) if config.time_selection else None,
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

    logger.info(f"Created collection config: {db_config.name} ({db_config.platform}) with {len(db_config.data_domains)} domains")
    return db_config


@router.get("/configs/{config_id}", response_model=CollectionConfigResponse)
async def get_config(
    config_id: int = Path(..., description="配置ID"),
    db: AsyncSession = Depends(get_async_db),
):
    """获取采集配置详情"""
    try:
        result = await db.execute(
            select(CollectionConfig).where(CollectionConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")

        return CollectionConfigResponse.model_validate(config)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("获取采集配置详情失败: config_id=%s", config_id)
        raise HTTPException(status_code=500, detail="获取配置详情失败")


@router.put("/configs/{config_id}", response_model=CollectionConfigResponse)
async def update_config(
    config_id: int,
    update_data: CollectionConfigUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """更新采集配置"""
    result = await db.execute(select(CollectionConfig).where(CollectionConfig.id == config_id))
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")

    update_dict = update_data.model_dump(exclude_unset=True)
    effective_platform = config.platform
    effective_domains = update_dict.get("data_domains") or config.data_domains or []
    valid_domains = get_supported_config_data_domains(effective_platform)
    for domain in effective_domains:
        if domain not in valid_domains:
            raise HTTPException(status_code=400, detail=f"无效的数据域: {domain}")
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
        date_range_type=None if time_selection_input is not None else (update_dict.get("date_range_type") or config.date_range_type),
        custom_date_start=None if time_selection_input is not None else (update_dict.get("custom_date_start") or config.custom_date_start),
        custom_date_end=None if time_selection_input is not None else (update_dict.get("custom_date_end") or config.custom_date_end),
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

    logger.info(f"Updated collection config: {config.name}")
    return config


@router.delete("/configs/{config_id}", response_model=SuccessResponse[None])
async def delete_config(
    config_id: int,
    db: AsyncSession = Depends(get_async_db),
):
    """删除采集配置"""
    try:
        result = await db.execute(
            select(CollectionConfig).where(CollectionConfig.id == config_id)
        )
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail="配置不存在")

        name = config.name
        await db.delete(config)
        await db.commit()

        logger.info("Deleted collection config: %s (id=%s)", name, config_id)
        return SuccessResponse(success=True, message="配置已删除", data=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("删除采集配置失败: config_id=%s", config_id)
        raise HTTPException(status_code=500, detail="删除配置失败")


# ============================================================
# 账号 API
# ============================================================

@router.get("/accounts", response_model=List[CollectionAccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="按平台筛选"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None
):
    """
    获取账号列表(脱敏)

    v4.7.0: 从数据库读取账号信息,返回脱敏后的数据
    [*] Phase 3: 添加缓存支持(5分钟TTL)
    """
    if request and hasattr(request.app.state, "cache_service"):
        try:
            cache_service = request.app.state.cache_service
            cached_data = await cache_service.get("accounts_list", platform=platform or "")
            if cached_data is not None and isinstance(cached_data, list):
                logger.debug(f"[Cache] 账号列表缓存命中: platform={platform}")
                return [CollectionAccountResponse(**item) for item in cached_data]
        except Exception as e:
            logger.warning(f"[Cache] 读取账号列表缓存失败，回退到数据库: {e}")

    try:
        result = []
        try:
            stmt = select(ShopAccount).where(ShopAccount.enabled == True)
            if platform:
                stmt = stmt.where(ShopAccount.platform == platform)
            stmt = stmt.order_by(ShopAccount.platform, ShopAccount.shop_account_id)
            accounts = (await db.execute(stmt)).scalars().all()

            for account in accounts:
                capability_rows = (
                    await db.execute(
                        select(ShopAccountCapability).where(
                            ShopAccountCapability.shop_account_id == account.id
                        )
                    )
                ).scalars().all()
                capabilities = {
                    row.data_domain: bool(row.enabled)
                    for row in capability_rows
                }
                result.append(
                    CollectionAccountResponse(
                        id=account.shop_account_id,
                        name=account.store_name or account.shop_account_id,
                        platform=account.platform,
                        shop_id=account.shop_region,
                        status="active" if account.enabled else "inactive",
                        shop_type=account.shop_type,
                        capabilities=capabilities,
                    )
                )
        except Exception:
            from backend.services.account_loader_service import get_account_loader_service

            account_loader = get_account_loader_service()
            accounts = await account_loader.load_all_accounts_async(db, platform=platform)
            for account in accounts:
                result.append(
                    CollectionAccountResponse(
                        id=account.get("account_id", "unknown"),
                        name=account.get("store_name", account.get("account_id", "unknown")),
                        platform=account.get("platform", "unknown"),
                        shop_id=account.get("shop_region"),
                        status="active" if account.get("enabled", False) else "inactive",
                        shop_type=account.get("shop_type"),
                        capabilities=account.get("capabilities") or {},
                    )
                )

        logger.info(f"返回账号列表: {len(result)} 条记录")

        if request and hasattr(request.app.state, "cache_service"):
            try:
                cache_service = request.app.state.cache_service
                to_cache = [r.model_dump() for r in result]
                await cache_service.set(
                    "accounts_list", to_cache, ttl=300, platform=platform or ""
                )
            except Exception as e:
                logger.warning(f"[Cache] 写入账号列表缓存失败: {e}")

        return result

    except Exception as e:
        logger.exception("加载账号列表失败")
        raise HTTPException(status_code=500, detail="加载账号列表失败")
