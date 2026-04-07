from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.services.collection_contracts import (
    build_date_range_from_time_selection,
    count_collection_targets,
    derive_granularity_from_time_selection,
    normalize_domain_subtypes,
    normalize_time_selection,
    resolve_shop_capabilities,
)
from backend.services.component_runtime_resolver import (
    ComponentRuntimeResolver,
    ComponentRuntimeResolverError,
)
from modules.core.db import CollectionConfig, CollectionTask, ShopAccount, ShopAccountCapability
from modules.core.logger import get_logger


logger = get_logger(__name__)


async def create_tasks_for_config(
    db: AsyncSession,
    *,
    config_id: int,
    trigger_type: str,
    app: Any = None,
    start_background: bool = False,
    resolve_runtime: bool = True,
) -> List[CollectionTask]:
    result = await db.execute(
        select(CollectionConfig)
        .options(selectinload(CollectionConfig.shop_scopes))
        .where(CollectionConfig.id == config_id, CollectionConfig.is_active == True)
    )
    config = result.scalar_one_or_none()
    if config is None:
        return []

    scope_rows = [scope for scope in list(config.shop_scopes or []) if getattr(scope, "enabled", True)]
    if not scope_rows:
        return []

    shop_ids = [scope.shop_account_id for scope in scope_rows]
    shop_result = await db.execute(
        select(ShopAccount).where(
            ShopAccount.shop_account_id.in_(shop_ids),
            ShopAccount.enabled == True,
        )
    )
    shops = {shop.shop_account_id: shop for shop in shop_result.scalars().all()}

    capability_rows = (
        await db.execute(
            select(ShopAccountCapability).where(
                ShopAccountCapability.shop_account_id.in_([shop.id for shop in shops.values()])
            )
        )
    ).scalars().all()
    capability_map: Dict[int, Dict[str, bool]] = {}
    for row in capability_rows:
        capability_map.setdefault(row.shop_account_id, {})[row.data_domain] = bool(row.enabled)

    time_selection = normalize_time_selection(
        date_range_type=config.date_range_type,
        custom_date_start=config.custom_date_start,
        custom_date_end=config.custom_date_end,
    )
    normalized_date_range = build_date_range_from_time_selection(time_selection)
    normalized_date_range["time_selection"] = time_selection
    effective_granularity = derive_granularity_from_time_selection(time_selection, config.granularity)

    created_tasks: List[CollectionTask] = []
    for scope in scope_rows:
        shop = shops.get(scope.shop_account_id)
        if shop is None:
            logger.warning("Config %s scope shop %s not found or disabled", config_id, scope.shop_account_id)
            continue

        existing_task = (
            await db.execute(
                select(CollectionTask).where(
                    CollectionTask.account == scope.shop_account_id,
                    CollectionTask.platform == config.platform,
                    CollectionTask.status.in_(["running", "queued", "paused"]),
                )
            )
        ).scalar_one_or_none()
        if existing_task is not None:
            logger.warning(
                "Skip config %s scope %s due to active task %s",
                config_id,
                scope.shop_account_id,
                existing_task.task_id,
            )
            continue

        capabilities = resolve_shop_capabilities(
            capability_map.get(shop.id),
            shop_type=shop.shop_type,
        )
        filtered_domains = [domain for domain in list(scope.data_domains or []) if capabilities.get(domain, False)]
        if not filtered_domains:
            logger.info("Skip config %s scope %s because no supported domains remain", config_id, scope.shop_account_id)
            continue

        normalized_sub_domains = normalize_domain_subtypes(
            data_domains=filtered_domains,
            sub_domains=scope.sub_domains,
        ) or None

        runtime_manifests: Optional[Dict[str, Any]] = None
        if resolve_runtime:
            try:
                runtime_manifests = await ComponentRuntimeResolver.from_async_session(db).resolve_task_manifests(
                    platform=config.platform,
                    data_domains=filtered_domains,
                    sub_domains=normalized_sub_domains,
                )
            except ComponentRuntimeResolverError as exc:
                logger.error(
                    "Config %s scope %s blocked by runtime preflight: %s",
                    config_id,
                    scope.shop_account_id,
                    exc,
                )
                continue

        task = CollectionTask(
            task_id=str(uuid.uuid4()),
            config_id=config_id,
            platform=config.platform,
            account=scope.shop_account_id,
            status="pending",
            progress=0,
            trigger_type=trigger_type,
            data_domains=filtered_domains,
            sub_domains=normalized_sub_domains,
            granularity=effective_granularity,
            date_range=normalized_date_range,
            total_domains=count_collection_targets(filtered_domains, normalized_sub_domains),
            completed_domains=[],
            failed_domains=[],
            current_domain=None,
            debug_mode=str(config.execution_mode or "headless").lower() == "headed",
            created_at=datetime.now(timezone.utc),
        )
        db.add(task)
        created_tasks.append(task)

        if start_background:
            from backend.routers.collection_tasks import _execute_collection_task_background

            asyncio.create_task(
                _execute_collection_task_background(
                    task_id=task.task_id,
                    platform=config.platform,
                    account_id=scope.shop_account_id,
                    data_domains=filtered_domains,
                    sub_domains=normalized_sub_domains,
                    date_range=normalized_date_range,
                    granularity=effective_granularity,
                    debug_mode=task.debug_mode,
                    parallel_mode=False,
                    max_parallel=3,
                    runtime_manifests=runtime_manifests,
                    app=app,
                )
            )

    await db.commit()
    for task in created_tasks:
        await db.refresh(task)
    return created_tasks
