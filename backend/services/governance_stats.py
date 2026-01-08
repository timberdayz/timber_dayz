#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据治理统计服务

v4.5.0新增：
- 提供待入库文件统计
- 提供模板覆盖度分析
- 提供缺少模板的域×粒度清单
- 支持今日自动入库统计
"""

from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_
from datetime import datetime, timedelta

from modules.core.db import CatalogFile, FieldMappingTemplate
from modules.core.logger import get_logger

logger = get_logger(__name__)


class GovernanceStats:
    """数据治理统计服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_overview(self, platform: str = None) -> Dict[str, Any]:
        """
        获取治理概览统计
        
        Args:
            platform: 平台代码（可选）
        
        Returns:
            {
                pending_files: 待入库文件数,
                template_coverage: 模板覆盖度（%）,
                today_auto_ingested: 今日自动入库数,
                missing_templates_count: 缺少模板的域×粒度数
            }
        """
        try:
            # 1. 待入库文件数
            stmt = select(func.count(CatalogFile.id)).where(
                CatalogFile.status == 'pending'
            )
            if platform:
                # [*] v4.10.0修复：同时使用platform_code和source_platform筛选
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower()
                    )
                )
            
            pending_files = self.db.execute(stmt).scalar() or 0
            
            # 2. 模板覆盖度（使用template_matcher计算）
            from backend.services.template_matcher import get_template_matcher
            matcher = get_template_matcher(self.db)
            coverage_data = matcher.get_template_coverage(platform)
            template_coverage = coverage_data['coverage_percentage']
            
            # 3. 今日自动入库数（v4.5.1简化：使用last_processed_at）
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            stmt = select(func.count(CatalogFile.id)).where(
                and_(
                    CatalogFile.status.in_(['ingested', 'partial_success']),
                    CatalogFile.last_processed_at >= today_start  # CatalogFile没有updated_at，使用last_processed_at
                )
            )
            if platform:
                # [*] v4.10.0修复：同时使用platform_code和source_platform筛选
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower()
                    )
                )
            
            today_auto_ingested = self.db.execute(stmt).scalar() or 0
            
            # 4. 缺少模板的域×粒度数
            missing_templates_count = len(coverage_data['missing_combinations'])
            
            result = {
                'pending_files': pending_files,
                'template_coverage': template_coverage,
                'today_auto_ingested': today_auto_ingested,
                'missing_templates_count': missing_templates_count
            }
            
            logger.info(f"[GovernanceStats] 治理概览: {result}")
            return result
            
        except Exception as e:
            logger.error(f"[GovernanceStats] 获取治理概览失败: {e}", exc_info=True)
            return {
                'pending_files': 0,
                'template_coverage': 0,
                'today_auto_ingested': 0,
                'missing_templates_count': 0
            }
    
    def get_missing_templates(self, platform: str = None) -> List[Dict]:
        """
        获取缺少模板的域×粒度清单
        
        Args:
            platform: 平台代码（可选）
        
        Returns:
            [{domain, granularity, file_count}]
        """
        try:
            from backend.services.template_matcher import get_template_matcher
            matcher = get_template_matcher(self.db)
            coverage_data = matcher.get_template_coverage(platform)
            
            missing_combinations = coverage_data['missing_combinations']
            
            # 统计每个组合的文件数
            result = []
            for combo in missing_combinations:
                domain = combo['domain']
                granularity = combo['granularity']
                
                # 统计文件数
                stmt = select(func.count(CatalogFile.id)).where(
                    CatalogFile.data_domain == domain,
                    CatalogFile.granularity == granularity,
                    CatalogFile.status == 'pending'
                )
                if platform:
                    # [*] v4.10.0修复：同时使用platform_code和source_platform筛选
                    stmt = stmt.where(
                        or_(
                            func.lower(CatalogFile.platform_code) == platform.lower(),
                            func.lower(CatalogFile.source_platform) == platform.lower()
                        )
                    )
                
                file_count = self.db.execute(stmt).scalar() or 0
                
                if file_count > 0:  # 只返回有文件的组合
                    result.append({
                        'domain': domain,
                        'granularity': granularity,
                        'file_count': file_count
                    })
            
            # 按文件数倒序
            result.sort(key=lambda x: x['file_count'], reverse=True)
            
            logger.info(f"[GovernanceStats] 缺少模板: {len(result)}个组合")
            return result
            
        except Exception as e:
            logger.error(f"[GovernanceStats] 获取缺少模板清单失败: {e}", exc_info=True)
            return []
    
    def get_pending_files(
        self, 
        platform: str = None,
        data_domain: str = None,
        granularity: str = None,
        since_hours: int = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        获取待入库文件列表
        
        Args:
            platform: 平台代码
            data_domain: 数据域
            granularity: 粒度
            since_hours: 最近N小时（可选）
            limit: 返回数量限制
        
        Returns:
            [{file_id, file_name, platform, domain, granularity, shop_id, collected_at}]
        """
        try:
            stmt = select(CatalogFile).where(
                CatalogFile.status == 'pending'
            )
            
            # 筛选条件
            if platform:
                # [*] v4.10.0修复：同时使用platform_code和source_platform筛选
                stmt = stmt.where(
                    or_(
                        func.lower(CatalogFile.platform_code) == platform.lower(),
                        func.lower(CatalogFile.source_platform) == platform.lower()
                    )
                )
            if data_domain:
                stmt = stmt.where(CatalogFile.data_domain == data_domain)
            if granularity:
                stmt = stmt.where(CatalogFile.granularity == granularity)
            if since_hours:
                since_time = datetime.now() - timedelta(hours=since_hours)
                stmt = stmt.where(CatalogFile.first_seen_at >= since_time)
            
            # 按创建时间倒序
            stmt = stmt.order_by(CatalogFile.first_seen_at.desc())
            stmt = stmt.limit(limit)
            
            files = self.db.execute(stmt).scalars().all()
            
            # 转换为字典
            result = [
                {
                    'file_id': f.id,
                    'file_name': f.file_name,
                    'platform': f.platform_code,
                    'domain': f.data_domain,
                    'granularity': f.granularity,
                    'shop_id': f.shop_id,
                    'collected_at': f.first_seen_at.isoformat() if f.first_seen_at else None
                }
                for f in files
            ]
            
            logger.info(f"[GovernanceStats] 待入库文件: {len(result)}个")
            return result
            
        except Exception as e:
            logger.error(f"[GovernanceStats] 获取待入库文件失败: {e}", exc_info=True)
            return []
    
    def get_auto_ingest_history(
        self,
        platform: str = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict]:
        """
        获取自动入库历史
        
        Args:
            platform: 平台代码
            days: 最近N天
            limit: 返回数量限制
        
        Returns:
            [{file_id, file_name, status, attempts, last_attempt, skip_reason}]
        """
        try:
            since_time = datetime.now() - timedelta(days=days)
            
            # v4.5.1简化：使用last_processed_at替代auto_ingest字段
            stmt = select(CatalogFile).where(
                and_(
                    CatalogFile.status.in_(['ingested', 'partial_success']),
                    CatalogFile.last_processed_at >= since_time
                )
            )
            
            if platform:
                stmt = stmt.where(CatalogFile.platform_code == platform)
            
            stmt = stmt.order_by(CatalogFile.last_processed_at.desc())
            stmt = stmt.limit(limit)
            
            files = self.db.execute(stmt).scalars().all()
            
            result = [
                {
                    'file_id': f.id,
                    'file_name': f.file_name,
                    'platform': f.platform_code,
                    'domain': f.data_domain,
                    'status': f.status,
                    'attempts': 1,  # 简化
                    'last_attempt': f.last_processed_at.isoformat() if f.last_processed_at else None,
                    'skip_reason': None  # 简化
                }
                for f in files
            ]
            
            logger.info(f"[GovernanceStats] 自动入库历史: {len(result)}条")
            return result
            
        except Exception as e:
            logger.error(f"[GovernanceStats] 获取自动入库历史失败: {e}", exc_info=True)
            return []


def get_governance_stats(db: Session) -> GovernanceStats:
    """获取治理统计服务实例"""
    return GovernanceStats(db)

