"""
组件版本管理服务 (Phase 9.4)

负责：
1. 组件版本注册和管理
2. A/B测试流量分配
3. 自动统计成功率
4. 智能切换稳定版本
"""

import random
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from modules.core.db import ComponentVersion
from modules.core.logger import get_logger

logger = get_logger(__name__)


class ComponentVersionService:
    """组件版本管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def register_version(
        self,
        component_name: str,
        version: str,
        file_path: str,
        description: str = None,
        is_stable: bool = False,
        created_by: str = None
    ) -> ComponentVersion:
        """
        注册新版本组件
        
        Args:
            component_name: 组件名称（如shopee/login）
            version: 版本号（如1.0.0）
            file_path: 文件路径（如shopee/components/login.py 或旧版 shopee/login_v1.0.yaml）
            description: 版本说明
            is_stable: 是否标记为稳定版本
            created_by: 创建人
            
        Returns:
            ComponentVersion对象
            
        Note:
            v4.8.0起，file_path 应使用 Python 组件路径（.py），
            旧版 YAML 组件路径（.yaml）已废弃。
        """
        # 检查是否已存在
        existing = self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.version == version
                )
            )
        ).scalar_one_or_none()
        
        if existing:
            logger.warning(f"Version {component_name} v{version} already exists")
            return existing
        
        # 创建新版本
        version_obj = ComponentVersion(
            component_name=component_name,
            version=version,
            file_path=file_path,
            description=description,
            is_stable=is_stable,
            is_active=True,
            is_testing=False,
            created_by=created_by,
        )
        
        self.db.add(version_obj)
        self.db.commit()
        self.db.refresh(version_obj)
        
        logger.info(f"Registered version: {component_name} v{version}")
        
        return version_obj
    
    def get_stable_version(self, component_name: str) -> Optional[ComponentVersion]:
        """
        获取稳定版本
        
        Args:
            component_name: 组件名称
            
        Returns:
            稳定版本，如果没有则返回None
        """
        return self.db.execute(
            select(ComponentVersion)
            .where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_stable == True,
                    ComponentVersion.is_active == True
                )
            )
            .order_by(ComponentVersion.success_rate.desc())
        ).scalar_one_or_none()
    
    def get_test_version(self, component_name: str) -> Optional[ComponentVersion]:
        """
        获取测试版本
        
        Args:
            component_name: 组件名称
            
        Returns:
            测试版本，如果没有则返回None
        """
        now = datetime.utcnow()
        
        return self.db.execute(
            select(ComponentVersion)
            .where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_testing == True,
                    ComponentVersion.is_active == True,
                    or_(
                        ComponentVersion.test_start_at == None,
                        ComponentVersion.test_start_at <= now
                    ),
                    or_(
                        ComponentVersion.test_end_at == None,
                        ComponentVersion.test_end_at >= now
                    )
                )
            )
        ).scalar_one_or_none()
    
    def select_version_for_use(
        self,
        component_name: str,
        force_version: str = None,
        enable_ab_test: bool = True
    ) -> Optional[ComponentVersion]:
        """
        选择要使用的版本（A/B测试逻辑）
        
        Args:
            component_name: 组件名称
            force_version: 强制使用指定版本
            enable_ab_test: 是否启用A/B测试
            
        Returns:
            选中的版本，如果没有则返回None
        """
        # 强制版本
        if force_version:
            return self.db.execute(
                select(ComponentVersion)
                .where(
                    and_(
                        ComponentVersion.component_name == component_name,
                        ComponentVersion.version == force_version,
                        ComponentVersion.is_active == True
                    )
                )
            ).scalar_one_or_none()
        
        # A/B测试逻辑
        if enable_ab_test:
            test_version = self.get_test_version(component_name)
            
            if test_version and test_version.test_ratio > 0:
                # 按流量比例随机选择
                if random.random() < test_version.test_ratio:
                    logger.info(
                        f"A/B Test: Using test version {component_name} v{test_version.version} "
                        f"(ratio={test_version.test_ratio:.2%})"
                    )
                    return test_version
        
        # 默认使用稳定版本
        stable_version = self.get_stable_version(component_name)
        
        if stable_version:
            return stable_version
        
        # 如果没有稳定版本，使用最新的活跃版本
        return self.db.execute(
            select(ComponentVersion)
            .where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_active == True
                )
            )
            .order_by(ComponentVersion.created_at.desc())
        ).scalar_one_or_none()
    
    def record_usage(
        self,
        component_name: str,
        version: str,
        success: bool
    ) -> None:
        """
        记录组件使用情况
        
        Args:
            component_name: 组件名称
            version: 版本号
            success: 是否成功
        """
        version_obj = self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.version == version
                )
            )
        ).scalar_one_or_none()
        
        if not version_obj:
            logger.warning(f"Version not found: {component_name} v{version}")
            return
        
        # 更新统计
        version_obj.usage_count += 1
        if success:
            version_obj.success_count += 1
        else:
            version_obj.failure_count += 1
        
        # 重新计算成功率
        if version_obj.usage_count > 0:
            version_obj.success_rate = version_obj.success_count / version_obj.usage_count
        
        self.db.commit()
        
        logger.info(
            f"Recorded usage: {component_name} v{version}, "
            f"success={success}, rate={version_obj.success_rate:.2%}"
        )
    
    def start_ab_test(
        self,
        component_name: str,
        test_version: str,
        test_ratio: float = 0.1,
        duration_days: int = 7
    ) -> ComponentVersion:
        """
        启动A/B测试
        
        Args:
            component_name: 组件名称
            test_version: 测试版本号
            test_ratio: 测试流量比例（0.0-1.0）
            duration_days: 测试持续天数
            
        Returns:
            测试版本对象
        """
        from datetime import timedelta
        
        # 获取版本
        version_obj = self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.version == test_version
                )
            )
        ).scalar_one_or_none()
        
        if not version_obj:
            raise ValueError(f"Version not found: {component_name} v{test_version}")
        
        # 停止其他测试
        self.db.execute(
            select(ComponentVersion)
            .where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_testing == True
                )
            )
        )
        for other_test in self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_testing == True
                )
            )
        ).scalars():
            other_test.is_testing = False
        
        # 启动测试
        now = datetime.utcnow()
        version_obj.is_testing = True
        version_obj.test_ratio = test_ratio
        version_obj.test_start_at = now
        version_obj.test_end_at = now + timedelta(days=duration_days)
        
        self.db.commit()
        self.db.refresh(version_obj)
        
        logger.info(
            f"Started A/B test: {component_name} v{test_version}, "
            f"ratio={test_ratio:.2%}, duration={duration_days}days"
        )
        
        return version_obj
    
    def promote_to_stable(self, component_name: str, version: str) -> ComponentVersion:
        """
        提升版本为稳定版本（v4.8.0 增强：确保稳定版本唯一性）
        
        Args:
            component_name: 组件名称
            version: 版本号
            
        Returns:
            提升后的版本对象
            
        Note:
            v4.8.0 增强：
            1. 取消该组件所有其他稳定版本的 is_stable 标志
            2. 特别处理相同 file_path 的版本，确保唯一性
        """
        # 获取版本
        version_obj = self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.version == version
                )
            )
        ).scalar_one_or_none()
        
        if not version_obj:
            raise ValueError(f"Version not found: {component_name} v{version}")
        
        # v4.8.0: 取消该组件所有其他稳定版本
        cancelled_count = 0
        for other_stable in self.db.execute(
            select(ComponentVersion).where(
                and_(
                    ComponentVersion.component_name == component_name,
                    ComponentVersion.is_stable == True,
                    ComponentVersion.id != version_obj.id
                )
            )
        ).scalars():
            other_stable.is_stable = False
            cancelled_count += 1
            logger.info(f"Cancelled stable status: {other_stable.component_name} v{other_stable.version}")
        
        # v4.8.0: 如果有相同 file_path 的其他稳定版本，也取消它们
        if version_obj.file_path:
            for same_path_stable in self.db.execute(
                select(ComponentVersion).where(
                    and_(
                        ComponentVersion.file_path == version_obj.file_path,
                        ComponentVersion.is_stable == True,
                        ComponentVersion.id != version_obj.id
                    )
                )
            ).scalars():
                if same_path_stable.is_stable:  # 双重检查
                    same_path_stable.is_stable = False
                    cancelled_count += 1
                    logger.info(
                        f"Cancelled stable status (same file_path): "
                        f"{same_path_stable.component_name} v{same_path_stable.version}"
                    )
        
        # 提升为稳定版本
        version_obj.is_stable = True
        version_obj.is_testing = False
        
        self.db.commit()
        self.db.refresh(version_obj)
        
        logger.info(
            f"Promoted to stable: {component_name} v{version} "
            f"(cancelled {cancelled_count} other stable versions)"
        )
        
        return version_obj
    
    def get_version_statistics(self, component_name: str) -> List[Dict[str, Any]]:
        """
        获取组件所有版本的统计信息
        
        Args:
            component_name: 组件名称
            
        Returns:
            版本统计列表
        """
        versions = self.db.execute(
            select(ComponentVersion)
            .where(ComponentVersion.component_name == component_name)
            .order_by(ComponentVersion.created_at.desc())
        ).scalars().all()
        
        return [
            {
                'version': v.version,
                'is_stable': v.is_stable,
                'is_testing': v.is_testing,
                'usage_count': v.usage_count,
                'success_count': v.success_count,
                'failure_count': v.failure_count,
                'success_rate': v.success_rate,
                'created_at': v.created_at.isoformat(),
            }
            for v in versions
        ]

