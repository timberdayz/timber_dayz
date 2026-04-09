#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据治理统计服务

v4.5.0新增:
- 提供待入库文件统计
- 提供模板覆盖度分析
- 提供缺少模板的域+粒度清单
- 支持今日自动入库统计
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import CatalogFile
from modules.core.logger import get_logger

logger = get_logger(__name__)


class GovernanceStats:
    """数据治理统计服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(self, platform: str = None) -> Dict[str, Any]:
        """获取治理概览统计"""
        try:
            stmt = select(func.count(CatalogFile.id)).where(CatalogFile.status == "pending")
            if platform:
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower(),
                    )
                )

            pending_files_result = await self.db.execute(stmt)
            pending_files = pending_files_result.scalar() or 0

            from backend.services.template_matcher import get_template_matcher

            matcher = get_template_matcher(self.db)
            coverage_data = await matcher.get_template_coverage(platform)
            template_coverage = coverage_data["coverage_percentage"]

            today_start = datetime.now(timezone.utc).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            stmt = select(func.count(CatalogFile.id)).where(
                and_(
                    CatalogFile.status.in_(["ingested", "partial_success"]),
                    CatalogFile.last_processed_at >= today_start,
                )
            )
            if platform:
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower(),
                    )
                )

            today_auto_ingested_result = await self.db.execute(stmt)
            today_auto_ingested = today_auto_ingested_result.scalar() or 0
            missing_templates_count = len(coverage_data["missing_combinations"])

            result = {
                "pending_files": pending_files,
                "template_coverage": template_coverage,
                "today_auto_ingested": today_auto_ingested,
                "missing_templates_count": missing_templates_count,
            }

            logger.info(f"[GovernanceStats] 治理概览: {result}")
            return result
        except Exception as exc:
            logger.error(f"[GovernanceStats] 获取治理概览失败: {exc}", exc_info=True)
            return {
                "pending_files": 0,
                "template_coverage": 0,
                "today_auto_ingested": 0,
                "missing_templates_count": 0,
            }

    async def get_missing_templates(self, platform: str = None) -> List[Dict[str, Any]]:
        """获取缺少模板的域+粒度清单"""
        try:
            from backend.services.template_matcher import get_template_matcher

            matcher = get_template_matcher(self.db)
            coverage_data = await matcher.get_template_coverage(platform)
            missing_combinations = coverage_data["missing_combinations"]

            result: List[Dict[str, Any]] = []
            for combo in missing_combinations:
                domain = combo["domain"]
                granularity = combo["granularity"]

                stmt = select(func.count(CatalogFile.id)).where(
                    CatalogFile.data_domain == domain,
                    CatalogFile.granularity == granularity,
                    CatalogFile.status == "pending",
                )
                if platform:
                    stmt = stmt.where(
                        or_(
                            func.lower(CatalogFile.platform_code) == platform.lower(),
                            func.lower(CatalogFile.source_platform) == platform.lower(),
                        )
                    )

                file_count_result = await self.db.execute(stmt)
                file_count = file_count_result.scalar() or 0

                if file_count > 0:
                    result.append(
                        {
                            "domain": domain,
                            "granularity": granularity,
                            "file_count": file_count,
                        }
                    )

            result.sort(key=lambda item: item["file_count"], reverse=True)
            logger.info(f"[GovernanceStats] 缺少模板: {len(result)}个组合")
            return result
        except Exception as exc:
            logger.error(f"[GovernanceStats] 获取缺少模板清单失败: {exc}", exc_info=True)
            return []

    async def get_pending_files(
        self,
        platform: str = None,
        data_domain: str = None,
        granularity: str = None,
        since_hours: int = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取待入库文件列表"""
        try:
            stmt = select(CatalogFile).where(CatalogFile.status == "pending")

            if platform:
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower(),
                    )
                )
            if data_domain:
                stmt = stmt.where(CatalogFile.data_domain == data_domain)
            if granularity:
                stmt = stmt.where(CatalogFile.granularity == granularity)
            if since_hours:
                since_time = datetime.now(timezone.utc) - timedelta(hours=since_hours)
                stmt = stmt.where(CatalogFile.first_seen_at >= since_time)

            stmt = stmt.order_by(CatalogFile.first_seen_at.desc()).limit(limit)

            files_result = await self.db.execute(stmt)
            files = files_result.scalars().all()

            result = [
                {
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "platform": file_record.platform_code,
                    "domain": file_record.data_domain,
                    "granularity": file_record.granularity,
                    "shop_id": file_record.shop_id,
                    "collected_at": file_record.first_seen_at.isoformat()
                    if file_record.first_seen_at
                    else None,
                }
                for file_record in files
            ]

            logger.info(f"[GovernanceStats] 待入库文件: {len(result)}个")
            return result
        except Exception as exc:
            logger.error(f"[GovernanceStats] 获取待入库文件失败: {exc}", exc_info=True)
            return []

    async def get_auto_ingest_history(
        self,
        platform: str = None,
        days: int = 7,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """获取自动入库历史"""
        try:
            since_time = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = select(CatalogFile).where(
                and_(
                    CatalogFile.status.in_(["ingested", "partial_success"]),
                    CatalogFile.last_processed_at >= since_time,
                )
            )

            if platform:
                stmt = stmt.where(CatalogFile.platform_code == platform)

            stmt = stmt.order_by(CatalogFile.last_processed_at.desc()).limit(limit)

            files_result = await self.db.execute(stmt)
            files = files_result.scalars().all()

            result = [
                {
                    "file_id": file_record.id,
                    "file_name": file_record.file_name,
                    "platform": file_record.platform_code,
                    "domain": file_record.data_domain,
                    "status": file_record.status,
                    "attempts": 1,
                    "last_attempt": file_record.last_processed_at.isoformat()
                    if file_record.last_processed_at
                    else None,
                    "skip_reason": None,
                }
                for file_record in files
            ]

            logger.info(f"[GovernanceStats] 自动入库历史: {len(result)}条")
            return result
        except Exception as exc:
            logger.error(f"[GovernanceStats] 获取自动入库历史失败: {exc}", exc_info=True)
            return []


def get_governance_stats(db: AsyncSession) -> GovernanceStats:
    """获取治理统计服务实例"""
    return GovernanceStats(db)
