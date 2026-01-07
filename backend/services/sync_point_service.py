"""
增量采集同步点管理服务 (Phase 9.2)

负责管理每个账号+数据域的最后采集时间点
"""

from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select

from modules.core.db import CollectionSyncPoint
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SyncPointService:
    """同步点管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_sync_point(
        self,
        platform: str,
        account_id: str,
        data_domain: str
    ) -> Optional[CollectionSyncPoint]:
        """
        获取同步点
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            
        Returns:
            CollectionSyncPoint或None
        """
        stmt = select(CollectionSyncPoint).where(
            CollectionSyncPoint.platform == platform,
            CollectionSyncPoint.account_id == account_id,
            CollectionSyncPoint.data_domain == data_domain
        )
        
        result = self.db.execute(stmt).scalar_one_or_none()
        return result
    
    def get_or_create_sync_point(
        self,
        platform: str,
        account_id: str,
        data_domain: str,
        default_days_ago: int = 7
    ) -> tuple[CollectionSyncPoint, bool]:
        """
        获取或创建同步点
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            default_days_ago: 如果不存在，默认回溯天数
            
        Returns:
            (sync_point, is_new) 元组
        """
        sync_point = self.get_sync_point(platform, account_id, data_domain)
        
        if sync_point:
            logger.info(
                f"Sync point found: {platform}/{account_id}/{data_domain}, "
                f"last_sync={sync_point.last_sync_at}"
            )
            return sync_point, False
        
        # 创建新同步点
        default_time = datetime.utcnow() - timedelta(days=default_days_ago)
        sync_point = CollectionSyncPoint(
            platform=platform,
            account_id=account_id,
            data_domain=data_domain,
            last_sync_at=default_time,
            last_sync_value=default_time.isoformat(),
            sync_mode="incremental",
            total_synced_count=0,
            last_batch_count=0,
        )
        
        self.db.add(sync_point)
        self.db.commit()
        self.db.refresh(sync_point)
        
        logger.info(
            f"Sync point created: {platform}/{account_id}/{data_domain}, "
            f"default_time={default_time}"
        )
        
        return sync_point, True
    
    def update_sync_point(
        self,
        platform: str,
        account_id: str,
        data_domain: str,
        new_sync_at: datetime,
        new_sync_value: Optional[str] = None,
        batch_count: int = 0
    ) -> CollectionSyncPoint:
        """
        更新同步点
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            new_sync_at: 新的同步时间
            new_sync_value: 新的同步值（可选）
            batch_count: 本次同步记录数
            
        Returns:
            更新后的同步点
        """
        sync_point = self.get_sync_point(platform, account_id, data_domain)
        
        if not sync_point:
            # 如果不存在，创建
            sync_point, _ = self.get_or_create_sync_point(
                platform, account_id, data_domain
            )
        
        # 更新
        sync_point.last_sync_at = new_sync_at
        sync_point.last_sync_value = new_sync_value or new_sync_at.isoformat()
        sync_point.last_batch_count = batch_count
        sync_point.total_synced_count += batch_count
        sync_point.updated_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(sync_point)
        
        logger.info(
            f"Sync point updated: {platform}/{account_id}/{data_domain}, "
            f"new_sync_at={new_sync_at}, batch_count={batch_count}"
        )
        
        return sync_point
    
    def get_last_sync_time(
        self,
        platform: str,
        account_id: str,
        data_domain: str,
        default_days_ago: int = 7
    ) -> datetime:
        """
        获取最后同步时间（便捷方法）
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            default_days_ago: 默认回溯天数
            
        Returns:
            最后同步时间
        """
        sync_point, is_new = self.get_or_create_sync_point(
            platform, account_id, data_domain, default_days_ago
        )
        
        return sync_point.last_sync_at
    
    def reset_sync_point(
        self,
        platform: str,
        account_id: str,
        data_domain: str,
        days_ago: int = 30
    ) -> CollectionSyncPoint:
        """
        重置同步点（强制全量采集）
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            days_ago: 重置到多少天前
            
        Returns:
            重置后的同步点
        """
        reset_time = datetime.utcnow() - timedelta(days=days_ago)
        
        return self.update_sync_point(
            platform=platform,
            account_id=account_id,
            data_domain=data_domain,
            new_sync_at=reset_time,
            new_sync_value=reset_time.isoformat(),
            batch_count=0
        )
    
    def get_incremental_params(
        self,
        platform: str,
        account_id: str,
        data_domain: str,
        default_days_ago: int = 7
    ) -> Dict:
        """
        获取增量采集参数（供组件使用）
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            data_domain: 数据域
            default_days_ago: 默认回溯天数
            
        Returns:
            参数字典，可直接用于组件执行
        """
        last_sync_time = self.get_last_sync_time(
            platform, account_id, data_domain, default_days_ago
        )
        
        return {
            "last_sync_time": last_sync_time.strftime("%Y-%m-%d %H:%M:%S"),
            "last_sync_timestamp": int(last_sync_time.timestamp()),
            "last_sync_iso": last_sync_time.isoformat(),
            "incremental_mode": True,
        }

